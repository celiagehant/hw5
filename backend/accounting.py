"""Agent 3: Accounting Manager.

Accounting is the leaf of the delegation graph: it has no delegation tool,
so no chain of agents can loop back through it. It has no payment tool
either; it can only prepare proposals for a human.
"""

from __future__ import annotations

from .agent_base import make_agent
from .models import AgentName, SpecialistReport

accounting_agent = make_agent(AgentName.ACCOUNTING, SpecialistReport)
