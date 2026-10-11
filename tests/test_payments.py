"""Offline checks of proposal recording, human approval and payment execution.

Runs against a temporary copy of the original database; neither real database
file is touched.  Run from the Homework 5 folder:
    .venv/bin/python tests/test_payments.py
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import threading
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp_server"))
import operations as ops  # noqa: E402

TODAY = date(2026, 8, 31)
NOW = "2026-10-11T12:00:00+00:00"
PASSED = 0


def check(cond: bool, label: str) -> None:
    global PASSED
    if not cond:
        raise AssertionError(label)
    PASSED += 1
    print("ok  ", label)


def fresh_db() -> Path:
    path = Path(tempfile.mkdtemp()) / "work.db"
    shutil.copy(ROOT / "data" / "campus_customs.db", path)
    path.chmod(0o644)
    return path


def conn_for(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(path, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def balance(c) -> float:
    return c.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]


def approve(c, pid, who="Celia (operator)", amount=None, payee=None):
    p = c.execute("SELECT amount, payee FROM action_proposals WHERE id=?", (pid,)).fetchone()
    return ops.approve_proposal(c, TODAY, NOW, pid, who,
                                p["amount"] if amount is None else amount,
                                p["payee"] if payee is None else payee)


def main() -> None:
    path = fresh_db()
    c = conn_for(path)

    out = ops.record_run_outcome(c, NOW, "run-a", 101, "blocked", [
        {"kind": "pay_invoice", "ref_id": 501, "amount": 840.0, "description": "pay 501"},
        {"kind": "purchase_order", "ref_id": 1, "sku": "CC-TEE-WHITE", "size": "S",
         "quantity": 1, "amount": 999.0, "description": "reprint"},
        {"kind": "pay_invoice", "ref_id": 501, "amount": 800.0, "description": "wrong amount"},
    ])
    inv_id, po_id = out["created_proposal_ids"]
    check(len(out["skipped"]) == 1 and "840.00" in out["skipped"][0]["reason"],
          "proposal with an amount different from the database is not recorded")
    po = c.execute("SELECT amount, payee FROM action_proposals WHERE id=?", (po_id,)).fetchone()
    check(po["amount"] == 8.0 and po["payee"] == "Bulldog Print Co",
          "purchase-order cost and payee come from the database, not the agent")

    r = approve(c, po_id)
    check(not r["ok"] and r["code"] == "vendor_ineligible" and balance(c) == 3400.0,
          "purchase order refused while the vendor has an unpaid invoice")
    r = approve(c, inv_id, amount=84.0)
    check(not r["ok"] and r["code"] == "mismatch", "approval for a different amount is refused")
    r = approve(c, inv_id, who="accounting")
    check(not r["ok"] and r["code"] == "invalid_approver", "an agent cannot be the approver")
    check(balance(c) == 3400.0 and c.execute("SELECT count(*) FROM payments").fetchone()[0] == 0,
          "refused approvals moved no cash and recorded no payment")

    r = approve(c, inv_id)
    check(r["ok"] and r["outcome"] == "executed" and r["balance_after"] == 2560.0,
          "approved invoice payment executes: 3400 -> 2560")
    inv = c.execute("SELECT status FROM invoices WHERE id=501").fetchone()["status"]
    pay = c.execute("SELECT kind, ref_id, amount, approved_by FROM payments").fetchone()
    check(inv == "paid" and tuple(pay) == ("invoice", 501, 840.0, "Celia (operator)"),
          "invoice marked paid and payment recorded with the approver")
    r = approve(c, inv_id)
    check(not r["ok"] and r["code"] == "not_pending" and balance(c) == 2560.0,
          "duplicate approval is refused; no second payment")

    r = approve(c, po_id)
    check(r["ok"] and r["outcome"] == "approved" and balance(c) == 2560.0,
          "purchase order approved after the invoice is paid, without moving cash")
    status = c.execute("SELECT status FROM tickets WHERE id=101").fetchone()[0]
    check(status == "resolved" and r["resolved_ticket_ids"] == [101],
          "ticket 101 resolved once every proposal from its latest run is done")

    out = ops.record_run_outcome(c, NOW, "run-b", 102, "awaiting_human_approval", [
        {"kind": "pay_rent", "ref_id": 1, "amount": 2400.0, "description": "rent"}])
    rent_id = out["created_proposal_ids"][0]
    again = ops.record_run_outcome(c, NOW, "run-c", 102, "awaiting_human_approval", [
        {"kind": "pay_rent", "ref_id": 1, "amount": 2400.0, "description": "rent again"}])
    check(again["kept_proposal_ids"] == [rent_id] and not again["created_proposal_ids"],
          "an identical proposal from a later run keeps its id (no duplicate)")
    r = approve(c, rent_id)
    lease = c.execute("SELECT next_due FROM leases WHERE id=1").fetchone()[0]
    check(r["ok"] and r["balance_after"] == 160.0 and lease == "2026-10-02",
          "rent paid: 2560 -> 160, next due moves to 2026-10-02")

    # A payment larger than the balance is refused and changes nothing.
    c.execute("INSERT INTO invoices (id, vendor_id, amount, due_date, status, description) "
              "VALUES (777, 2, 500.0, '2026-09-10', 'open', 'test invoice')")
    out = ops.record_run_outcome(c, NOW, "run-d", 103, "awaiting_human_approval", [
        {"kind": "pay_invoice", "ref_id": 777, "amount": 500.0, "description": "big"}])
    big = out["created_proposal_ids"][0]
    r = approve(c, big)
    payments = c.execute("SELECT count(*) FROM payments").fetchone()[0]
    st = c.execute("SELECT status FROM invoices WHERE id=777").fetchone()[0]
    check(not r["ok"] and r["code"] == "insufficient_funds" and balance(c) == 160.0
          and payments == 2 and st == "open",
          "insufficient cash: refused, balance unchanged, invoice still open")
    refused = c.execute("SELECT count(*) FROM approvals WHERE outcome='refused'").fetchone()[0]
    check(refused >= 4, "refused attempts are recorded in approvals")

    try:
        c.execute("UPDATE cash_accounts SET balance = -1 WHERE name='checking'")
        check(False, "negative balance must be refused")
    except sqlite3.IntegrityError:
        check(balance(c) == 160.0, "database trigger refuses a negative balance")

    out = ops.record_run_outcome(c, NOW, "run-e", 103, "escalated", [])
    st = c.execute("SELECT status FROM action_proposals WHERE id=?", (big,)).fetchone()[0]
    check(st == "superseded", "pending proposals a newer run did not repeat are superseded")

    # Concurrency: two approvals of one proposal, and two payments that together
    # exceed cash, each from its own connection at the same moment.
    path2 = fresh_db()
    c2 = conn_for(path2)
    out = ops.record_run_outcome(c2, NOW, "run-x", 102, "awaiting_human_approval", [
        {"kind": "pay_rent", "ref_id": 1, "amount": 2400.0, "description": "rent"}])
    rid = out["created_proposal_ids"][0]
    c2.execute("INSERT INTO invoices (id, vendor_id, amount, due_date, status, description) "
               "VALUES (778, 2, 1500.0, '2026-09-10', 'open', 'test invoice')")
    out = ops.record_run_outcome(c2, NOW, "run-y", 103, "awaiting_human_approval", [
        {"kind": "pay_invoice", "ref_id": 778, "amount": 1500.0, "description": "big"}])
    iid = out["created_proposal_ids"][0]

    results = []
    barrier = threading.Barrier(3)

    def worker(pid, amount, payee):
        own = conn_for(path2)
        barrier.wait()
        results.append(ops.approve_proposal(own, TODAY, NOW, pid, "Operator", amount, payee))
        own.close()

    threads = [threading.Thread(target=worker, args=(rid, 2400.0, "Elm City Properties")),
               threading.Thread(target=worker, args=(rid, 2400.0, "Elm City Properties")),
               threading.Thread(target=worker, args=(iid, 1500.0, "Elm City Gifts"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = [r for r in results if r["ok"]]
    final = balance(c2)
    paid_total = c2.execute("SELECT coalesce(sum(amount),0) FROM payments").fetchone()[0]
    check(len(ok) == 1 and final >= 0 and abs(3400.0 - paid_total - final) < 0.005,
          f"3 simultaneous approvals: exactly 1 payment ran, balance {final:.2f} never negative")

    # Discounts: a price decision for the requester; no cash moves.
    path3 = fresh_db()
    c3 = conn_for(path3)
    out = ops.record_run_outcome(c3, NOW, "run-q", 103, "awaiting_human_approval", [
        {"kind": "offer_discount", "ref_id": 103, "sku": "CC-HOOD-NAVY", "quantity": 20,
         "discount_pct": 10, "description": "10% bulk discount"},
        {"kind": "offer_discount", "ref_id": 103, "sku": "CC-HOOD-NAVY", "quantity": 20,
         "discount_pct": 65, "description": "too deep"},
        {"kind": "purchase_order", "ref_id": 1, "sku": "CC-HOOD-NAVY", "size": "M",
         "quantity": 12, "description": "restock 12"},
    ])
    disc_id, po12 = out["created_proposal_ids"]
    check(len(out["skipped"]) == 1 and "below" in out["skipped"][0]["reason"],
          "a discount at or below unit cost is not recorded")
    d = c3.execute("SELECT amount, payee, discount_pct FROM action_proposals WHERE id=?",
                   (disc_id,)).fetchone()
    check(tuple(d) == (116.0, "Yale AI Club", 10.0),
          "discount value ($5.80 x 20) and requester come from the database")
    r = ops.decline_proposal(c3, NOW, po12, "boss", "x")
    check(not r["ok"] and r["code"] == "invalid_approver", "an agent cannot decline")
    r = ops.decline_proposal(c3, NOW, po12, "Operator", "cannot fund the restock yet")
    check(r["ok"] and c3.execute("SELECT status FROM action_proposals WHERE id=?", (po12,)).fetchone()[0]
          == "declined" and balance(c3) == 3400.0, "a human decline is recorded; nothing moves")
    r = ops.decline_proposal(c3, NOW, po12, "Operator", "again")
    check(not r["ok"] and r["code"] == "not_pending", "a decided proposal cannot be declined again")
    r = approve(c3, disc_id)
    check(r["ok"] and r["outcome"] == "approved" and balance(c3) == 3400.0
          and r["resolved_ticket_ids"] == [103],
          "approved discount moves no cash; ticket resolves once every proposal is decided")

    original = sqlite3.connect((ROOT / "data" / "campus_customs.db").as_uri() + "?mode=ro", uri=True)
    tables = {r[0] for r in original.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    check("action_proposals" not in tables and
          original.execute("SELECT balance FROM cash_accounts").fetchone()[0] == 3400.0,
          "original database untouched")
    print(f"\n{PASSED} checks passed")


if __name__ == "__main__":
    main()
