"""Offline checks of the safeguards — no model calls, no database writes.

Run from the Homework 5 folder:  .venv/bin/python tests/test_offline.py
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PORTKEY_API_KEY", "test-key-not-used-0000")

from backend.audit import AuditError, AuditLog, EventType  # noqa: E402
from backend.deps import AgentDeps  # noqa: E402
from backend.guards import FactLedger, apply_action_rules, output_problems  # noqa: E402
from backend.models import (  # noqa: E402
    ActionStatus, ActionType, AgentName, DbTable, Evidence, Finding, ProposedAction, RecordRef,
    SpecialistReport, TaskOutcome, TicketContext,
)
from backend.workflow import TicketWorkflow  # noqa: E402

PASSED = 0


def check(cond: bool, label: str) -> None:
    global PASSED
    if not cond:
        raise AssertionError(label)
    PASSED += 1
    print("ok  ", label)


def ledger_from_db_shape() -> FactLedger:
    """Feed the ledger tool results shaped exactly like the MCP server's output."""
    led = FactLedger()
    led.ingest("check_vendor_eligibility", {"found": True, "shop_date": "2026-08-31", "vendors": [
        {"vendor_id": 1, "eligible_to_ship": False, "eligibility_reason": "Open unpaid invoice(s): 501",
         "invoices": [{"invoice_id": 501, "amount": 840.0, "status": "open", "payments_recorded": []}]},
        {"vendor_id": 2, "eligible_to_ship": True, "eligibility_reason": "No open invoices.", "invoices": []}]})
    led.ingest("get_cash_and_obligations", {"found": True, "shop_date": "2026-08-31", "database": {
        "cash_account": {"name": "checking", "balance": 3400.0, "date": "2026-08-31"},
        "open_invoices": [{"invoice_id": 501, "vendor_id": 1, "amount": 840.0, "status": "open"}],
        "next_rent_by_lease": [{"lease_id": 1, "monthly_rent": 2400.0}], "recent_payments": []}})
    return led


def test_tool_access() -> None:
    from backend.deps import ALLOWED_TOOLS
    backend_only = {"record_run_outcome", "approve_proposal", "decline_proposal", "list_tickets",
                    "list_action_proposals"}
    check(all(not (tools & backend_only) for tools in ALLOWED_TOOLS.values()),
          "no agent can reach the backend-only MCP tools (approvals, payments, run records)")


def test_models() -> None:
    try:
        ProposedAction(action_type=ActionType.PAY_INVOICE, description="pay")
        check(False, "payment without amount must fail")
    except ValueError:
        check(True, "payment action requires target, amount and payee")
    a = ProposedAction(action_type=ActionType.OFFER_DISCOUNT, description="10% off",
                       target=RecordRef(table=DbTable.PRICING, id="CC-HOOD-NAVY"),
                       discount_pct=10, requires_human_approval=False)
    check(a.requires_human_approval, "an agent cannot waive human approval")


def test_guards() -> None:
    led = ledger_from_db_shape()
    fake = SpecialistReport(outcome=TaskOutcome.COMPLETED, summary="s", next_step="n", findings=[
        Finding(summary="x", evidence=[Evidence(record=RecordRef(table=DbTable.INVOICES, id="999"),
                                                fact="made up")])])
    check(bool(output_problems(fake, led)), "evidence citing an unseen record is rejected")

    wrong = SpecialistReport(outcome=TaskOutcome.COMPLETED, summary="s", next_step="n",
                             recommended_actions=[ProposedAction(
                                 action_type=ActionType.PAY_INVOICE, description="pay 501",
                                 target=RecordRef(table=DbTable.INVOICES, id="501"),
                                 amount=800.0, payee="Bulldog Print Co")])
    check(any("840.00" in p for p in output_problems(wrong, led)),
          "payment amount different from the database is rejected")

    po = ProposedAction(action_type=ActionType.DRAFT_PURCHASE_ORDER, description="reprint",
                        target=RecordRef(table=DbTable.VENDORS, id="1"), sku="CC-TEE-WHITE",
                        size="S", quantity=1)
    pay = ProposedAction(action_type=ActionType.PAY_INVOICE, description="pay 501",
                         target=RecordRef(table=DbTable.INVOICES, id="501"), amount=840.0,
                         payee="Bulldog Print Co")
    big = ProposedAction(action_type=ActionType.PAY_RENT, description="rent",
                         target=RecordRef(table=DbTable.LEASES, id="1"), amount=2400.0,
                         payee="Elm City Properties")
    actions, notes = apply_action_rules([po, pay, pay, big], led)
    check(actions[0].status is ActionStatus.BLOCKED, "purchase order to a vendor with an open invoice is blocked")
    check(len(actions) == 3, "duplicate payment proposal is dropped")
    check(actions[1].status is ActionStatus.NEEDS_HUMAN_APPROVAL, "payment waits for human approval")

    from backend.guards import draft_problems
    from backend.models import CustomerMessageDraft, CustomerServiceReport
    def cs(body):
        return CustomerServiceReport(outcome=TaskOutcome.COMPLETED, summary="s", next_step="n",
                                     draft=CustomerMessageDraft(to="Club", subject="Re", body=body))
    check(bool(draft_problems(cs("We are reviewing a 10% discount ($52.20 each)."))),
          "customer draft quoting an unapproved discount is rejected")
    check(bool(draft_problems(cs("Our vendor has an unpaid invoice."))),
          "customer draft revealing internal finances is rejected")
    check(not draft_problems(cs("Your discount request is under review; 8 are in stock now.")),
          "a compliant draft passes")

    led.pricing["CC-HOOD-NAVY"] = (22.0, 58.0)
    led.refs.add(("pricing", "CC-HOOD-NAVY"))
    def disc(pct):
        return SpecialistReport(outcome=TaskOutcome.COMPLETED, summary="s", next_step="n",
                                recommended_actions=[ProposedAction(
                                    action_type=ActionType.OFFER_DISCOUNT, description="d",
                                    target=RecordRef(table=DbTable.PRICING, id="CC-HOOD-NAVY"),
                                    discount_pct=pct)])
    check(bool(output_problems(disc(65), led)), "discount pricing below unit cost is rejected")
    check(not output_problems(disc(10), led), "discount above cost passes")

    unchecked = ProposedAction(action_type=ActionType.DRAFT_PURCHASE_ORDER, description="x",
                               target=RecordRef(table=DbTable.VENDORS, id="3"), sku="X", quantity=1)
    actions, _ = apply_action_rules([unchecked], led)
    check(actions[0].status is ActionStatus.BLOCKED, "vendor not re-checked in this run is blocked")

    led.cash_balance["checking"] = 1000.0
    actions, notes = apply_action_rules([pay, big], led)
    check(actions[1].status is ActionStatus.BLOCKED, "payment above the cash balance is blocked")


def test_delegation_rules() -> None:
    audit = AuditLog(Path(tempfile.mkdtemp()) / "audit.json")
    wf = TicketWorkflow("test", 101, audit)
    wf.ticket = TicketContext(ticket_id=101, type="customer_order", requester="R", subject="s",
                              status="open", created_at="2026-08-31T09:15:00-04:00")
    calls = []

    async def fake_run_agent(name, request, chain, depth):
        calls.append(name)
        return SpecialistReport(outcome=TaskOutcome.COMPLETED, summary="done", next_step="n")
    wf.run_agent = fake_run_agent

    def deps(*chain: AgentName) -> AgentDeps:
        return AgentDeps(workflow=wf, agent=chain[-1], depth=len(chain) - 1, chain=chain, trace_id="t")

    run = asyncio.run
    r = run(wf.delegate(deps(AgentName.BOSS), AgentName.INVENTORY, "check stock", "why", ""))
    check(r.status == "completed" and calls == [AgentName.INVENTORY], "delegation runs the target agent")
    r = run(wf.delegate(deps(AgentName.BOSS), AgentName.INVENTORY, "Check  stock", "again", ""))
    check(r.status == "cached" and len(calls) == 1, "repeated task returns cached result, no re-run")
    r = run(wf.delegate(deps(AgentName.INVENTORY), AgentName.FACILITIES, "x", "y", ""))
    check(r.status == "refused" and "not permitted" in r.error, "delegation outside the graph is refused")
    r = run(wf.delegate(deps(AgentName.BOSS, AgentName.CUSTOMER_SERVICE, AgentName.INVENTORY),
                        AgentName.ACCOUNTING, "y", "z", ""))
    check(r.status == "completed", "depth 3 chain Boss→CS→Inventory→Accounting is allowed")
    wf.limits = type(wf.limits)(**{**wf.limits.__dict__, "max_delegation_depth": 2})
    r = run(wf.delegate(deps(AgentName.BOSS, AgentName.CUSTOMER_SERVICE, AgentName.INVENTORY),
                        AgentName.ACCOUNTING, "new task", "z", ""))
    check(r.status == "refused" and "max_delegation_depth" in r.error, "depth limit is enforced")
    # A cycle cannot be built from the allowed graph; test the guard directly.
    wf.limits = type(wf.limits)(**{**wf.limits.__dict__, "max_delegation_depth": 9})
    import backend.workflow as wmod
    saved = wmod.ALLOWED_DELEGATIONS[AgentName.ACCOUNTING]
    wmod.ALLOWED_DELEGATIONS[AgentName.ACCOUNTING] = frozenset({AgentName.INVENTORY})
    try:
        r = run(wf.delegate(deps(AgentName.BOSS, AgentName.INVENTORY, AgentName.ACCOUNTING),
                            AgentName.INVENTORY, "loop", "z", ""))
        check(r.status == "refused" and "circular" in r.error, "circular delegation is refused")
    finally:
        wmod.ALLOWED_DELEGATIONS[AgentName.ACCOUNTING] = saved
    wf.calls_total = wf.limits.max_agent_calls_per_ticket
    r = run(wf.delegate(deps(AgentName.BOSS), AgentName.FACILITIES, "rent", "z", ""))
    check(r.status == "refused" and wf.stop_reason and "max_agent_calls" in wf.stop_reason,
          "agent-call limit stops the workflow with a recorded reason")
    events = audit.read()
    check(any(e["event_type"] == "limit_reached" for e in events), "limit is written to the audit trail")


def _append_many(path: str, n: int) -> None:
    log = AuditLog(Path(path))
    for i in range(n):
        log.append(EventType.MCP_TOOL_CALL, run_id=f"p{os.getpid()}", ticket_id=1, tool_name="x",
                   retry_attempt=i)


def test_audit() -> None:
    path = Path(tempfile.mkdtemp()) / "audit.json"
    procs = [multiprocessing.Process(target=_append_many, args=(str(path), 25)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    events = json.loads(path.read_text())
    check(len(events) == 100, "4 processes x 25 concurrent appends: all 100 events kept, file valid JSON")
    check(all(list(e) == list(events[0]) for e in events), "every event has the same schema")

    log = AuditLog(path)
    e = log.append(EventType.AGENT_FAILED, run_id="r", error="key=" + os.environ["PORTKEY_API_KEY"],
                   tool_args={"api_key": "abc12345", "sku": "X"}, usage={"input_tokens": 5})
    check("test-key-not-used" not in json.dumps(e), "secret values are redacted")
    check(e["tool_args"]["api_key"] == "[REDACTED]" and e["usage"]["input_tokens"] == 5,
          "credential fields redacted, token counts kept")
    check(len(log.append(EventType.AGENT_STARTED, run_id="r", task="x" * 5000)["task"]) < 500,
          "long text is truncated")
    try:
        log.append(EventType.AGENT_STARTED, run_id="r", not_a_field=1)
        check(False, "unknown field must fail")
    except AuditError:
        check(True, "unknown audit fields are rejected (consistent schema)")

    path.write_text('[{"partial": ')
    try:
        log.append(EventType.AGENT_STARTED, run_id="r")
        check(False, "corrupt file must not be overwritten")
    except AuditError:
        check(path.read_text() == '[{"partial": ', "a corrupt audit file is never overwritten")


if __name__ == "__main__":
    test_tool_access()
    test_models()
    test_guards()
    test_delegation_rules()
    test_audit()
    print(f"\n{PASSED} checks passed")
