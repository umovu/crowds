"""Run events: an append-only record of run *metadata*, never run content.

One row when a run starts, one when it ends. Enough to answer "is this user
profitable", "how often do runs fail", "did they come back", "which mode do people
use" — without the operator ever being able to read what a user asked.

The privacy fence is the point of this module, not a nicety:

* ``ALLOWED_FIELDS`` is an allow-list. Anything else is dropped, silently.
* Every value must be a scalar, and strings are capped at ``MAX_VALUE_LEN``. A pitch,
  a seed, a persona answer — none of them fit through that, so a future edit cannot
  leak a scenario into the log by accident.
* There is no field for free text and there must never be one.

Storage: the local JSONL file under DATA_ROOT is written first and always, and
Supabase is a best-effort mirror on top. That order matters — local dev keeps working
with no database, and a failed mirror never loses the line.

A logging failure must never break a run. Nothing here raises.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# No module-level app imports on purpose: tests load this file by path, with no
# package, so the privacy fence can be asserted without importing the app at all.
logger = logging.getLogger("fub.run_events")

TABLE = "run_events"

#: The only keys that may ever reach storage. No free-text field belongs here.
ALLOWED_FIELDS = {
    "event",            # "start" | "end"
    "run_id",           # session/sim id, so start and end pair up
    "user_id",
    "run_type",         # "panel" | "simulation"
    "mode",             # "product" | "policy"
    "crowd_size",
    "duration_seconds",
    "status",           # "started" | "ok" | "failed"
    "error_code",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
}

#: Long enough for an id or an error code, far too short for a scenario.
MAX_VALUE_LEN = 64


def _ledger_path() -> str:
    # Imported here so the module stays importable if config side-effects fail.
    try:
        from app.config import Config
        root = Config.DATA_ROOT
    except Exception:  # noqa: BLE001
        root = os.environ.get("DATA_ROOT") or os.getcwd()
    return os.path.join(root, "run_events.jsonl")


def _supabase():
    """Imported lazily: see the note on the imports above."""
    from app.repositories import supabase
    return supabase


def sanitize(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Only allow-listed, scalar, length-capped fields.

    This is the fence. It is a separate function so it can be asserted on directly in
    tests, with no storage and no network involved.
    """
    clean: Dict[str, Any] = {}
    for key, value in (fields or {}).items():
        if key not in ALLOWED_FIELDS or value is None:
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                clean[key] = trimmed[:MAX_VALUE_LEN]
        # Anything else (dict, list, object) is dropped: only scalars pass.
    return clean


def record(**fields: Any) -> None:
    """Append one metadata row. Never raises, never blocks a run for long."""
    try:
        row = sanitize(fields)
        if not row:
            return
        row["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_local(row)
        if _supabase().enabled():
            _write_supabase(row)
    except Exception as e:  # pragma: no cover - defensive by design
        logger.warning("run event record failed: %s", e)


def record_start(**fields: Any) -> None:
    record(event="start", status="started", **fields)


def record_end(**fields: Any) -> None:
    record(event="end", **fields)


def _write_local(row: Dict[str, Any]) -> None:
    path = _ledger_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not write run events at %s: %s", path, e)


def _write_supabase(row: Dict[str, Any]) -> None:
    try:
        resp = _supabase().insert(TABLE, row, prefer="return=minimal")
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        # The local line is already written; the mirror is best-effort.
        logger.warning("run event mirror to Supabase failed: %s", e)


def totals(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Sum the local ledger — runs, tokens, cost, failures.

    Cheap: one short line per run. The hosted copy is queried in its own table view,
    not from here.
    """
    runs = failed = total_tokens = 0
    total_cost = 0.0
    try:
        with open(_ledger_path(), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:  # noqa: BLE001 - a torn line is skipped
                    continue
                if row.get("event") != "end":
                    continue
                if user_id and row.get("user_id") != user_id:
                    continue
                runs += 1
                if row.get("status") == "failed":
                    failed += 1
                total_tokens += int(row.get("total_tokens", 0) or 0)
                total_cost += float(row.get("cost_usd", 0.0) or 0.0)
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read run events: %s", e)
    return {
        "runs": runs,
        "failed": failed,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
    }
