"""
Run events — an append-only record of run *metadata*, never run content.

One row when a run starts, one when it ends. Enough to answer "is this user
profitable", "how often do runs fail", "did they come back", "which mode do
people use" — without the operator ever being able to read what a user asked.

The privacy fence is the point of this module, not a nicety:

* ``ALLOWED_FIELDS`` is an allow-list. Anything else is dropped, silently.
* Every value must be a scalar, and strings are capped at ``MAX_VALUE_LEN``.
  A pitch, a seed, a persona answer — none of them can fit through that, so a
  future edit cannot leak a scenario into the log by accident.
* There is no field for free text and there must never be one.

Storage mirrors `operator_context`: Supabase when configured, a JSONL file
under DATA_ROOT otherwise, so local dev works with no database.

A logging failure must never break a run. Nothing here raises.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

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
    except Exception:
        root = os.environ.get("DATA_ROOT") or os.getcwd()
    return os.path.join(root, "run_events.jsonl")


def _supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or "").rstrip("/")


def _service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""


def _enabled() -> bool:
    return bool(_supabase_url() and _service_key())


def _headers() -> dict:
    k = _service_key()
    return {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def sanitize(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Return only allow-listed, scalar, length-capped fields.

    This is the fence. It is a separate function so it can be asserted on
    directly in tests, with no storage and no network involved.
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
        if _enabled():
            _write_supabase(row)
    except Exception as e:  # pragma: no cover - defensive by design
        logger.warning("run_events.record failed: %s", e)


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
    except Exception as e:
        logger.warning("Could not write run events at %s: %s", path, e)


def _write_supabase(row: Dict[str, Any]) -> None:
    try:
        resp = requests.post(
            f"{_supabase_url()}/rest/v1/{TABLE}",
            json=row,
            headers={**_headers(), "Prefer": "return=minimal"},
            timeout=6,
        )
        resp.raise_for_status()
    except Exception as e:
        # The local line is already written; the mirror is best-effort.
        logger.warning("run_events supabase write failed: %s", e)


def totals(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Sum the local ledger — runs, tokens, cost, failures. Cheap: one short
    line per run. Supabase is queried in its own table view, not from here."""
    runs = failed = total_tokens = 0
    total_cost = 0.0
    try:
        with open(_ledger_path(), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("event") != "end":
                    continue
                if user_id and r.get("user_id") != user_id:
                    continue
                runs += 1
                if r.get("status") == "failed":
                    failed += 1
                total_tokens += int(r.get("total_tokens", 0) or 0)
                total_cost += float(r.get("cost_usd", 0.0) or 0.0)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Could not read run events: %s", e)
    return {
        "runs": runs,
        "failed": failed,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
    }
