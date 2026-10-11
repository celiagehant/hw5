"""State-changing operations on the working database: proposal records, human
approvals and payment execution.

These functions back the MCP server's write tools (record_run_outcome,
approve_proposal). Those tools are reserved for the FastAPI backend: no agent's
tool list includes them. Every write runs inside `BEGIN IMMEDIATE`, which takes
SQLite's write lock before any check is made, so two approvals can never both
see the same cash or the same pending proposal.

Tables added to the working copy (a reset removes them; they are recreated on
the next write):
  ticket_runs       one row per finished agent run: its final workflow status
  action_proposals  payment and purchase proposals with stable ids
  approvals         every human approval attempt and its outcome
A trigger makes the database itself refuse a negative cash balance.
"""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date

PAYMENT_KIND_INVOICE = "invoice"
PAYMENT_KIND_RENT = "rent"
TOLERANCE = 0.005

PROPOSAL_KINDS = ("pay_invoice", "pay_rent", "purchase_order", "offer_discount")
RUN_STATUSES = ("awaiting_human_approval", "blocked", "needs_clarification", "escalated",
                "resolved", "limit_reached", "failed")
AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service",
               "customer service", "agent", "system"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticket_runs (
    run_id      TEXT PRIMARY KEY,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    run_status  TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS action_proposals (
    id             INTEGER PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES ticket_runs(run_id),
    ticket_id      INTEGER NOT NULL REFERENCES tickets(id),
    kind           TEXT NOT NULL
                   CHECK (kind IN ('pay_invoice', 'pay_rent', 'purchase_order', 'offer_discount')),
    ref_table      TEXT NOT NULL,
    ref_id         INTEGER NOT NULL,
    amount         REAL NOT NULL CHECK (amount >= 0),
    payee          TEXT NOT NULL,
    sku            TEXT,
    size           TEXT,
    quantity       INTEGER,
    discount_pct   REAL CHECK (discount_pct IS NULL OR (discount_pct > 0 AND discount_pct < 100)),
    description    TEXT NOT NULL,
    blocked_reason TEXT,
    status         TEXT NOT NULL
                   CHECK (status IN ('pending', 'executed', 'approved', 'declined', 'superseded')),
    created_at     TEXT NOT NULL,
    decided_at     TEXT,
    decided_by     TEXT,
    payment_id     INTEGER REFERENCES payments(id),
    balance_after  REAL,
    result         TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    id              INTEGER PRIMARY KEY,
    proposal_id     INTEGER NOT NULL REFERENCES action_proposals(id),
    approved_by     TEXT NOT NULL,
    approved_amount REAL NOT NULL,
    approved_payee  TEXT NOT NULL,
    outcome         TEXT NOT NULL
                    CHECK (outcome IN ('executed', 'approved', 'declined', 'refused')),
    detail          TEXT,
    created_at      TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS cash_balance_never_negative
BEFORE UPDATE OF balance ON cash_accounts
WHEN NEW.balance < 0
BEGIN
    SELECT RAISE(ABORT, 'cash balance cannot go negative');
END;
"""


class Refusal(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def add_one_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _row(conn: sqlite3.Connection, sql: str, args: tuple) -> sqlite3.Row | None:
    return conn.execute(sql, args).fetchone()


def _checking(conn: sqlite3.Connection) -> sqlite3.Row:
    cash = _row(conn, "SELECT name, balance, date FROM cash_accounts WHERE name = 'checking'", ())
    if cash is None:
        raise Refusal("no_account", "No cash account named 'checking' exists.")
    return cash


# --- Recording proposals from a finished run -----------------------------------

def _validate_proposal(conn: sqlite3.Connection, p: dict) -> dict:
    """Check a proposal against the database and fill in database values."""
    kind = p["kind"]
    if kind == "pay_invoice":
        inv = _row(conn, "SELECT i.id, i.amount, i.status, v.name FROM invoices i "
                         "JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?", (p["ref_id"],))
        if inv is None:
            raise Refusal("not_found", f"invoice {p['ref_id']} does not exist")
        if inv["status"].lower() != "open":
            raise Refusal("not_payable", f"invoice {inv['id']} is '{inv['status']}', not open")
        if p.get("amount") is None or abs(p["amount"] - inv["amount"]) > TOLERANCE:
            raise Refusal("mismatch", f"invoice {inv['id']} is ${inv['amount']:.2f}, "
                                      f"proposal says {p.get('amount')}")
        return {"ref_table": "invoices", "amount": inv["amount"], "payee": inv["name"]}
    if kind == "pay_rent":
        lease = _row(conn, "SELECT id, monthly_rent, landlord FROM leases WHERE id = ?",
                     (p["ref_id"],))
        if lease is None:
            raise Refusal("not_found", f"lease {p['ref_id']} does not exist")
        if p.get("amount") is None or abs(p["amount"] - lease["monthly_rent"]) > TOLERANCE:
            raise Refusal("mismatch", f"lease {lease['id']} rent is ${lease['monthly_rent']:.2f}, "
                                      f"proposal says {p.get('amount')}")
        return {"ref_table": "leases", "amount": lease["monthly_rent"], "payee": lease["landlord"]}
    if kind == "purchase_order":
        vendor = _row(conn, "SELECT id, name FROM vendors WHERE id = ?", (p["ref_id"],))
        if vendor is None:
            raise Refusal("not_found", f"vendor {p['ref_id']} does not exist")
        if not p.get("sku") or not p.get("quantity") or p["quantity"] < 1:
            raise Refusal("invalid", "a purchase order needs a sku and a positive quantity")
        price = _row(conn, "SELECT unit_cost FROM pricing WHERE sku = ?", (p["sku"],))
        if price is None:
            raise Refusal("not_found", f"no pricing for {p['sku']}")
        if p.get("size") and _row(conn, "SELECT 1 FROM inventory WHERE sku = ? AND size = ?",
                                  (p["sku"], p["size"])) is None:
            raise Refusal("not_found", f"no inventory row for {p['sku']} size {p['size']}")
        # The cost comes from pricing, never from the agent.
        return {"ref_table": "vendors", "amount": round(price["unit_cost"] * p["quantity"], 2),
                "payee": vendor["name"]}
    if kind == "offer_discount":
        # A price decision for the requester on this ticket. No cash moves.
        ticket = _row(conn, "SELECT id, requester, sku, qty FROM tickets WHERE id = ?",
                      (p["ref_id"],))
        if ticket is None:
            raise Refusal("not_found", f"ticket {p['ref_id']} does not exist")
        sku = p.get("sku") or ticket["sku"]
        pct = p.get("discount_pct")
        qty = p.get("quantity") or ticket["qty"]
        if not sku or pct is None or not 0 < pct < 100 or not qty:
            raise Refusal("invalid", "a discount needs a sku, a discount_pct between 0 and 100 "
                                     "and a quantity")
        price = _row(conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
        if price is None:
            raise Refusal("not_found", f"no pricing for {sku}")
        unit_price = round(price["list_price"] * (1 - pct / 100), 2)
        if unit_price <= price["unit_cost"] + TOLERANCE:
            raise Refusal("below_cost", f"{pct:g}% off prices {sku} at ${unit_price:.2f}, at or "
                                        f"below its ${price['unit_cost']:.2f} unit cost")
        # amount = list-price revenue given up across the quantity
        return {"ref_table": "tickets", "payee": ticket["requester"], "sku": sku, "quantity": qty,
                "amount": round((price["list_price"] - unit_price) * qty, 2)}
    raise Refusal("invalid", f"unknown proposal kind {kind!r}")


def record_run_outcome(conn: sqlite3.Connection, now: str, run_id: str, ticket_id: int,
                       run_status: str, proposals: list[dict]) -> dict:
    if run_status not in RUN_STATUSES:
        raise Refusal("invalid", f"run_status must be one of {', '.join(RUN_STATUSES)}")
    ensure_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        if _row(conn, "SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)) is None:
            raise Refusal("not_found", f"ticket {ticket_id} does not exist")
        if _row(conn, "SELECT 1 FROM ticket_runs WHERE run_id = ?", (run_id,)):
            raise Refusal("duplicate", f"run {run_id} was already recorded")
        conn.execute("INSERT INTO ticket_runs (run_id, ticket_id, run_status, recorded_at) "
                     "VALUES (?, ?, ?, ?)", (run_id, ticket_id, run_status, now))

        created, kept, skipped = [], [], []
        for p in proposals:
            try:
                db = _validate_proposal(conn, p)
            except Refusal as r:
                skipped.append({"kind": p["kind"], "ref_id": p["ref_id"], "reason": r.message})
                continue
            p = {**p, "sku": db.get("sku", p.get("sku")), "quantity": db.get("quantity", p.get("quantity"))}
            same = _row(conn, """
                SELECT id FROM action_proposals
                WHERE ticket_id = ? AND status = 'pending' AND kind = ? AND ref_id = ?
                  AND abs(amount - ?) < ? AND payee = ? AND coalesce(sku, '') = ?
                  AND coalesce(size, '') = ? AND coalesce(quantity, 0) = ?
                  AND coalesce(discount_pct, 0) = ?""",
                (ticket_id, p["kind"], p["ref_id"], db["amount"], TOLERANCE, db["payee"],
                 p.get("sku") or "", p.get("size") or "", p.get("quantity") or 0,
                 p.get("discount_pct") or 0))
            if same:
                # Identical to a pending proposal: keep its id (and any approval context).
                conn.execute("UPDATE action_proposals SET run_id = ?, blocked_reason = ? "
                             "WHERE id = ?", (run_id, p.get("blocked_reason"), same["id"]))
                kept.append(same["id"])
                continue
            cur = conn.execute("""
                INSERT INTO action_proposals (run_id, ticket_id, kind, ref_table, ref_id, amount,
                    payee, sku, size, quantity, discount_pct, description, blocked_reason, status,
                    created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (run_id, ticket_id, p["kind"], db["ref_table"], p["ref_id"], db["amount"],
                 db["payee"], p.get("sku"), p.get("size"), p.get("quantity"),
                 p.get("discount_pct") if p["kind"] == "offer_discount" else None,
                 p["description"][:300], p.get("blocked_reason"), now))
            created.append(cur.lastrowid)

        # Pending proposals this run did not repeat are replaced: a changed
        # proposal needs a fresh approval.
        live = created + kept
        superseded = [r["id"] for r in conn.execute(
            "SELECT id FROM action_proposals WHERE ticket_id = ? AND status = 'pending'",
            (ticket_id,)) if r["id"] not in live]
        if superseded:
            conn.execute(f"UPDATE action_proposals SET status = 'superseded', result = ? "
                         f"WHERE id IN ({','.join('?' * len(superseded))})",
                         (f"replaced by run {run_id}", *superseded))

        resolved = False
        if run_status == "resolved" and not live:
            resolved = conn.execute("UPDATE tickets SET status = 'resolved' "
                                    "WHERE id = ? AND status = 'open'", (ticket_id,)).rowcount == 1
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {"run_id": run_id, "ticket_id": ticket_id, "run_status": run_status,
            "created_proposal_ids": created, "kept_proposal_ids": kept,
            "superseded_proposal_ids": superseded, "skipped": skipped,
            "ticket_resolved": resolved}


# --- Human approval and payment execution -------------------------------------------

def _maybe_resolve(conn: sqlite3.Connection, ticket_id: int) -> bool:
    """Resolve a ticket once every proposal from its latest run is done.

    Only runs that ended waiting for approval (or blocked on something an
    approval clears) qualify; escalated or unclear tickets stay open for a human.
    Declined and superseded proposals count as decided, but at least one
    proposal must have been carried out.
    """
    last = _row(conn, "SELECT run_id, run_status FROM ticket_runs WHERE ticket_id = ? "
                      "ORDER BY recorded_at DESC, rowid DESC LIMIT 1", (ticket_id,))
    if last is None or last["run_status"] not in ("awaiting_human_approval", "blocked"):
        return False
    statuses = [r["status"] for r in conn.execute(
        "SELECT status FROM action_proposals WHERE run_id = ?", (last["run_id"],))]
    if not statuses or "pending" in statuses:
        return False
    if not any(s in ("executed", "approved") for s in statuses):
        return False
    return conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ? AND status = 'open'",
                        (ticket_id,)).rowcount == 1


def approve_proposal(conn: sqlite3.Connection, today: date, now: str, proposal_id: int,
                     approved_by: str, confirm_amount: float, confirm_payee: str) -> dict:
    """Process one explicit human approval. Payments are executed; purchase orders
    are only marked approved (no cash moves, nothing is sent)."""
    approver = approved_by.strip()
    if not has_table(conn, "action_proposals"):
        return {"ok": False, "code": "not_found", "message": f"No proposal {proposal_id}."}
    if not approver or approver.lower() in AGENT_NAMES:
        return {"ok": False, "code": "invalid_approver",
                "message": "Approval must name the human operator who approves it."}

    conn.execute("BEGIN IMMEDIATE")
    try:
        p = _row(conn, "SELECT * FROM action_proposals WHERE id = ?", (proposal_id,))
        if p is None:
            conn.execute("ROLLBACK")
            return {"ok": False, "code": "not_found", "message": f"No proposal {proposal_id}."}
        if p["status"] != "pending":
            raise Refusal("not_pending", f"Proposal {proposal_id} is already {p['status']}"
                          + (f" ({p['result']})" if p["result"] else "") + ".")
        if abs(p["amount"] - confirm_amount) > TOLERANCE or p["payee"] != confirm_payee.strip():
            raise Refusal("mismatch", f"Proposal {proposal_id} is ${p['amount']:.2f} to "
                          f"{p['payee']}; the approval was for ${confirm_amount:.2f} to "
                          f"{confirm_payee.strip()}. Review the proposal and approve it as shown.")

        balance_before = _checking(conn)["balance"]
        payment_id = None
        if p["kind"] in ("pay_invoice", "pay_rent"):
            if p["kind"] == "pay_invoice":
                inv = _row(conn, "SELECT amount, status FROM invoices WHERE id = ?", (p["ref_id"],))
                if inv is None or inv["status"].lower() != "open":
                    raise Refusal("not_payable", f"Invoice {p['ref_id']} is "
                                  f"{'missing' if inv is None else repr(inv['status'])}, not open.")
                if abs(inv["amount"] - p["amount"]) > TOLERANCE:
                    raise Refusal("mismatch", f"Invoice {p['ref_id']} is now ${inv['amount']:.2f}; "
                                  "the proposal is out of date.")
            else:
                lease = _row(conn, "SELECT monthly_rent, next_due FROM leases WHERE id = ?",
                             (p["ref_id"],))
                if lease is None or abs(lease["monthly_rent"] - p["amount"]) > TOLERANCE:
                    raise Refusal("mismatch", f"Lease {p['ref_id']} no longer matches the proposal.")
            if balance_before + TOLERANCE < p["amount"]:
                raise Refusal("insufficient_funds",
                              f"Checking holds ${balance_before:,.2f}; the payment needs "
                              f"${p['amount']:,.2f}. Nothing was paid.")
            moved = conn.execute(
                "UPDATE cash_accounts SET balance = round(balance - ?, 2), date = ? "
                "WHERE name = 'checking' AND balance >= ?",
                (p["amount"], today.isoformat(), p["amount"] - TOLERANCE)).rowcount
            if moved != 1:
                raise Refusal("insufficient_funds", "The balance changed; nothing was paid.")
            payment_id = conn.execute(
                "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                "VALUES (?, ?, ?, 'checking', ?, ?)",
                (PAYMENT_KIND_INVOICE if p["kind"] == "pay_invoice" else PAYMENT_KIND_RENT,
                 p["ref_id"], p["amount"], today.isoformat(), approver)).lastrowid
            if p["kind"] == "pay_invoice":
                if conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ? "
                                "AND lower(status) = 'open'", (p["ref_id"],)).rowcount != 1:
                    raise Refusal("not_payable", f"Invoice {p['ref_id']} could not be marked paid.")
                result = f"Paid invoice {p['ref_id']}; payment {payment_id}."
            else:
                next_due = add_one_month(date.fromisoformat(lease["next_due"]))
                conn.execute("UPDATE leases SET next_due = ? WHERE id = ?",
                             (next_due.isoformat(), p["ref_id"]))
                result = (f"Paid rent for lease {p['ref_id']} due {lease['next_due']}; payment "
                          f"{payment_id}; next due {next_due.isoformat()}.")
            outcome = "executed"
        elif p["kind"] == "offer_discount":
            price = _row(conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (p["sku"],))
            if price is None:
                raise Refusal("not_found", f"No pricing for {p['sku']}.")
            unit_price = round(price["list_price"] * (1 - p["discount_pct"] / 100), 2)
            if unit_price <= price["unit_cost"] + TOLERANCE:
                raise Refusal("below_cost", f"{p['discount_pct']:g}% off would sell {p['sku']} "
                              f"at ${unit_price:.2f}, at or below its ${price['unit_cost']:.2f} cost.")
            result = (f"Discount approved: {p['discount_pct']:g}% off {p['sku']} for {p['payee']} "
                      f"(${price['list_price']:.2f} -> ${unit_price:.2f} each, {p['quantity']} units, "
                      f"${p['amount']:.2f} below list). No cash moved, the price list is unchanged "
                      "and nothing was sent.")
            outcome = "approved"
        else:
            # Eligibility is rechecked now, not taken from the proposal.
            unpaid = [r["id"] for r in conn.execute(
                "SELECT id FROM invoices WHERE vendor_id = ? AND lower(status) != 'paid'",
                (p["ref_id"],))]
            if unpaid:
                raise Refusal("vendor_ineligible",
                              f"{p['payee']} still has unpaid invoice(s) "
                              f"{', '.join(map(str, unpaid))}; it may not ship new product.")
            result = (f"Purchase order approved as a draft: {p['quantity']} x {p['sku']}"
                      f"{' ' + p['size'] if p['size'] else ''} from {p['payee']}. Not sent; "
                      "no cash moved.")
            outcome = "approved"

        balance_after = _checking(conn)["balance"]
        if conn.execute("UPDATE action_proposals SET status = ?, decided_at = ?, decided_by = ?, "
                        "payment_id = ?, balance_after = ?, result = ? "
                        "WHERE id = ? AND status = 'pending'",
                        (outcome, now, approver, payment_id, balance_after, result,
                         proposal_id)).rowcount != 1:
            raise Refusal("not_pending", f"Proposal {proposal_id} was decided concurrently.")
        conn.execute("INSERT INTO approvals (proposal_id, approved_by, approved_amount, "
                     "approved_payee, outcome, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (proposal_id, approver, confirm_amount, confirm_payee.strip(), outcome,
                      result, now))

        touched = {p["ticket_id"]}
        if payment_id is not None:
            # Other pending proposals to pay the same target can never run now.
            dupes = conn.execute("SELECT id, ticket_id FROM action_proposals WHERE status = "
                                 "'pending' AND kind = ? AND ref_id = ?",
                                 (p["kind"], p["ref_id"])).fetchall()
            for d in dupes:
                conn.execute("UPDATE action_proposals SET status = 'superseded', result = ? "
                             "WHERE id = ?", (f"target already paid by proposal {proposal_id}",
                                              d["id"]))
                touched.add(d["ticket_id"])
        resolved = sorted(t for t in touched if _maybe_resolve(conn, t))
        conn.execute("COMMIT")
    except Refusal as r:
        conn.execute("ROLLBACK")
        _record_refusal(conn, now, proposal_id, approver, confirm_amount, confirm_payee, r.message)
        return {"ok": False, "code": r.code, "message": r.message, "proposal_id": proposal_id,
                "ticket_id": p["ticket_id"], "balance": _checking_or_none(conn)}
    except sqlite3.DatabaseError as e:  # e.g. the never-negative trigger
        conn.execute("ROLLBACK")
        message = f"The database rejected the operation: {e}. Nothing was paid."
        _record_refusal(conn, now, proposal_id, approver, confirm_amount, confirm_payee, message)
        return {"ok": False, "code": "database_rejected", "message": message,
                "proposal_id": proposal_id, "ticket_id": p["ticket_id"],
                "balance": _checking_or_none(conn)}

    return {"ok": True, "outcome": outcome, "proposal_id": proposal_id,
            "ticket_id": p["ticket_id"], "run_id": p["run_id"], "kind": p["kind"],
            "ref_table": p["ref_table"], "ref_id": p["ref_id"], "amount": p["amount"],
            "payee": p["payee"], "approved_by": approver, "payment_id": payment_id,
            "balance_before": balance_before, "balance_after": balance_after,
            "message": result, "resolved_ticket_ids": resolved}


def decline_proposal(conn: sqlite3.Connection, now: str, proposal_id: int, declined_by: str,
                     reason: str) -> dict:
    """Record an explicit human decision not to approve a proposal. Nothing is paid,
    ordered or changed except the proposal's status and the approvals record."""
    who = declined_by.strip()
    if not has_table(conn, "action_proposals"):
        return {"ok": False, "code": "not_found", "message": f"No proposal {proposal_id}."}
    if not who or who.lower() in AGENT_NAMES:
        return {"ok": False, "code": "invalid_approver",
                "message": "A decline must name the human operator who makes it."}
    note = reason.strip()[:300] or "no reason given"
    conn.execute("BEGIN IMMEDIATE")
    try:
        p = _row(conn, "SELECT * FROM action_proposals WHERE id = ?", (proposal_id,))
        if p is None:
            conn.execute("ROLLBACK")
            return {"ok": False, "code": "not_found", "message": f"No proposal {proposal_id}."}
        if p["status"] != "pending":
            conn.execute("ROLLBACK")
            return {"ok": False, "code": "not_pending", "ticket_id": p["ticket_id"],
                    "message": f"Proposal {proposal_id} is already {p['status']}."}
        result = f"Declined by {who}: {note}"
        conn.execute("UPDATE action_proposals SET status = 'declined', decided_at = ?, "
                     "decided_by = ?, result = ? WHERE id = ? AND status = 'pending'",
                     (now, who, result, proposal_id))
        conn.execute("INSERT INTO approvals (proposal_id, approved_by, approved_amount, "
                     "approved_payee, outcome, detail, created_at) "
                     "VALUES (?, ?, ?, ?, 'declined', ?, ?)",
                     (proposal_id, who, p["amount"], p["payee"], note, now))
        resolved = _maybe_resolve(conn, p["ticket_id"])
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {"ok": True, "outcome": "declined", "proposal_id": proposal_id,
            "ticket_id": p["ticket_id"], "run_id": p["run_id"], "kind": p["kind"],
            "amount": p["amount"], "payee": p["payee"], "declined_by": who, "message": result,
            "resolved_ticket_ids": [p["ticket_id"]] if resolved else []}


def _checking_or_none(conn: sqlite3.Connection) -> float | None:
    row = _row(conn, "SELECT balance FROM cash_accounts WHERE name = 'checking'", ())
    return row["balance"] if row else None


def _record_refusal(conn, now, proposal_id, approver, amount, payee, message) -> None:
    """Keep a record of a refused attempt; it changes nothing else."""
    if not approver:
        return
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO approvals (proposal_id, approved_by, approved_amount, approved_payee, "
                 "outcome, detail, created_at) VALUES (?, ?, ?, ?, 'refused', ?, ?)",
                 (proposal_id, approver, amount, payee.strip(), message, now))
    conn.execute("COMMIT")


# --- Reads ------------------------------------------------------------------------------

def list_proposals(conn: sqlite3.Connection, ticket_id: int | None, status: str | None) -> list[dict]:
    if not has_table(conn, "action_proposals"):
        return []
    sql = "SELECT * FROM action_proposals WHERE 1 = 1"
    args: list = []
    if ticket_id is not None:
        sql += " AND ticket_id = ?"
        args.append(ticket_id)
    if status is not None:
        sql += " AND status = ?"
        args.append(status)
    return [dict(r) for r in conn.execute(sql + " ORDER BY id DESC LIMIT 100", args)]


def latest_run_status(conn: sqlite3.Connection) -> dict[int, dict]:
    if not has_table(conn, "ticket_runs"):
        return {}
    rows = conn.execute("SELECT ticket_id, run_id, run_status, recorded_at FROM ticket_runs "
                        "ORDER BY recorded_at, rowid").fetchall()
    return {r["ticket_id"]: dict(r) for r in rows}
