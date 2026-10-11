"""Agent 2: Inventory Manager."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from .agent_base import delegate, make_agent
from .deps import AgentDeps
from .models import AgentName, SpecialistReport

inventory_agent = make_agent(AgentName.INVENTORY, SpecialistReport)


@inventory_agent.tool
async def ask_accounting(
    ctx: RunContext[AgentDeps],
    task: Annotated[str, Field(max_length=600)],
    reason: Annotated[str, Field(max_length=300)],
    context: Annotated[str, Field(max_length=2500)] = "",
) -> dict:
    """Ask the Accounting Manager for a financial assessment and wait for its report.

    Use when a replenishment depends on money: a vendor is blocked by an unpaid
    invoice, or a purchase order's cost must be checked against cash.
    context: the stock and vendor facts Accounting needs (ids and amounts).
    """
    return await delegate(ctx, AgentName.ACCOUNTING, task, reason, context)
