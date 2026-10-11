"""One place for the model every agent uses and for the limits on each run.

All five agents use GPT-6 Luna through Portkey's OpenAI-compatible endpoint.
The API key is read from PORTKEY_API_KEY (the .env file); it is never written
to code, logs or the audit trail.

Every limit can be overridden with an environment variable named
CC_<FIELD_NAME_IN_CAPITALS>, e.g. CC_MAX_AGENT_CALLS_PER_TICKET=6.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import ModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

HW_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(HW_ROOT / ".env")
load_dotenv(HW_ROOT.parent / ".env")  # the course's shared .env holds PORTKEY_API_KEY
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MODEL_ID = "gpt-6-luna"  # required for all five agents; deliberately not overridable

MCP_SERVER_SCRIPT = HW_ROOT / "mcp_server" / "server.py"
WORKING_DB = "data/campus_customs_new.db"
WORKING_DB_PATH = HW_ROOT / WORKING_DB
ORIGINAL_DB_PATH = HW_ROOT / "data" / "campus_customs.db"  # never written; the reset baseline
AUDIT_PATH = HW_ROOT / "output" / "audit_trail.json"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class Limits:
    # Workflow-wide limits for one ticket.
    max_agent_calls_per_ticket: int = 8
    max_calls_per_agent_per_ticket: int = 3
    max_delegation_depth: int = 3          # Boss is depth 0
    ticket_timeout_s: float = 600
    max_total_tokens_per_ticket: int = 250_000
    # Limits for one agent run.
    max_model_requests_per_agent_run: int = 8
    max_tool_calls_per_agent_run: int = 6
    agent_run_timeout_s: float = 240
    max_retries: int = 2                   # tool-argument and output-validation retries in a run
    max_run_retries: int = 1               # re-runs of an agent after a timeout or API failure
    # Limits for one model request.
    model_request_timeout_s: float = 90
    max_http_retries: int = 2
    max_output_tokens_per_response: int = 6000
    # Size limits.
    max_ticket_notes_chars: int = 1000
    max_caller_context_chars: int = 2500
    max_tool_result_chars: int = 6000
    max_audit_text_chars: int = 400
    max_audit_list_items: int = 12


def load_limits() -> Limits:
    overrides = {}
    for f in fields(Limits):
        raw = os.environ.get(f"CC_{f.name.upper()}")
        if raw is not None:
            overrides[f.name] = type(f.default)(raw)
    return Limits(**overrides)


LIMITS = load_limits()


def build_model(limits: Limits = LIMITS) -> OpenAIResponsesModel:
    """The single model configuration shared by all five agents."""
    api_key = os.environ.get("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set; add it to the .env file.")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        timeout=limits.model_request_timeout_s,
        max_retries=limits.max_http_retries,
    )
    return OpenAIResponsesModel(MODEL_ID, provider=OpenAIProvider(openai_client=client))


def run_model_settings(trace_id: str, limits: Limits = LIMITS) -> ModelSettings:
    """Per-run settings: output cap, request timeout, and the Portkey trace id header."""
    return ModelSettings(
        max_tokens=limits.max_output_tokens_per_response,
        timeout=limits.model_request_timeout_s,
        extra_headers={"x-portkey-trace-id": trace_id},
    )
