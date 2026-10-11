"""Agent 4: Facilities Manager."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from .agent_base import delegate, make_agent
from .deps import AgentDeps
from .models import AgentName, SpecialistReport

facilities_agent = make_agent(AgentName.FACILITIES, SpecialistReport)


@facilities_agent.tool
async def ask_accounting(
    ctx: RunContext[AgentDeps],
    task: Annotated[str, Field(max_length=600)],
    reason: Annotated[str, Field(max_length=300)],
    context: Annotated[str, Field(max_length=2500)] = "",
) -> dict:
    """Ask the Accounting Manager to assess and prepare a facilities payment.

    Use when rent or another facilities obligation needs paying: Accounting
    checks it against cash and the other open bills and prepares the proposal.
    context: the lease id, amount and due date you found.
    """
    return await delegate(ctx, AgentName.ACCOUNTING, task, reason, context)
