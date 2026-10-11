"""Campus Customs operations MCP server — Homework 5.

The controlled interface to the working database ../data/campus_customs_new.db.
The original ../data/campus_customs.db is never opened.

The agent-facing tools are read-only. The two write tools at the end
(record_run_outcome, approve_proposal) are reserved for the FastAPI backend:
no agent is given them, and approve_proposal is only called for an explicit
human approval. Their logic lives in operations.py.

Run (stdio):  python mcp_server/server.py
Run (HTTP):   python mcp_server/server.py --http
HTTP URL:     http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

import operations as ops

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# CAMPUS_CUSTOMS_DB (set in .mcp.json) names the working copy; relative paths
# are resolved from the Homework 5 folder.
DB_PATH = ROOT / os.environ.get("CAMPUS_CUSTOMS_DB", "data/campus_customs_new.db")
ORIGINAL_DB_PATH = ROOT / "data" / "campus_customs.db"

# Values the payment tool will write to payments.kind. The payments table is
# empty in the source data, so these are this system's own convention.
PAYMENT_KIND_INVOICE = "invoice"
PAYMENT_KIND_RENT = "rent"

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True}
WRITES = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
MOVES_MONEY = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}

mcp = FastMCP("campus-customs-ops")


def _check_path() -> None:
    if not DB_PATH.exists():
        raise ToolError(f"Working database not found: {DB_PATH.name}")
    if DB_PATH.resolve() == ORIGINAL_DB_PATH.resolve() or DB_PATH.samefile(ORIGINAL_DB_PATH):
        raise ToolError("Refusing to open the original database.")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the working database read-only, and always close it afterwards."""
    _check_path()
    conn = sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def connect_rw() -> Iterator[sqlite3.Connection]:
    """A write connection for the backend-only tools. Transactions are explicit
    (BEGIN IMMEDIATE in operations.py), so autocommit mode is used here."""
    _check_path()
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def shop_date(conn: sqlite3.Connection) -> date:
    """The shop's business date from desk.date_today — the system clock is never used."""
    rows = conn.execute("SELECT date_today FROM desk").fetchall()
    if len(rows) != 1:
        raise ToolError(
            f"desk must hold exactly one date_today row, found {len(rows)}; "
            "the shop's current date is ambiguous."
        )
    today = parse_date(rows[0]["date_today"])
    if today is None:
        raise ToolError(f"desk.date_today is not a valid date: {rows[0]['date_today']!r}")
    return today


def days_between(start: date, end: str | None) -> int | None:
    end_date = parse_date(end)
    return (end_date - start).days if end_date else None


def money(value: float) -> float:
    return round(value, 2)


def due_label(days_until_due: int | None) -> str:
    if days_until_due is None:
        return "unknown"
    if days_until_due < 0:
        return f"overdue by {-days_until_due} day(s)"
    if days_until_due == 0:
        return "due today"
    return f"due in {days_until_due} day(s)"


@mcp.tool(annotations=READ_ONLY)
def get_stock_and_pricing(
    sku: str, size: str | None = None, qty_needed: int | None = None
) -> dict:
    """Stock on hand for one product SKU, by size, plus its unit cost and list price.

    Use when a ticket asks for a quantity of a product (a customer order or a
    bulk request) to see whether stock covers it, how many units are short,
    and what margin the shop earns per unit before any discount.

    sku: product code, e.g. "CC-TEE-WHITE".
    size: e.g. "S", "M", "L", "XL", or "OS". Omit to see every size.
    qty_needed: units the ticket asks for. Needs a size unless the SKU has only one.
    """
    sku = sku.strip().upper()
    if not sku:
        raise ToolError("sku is required.")
    size = size.strip().upper() if size and size.strip() else None
    if qty_needed is not None and qty_needed < 1:
        raise ToolError("qty_needed must be a positive whole number.")

    with connect() as conn:
        rows = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? "
            "ORDER BY rowid",
            (sku,),
        ).fetchall()
        if not rows:
            known = [r["sku"] for r in conn.execute("SELECT DISTINCT sku FROM inventory")]
            return {"found": False, "sku": sku, "message": f"No inventory rows for SKU {sku}.",
                    "known_skus": known}
        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()

    stock = [{"size": r["size"], "qty": r["qty"], "location": r["location"]} for r in rows]
    sizes = [s["size"] for s in stock]
    notes: list[str] = []

    if size is None and qty_needed is not None:
        if len(stock) != 1:
            raise ToolError(f"qty_needed needs a size; {sku} comes in {', '.join(sizes)}.")
        size = sizes[0]

    requested = next((s for s in stock if s["size"] == size), None) if size else None
    if size and requested is None:
        notes.append(f"No inventory row for {sku} size {size}; recorded sizes are "
                     f"{', '.join(sizes)}. Stock for that size is unknown, not zero.")

    computed: dict = {}
    if requested is not None and qty_needed is not None:
        computed["shortfall"] = max(0, qty_needed - requested["qty"])
        computed["can_fill_from_stock"] = requested["qty"] >= qty_needed

    pricing = None
    if price is None:
        notes.append(f"No pricing row for {sku}; cost and margin cannot be calculated.")
    else:
        pricing = {"unit_cost": price["unit_cost"], "list_price": price["list_price"]}
        unit_margin = price["list_price"] - price["unit_cost"]
        computed["unit_margin"] = money(unit_margin)
        if price["list_price"] > 0:
            computed["margin_pct_of_list_price"] = money(100 * unit_margin / price["list_price"])
            computed["max_discount_pct_before_selling_below_cost"] = computed["margin_pct_of_list_price"]
        if requested is not None and qty_needed is not None:
            computed["revenue_at_list_price_for_qty_needed"] = money(price["list_price"] * qty_needed)
            computed["cost_for_qty_needed"] = money(price["unit_cost"] * qty_needed)

    return {
        "found": True,
        "sku": sku,
        "product_name": rows[0]["name"],
        "requested": {"size": size, "qty_needed": qty_needed},
        "database": {"stock_by_size": stock,
                     "requested_size_stock": requested,
                     "pricing": pricing},
        "computed": computed,
        "notes": notes,
    }


@mcp.tool(annotations=READ_ONLY)
def check_vendor_eligibility(vendor_id: int | None = None) -> dict:
    """Whether each vendor may ship new product, with lead times and their invoices.

    A vendor with an open, unpaid invoice may not ship new product. Use before
    recommending a restock or purchase order, and again before acting on one,
    because eligibility changes when an invoice is paid. Also lists each
    vendor's invoices with days past due, measured from the shop's date.

    vendor_id: one vendor's id. Omit to check every vendor.
    """
    if vendor_id is not None and vendor_id < 1:
        raise ToolError("vendor_id must be a positive whole number.")

    with connect() as conn:
        today = shop_date(conn)
        if vendor_id is None:
            vendors = conn.execute(
                "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"
            ).fetchall()
        else:
            vendors = conn.execute(
                "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
            ).fetchall()
            if not vendors:
                known = [r["id"] for r in conn.execute("SELECT id FROM vendors ORDER BY id")]
                return {"found": False, "vendor_id": vendor_id,
                        "message": f"No vendor with id {vendor_id}.", "known_vendor_ids": known}

        results = []
        for v in vendors:
            invoices = []
            for inv in conn.execute(
                "SELECT id, amount, due_date, status, description FROM invoices "
                "WHERE vendor_id = ? ORDER BY due_date",
                (v["id"],),
            ):
                payments = [dict(p) for p in conn.execute(
                    "SELECT id, amount, paid_at, approved_by FROM payments "
                    "WHERE kind = ? AND ref_id = ?",
                    (PAYMENT_KIND_INVOICE, inv["id"]),
                )]
                days_to_due = days_between(today, inv["due_date"])
                invoices.append({
                    "invoice_id": inv["id"], "amount": inv["amount"],
                    "due_date": inv["due_date"], "status": inv["status"],
                    "description": inv["description"], "payments_recorded": payments,
                    "days_past_due": max(0, -days_to_due) if days_to_due is not None else None,
                })

            blocking = [i for i in invoices if i["status"].lower() == "open"]
            unrecognized = [i for i in invoices if i["status"].lower() not in ("open", "paid")]
            conflicts = [i for i in blocking if i["payments_recorded"]]
            if unrecognized or conflicts:
                eligible = None
                problems = [f"invoice {i['invoice_id']} has unrecognized status {i['status']!r}"
                            for i in unrecognized]
                problems += [f"invoice {i['invoice_id']} is open but has a recorded payment"
                             for i in conflicts]
                reason = "Cannot determine: " + "; ".join(problems) + ". A human must confirm."
            elif blocking:
                eligible = False
                reason = "Open unpaid invoice(s): " + ", ".join(
                    f"{i['invoice_id']} (${i['amount']:.2f}, due {i['due_date']})" for i in blocking)
            else:
                eligible = True
                reason = "No open invoices."

            results.append({
                "vendor_id": v["id"], "name": v["name"], "specialty": v["specialty"],
                "lead_days": v["lead_days"], "invoices": invoices,
                "eligible_to_ship": eligible, "eligibility_reason": reason,
                "open_unpaid_total": money(sum(i["amount"] for i in blocking)),
                "earliest_arrival_if_ordered_today": (
                    (today + timedelta(days=v["lead_days"])).isoformat() if eligible else None),
            })

    return {
        "found": True,
        "shop_date": today.isoformat(),
        "vendors": results,
        "notes": [
            "The database has no product-to-vendor table. Matching a SKU to a vendor "
            "by its specialty text is the agent's judgment, not a database fact.",
            "earliest_arrival_if_ordered_today counts lead_days as calendar days from "
            "the shop's date; the vendors table does not say which kind of days they are.",
        ],
    }


@mcp.tool(annotations=READ_ONLY)
def get_rent_due_and_cash_position(lease_id: int, account: str = "checking") -> dict:
    """A lease's rent and due date next to the cash balance and other open bills.

    Use for a rent notice or any facilities payment question: shows how many
    days until rent is due (from the shop's date), rent payments already
    recorded, the cash balance, and the open vendor invoices competing for
    the same cash, so an agent can judge whether rent is affordable.

    lease_id: the lease's id, e.g. from a ticket's lease_id.
    account: the cash account to check; defaults to "checking".
    """
    if lease_id < 1:
        raise ToolError("lease_id must be a positive whole number.")
    account = account.strip()
    if not account:
        raise ToolError("account is required.")

    with connect() as conn:
        today = shop_date(conn)
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
            "FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            known = [r["id"] for r in conn.execute("SELECT id FROM leases ORDER BY id")]
            return {"found": False, "lease_id": lease_id,
                    "message": f"No lease with id {lease_id}.", "known_lease_ids": known}
        cash = conn.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)
        ).fetchone()
        if cash is None:
            known = [r["name"] for r in conn.execute("SELECT name FROM cash_accounts")]
            return {"found": False, "account": account,
                    "message": f"No cash account named {account!r}.", "known_accounts": known}
        rent_payments = [dict(p) for p in conn.execute(
            "SELECT id, amount, account, paid_at, approved_by FROM payments "
            "WHERE kind = ? AND ref_id = ? ORDER BY paid_at",
            (PAYMENT_KIND_RENT, lease_id),
        )]
        open_invoices = [dict(r) for r in conn.execute(
            "SELECT i.id AS invoice_id, i.vendor_id, v.name AS vendor_name, i.amount, "
            "i.due_date, i.status, i.description "
            "FROM invoices i LEFT JOIN vendors v ON v.id = i.vendor_id "
            "WHERE lower(i.status) = 'open' ORDER BY i.due_date"
        )]

    notes: list[str] = []
    days_until_due = days_between(today, lease["next_due"])
    due_status = due_label(days_until_due)
    if days_until_due is None:
        notes.append(f"leases.next_due is not a valid date: {lease['next_due']!r}.")
    if not (lease["notes"] or "").strip():
        notes.append("The lease has no notes: the database records no grace period, "
                     "late fee or penalty terms. Escalate questions about them to a human.")
    notes.append("payments has no billing-period field, so a recorded rent payment "
                 "cannot be tied to a specific due date from the database alone.")
    if cash["date"] != today.isoformat():
        notes.append(f"The cash balance is dated {cash['date']}, not the shop date "
                     f"{today.isoformat()}.")

    open_total = sum(i["amount"] for i in open_invoices)
    return {
        "found": True,
        "shop_date": today.isoformat(),
        "database": {
            "lease": dict(lease),
            "rent_payments_recorded": rent_payments,
            "cash_account": dict(cash),
            "open_invoices": open_invoices,
        },
        "computed": {
            "days_until_rent_due": days_until_due,
            "rent_due_status": due_status,
            "cash_covers_rent": cash["balance"] >= lease["monthly_rent"],
            "balance_after_rent": money(cash["balance"] - lease["monthly_rent"]),
            "open_invoices_total": money(open_total),
            "balance_after_rent_and_open_invoices": money(
                cash["balance"] - lease["monthly_rent"] - open_total),
        },
        "notes": notes,
    }


@mcp.tool(annotations=READ_ONLY)
def list_open_tickets() -> dict:
    """The operations tickets whose status is "open", oldest first.

    Use to find which tickets still need work before reading one in full
    with get_ticket_details.
    """
    with connect() as conn:
        today = shop_date(conn)
        rows = conn.execute(
            "SELECT id, type, requester, subject, status, created_at FROM tickets "
            "WHERE lower(status) = 'open' ORDER BY created_at, id"
        ).fetchall()
    return {"shop_date": today.isoformat(),
            "tickets": [{"ticket_id": r["id"], **{k: r[k] for k in r.keys() if k != "id"}}
                        for r in rows]}


@mcp.tool(annotations=READ_ONLY)
def get_ticket_details(ticket_id: int) -> dict:
    """One ticket in full, plus a check of every record it links to.

    Use first on any ticket: it returns the request (type, requester, notes,
    SKU, size, quantity) and confirms whether the linked inventory row,
    lease and invoice exist, with the ids needed for the other tools. It does
    not return stock levels, cash or rent amounts; use the specialist tools.

    ticket_id: the ticket's id.
    """
    if ticket_id < 1:
        raise ToolError("ticket_id must be a positive whole number.")

    with connect() as conn:
        today = shop_date(conn)
        ticket = conn.execute(
            "SELECT id, type, requester, subject, sku, size, qty, lease_id, invoice_id, "
            "status, notes, created_at FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        if ticket is None:
            known = [r["id"] for r in conn.execute("SELECT id FROM tickets ORDER BY id")]
            return {"found": False, "ticket_id": ticket_id,
                    "message": f"No ticket with id {ticket_id}.", "known_ticket_ids": known}

        links: dict = {}
        notes: list[str] = []
        if ticket["sku"]:
            product = conn.execute(
                "SELECT name FROM inventory WHERE sku = ? LIMIT 1", (ticket["sku"],)
            ).fetchone()
            row = conn.execute(
                "SELECT 1 FROM inventory WHERE sku = ? AND size = ?",
                (ticket["sku"], ticket["size"]),
            ).fetchone()
            links["product"] = {"sku": ticket["sku"], "size": ticket["size"],
                                "sku_exists": product is not None,
                                "product_name": product["name"] if product else None,
                                "inventory_row_exists": row is not None}
            if ticket["size"] is None:
                notes.append("The ticket names a SKU but no size.")
        if ticket["lease_id"] is not None:
            lease = conn.execute(
                "SELECT id, space_name, landlord FROM leases WHERE id = ?", (ticket["lease_id"],)
            ).fetchone()
            links["lease"] = dict(lease) if lease else {"id": ticket["lease_id"], "exists": False}
        if ticket["invoice_id"] is not None:
            invoice = conn.execute(
                "SELECT i.id, i.vendor_id, v.name AS vendor_name, i.status FROM invoices i "
                "LEFT JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (ticket["invoice_id"],),
            ).fetchone()
            links["invoice"] = (dict(invoice) if invoice
                                else {"id": ticket["invoice_id"], "exists": False})
        for name, link in links.items():
            if link.get("exists") is False or link.get("sku_exists") is False:
                notes.append(f"The ticket's linked {name} was not found in the database.")

    return {
        "found": True,
        "shop_date": today.isoformat(),
        "database": {"ticket": {"ticket_id": ticket["id"],
                                **{k: ticket[k] for k in ticket.keys() if k != "id"}},
                     "linked_records": links},
        "notes": notes,
    }


@mcp.tool(annotations=READ_ONLY)
def get_cash_and_obligations(account: str = "checking") -> dict:
    """The cash balance next to everything the shop currently owes.

    Use for any payment, purchase or affordability question: lists every
    open vendor invoice with days past due, every lease's next rent with
    days until due, and payments already recorded, then totals them against
    the cash balance. Days are counted from the shop's date.

    account: the cash account to check; defaults to "checking".
    """
    account = account.strip()
    if not account:
        raise ToolError("account is required.")

    with connect() as conn:
        today = shop_date(conn)
        cash = conn.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)
        ).fetchone()
        if cash is None:
            known = [r["name"] for r in conn.execute("SELECT name FROM cash_accounts")]
            return {"found": False, "account": account,
                    "message": f"No cash account named {account!r}.", "known_accounts": known}
        invoices = conn.execute(
            "SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date, "
            "i.status, i.description FROM invoices i "
            "LEFT JOIN vendors v ON v.id = i.vendor_id "
            "WHERE lower(i.status) = 'open' ORDER BY i.due_date"
        ).fetchall()
        leases = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due FROM leases ORDER BY next_due"
        ).fetchall()
        payments = [dict(p) for p in conn.execute(
            "SELECT id, kind, ref_id, amount, account, paid_at, approved_by FROM payments "
            "ORDER BY paid_at DESC LIMIT 20"
        )]

    open_invoices = []
    for inv in invoices:
        days_to_due = days_between(today, inv["due_date"])
        open_invoices.append({
            "invoice_id": inv["id"], "vendor_id": inv["vendor_id"],
            "vendor_name": inv["vendor_name"], "amount": inv["amount"],
            "due_date": inv["due_date"], "status": inv["status"],
            "description": inv["description"],
            "days_past_due": max(0, -days_to_due) if days_to_due is not None else None,
        })
    rent = []
    for lease in leases:
        days_until_due = days_between(today, lease["next_due"])
        rent.append({"lease_id": lease["id"], "space_name": lease["space_name"],
                     "landlord": lease["landlord"], "monthly_rent": lease["monthly_rent"],
                     "next_due": lease["next_due"], "days_until_due": days_until_due,
                     "due_status": due_label(days_until_due)})

    invoices_total = sum(i["amount"] for i in open_invoices)
    overdue_total = sum(i["amount"] for i in open_invoices if i["days_past_due"])
    rent_total = sum(r["monthly_rent"] for r in rent)
    notes = ["Cash only flows out in this system: the database has no sales or "
             "receipts, so the balance cannot be assumed to grow before a due date."]
    if cash["date"] != today.isoformat():
        notes.append(f"The cash balance is dated {cash['date']}, not the shop date "
                     f"{today.isoformat()}.")

    return {
        "found": True,
        "shop_date": today.isoformat(),
        "database": {"cash_account": dict(cash), "open_invoices": open_invoices,
                     "next_rent_by_lease": rent, "recent_payments": payments},
        "computed": {
            "open_invoices_total": money(invoices_total),
            "overdue_invoices_total": money(overdue_total),
            "next_rent_total": money(rent_total),
            "all_listed_obligations_total": money(invoices_total + rent_total),
            "balance_after_all_listed_obligations": money(
                cash["balance"] - invoices_total - rent_total),
        },
        "notes": notes,
    }


@mcp.tool(annotations=READ_ONLY)
def list_tickets(status: Literal["all", "open", "resolved"] = "all") -> dict:
    """Every ticket with its persisted status, plus the latest recorded agent run.

    Use for the operator dashboard. status filters by tickets.status.
    """
    with connect() as conn:
        today = shop_date(conn)
        sql = ("SELECT id, type, requester, subject, sku, size, qty, lease_id, invoice_id, "
               "status, created_at FROM tickets")
        args: tuple = ()
        if status != "all":
            sql += " WHERE lower(status) = ?"
            args = (status,)
        rows = conn.execute(sql + " ORDER BY created_at, id", args).fetchall()
        runs = ops.latest_run_status(conn)
    return {"shop_date": today.isoformat(),
            "tickets": [{"ticket_id": r["id"], **{k: r[k] for k in r.keys() if k != "id"},
                         "latest_run": runs.get(r["id"])} for r in rows]}


@mcp.tool(annotations=READ_ONLY)
def list_action_proposals(ticket_id: int | None = None,
                          status: Literal["pending", "executed", "approved", "declined",
                                          "superseded"] | None = None) -> dict:
    """Payment and purchase proposals recorded from agent runs, newest first (max 100).

    Each has a stable id, its kind (pay_invoice, pay_rent, purchase_order, offer_discount),
    the database record it targets, amount, payee and status.
    """
    with connect() as conn:
        return {"proposals": ops.list_proposals(conn, ticket_id, status)}


class ProposalIn(BaseModel):
    kind: Literal["pay_invoice", "pay_rent", "purchase_order", "offer_discount"]
    ref_id: int = Field(description="invoices.id, leases.id, vendors.id for a purchase order, "
                                    "or tickets.id for a discount")
    amount: float | None = Field(default=None, ge=0)
    payee: str | None = None
    sku: str | None = None
    size: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    discount_pct: float | None = Field(default=None, gt=0, lt=100)
    description: str = Field(max_length=300)
    blocked_reason: str | None = Field(default=None, max_length=300)


@mcp.tool(annotations=WRITES)
def record_run_outcome(run_id: str, ticket_id: int, run_status: str,
                       proposals: list[ProposalIn]) -> dict:
    """BACKEND ONLY — not available to agents. Record a finished run's status and its
    payment and purchase proposals.

    Each proposal is checked against the database: payment amounts must match the
    invoice or rent exactly, and purchase-order cost is taken from pricing. A
    proposal identical to a pending one keeps its id; pending proposals the run
    did not repeat are superseded. Marks the ticket resolved only when the run
    resolved it with nothing left to approve.
    """
    if not run_id.strip():
        raise ToolError("run_id is required.")
    with connect_rw() as conn:
        try:
            return ops.record_run_outcome(conn, utc_now(), run_id, ticket_id, run_status,
                                          [p.model_dump() for p in proposals])
        except ops.Refusal as r:
            raise ToolError(f"{r.code}: {r.message}") from r


@mcp.tool(annotations=MOVES_MONEY)
def approve_proposal(proposal_id: int, approved_by: str, confirm_amount: float,
                     confirm_payee: str) -> dict:
    """BACKEND ONLY — not available to agents. Process one explicit human approval.

    The approval must repeat the proposal's exact amount and payee. Everything is
    re-checked inside one locked transaction: the proposal is still pending, the
    invoice is still open or the rent unchanged, and checking holds enough cash.
    A payment then debits checking, records the payment, and marks the invoice
    paid or moves the rent due date on a month. A purchase order is approved
    only if the vendor has no unpaid invoice; a discount only if the price stays
    above unit cost. Neither moves cash, and nothing is ever sent.
    Refusals change nothing except the record of the attempt.
    """
    with connect_rw() as conn:
        today = shop_date(conn)
        return ops.approve_proposal(conn, today, utc_now(), proposal_id, approved_by,
                                    confirm_amount, confirm_payee)


@mcp.tool(annotations=WRITES)
def decline_proposal(proposal_id: int, declined_by: str, reason: str = "") -> dict:
    """BACKEND ONLY — not available to agents. Record a human's decision not to
    approve a pending proposal. Nothing is paid, ordered or sent; the proposal is
    marked declined and the decision is stored in approvals.
    """
    with connect_rw() as conn:
        return ops.decline_proposal(conn, utc_now(), proposal_id, declined_by, reason)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs operations MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP on port 8001 (keeps FastAPI free on 8000)",
    )
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=8001, show_banner=False)
    else:
        mcp.run(show_banner=False)
