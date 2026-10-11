"""Entry point for running the agent team on tickets.

    python -m backend.orchestrator --ticket 101
    python -m backend.orchestrator --all          # every open ticket, one at a time

Each run appends its events to output/audit_trail.json and prints the
TicketRunResult as JSON. Nothing is paid, sent or ordered: the result lists
what a human must approve.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import datetime, timezone

from .audit import AuditLog, EventType
from .config import LIMITS, MODEL_ID, Limits
from .guards import approvals_for
from .mcp_client import MCP_TOOLSET, call_tool_direct
from .models import (
    ActionType, AgentName, BossDecision, CustomerServiceReport, TaskRequest, TicketContext, TicketRunResult, UsageTotals,
    WorkflowStatus,
)
from .workflow import TicketWorkflow, _clip

BOSS_TASK = ("Triage this ticket: identify the problem, urgency, relevant records and expected "
             "outcome; assign the specialists it needs; review their findings; and return your "
             "decision with every action that needs human approval.")


async def run_ticket(ticket_id: int, *, run_id: str | None = None, audit: AuditLog | None = None,
                     limits: Limits = LIMITS) -> TicketRunResult:
    audit = audit or AuditLog()
    run_id = run_id or uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc)
    wf = TicketWorkflow(run_id, ticket_id, audit, limits)
    wf.audit_event(EventType.RUN_STARTED, None, model=MODEL_ID,
                   reason=f"limits: {limits.max_agent_calls_per_ticket} agent calls, depth "
                          f"{limits.max_delegation_depth}, {limits.ticket_timeout_s:.0f}s")
    try:
        async with MCP_TOOLSET:
            details = await call_tool_direct(wf, "get_ticket_details", {"ticket_id": ticket_id})
            if not details.get("found"):
                wf.transition(WorkflowStatus.FAILED, details.get("message", "ticket not found"))
                return _result(wf, None, started_at, WorkflowStatus.FAILED, details.get("message"))
            row = dict(details["database"]["ticket"])
            if row.get("notes"):
                row["notes"] = _clip(row["notes"], limits.max_ticket_notes_chars)
            wf.ticket = TicketContext(**row)
            wf.shop_date = details["shop_date"]
            wf.audit_event(EventType.TICKET_LOADED, None, task=wf.ticket.subject,
                           record_ids=sorted(f"{t}:{i}" for t, i in wf.ledger.refs))
            if wf.ticket.status.lower() != "open":
                reason = f"ticket status is '{wf.ticket.status}', not open"
                return _result(wf, None, started_at, WorkflowStatus.RESOLVED, reason)

            wf.transition(WorkflowStatus.IN_PROGRESS, "assigned to the Boss")
            request = TaskRequest(ticket=wf.ticket, shop_date=wf.shop_date,
                                  requested_by="operator", task=BOSS_TASK,
                                  reason="new open ticket")
            decision = await wf.run_agent(AgentName.BOSS, request, (), 0)

            status, reason = wf.final_status(decision)
            if decision is not None and status.value != decision.proposed_status.value:
                wf.audit_event(EventType.GUARDRAIL_APPLIED, None,
                               reason=f"Boss proposed {decision.proposed_status.value}; backend "
                                      f"set {status.value} ({reason})")
            wf.transition(status, reason or "")
            recorded, recording_error = await _record_outcome(wf, decision, status)
    except Exception as e:
        wf.audit_event(EventType.RUN_FAILED, None, error=f"{type(e).__name__}: {e}",
                       stop_reason="run aborted")
        wf.transition(WorkflowStatus.FAILED, f"{type(e).__name__}")
        raise
    return _result(wf, decision, started_at, status, reason, recorded, recording_error)


def _proposals_from(decision: BossDecision | None) -> list[dict]:
    """The Boss's payment and purchase actions, in the shape record_run_outcome takes."""
    kinds = {ActionType.PAY_INVOICE: "pay_invoice", ActionType.PAY_RENT: "pay_rent",
             ActionType.DRAFT_PURCHASE_ORDER: "purchase_order"}
    out = []
    for a in decision.actions if decision else []:
        if a.action_type in kinds and a.target is not None:
            out.append({"kind": kinds[a.action_type], "ref_id": int(a.target.id),
                        "amount": a.amount, "payee": a.payee, "sku": a.sku, "size": a.size,
                        "quantity": a.quantity, "description": a.description,
                        "blocked_reason": a.blocked_reason})
        elif a.action_type is ActionType.OFFER_DISCOUNT and a.discount_pct is not None:
            # A discount is decided for this ticket's requester; the MCP tool checks the
            # price against pricing and computes the dollar value itself.
            sku = a.sku or (a.target.id if a.target is not None else None)
            out.append({"kind": "offer_discount", "ref_id": decision.ticket_id, "sku": sku,
                        "size": a.size, "quantity": a.quantity, "discount_pct": a.discount_pct,
                        "description": a.description, "blocked_reason": a.blocked_reason})
    return out


async def _record_outcome(wf: TicketWorkflow, decision: BossDecision | None,
                          status: WorkflowStatus) -> tuple[dict | None, str | None]:
    """Persist the run's status and proposals through the MCP server. A failure is
    logged and returned, never hidden."""
    proposals = _proposals_from(decision)
    try:
        recorded = await MCP_TOOLSET.direct_call_tool("record_run_outcome", {
            "run_id": wf.run_id, "ticket_id": wf.ticket_id, "run_status": status.value,
            "proposals": proposals})
        recorded = json.loads(recorded) if isinstance(recorded, str) else recorded
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        wf.audit_event(EventType.PROPOSALS_RECORDED, None, tool_name="record_run_outcome",
                       tool_outcome="error", error=error)
        return None, error
    wf.audit_event(
        EventType.PROPOSALS_RECORDED, None, tool_name="record_run_outcome",
        tool_args={"run_status": status.value, "proposals": len(proposals)},
        tool_outcome=("ticket resolved" if recorded["ticket_resolved"] else "ok"),
        record_ids=[f"action_proposals:{i}" for i in
                    recorded["created_proposal_ids"] + recorded["kept_proposal_ids"]],
        reason=(f"skipped: {recorded['skipped']}" if recorded["skipped"] else None))
    return recorded, None


def _result(wf: TicketWorkflow, decision, started_at, status, reason, recorded=None,
            recording_error=None) -> TicketRunResult:
    blockers = list(dict.fromkeys(
        (decision.blockers if decision else [])
        + [b for r in wf.specialist_results for b in r.report.blockers]
        + [n for n in wf.guardrail_notes if "a human must choose" in n]))
    drafts = [r.report.draft for r in wf.specialist_results
              if isinstance(r.report, CustomerServiceReport) and r.report.draft]
    result = TicketRunResult(
        run_id=wf.run_id, ticket_id=wf.ticket_id, status=status, stop_reason=reason,
        decision=decision, approvals_required=approvals_for(decision.actions) if decision else [],
        blockers=blockers, customer_drafts=drafts, specialist_reports=wf.specialist_results,
        agent_runs=wf.agent_runs, recorded_proposals=recorded, recording_error=recording_error,
        usage=UsageTotals(requests=wf.usage.requests, tool_calls=wf.usage.tool_calls,
                          input_tokens=wf.usage.input_tokens, output_tokens=wf.usage.output_tokens),
        started_at=started_at, finished_at=datetime.now(timezone.utc),
    )
    wf.audit_event(EventType.RUN_COMPLETED, None, state_to=status.value, stop_reason=reason,
                   recommendation=[f"{a.action_type.value} [{a.status.value}]"
                                   for a in result.approvals_required],
                   error=recording_error, usage=result.usage.model_dump())
    return result


async def open_ticket_ids() -> list[int]:
    async with MCP_TOOLSET:
        data = await MCP_TOOLSET.direct_call_tool("list_open_tickets", {})
    data = json.loads(data) if isinstance(data, str) else data
    return [t["ticket_id"] for t in data["tickets"]]


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticket", type=int, help="ticket id to run")
    group.add_argument("--all", action="store_true", help="run every open ticket")
    args = parser.parse_args()
    ids = await open_ticket_ids() if args.all else [args.ticket]
    for tid in ids:
        result = await run_ticket(tid)
        print(result.model_dump_json(indent=2, exclude_none=True))


if __name__ == "__main__":
    asyncio.run(_main())
