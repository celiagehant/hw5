"""Restore the working database from the untouched original.

Uses SQLite's backup API, which replaces every page of the working copy, so
tables added by the system (ticket_runs, action_proposals, approvals) disappear
and every row returns to its baseline value. The original is opened read-only,
and its checksum is compared before and after to prove it was not changed.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from .config import HW_ROOT, ORIGINAL_DB_PATH, WORKING_DB_PATH


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(path: Path) -> dict:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        tables = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"))
        return {
            "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
            "row_counts": {t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                           for t in tables},
            "checking_balance": conn.execute(
                "SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()[0],
            "ticket_status": {r[0]: r[1] for r in conn.execute("SELECT id, status FROM tickets")},
            "open_invoices": [r[0] for r in conn.execute(
                "SELECT id FROM invoices WHERE lower(status) = 'open'")],
        }


def restore_working_db() -> dict:
    if not ORIGINAL_DB_PATH.exists():
        raise FileNotFoundError("The original database is missing; nothing to restore from.")
    if WORKING_DB_PATH.exists() and WORKING_DB_PATH.resolve() == ORIGINAL_DB_PATH.resolve():
        raise RuntimeError("The working path points at the original database; refusing.")

    original_hash = _sha256(ORIGINAL_DB_PATH)
    with closing(sqlite3.connect(ORIGINAL_DB_PATH.as_uri() + "?mode=ro", uri=True)) as src, \
            closing(sqlite3.connect(WORKING_DB_PATH, timeout=10)) as dst:
        src.backup(dst)

    if _sha256(ORIGINAL_DB_PATH) != original_hash:
        raise RuntimeError("The original database changed during the reset.")
    baseline = _snapshot(ORIGINAL_DB_PATH)
    restored = _snapshot(WORKING_DB_PATH)
    if restored != baseline or restored["integrity"] != "ok":
        raise RuntimeError("The restored working database does not match the original.")
    return {
        "ok": True,
        "restored_from": str(ORIGINAL_DB_PATH.relative_to(HW_ROOT)),
        "working_db": str(WORKING_DB_PATH.relative_to(HW_ROOT)),
        "original_sha256_unchanged": original_hash,
        **restored,
    }
