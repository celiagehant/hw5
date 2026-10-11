"""Agent 5: Customer Service Manager.

Produces drafts only; there is no tool that can send a message.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from .agent_base import delegate, make_agent
from .deps import AgentDeps
from .models import AgentName, CustomerServiceReport

customer_service_agent = make_agent(AgentName.CUSTOMER_SERVICE, CustomerServiceReport)


@customer_service_agent.tool
async def ask_inventory(
    ctx: RunContext[AgentDeps],
    task: Annotated[str, Field(max_length=600)],
    reason: Annotated[str, Field(max_length=300)],
    context: Annotated[str, Field(max_length=2500)] = "",
) -> dict:
    """Ask the Inventory Manager for availability or restock timing and wait for its report.

    Use only when the message depends on stock or timing that is not already in
    the context you were given.
    """
    return await delegate(ctx, AgentName.INVENTORY, task, reason, context)
