"""The agents' only route to shop data: the campus-customs-ops MCP server.

One stdio connection is shared by every agent in a run. Each agent receives a
filtered view with just its allowed tools, and every call passes through
`_audit_tool_call`, which logs it, records the returned rows in the run's
FactLedger, and caps the result size before the model sees it.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from fastmcp.client.transports import StdioTransport
from pydantic_ai import RunContext
from pydantic_ai.mcp import CallToolFunc, MCPToolset

from .audit import EventType
from .config import HW_ROOT, LIMITS, MCP_SERVER_SCRIPT, WORKING_DB
from .deps import ALLOWED_TOOLS, AgentDeps
from .models import AgentName


def _as_data(result: Any) -> Any:
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    return result


def _bounded(data: Any) -> Any:
    text = json.dumps(data, default=str)
    if len(text) <= LIMITS.max_tool_result_chars:
        return data
    return {"truncated": True,
            "note": f"Result cut to {LIMITS.max_tool_result_chars} characters; narrow the query.",
            "partial_json": text[: LIMITS.max_tool_result_chars]}


def _outcome(data: Any) -> str:
    if isinstance(data, dict) and data.get("found") is False:
        return f"not_found: {data.get('message', '')}"
    return "ok"


async def _audit_tool_call(ctx: RunContext[AgentDeps], call_tool: CallToolFunc,
                           name: str, args: dict[str, Any]) -> Any:
    deps = ctx.deps
    wf = deps.workflow
    if name not in ALLOWED_TOOLS[deps.agent]:  # second line of defence behind the filter
        wf.audit_event(EventType.MCP_TOOL_ERROR, deps, tool_name=name, tool_args=args,
                       error="tool not permitted for this agent")
        raise PermissionError(f"{deps.agent.value} may not call {name}")
    try:
        result = await call_tool(name, args)
    except Exception as e:
        wf.audit_event(EventType.MCP_TOOL_ERROR, deps, tool_name=name, tool_args=args,
                       tool_outcome="error", error=f"{type(e).__name__}: {e}")
        raise
    data = _as_data(result)
    record_ids = wf.ledger.ingest(name, data)
    wf.audit_event(EventType.MCP_TOOL_CALL, deps, tool_name=name, tool_args=args,
                   tool_outcome=_outcome(data), record_ids=record_ids)
    return _bounded(data)


def build_toolset() -> MCPToolset:
    transport = StdioTransport(
        command=sys.executable,
        args=[str(MCP_SERVER_SCRIPT)],
        env={"CAMPUS_CUSTOMS_DB": WORKING_DB},  # no API keys are passed to the server
        cwd=str(HW_ROOT),
    )
    # The server process needs several seconds to import FastMCP, so the
    # handshake timeout is generous.
    return MCPToolset(transport, id="campus-customs-ops", process_tool_call=_audit_tool_call,
                      max_retries=LIMITS.max_retries, init_timeout=60)


MCP_TOOLSET = build_toolset()


def toolset_for(agent: AgentName):
    allowed = ALLOWED_TOOLS[agent]
    return MCP_TOOLSET.filtered(lambda ctx, tool_def: tool_def.name in allowed)


async def call_tool_direct(wf, name: str, args: dict[str, Any]) -> Any:
    """Orchestrator-level MCP call (no agent involved), logged the same way."""
    try:
        data = _as_data(await MCP_TOOLSET.direct_call_tool(name, args))
    except Exception as e:
        wf.audit_event(EventType.MCP_TOOL_ERROR, None, tool_name=name, tool_args=args,
                       tool_outcome="error", error=f"{type(e).__name__}: {e}")
        raise
    record_ids = wf.ledger.ingest(name, data)
    wf.audit_event(EventType.MCP_TOOL_CALL, None, tool_name=name, tool_args=args,
                   tool_outcome=_outcome(data), record_ids=record_ids)
    return data
