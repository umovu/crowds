"""
Usage ledger — an append-only record of token spend across runs.

Every completed simulation/panel appends one JSON line to
``{DATA_ROOT}/usage_ledger.jsonl`` with its token counts and estimated cost.
This lets you watch prepaid credit (e.g. a $10 DeepSeek top-up) deplete over
time without opening the provider dashboard.

The per-run figures already come from the sim's own token counting
(``opinion_skill.get_token_stats()``); this module only persists and totals
them. It is deliberately defensive: a ledger write must never crash a run.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("fub.usage_ledger")


def _ledger_path() -> str:
    # Import here so the module stays importable even if config side-effects fail.
    try:
        from app.config import Config
        root = Config.DATA_ROOT
    except Exception:
        root = os.environ.get("DATA_ROOT") or os.getcwd()
    return os.path.join(root, "usage_ledger.jsonl")


def record_usage(
    kind: str,
    token_stats: Dict[str, Any],
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append one run's usage to the ledger and return cumulative totals.

    Parameters
    ----------
    kind : str
        "simulation" or "panel".
    token_stats : dict
        The shape returned by ``get_token_stats`` — expects
        ``total_prompt_tokens``, ``total_completion_tokens``, ``total_tokens``,
        ``estimated_cost_usd`` and ``model``.
    meta : dict, optional
        Extra context to store on the row (e.g. sim_id, agent count).

    Returns
    -------
    dict with cumulative ``runs``, ``total_tokens`` and ``total_cost_usd``.
    Never raises — on failure returns the single run's figures.
    """
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "model": token_stats.get("model", "unknown"),
        "prompt_tokens": int(token_stats.get("total_prompt_tokens", 0) or 0),
        "completion_tokens": int(token_stats.get("total_completion_tokens", 0) or 0),
        "total_tokens": int(token_stats.get("total_tokens", 0) or 0),
        "cost_usd": round(float(token_stats.get("estimated_cost_usd", 0.0) or 0.0), 6),
    }
    if meta:
        row.update({k: v for k, v in meta.items() if k not in row})

    path = _ledger_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception as e:
        logger.warning("Could not write usage ledger at %s: %s", path, e)
        return {
            "runs": 1,
            "total_tokens": row["total_tokens"],
            "total_cost_usd": row["cost_usd"],
        }

    return _totals(path)


def _totals(path: str) -> Dict[str, Any]:
    """Sum the whole ledger. Cheap — the file is one short line per run."""
    runs = 0
    total_tokens = 0
    total_cost = 0.0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                runs += 1
                total_tokens += int(r.get("total_tokens", 0) or 0)
                total_cost += float(r.get("cost_usd", 0.0) or 0.0)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Could not read usage ledger at %s: %s", path, e)
    return {
        "runs": runs,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
    }
