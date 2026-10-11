"""The controlled workflow for one ticket: runs agents, performs delegation and
enforces every limit. Agents never call each other directly; they ask this
object, which decides whether the call is allowed.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from typing import Any

from pydantic_ai import UsageLimits
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.usage import RunUsage

from .audit import AuditLog, EventType
from .config import LIMITS, Limits, build_model, run_model_settings
from .deps import ALLOWED_DELEGATIONS, AgentDeps
from .guards import FactLedger, apply_action_rules
from .models import (
    AgentName, AgentOutput, AgentRunSummary, BossDecision, CustomerServiceReport,
    DelegationResult, SpecialistReport, SpecialistResult, TaskOutcome, TaskRequest,
    TicketContext, WorkflowStatus,
)

_RETRYABLE = (asyncio.TimeoutError, ModelAPIError, UnexpectedModelBehavior)


def _agents() -> dict[AgentName, Any]:
    from .accounting import accounting_agent
    from .boss import boss_agent
    from .customer_service import customer_service_agent
    from .facilities import facilities_agent
    from .inventory import inventory_agent
    return {AgentName.BOSS: boss_agent, AgentName.INVENTORY: inventory_agent,
            AgentName.ACCOUNTING: accounting_agent, AgentName.FACILITIES: facilities_agent,
            AgentName.CUSTOMER_SERVICE: customer_service_agent}


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 15] + " …[truncated]"


class TicketWorkflow:
    def __init__(self, run_id: str, ticket_id: int, audit: AuditLog, limits: Limits = LIMITS):
        self.run_id = run_id
        self.ticket_id = ticket_id
        self.audit = audit
        self.limits = limits
        self.ledger = FactLedger()
        self.model = build_model(limits)
        self.agents = _agents()
        self.ticket: TicketContext | None = None
        self.shop_date = ""
        self.status = WorkflowStatus.RECEIVED
        self.stop_reason: str | None = None      # set when a hard limit stops the workflow
        self.calls_total = 0
        self.calls_by_agent: Counter[AgentName] = Counter()
        self.cache: dict[tuple[AgentName, str], DelegationResult] = {}
        self.usage = RunUsage()
        self.started = time.monotonic()
        self.agent_runs: list[AgentRunSummary] = []
        self.specialist_results: list[SpecialistResult] = []
        self.guardrail_notes: list[str] = []

    # --- audit helpers ----------------------------------------------------------

    def audit_event(self, event_type: EventType, deps: AgentDeps | None, **fields: Any) -> None:
        if deps is not None:
            fields.setdefault("agent", deps.agent.value)
            fields.setdefault("depth", deps.depth)
            fields.setdefault("portkey_trace_id", deps.trace_id)
        self.audit.append(event_type, run_id=self.run_id, ticket_id=self.ticket_id, **fields)

    def transition(self, new: WorkflowStatus, reason: str) -> None:
        if new is self.status:
            return
        self.audit_event(EventType.STATE_TRANSITION, None, state_from=self.status.value,
                         state_to=new.value, reason=reason)
        self.status = new

    def hard_stop(self, reason: str, deps: AgentDeps | None = None) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
            self.audit_event(EventType.LIMIT_REACHED, deps, stop_reason=reason)

    # --- limits -------------------------------------------------------------------

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def _hard_limit(self) -> str | None:
        if self.stop_reason:
            return self.stop_reason
        if self.calls_total >= self.limits.max_agent_calls_per_ticket:
            return f"max_agent_calls_per_ticket ({self.limits.max_agent_calls_per_ticket}) reached"
        if self.elapsed() >= self.limits.ticket_timeout_s:
            return f"ticket_timeout_s ({self.limits.ticket_timeout_s:.0f}s) reached"
        if self.usage.total_tokens >= self.limits.max_total_tokens_per_ticket:
            return f"max_total_tokens_per_ticket ({self.limits.max_total_tokens_per_ticket}) reached"
        return None

    def _refusal(self, caller: AgentDeps, target: AgentName) -> tuple[str, bool] | None:
        """(reason, is_hard_limit) if this delegation may not run."""
        if target not in ALLOWED_DELEGATIONS[caller.agent]:
            return f"{caller.agent.value} is not permitted to delegate to {target.value}", False
        if target in caller.chain:
            chain = " -> ".join(a.value for a in caller.chain + (target,))
            return f"circular delegation refused ({chain})", False
        if caller.depth + 1 > self.limits.max_delegation_depth:
            return f"max_delegation_depth ({self.limits.max_delegation_depth}) reached", False
        if self.calls_by_agent[target] >= self.limits.max_calls_per_agent_per_ticket:
            return (f"max_calls_per_agent_per_ticket ({self.limits.max_calls_per_agent_per_ticket}) "
                    f"reached for {target.value}"), False
        hard = self._hard_limit()
        if hard:
            return hard, True
        return None

    # --- delegation -----------------------------------------------------------------

    async def delegate(self, caller: AgentDeps, target: AgentName, task: str, reason: str,
                       context: str) -> DelegationResult:
        task_key = re.sub(r"\s+", " ", task.strip().lower())
        cached = self.cache.get((target, task_key))
        if cached is not None:
            self.audit_event(EventType.DELEGATION_COMPLETED, caller, delegation_target=target.value,
                             task=task, reason=reason, delegation_result="cached result reused; "
                             "agent not re-run")
            return cached.model_copy(update={"status": "cached"})

        refusal = self._refusal(caller, target)
        if refusal:
            why, is_hard = refusal
            if is_hard:
                self.hard_stop(why, caller)
            self.audit_event(EventType.DELEGATION_REFUSED, caller, delegation_target=target.value,
                             task=task, reason=reason, stop_reason=why)
            return DelegationResult(target=target, task=task, reason=reason, status="refused",
                                    error=why)

        self.audit_event(EventType.DELEGATION_REQUESTED, caller, delegation_target=target.value,
                         task=task, reason=reason)
        request = TaskRequest(
            ticket=self.ticket, shop_date=self.shop_date, requested_by=caller.agent.value,
            task=task, reason=reason,
            context_from_caller=_clip(context, self.limits.max_caller_context_chars),
        )
        mark = len(self.specialist_results)
        report = await self.run_agent(target, request, caller.chain, caller.depth + 1)
        consulted = [f"{r.agent.value}: {r.report.outcome.value} — {r.report.summary}"
                     for r in self.specialist_results[mark:] if r.requested_by == target.value]
        if report is None:
            result = DelegationResult(target=target, task=task, reason=reason, status="failed",
                                      error=self.stop_reason or f"{target.value} did not return a result")
        else:
            result = DelegationResult(target=target, task=task, reason=reason, status="completed",
                                      report=report, consulted=consulted)
            self.cache[(target, task_key)] = result
        self.audit_event(EventType.DELEGATION_COMPLETED, caller, delegation_target=target.value,
                         task=task, delegation_result=result.status
                         + (f": {report.outcome.value} — {report.summary}" if report else
                            f": {result.error}"))
        return result

    # --- running one agent -------------------------------------------------------------

    async def run_agent(self, name: AgentName, request: TaskRequest,
                        parent_chain: tuple[AgentName, ...], depth: int) -> AgentOutput | None:
        self.calls_total += 1
        self.calls_by_agent[name] += 1
        trace_id = f"{self.run_id}-t{self.ticket_id}-{self.calls_total:02d}-{name.value}"
        deps = AgentDeps(workflow=self, agent=name, depth=depth,
                         chain=parent_chain + (name,), trace_id=trace_id)
        self.audit_event(EventType.AGENT_STARTED, deps, task=request.task, reason=request.reason,
                         delegation_target=None)
        agent = self.agents[name]
        prompt = request.model_dump_json()
        started = time.monotonic()

        result = None
        for attempt in range(self.limits.max_run_retries + 1):
            remaining = self.limits.ticket_timeout_s - self.elapsed()
            tokens_left = self.limits.max_total_tokens_per_ticket - self.usage.total_tokens
            if remaining <= 0 or tokens_left <= 0:
                self.hard_stop(self._hard_limit() or "ticket budget exhausted", deps)
                break
            try:
                result = await asyncio.wait_for(
                    agent.run(
                        prompt, deps=deps, model=self.model,
                        model_settings=run_model_settings(trace_id, self.limits),
                        usage_limits=UsageLimits(
                            request_limit=self.limits.max_model_requests_per_agent_run,
                            tool_calls_limit=self.limits.max_tool_calls_per_agent_run,
                            total_tokens_limit=tokens_left,
                        ),
                    ),
                    timeout=min(self.limits.agent_run_timeout_s, remaining),
                )
                break
            except UsageLimitExceeded as e:
                self.audit_event(EventType.AGENT_FAILED, deps, error=f"usage limit: {e}",
                                 stop_reason="per-run usage limit exceeded")
                if name is AgentName.BOSS:
                    self.hard_stop(f"boss usage limit exceeded: {e}", deps)
                break
            except _RETRYABLE as e:
                error = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                if attempt < self.limits.max_run_retries:
                    self.audit_event(EventType.AGENT_RETRY, deps, retry_attempt=attempt + 1,
                                     error=error)
                    continue
                self.audit_event(EventType.AGENT_FAILED, deps, retry_attempt=attempt, error=error,
                                 stop_reason="retries exhausted")
            except Exception as e:  # unexpected: log it, never swallow silently
                self.audit_event(EventType.AGENT_FAILED, deps,
                                 error=f"{type(e).__name__}: {e}", stop_reason="unexpected error")
                raise

        duration = round(time.monotonic() - started, 2)
        if result is None:
            self.agent_runs.append(AgentRunSummary(
                agent=name, depth=depth, requested_by=request.requested_by, task=request.task,
                outcome="failed", duration_s=duration, portkey_trace_id=trace_id))
            return None

        self.usage = self.usage + result.usage
        output = result.output
        if isinstance(output, BossDecision):
            actions = output.actions
        else:
            actions = output.recommended_actions
        actions, notes = apply_action_rules(actions, self.ledger)
        for note in notes:
            self.audit_event(EventType.GUARDRAIL_APPLIED, deps, reason=note)
        self.guardrail_notes.extend(notes)
        if isinstance(output, BossDecision):
            output = output.model_copy(update={"actions": actions})
            findings = [output.decision]
        else:
            output = output.model_copy(update={"recommended_actions": actions})
            findings = [f.summary for f in output.findings]
            self.specialist_results.append(SpecialistResult(
                agent=name, requested_by=request.requested_by, task=request.task, report=output))

        model_name = result.response.model_name
        outcome = (output.proposed_status.value if isinstance(output, BossDecision)
                   else output.outcome.value)
        self.audit_event(
            EventType.AGENT_COMPLETED, deps, task=request.task, findings=findings,
            recommendation=[f"{a.action_type.value} [{a.status.value}]: {a.description}"
                            for a in actions] or output.next_step,
            record_ids=output.record_ids(), tool_outcome=outcome, model=model_name,
            usage={"requests": result.usage.requests, "tool_calls": result.usage.tool_calls,
                   "input_tokens": result.usage.input_tokens,
                   "output_tokens": result.usage.output_tokens},
            stop_reason=(output.escalation_reason
                         if isinstance(output, SpecialistReport) else None),
        )
        self.agent_runs.append(AgentRunSummary(
            agent=name, depth=depth, requested_by=request.requested_by, task=request.task,
            outcome=outcome, duration_s=duration, model=model_name, portkey_trace_id=trace_id,
            requests=result.usage.requests, tool_calls=result.usage.tool_calls,
            total_tokens=result.usage.total_tokens))
        return output

    # --- final status ---------------------------------------------------------------------

    def final_status(self, decision: BossDecision | None) -> tuple[WorkflowStatus, str | None]:
        """The backend, not the Boss, has the last word on the ticket's status."""
        if decision is None:
            if self.stop_reason:
                return WorkflowStatus.LIMIT_REACHED, self.stop_reason
            return WorkflowStatus.FAILED, "the Boss did not return a decision"
        if self.stop_reason:
            return WorkflowStatus.LIMIT_REACHED, self.stop_reason
        proposed = decision.proposed_status
        if proposed in (WorkflowStatus.ESCALATED, WorkflowStatus.BLOCKED,
                        WorkflowStatus.NEEDS_CLARIFICATION):
            return proposed, f"boss: {proposed.value}"
        pending = [a for a in decision.actions if a.requires_human_approval]
        unresolved = [r for r in self.specialist_results
                      if r.report.outcome in (TaskOutcome.BLOCKED, TaskOutcome.ESCALATE)]
        if pending:
            return WorkflowStatus.AWAITING_HUMAN_APPROVAL, "actions need human approval"
        if proposed is WorkflowStatus.RESOLVED and unresolved:
            return WorkflowStatus.ESCALATED, ("boss marked the ticket resolved while a specialist "
                                              "reported it blocked or escalated")
        if proposed is WorkflowStatus.AWAITING_HUMAN_APPROVAL:
            return WorkflowStatus.ESCALATED, "boss expected approvals but proposed no actions"
        return WorkflowStatus.RESOLVED, "boss: resolved"
