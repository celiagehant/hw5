"""Operations service behind the FastAPI routes.

Keeps the business rules out of the route handlers:
- Agent runs execute in the background through the existing orchestrator,
  one active run per ticket.
- Approvals go to the MCP server's backend-only approve_proposal tool, which
  re-checks everything inside one database transaction.
- A reset is refused while any run or approval is in progress.
All shop data is read through the MCP server; events come from the audit trail.

Active-run tracking and finished run results live in memory. Restarting the
server forgets them (and abandons a run in progress), but nothing durable is
lost: events stay in output/audit_trail.json, and ticket status, proposals,
approvals and payments are in the working database. Run uvicorn with a single
worker so that the in-memory guards see every request.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from .audit import AuditLog, EventType
from .db_reset import restore_working_db
from .mcp_client import MCP_TOOLSET
from .models import TicketRunResult
from .orchestrator import run_ticket

MAX_KEPT_RUNS = 50


class ServiceError(Exception):
    status_code = 500

    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


class BadRequest(ServiceError):
    status_code = 400


class NotFound(ServiceError):
    status_code = 404


class Conflict(ServiceError):
    status_code = 409


class Upstream(ServiceError):
    status_code = 502


# Approval refusals from the MCP tool, mapped to HTTP status codes.
_APPROVAL_STATUS = {"not_found": NotFound, "invalid_approver": BadRequest}


@dataclass
class RunRecord:
    run_id: str
    ticket_id: int
    state: Literal["running", "completed", "failed"] = "running"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    result: TicketRunResult | None = None
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    def summary(self, include_result: bool = False) -> dict:
        out = {"run_id": self.run_id, "ticket_id": self.ticket_id, "state": self.state,
               "started_at": self.started_at.isoformat(),
               "finished_at": self.finished_at.isoformat() if self.finished_at else None,
               "workflow_status": self.result.status.value if self.result else None,
               "stop_reason": self.result.stop_reason if self.result else None,
               "error": self.error}
        if include_result and self.result is not None:
            out["result"] = self.result.model_dump(mode="json", exclude_none=True)
        return out


class OperationsService:
    def __init__(self, audit: AuditLog | None = None):
        self.audit = audit or AuditLog()
        self.runs: dict[str, RunRecord] = {}
        self.active: dict[int, str] = {}          # ticket_id -> run_id
        self.approvals_in_progress = 0
        self.resetting = False
        self._gate = asyncio.Lock()

    async def _mcp(self, tool: str, args: dict) -> dict:
        try:
            data = await MCP_TOOLSET.direct_call_tool(tool, args)
        except Exception as e:
            raise Upstream("mcp_error", f"MCP tool {tool} failed: {e}") from e
        return json.loads(data) if isinstance(data, str) else data

    # --- A. tickets ------------------------------------------------------------------

    async def list_tickets(self) -> dict:
        data = await self._mcp("list_tickets", {"status": "all"})
        tickets = []
        for t in data["tickets"]:
            run_id = self.active.get(t["ticket_id"])
            tickets.append({**t, "status": t["status"].lower(),
                            "active_run": self.runs[run_id].summary() if run_id else None})
        return {"shop_date": data["shop_date"], "count": len(tickets), "tickets": tickets}

    async def ticket(self, ticket_id: int) -> dict:
        data = await self._mcp("get_ticket_details", {"ticket_id": ticket_id})
        if not data.get("found"):
            raise NotFound("ticket_not_found", data.get("message", f"No ticket {ticket_id}."),
                           known_ticket_ids=data.get("known_ticket_ids"))
        return data

    # --- B. runs ---------------------------------------------------------------------

    async def start_run(self, ticket_id: int) -> RunRecord:
        async with self._gate:
            if self.resetting:
                raise Conflict("reset_in_progress", "The database is being reset; try again shortly.")
            if ticket_id in self.active:
                raise Conflict("run_already_active",
                               f"Ticket {ticket_id} already has a run in progress.",
                               run_id=self.active[ticket_id])
            details = await self.ticket(ticket_id)
            status = details["database"]["ticket"]["status"].lower()
            if status != "open":
                raise Conflict("ticket_not_open", f"Ticket {ticket_id} is {status}; reset the "
                               "database to run it again.")
            record = RunRecord(run_id=uuid.uuid4().hex[:12], ticket_id=ticket_id)
            self.runs[record.run_id] = record
            self.active[ticket_id] = record.run_id
            record.task = asyncio.create_task(self._execute(record))
            self._trim_runs()
        return record

    async def _execute(self, record: RunRecord) -> None:
        try:
            record.result = await run_ticket(record.ticket_id, run_id=record.run_id,
                                             audit=self.audit)
            record.state = "completed"
        except Exception as e:
            record.state = "failed"
            record.error = f"{type(e).__name__}: {e}"
            self.audit.append(EventType.RUN_FAILED, run_id=record.run_id,
                              ticket_id=record.ticket_id, error=record.error,
                              stop_reason="background run ended with an error")
        finally:
            record.finished_at = datetime.now(timezone.utc)
            self.active.pop(record.ticket_id, None)

    def _trim_runs(self) -> None:
        finished = [r for r in self.runs.values() if r.state != "running"]
        for r in sorted(finished, key=lambda r: r.started_at)[: max(0, len(self.runs) - MAX_KEPT_RUNS)]:
            del self.runs[r.run_id]

    def get_run(self, run_id: str) -> dict:
        record = self.runs.get(run_id)
        if record is None:
            raise NotFound("run_not_found", f"No run {run_id} in this server session. Its "
                           "events remain in the audit trail.")
        return record.summary(include_result=True)

    def list_runs(self) -> list[dict]:
        return [r.summary() for r in sorted(self.runs.values(), key=lambda r: r.started_at,
                                            reverse=True)]

    # --- C. events --------------------------------------------------------------------

    def events(self, *, ticket_id: int | None, run_id: str | None, after: str | None,
               limit: int) -> dict:
        events = self.audit.read()
        if after:
            ids = [e["event_id"] for e in events]
            if after not in ids:
                raise NotFound("event_not_found", f"No event {after}.")
            events = events[ids.index(after) + 1:]
        if ticket_id is not None:
            events = [e for e in events if e["ticket_id"] == ticket_id]
        if run_id is not None:
            events = [e for e in events if e["run_id"] == run_id]
        total = len(events)
        events = events[:limit] if after else events[-limit:]
        shaped = [dashboard_event(e) for e in events]
        return {"count": len(shaped), "total_matching": total,
                "next_after": shaped[-1]["event_id"] if shaped else after, "events": shaped}

    # --- D. approvals -----------------------------------------------------------------

    async def proposals(self, ticket_id: int | None, status: str | None) -> dict:
        args = {k: v for k, v in {"ticket_id": ticket_id, "status": status}.items() if v is not None}
        return await self._mcp("list_action_proposals", args)

    async def approve(self, proposal_id: int, approved_by: str, confirm_amount: float,
                      confirm_payee: str) -> dict:
        async with self._gate:
            if self.resetting:
                raise Conflict("reset_in_progress", "The database is being reset; nothing was approved.")
            self.approvals_in_progress += 1
        try:
            result = await self._mcp("approve_proposal", {
                "proposal_id": proposal_id, "approved_by": approved_by,
                "confirm_amount": confirm_amount, "confirm_payee": confirm_payee})
        finally:
            async with self._gate:
                self.approvals_in_progress -= 1

        args = {"proposal_id": proposal_id, "approved_by": approved_by,
                "confirm_amount": confirm_amount, "confirm_payee": confirm_payee}
        if result.get("ok"):
            refs = [f"action_proposals:{proposal_id}", f"{result['ref_table']}:{result['ref_id']}"]
            if result.get("payment_id"):
                refs.append(f"payments:{result['payment_id']}")
            self.audit.append(
                EventType.PAYMENT_EXECUTED if result["outcome"] == "executed"
                else EventType.DISCOUNT_APPROVED if result["kind"] == "offer_discount"
                else EventType.PURCHASE_APPROVED,
                run_id=result["run_id"], ticket_id=result["ticket_id"], agent="human_operator",
                task=f"Approve proposal {proposal_id}: {result['kind']} ${result['amount']:,.2f} "
                     f"to {result['payee']}",
                tool_name="approve_proposal", tool_args=args, tool_outcome=result["message"],
                record_ids=refs,
                state_to=("resolved" if result["ticket_id"] in result["resolved_ticket_ids"]
                          else None),
                stop_reason=f"checking ${result['balance_before']:,.2f} -> "
                            f"${result['balance_after']:,.2f}")
            return result
        self.audit.append(
            EventType.APPROVAL_REFUSED, run_id=f"approval-{proposal_id}",
            ticket_id=result.get("ticket_id"), agent="human_operator",
            task=f"Approve proposal {proposal_id}", tool_name="approve_proposal", tool_args=args,
            tool_outcome="refused", stop_reason=result["code"], error=result["message"])
        cls = _APPROVAL_STATUS.get(result["code"], Conflict)
        raise cls(result["code"], result["message"], balance=result.get("balance"),
                  proposal_id=proposal_id)

    async def decline(self, proposal_id: int, declined_by: str, reason: str) -> dict:
        async with self._gate:
            if self.resetting:
                raise Conflict("reset_in_progress", "The database is being reset; nothing was declined.")
            self.approvals_in_progress += 1
        try:
            result = await self._mcp("decline_proposal", {
                "proposal_id": proposal_id, "declined_by": declined_by, "reason": reason})
        finally:
            async with self._gate:
                self.approvals_in_progress -= 1
        args = {"proposal_id": proposal_id, "declined_by": declined_by, "reason": reason}
        if result.get("ok"):
            self.audit.append(
                EventType.PROPOSAL_DECLINED, run_id=result["run_id"], ticket_id=result["ticket_id"],
                agent="human_operator",
                task=f"Decline proposal {proposal_id}: {result['kind']} ${result['amount']:,.2f} "
                     f"to {result['payee']}",
                tool_name="decline_proposal", tool_args=args, tool_outcome=result["message"],
                record_ids=[f"action_proposals:{proposal_id}"],
                state_to=("resolved" if result["ticket_id"] in result["resolved_ticket_ids"]
                          else None),
                stop_reason="declined by a human; nothing paid, ordered or sent")
            return result
        self.audit.append(
            EventType.APPROVAL_REFUSED, run_id=f"approval-{proposal_id}",
            ticket_id=result.get("ticket_id"), agent="human_operator",
            task=f"Decline proposal {proposal_id}", tool_name="decline_proposal", tool_args=args,
            tool_outcome="refused", stop_reason=result["code"], error=result["message"])
        cls = _APPROVAL_STATUS.get(result["code"], Conflict)
        raise cls(result["code"], result["message"], proposal_id=proposal_id)

    # --- E. balance ---------------------------------------------------------------------

    async def checking_balance(self) -> dict:
        data = await self._mcp("get_cash_and_obligations", {"account": "checking"})
        if not data.get("found"):
            raise NotFound("account_not_found", data.get("message", "No checking account."),
                           known_accounts=data.get("known_accounts"))
        cash = data["database"]["cash_account"]
        if not isinstance(cash.get("balance"), (int, float)):
            raise ServiceError("balance_unavailable", "The checking balance could not be read.")
        return {"account": cash["name"], "balance": cash["balance"], "currency": "USD",
                "balance_date": cash["date"], "shop_date": data["shop_date"]}

    # --- F. reset -------------------------------------------------------------------------

    async def reset(self) -> dict:
        async with self._gate:
            if self.resetting:
                raise Conflict("reset_in_progress", "A reset is already running.")
            if self.active:
                raise Conflict("runs_active", "Agent runs are in progress; reset refused.",
                               active_runs=dict(self.active))
            if self.approvals_in_progress:
                raise Conflict("approvals_active", "An approval is being processed; reset refused.")
            self.resetting = True
        run_id = f"reset-{uuid.uuid4().hex[:8]}"
        try:
            report = await asyncio.to_thread(restore_working_db)
        except Exception as e:
            self.audit.append(EventType.DATABASE_RESET, run_id=run_id, agent="human_operator",
                              tool_outcome="failed", error=f"{type(e).__name__}: {e}")
            raise ServiceError("reset_failed", f"Reset failed: {e}") from e
        finally:
            self.resetting = False
        # Finished run results describe the pre-reset database; their events stay in the audit trail.
        self.runs = {k: r for k, r in self.runs.items() if r.state == "running"}
        self.audit.append(EventType.DATABASE_RESET, run_id=run_id, agent="human_operator",
                          task="Reset the working database to the original baseline",
                          tool_outcome="ok", state_to="baseline",
                          reason=f"restored from {report['restored_from']}; checking "
                                 f"${report['checking_balance']:,.2f}; tickets "
                                 f"{report['ticket_status']}")
        return report


# --- Event shaping for the dashboard -----------------------------------------------------

_CATEGORY = {
    "run_started": "run", "ticket_loaded": "run", "state_transition": "status",
    "agent_started": "agent_started", "agent_completed": "finding",
    "agent_retry": "error", "agent_failed": "error",
    "mcp_tool_call": "tool_call", "mcp_tool_error": "error",
    "delegation_requested": "delegation", "delegation_completed": "delegation",
    "delegation_refused": "delegation", "guardrail_applied": "guardrail",
    "limit_reached": "error", "run_completed": "completion", "run_failed": "error",
    "proposals_recorded": "completion", "payment_executed": "approval",
    "purchase_approved": "approval", "discount_approved": "approval",
    "proposal_declined": "approval", "approval_refused": "error", "database_reset": "reset",
}


def _join(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return "" if value is None else str(value)


def _describe(e: dict) -> str:
    t, agent = e["event_type"], e["agent"] or "orchestrator"
    if t == "run_started":
        return f"Run started ({e['model']}). {_join(e['reason'])}"
    if t == "ticket_loaded":
        return f"Loaded ticket: {_join(e['task'])}"
    if t == "state_transition":
        return f"Status {e['state_from']} → {e['state_to']}: {_join(e['reason'])}"
    if t == "agent_started":
        return f"{agent} started: {_join(e['task'])}"
    if t == "agent_completed":
        kind = "decided" if agent == "boss" else "reported"
        return f"{agent} {kind} ({e['tool_outcome']}): {_join(e['findings'])}"
    if t == "mcp_tool_call":
        return f"{agent} called {e['tool_name']} → {e['tool_outcome']}"
    if t == "delegation_requested":
        return f"{agent} → {e['delegation_target']}: {_join(e['task'])} (why: {_join(e['reason'])})"
    if t == "delegation_completed":
        return f"{e['delegation_target']} answered {agent}: {_join(e['delegation_result'])}"
    if t == "delegation_refused":
        return f"{agent} → {e['delegation_target']} refused: {_join(e['stop_reason'])}"
    if t in ("guardrail_applied", "limit_reached"):
        return f"{agent}: {_join(e['reason'] or e['error'] or e['stop_reason'])}"
    if t == "run_completed":
        return f"Run finished: {e['state_to']} ({_join(e['stop_reason'])})"
    if t == "proposals_recorded":
        return f"Recorded proposals: {_join(e['record_ids']) or 'none'} → {e['tool_outcome']}"
    if t in ("payment_executed", "purchase_approved", "discount_approved"):
        return f"Human approval: {_join(e['tool_outcome'])} ({_join(e['stop_reason'])})"
    if t == "proposal_declined":
        return f"Human decision: {_join(e['tool_outcome'])}"
    if t == "database_reset":
        return f"Database reset {e['tool_outcome']}: {_join(e['reason'] or e['error'])}"
    return _join(e["error"] or e["reason"] or e["task"]) or t


def dashboard_event(e: dict) -> dict:
    """A concise, dashboard-ready view of one audit event (already redacted at write time)."""
    tool = None
    if e["tool_name"]:
        tool = {"name": e["tool_name"], "args": e["tool_args"], "outcome": e["tool_outcome"],
                "record_ids": e["record_ids"]}
    return {
        "event_id": e["event_id"], "timestamp": e["timestamp"], "run_id": e["run_id"],
        "ticket_id": e["ticket_id"], "agent": e["agent"], "depth": e["depth"],
        "event_type": e["event_type"], "category": _CATEGORY.get(e["event_type"], "other"),
        "description": _describe(e), "delegation_target": e["delegation_target"],
        "tool": tool, "findings": e["findings"], "recommendation": e["recommendation"],
        "status": e["state_to"] or (e["tool_outcome"] if e["event_type"] == "agent_completed" else None),
        "stop_reason": e["stop_reason"], "error": e["error"], "model": e["model"],
        "portkey_trace_id": e["portkey_trace_id"],
    }
