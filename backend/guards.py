"""Business safeguards enforced in code, not just in prompts.

FactLedger records every database row that MCP tools returned during one
ticket run. Agent outputs are checked against it before they are passed on:
an agent cannot cite a record it never saw, propose paying an amount that
differs from the database, or skip the approval, vendor-eligibility and cash
checks below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .models import (
    APPROVAL_REQUIRED_ACTIONS, PAYMENT_ACTIONS, ActionStatus, ActionType, ApprovalRequirement,
    BossDecision, DbTable, ProposedAction, SpecialistReport,
)

AMOUNT_TOLERANCE = 0.005


@dataclass
class FactLedger:
    refs: set[tuple[str, str]] = field(default_factory=set)
    invoice_amount: dict[str, float] = field(default_factory=dict)
    invoice_status: dict[str, str] = field(default_factory=dict)
    lease_rent: dict[str, float] = field(default_factory=dict)
    vendor_eligible: dict[str, bool | None] = field(default_factory=dict)
    vendor_reason: dict[str, str] = field(default_factory=dict)
    cash_balance: dict[str, float] = field(default_factory=dict)
    pricing: dict[str, tuple[float, float]] = field(default_factory=dict)  # sku -> (unit_cost, list_price)

    def _add(self, table: DbTable, record_id: Any) -> str:
        self.refs.add((table.value, str(record_id)))
        return f"{table.value}:{record_id}"

    def ingest(self, tool_name: str, data: Any) -> list[str]:
        """Record the rows in one MCP result; returns their ids for the audit trail."""
        if not isinstance(data, dict) or data.get("found") is False:
            return []
        db = data.get("database", data)
        ids: list[str] = []
        if data.get("shop_date"):
            ids.append(self._add(DbTable.DESK, "date_today"))

        if tool_name == "get_stock_and_pricing":
            sku = data["sku"]
            for row in db.get("stock_by_size", []):
                ids.append(self._add(DbTable.INVENTORY, f"{sku}:{row['size']}"))
            if db.get("pricing"):
                self.pricing[sku] = (db["pricing"]["unit_cost"], db["pricing"]["list_price"])
                ids.append(self._add(DbTable.PRICING, sku))

        elif tool_name == "check_vendor_eligibility":
            for v in data.get("vendors", []):
                vid = str(v["vendor_id"])
                ids.append(self._add(DbTable.VENDORS, vid))
                self.vendor_eligible[vid] = v["eligible_to_ship"]
                self.vendor_reason[vid] = v["eligibility_reason"]
                for inv in v.get("invoices", []):
                    ids.append(self._invoice(inv))
                    for p in inv.get("payments_recorded", []):
                        ids.append(self._add(DbTable.PAYMENTS, p["id"]))

        elif tool_name in ("get_rent_due_and_cash_position", "get_cash_and_obligations"):
            if db.get("lease"):
                ids.append(self._lease(db["lease"]["id"], db["lease"]["monthly_rent"]))
            for lease in db.get("next_rent_by_lease", []):
                ids.append(self._lease(lease["lease_id"], lease["monthly_rent"]))
            if db.get("cash_account"):
                cash = db["cash_account"]
                self.cash_balance[cash["name"]] = cash["balance"]
                ids.append(self._add(DbTable.CASH_ACCOUNTS, cash["name"]))
            for inv in db.get("open_invoices", []):
                ids.append(self._invoice(inv))
                if inv.get("vendor_id") is not None:
                    ids.append(self._add(DbTable.VENDORS, inv["vendor_id"]))
            for p in db.get("rent_payments_recorded", []) + db.get("recent_payments", []):
                ids.append(self._add(DbTable.PAYMENTS, p["id"]))

        elif tool_name == "get_ticket_details":
            ids.append(self._add(DbTable.TICKETS, db["ticket"]["ticket_id"]))
            links = db.get("linked_records", {})
            product = links.get("product")
            if product and product.get("inventory_row_exists"):
                ids.append(self._add(DbTable.INVENTORY, f"{product['sku']}:{product['size']}"))
            if links.get("lease", {}).get("exists", True) and "lease" in links:
                ids.append(self._add(DbTable.LEASES, links["lease"]["id"]))
            invoice = links.get("invoice")
            if invoice and invoice.get("exists", True):
                ids.append(self._add(DbTable.INVOICES, invoice["id"]))
                self.invoice_status[str(invoice["id"])] = invoice["status"]
                if invoice.get("vendor_id") is not None:
                    ids.append(self._add(DbTable.VENDORS, invoice["vendor_id"]))

        elif tool_name == "list_open_tickets":
            for t in data.get("tickets", []):
                ids.append(self._add(DbTable.TICKETS, t["ticket_id"]))

        return sorted(set(ids))

    def _invoice(self, inv: dict) -> str:
        iid = str(inv["invoice_id"])
        self.invoice_amount[iid] = inv["amount"]
        self.invoice_status[iid] = inv["status"]
        return self._add(DbTable.INVOICES, iid)

    def _lease(self, lease_id: Any, rent: float) -> str:
        self.lease_rent[str(lease_id)] = rent
        return self._add(DbTable.LEASES, lease_id)

    def has(self, table: DbTable, record_id: str) -> bool:
        return (table.value, record_id) in self.refs


# --- Checks on agent output (failures go back to the model as a retry) ----------

# A customer draft may not quote a discount (none is approved during a run) or
# reveal the shop's internal finances.
_DISCOUNT_FIGURE = re.compile(r"\d+(\.\d+)?\s*%|\$\s*\d")
_INTERNAL_TERMS = re.compile(
    r"\b(invoices?|unpaid|overdue|cash|bank balance|margins?|unit cost|rent|vendor'?s? (bill|debt))\b",
    re.IGNORECASE)


def draft_problems(output: object) -> list[str]:
    draft = getattr(output, "draft", None)
    if draft is None:
        return []
    text = f"{draft.subject}\n{draft.body}"
    problems = []
    if "discount" in text.lower() and _DISCOUNT_FIGURE.search(text):
        problems.append("The draft quotes a discount figure. No discount has been approved by "
                        "a human; say the request is under review without numbers.")
    found = sorted({m.group(0).lower() for m in _INTERNAL_TERMS.finditer(text)})
    if found:
        problems.append(f"The draft mentions internal matters ({', '.join(found)}); remove them.")
    return problems


def output_problems(output: SpecialistReport | BossDecision, ledger: FactLedger) -> list[str]:
    """Reasons the output must be rejected; empty when it may be passed on."""
    problems: list[str] = draft_problems(output)
    if isinstance(output, BossDecision):
        evidence = list(output.evidence)
        actions = output.actions
    else:
        evidence = [e for f in output.findings for e in f.evidence]
        actions = output.recommended_actions

    for e in evidence:
        if not ledger.has(e.record.table, e.record.id):
            problems.append(f"Evidence cites {e.record.table.value}:{e.record.id}, which no MCP "
                            "tool returned in this run. Cite only records you retrieved.")
    for a in actions:
        if a.target and not ledger.has(a.target.table, a.target.id):
            problems.append(f"Action '{a.action_type.value}' targets {a.target.table.value}:"
                            f"{a.target.id}, which no MCP tool returned in this run.")
            continue
        if a.action_type is ActionType.PAY_INVOICE:
            expected = ledger.invoice_amount.get(a.target.id)
            if expected is None:
                problems.append(f"No amount for invoice {a.target.id} was retrieved; fetch it "
                                "through MCP before proposing payment.")
            elif abs(a.amount - expected) > AMOUNT_TOLERANCE:
                problems.append(f"Invoice {a.target.id} amount is {expected:.2f} in the database, "
                                f"not {a.amount:.2f}.")
        if a.action_type is ActionType.OFFER_DISCOUNT:
            if a.target.id not in ledger.pricing:
                problems.append(f"No pricing for {a.target.id} was retrieved; fetch it before "
                                "proposing a discount.")
            else:
                cost, list_price = ledger.pricing[a.target.id]
                price = list_price * (1 - a.discount_pct / 100)
                if price <= cost + AMOUNT_TOLERANCE:
                    problems.append(f"A {a.discount_pct:g}% discount prices {a.target.id} at "
                                    f"${price:.2f}, at or below its ${cost:.2f} unit cost.")
        if a.action_type is ActionType.PAY_RENT:
            expected = ledger.lease_rent.get(a.target.id)
            if expected is None:
                problems.append(f"No rent for lease {a.target.id} was retrieved; fetch it "
                                "through MCP before proposing payment.")
            elif abs(a.amount - expected) > AMOUNT_TOLERANCE:
                problems.append(f"Lease {a.target.id} rent is {expected:.2f} in the database, "
                                f"not {a.amount:.2f}.")
    return problems


# --- Deterministic rules applied after validation ------------------------------

def apply_action_rules(actions: list[ProposedAction], ledger: FactLedger) -> tuple[list[ProposedAction], list[str]]:
    """Set approval and blocked status from database facts; returns (actions, notes)."""
    notes: list[str] = []
    kept: list[ProposedAction] = []
    seen: set[tuple] = set()
    for action in actions:
        key = action.dedupe_key()
        if key in seen:
            notes.append(f"Dropped duplicate action {action.action_type.value} on {key[1]}.")
            continue
        seen.add(key)
        a = action.model_copy()
        a.status = (ActionStatus.NEEDS_HUMAN_APPROVAL if a.action_type in APPROVAL_REQUIRED_ACTIONS
                    else ActionStatus.PROPOSED)
        a.blocked_reason = None

        if a.action_type is ActionType.DRAFT_PURCHASE_ORDER:
            vid = a.target.id
            if vid not in ledger.vendor_eligible:
                a.status, a.blocked_reason = (ActionStatus.BLOCKED,
                    f"Vendor {vid}'s eligibility was not checked in this run.")
            elif ledger.vendor_eligible[vid] is not True:
                a.status, a.blocked_reason = (ActionStatus.BLOCKED,
                    f"Vendor {vid} may not ship: {ledger.vendor_reason.get(vid, 'eligibility unknown')}")

        if a.action_type is ActionType.PAY_INVOICE:
            status = ledger.invoice_status.get(a.target.id, "").lower()
            if status and status != "open":
                a.status, a.blocked_reason = (ActionStatus.BLOCKED,
                    f"Invoice {a.target.id} is marked '{status}' in the database, not open.")

        if a.action_type in PAYMENT_ACTIONS and a.status is not ActionStatus.BLOCKED:
            balance = ledger.cash_balance.get("checking")
            if balance is not None and a.amount > balance + AMOUNT_TOLERANCE:
                a.status, a.blocked_reason = (ActionStatus.BLOCKED,
                    f"${a.amount:,.2f} exceeds the ${balance:,.2f} checking balance.")

        if a.status is ActionStatus.BLOCKED:
            notes.append(f"{a.action_type.value} blocked: {a.blocked_reason}")
        kept.append(a)

    payments = [a for a in kept if a.action_type in PAYMENT_ACTIONS
                and a.status is not ActionStatus.BLOCKED]
    balance = ledger.cash_balance.get("checking")
    total = sum(a.amount for a in payments)
    if balance is not None and total > balance + AMOUNT_TOLERANCE:
        notes.append(f"Proposed payments total ${total:,.2f}, more than the ${balance:,.2f} "
                     "checking balance; a human must choose which to approve.")
    return kept, notes


def approvals_for(actions: list[ProposedAction]) -> list[ApprovalRequirement]:
    return [
        ApprovalRequirement(action_type=a.action_type, description=a.description, target=a.target,
                            amount=a.amount, payee=a.payee, status=a.status,
                            blocked_reason=a.blocked_reason)
        for a in actions if a.requires_human_approval
    ]
