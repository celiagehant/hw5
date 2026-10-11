"""Per-run dependencies and the access policy: which MCP tools and which
delegation targets each agent may use. The backend enforces both; prompts
only describe them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import AgentName

if TYPE_CHECKING:
    from .workflow import TicketWorkflow

ALLOWED_TOOLS: dict[AgentName, frozenset[str]] = {
    AgentName.BOSS: frozenset({"get_ticket_details"}),
    AgentName.INVENTORY: frozenset({"get_stock_and_pricing", "check_vendor_eligibility"}),
    AgentName.ACCOUNTING: frozenset({"get_cash_and_obligations", "check_vendor_eligibility",
                                     "get_stock_and_pricing"}),
    AgentName.FACILITIES: frozenset({"get_rent_due_and_cash_position"}),
    AgentName.CUSTOMER_SERVICE: frozenset({"get_ticket_details"}),
}

# A directed acyclic graph: Accounting is a leaf, so no chain can loop back.
ALLOWED_DELEGATIONS: dict[AgentName, frozenset[AgentName]] = {
    AgentName.BOSS: frozenset({AgentName.INVENTORY, AgentName.ACCOUNTING,
                               AgentName.FACILITIES, AgentName.CUSTOMER_SERVICE}),
    AgentName.INVENTORY: frozenset({AgentName.ACCOUNTING}),
    AgentName.FACILITIES: frozenset({AgentName.ACCOUNTING}),
    AgentName.CUSTOMER_SERVICE: frozenset({AgentName.INVENTORY}),
    AgentName.ACCOUNTING: frozenset(),
}


@dataclass(frozen=True)
class AgentDeps:
    workflow: TicketWorkflow
    agent: AgentName
    depth: int
    chain: tuple[AgentName, ...]   # callers from the Boss down to this agent, inclusive
    trace_id: str
