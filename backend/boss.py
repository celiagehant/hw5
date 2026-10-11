"""Agent 1: Boss / Operations Manager."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import RunContext

from .agent_base import delegate, make_agent
from .deps import AgentDeps
from .models import AgentName, BossDecision

boss_agent = make_agent(AgentName.BOSS, BossDecision)


@boss_agent.tool
async def delegate_to_specialist(
    ctx: RunContext[AgentDeps],
    specialist: Literal["inventory", "accounting", "facilities", "customer_service"],
    task: Annotated[str, Field(max_length=600)],
    reason: Annotated[str, Field(max_length=300)],
    context: Annotated[str, Field(max_length=2500)] = "",
) -> dict:
    """Assign a task to one specialist agent and wait for its structured report.

    specialist: who should do the work.
    task: exactly what you need answered or prepared.
    reason: why this specialist is needed for this ticket.
    context: findings from other specialists that this one needs (keep it short).

    Returns status "completed" or "cached" with the report, or "refused"/"failed"
    with the reason (for example a limit was reached). Never ask for the same task twice.
    """
    return await delegate(ctx, AgentName(specialist), task, reason, context)
