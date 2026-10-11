"""Shared construction for the five PydanticAI agents."""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext

from .audit import EventType
from .config import LIMITS, PROMPTS_DIR
from .deps import AgentDeps
from .guards import output_problems
from .mcp_client import toolset_for
from .models import AgentName


def load_prompt(agent: AgentName) -> str:
    return (PROMPTS_DIR / f"{agent.value}.md").read_text()


def make_agent(name: AgentName, output_type: type) -> Agent[AgentDeps, Any]:
    """An agent with its own prompt, its own MCP tool subset and the evidence check.

    The model is supplied per run by the workflow (config.build_model), so all
    five agents share one model configuration.
    """
    agent = Agent(
        None,
        output_type=output_type,
        deps_type=AgentDeps,
        instructions=load_prompt(name),
        name=name.value,
        retries=LIMITS.max_retries,
        toolsets=[toolset_for(name)],
        defer_model_check=True,
    )

    @agent.output_validator
    async def _check_against_database(ctx: RunContext[AgentDeps], output: Any) -> Any:
        problems = output_problems(output, ctx.deps.workflow.ledger)
        if problems:
            ctx.deps.workflow.audit_event(
                EventType.GUARDRAIL_APPLIED, ctx.deps,
                error="; ".join(problems), stop_reason="output rejected; model asked to correct it")
            raise ModelRetry("Your output was rejected:\n- " + "\n- ".join(problems))
        return output

    return agent


async def delegate(ctx: RunContext[AgentDeps], target: AgentName, task: str, reason: str,
                   context: str) -> dict:
    """Run another agent through the workflow (which applies every limit) and return its result."""
    result = await ctx.deps.workflow.delegate(ctx.deps, target, task, reason, context)
    return result.model_dump(mode="json", exclude_none=True)
