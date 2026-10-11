"""Append-only audit trail shared by every agent and orchestration step.

output/audit_trail.json is a JSON array of events with one fixed schema.
Each append takes an exclusive file lock, reads the current array, adds the
event and atomically replaces the file, so concurrent runs cannot interleave
writes and a crash mid-write leaves the previous valid file in place. A file
that is not valid JSON is never overwritten: the append fails loudly instead.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .config import AUDIT_PATH, LIMITS, Limits


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    TICKET_LOADED = "ticket_loaded"
    STATE_TRANSITION = "state_transition"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_RETRY = "agent_retry"
    AGENT_FAILED = "agent_failed"
    MCP_TOOL_CALL = "mcp_tool_call"
    MCP_TOOL_ERROR = "mcp_tool_error"
    DELEGATION_REQUESTED = "delegation_requested"
    DELEGATION_COMPLETED = "delegation_completed"
    DELEGATION_REFUSED = "delegation_refused"
    GUARDRAIL_APPLIED = "guardrail_applied"
    LIMIT_REACHED = "limit_reached"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    PROPOSALS_RECORDED = "proposals_recorded"
    PAYMENT_EXECUTED = "payment_executed"
    PURCHASE_APPROVED = "purchase_approved"
    APPROVAL_REFUSED = "approval_refused"
    DISCOUNT_APPROVED = "discount_approved"
    PROPOSAL_DECLINED = "proposal_declined"
    DATABASE_RESET = "database_reset"


# Every event has exactly these keys, in this order; unused ones are null.
EVENT_FIELDS = (
    "event_id", "timestamp", "run_id", "ticket_id", "agent", "depth", "event_type",
    "task", "reason", "delegation_target", "delegation_result",
    "tool_name", "tool_args", "tool_outcome", "record_ids",
    "findings", "recommendation", "state_from", "state_to",
    "stop_reason", "retry_attempt", "error", "model", "portkey_trace_id", "usage",
)

# Env vars whose values are scrubbed from every logged string.
_SECRET_ENV_NAME = re.compile(r"(key|token|secret|password|authorization)", re.IGNORECASE)
# Dict keys whose values are never logged.
_SECRET_FIELD = re.compile(r"(api[_-]?key|access[_-]?token|secret|password|authorization)",
                           re.IGNORECASE)


class AuditError(RuntimeError):
    pass


def _secret_values() -> list[str]:
    return [v for k, v in os.environ.items() if _SECRET_ENV_NAME.search(k) and len(v) >= 8]


class AuditLog:
    def __init__(self, path: Path = AUDIT_PATH, limits: Limits = LIMITS):
        self.path = path
        self.lock_path = path.with_name(f".{path.name}.lock")
        self.limits = limits
        self._thread_lock = threading.Lock()
        self._secrets = _secret_values()

    # --- bounding and redaction ---------------------------------------------

    def _clean(self, value: Any, depth: int = 0) -> Any:
        if isinstance(value, Enum):
            value = value.value
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, "[REDACTED]")
            limit = self.limits.max_audit_text_chars
            return value if len(value) <= limit else value[:limit] + "…[truncated]"
        if isinstance(value, dict):
            if depth > 4:
                return "[nested data omitted]"
            return {str(k): ("[REDACTED]" if _SECRET_FIELD.search(str(k)) else self._clean(v, depth + 1))
                    for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            items = list(value)
            cleaned = [self._clean(v, depth + 1) for v in items[: self.limits.max_audit_list_items]]
            if len(items) > self.limits.max_audit_list_items:
                cleaned.append(f"…[{len(items) - self.limits.max_audit_list_items} more]")
            return cleaned
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self._clean(str(value), depth)

    # --- writing ------------------------------------------------------------

    def append(self, event_type: EventType, *, run_id: str, ticket_id: int | None = None,
               **fields: Any) -> dict:
        unknown = set(fields) - set(EVENT_FIELDS)
        if unknown:
            raise AuditError(f"Unknown audit fields: {sorted(unknown)}")
        event = dict.fromkeys(EVENT_FIELDS)
        event.update({k: self._clean(v) for k, v in fields.items()})
        event.update(
            event_id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            run_id=run_id,
            ticket_id=ticket_id,
            event_type=event_type.value,
        )
        self._write(event)
        return event

    def _write(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._thread_lock, open(self.lock_path, "a") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                events = self._read_existing()
                events.append(event)
                fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".audit_", suffix=".tmp")
                try:
                    with os.fdopen(fd, "w") as f:
                        json.dump(events, f, indent=1, ensure_ascii=False)
                        f.write("\n")
                        f.flush()
                        os.fsync(f.fileno())
                    os.chmod(tmp, 0o644)  # mkstemp creates 0600
                    os.replace(tmp, self.path)
                except BaseException:
                    Path(tmp).unlink(missing_ok=True)
                    raise
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    def _read_existing(self) -> list:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return []
        try:
            data = json.loads(self.path.read_text())
        except json.JSONDecodeError as e:
            raise AuditError(f"{self.path.name} is not valid JSON ({e}); refusing to overwrite it.") from e
        if not isinstance(data, list):
            raise AuditError(f"{self.path.name} must hold a JSON array; refusing to overwrite it.")
        return data

    def read(self) -> list[dict]:
        with self._thread_lock, open(self.lock_path, "a") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_SH)
            try:
                return self._read_existing()
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
