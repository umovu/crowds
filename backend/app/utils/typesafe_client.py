"""TypeSafe (Jev) — typed questions over a state, for labelling work only.

A third tier beside `LLM_*` (research/personas) and `SIM_LLM_*` (simulation
runtime). This one never writes prose: it answers a fixed set of typed
questions about a piece of text and returns numbers.

  choice  pick one option      -> {choice, probabilities, confidence}
  score   rate on a ladder     -> {score, probabilities, legend, confidence}
  noul    is this true         -> {noul}   (0..1, no confidence field)

All questions in a request are evaluated in parallel against one `state`, so
asking an extra question costs a few tokens and almost no time.

Absent key or a failed call returns None. Every caller must have a working
deterministic path for that — nothing here may become load-bearing.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .logger import get_logger

logger = get_logger("fub.typesafe")

_DEFAULT_BASE_URL = "https://api.typesafe.ai/v1"
_DEFAULT_MODEL = "jev-latest"
# One request carries one state; the budget is shared by the state and every
# question. 32k tokens for state plus the longest question (jev-1.13.0).
_TIMEOUT = 60.0


def api_key() -> Optional[str]:
    return os.environ.get("TYPESAFE_API_KEY") or None


def enabled() -> bool:
    """True when a key is configured. Callers still handle a None result."""
    return bool(api_key())


def score_question(instructions: str, levels: List[str]) -> Dict[str, Any]:
    """A rung-ladder question. `levels` runs low to high; 2..10 rungs."""
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


def choice_question(instructions: str, options: Dict[str, Optional[str]]) -> Dict[str, Any]:
    """Pick one of `options` (name -> description, or None). Up to 255."""
    return {"type": "choice", "instructions": instructions, "criteria": dict(options)}


def noul_question(instructions: str,
                  when_true: Optional[str] = None,
                  when_false: Optional[str] = None) -> Dict[str, Any]:
    """Is this statement true of the state? Returns a probability, no confidence."""
    q: Dict[str, Any] = {"type": "noul", "instructions": instructions}
    if when_true or when_false:
        q["criteria"] = {"true": when_true, "false": when_false}
    return q


def ask(state: Any, questions: Dict[str, Dict[str, Any]],
        *, model: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Answer every question against one state. None on any failure.

    `state` may be a string, an object or a list. Keep it to the material the
    questions actually need — unrelated detail costs accuracy.
    """
    key = api_key()
    if not key:
        return None
    if not questions:
        return {}

    base = (os.environ.get("TYPESAFE_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
    body = json.dumps({
        "state": state,
        "model": model or os.environ.get("TYPESAFE_MODEL") or _DEFAULT_MODEL,
        "questions": questions,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/systemone", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        logger.warning("TypeSafe HTTP %s: %s", e.code, detail)
        return None
    except Exception as e:
        logger.warning("TypeSafe call failed: %s", e)
        return None

    usage = payload.get("usage") or {}
    logger.info("TypeSafe %s answered %d question(s), %s input tokens",
                payload.get("model"), len(payload.get("answers") or {}),
                usage.get("input_tokens"))
    return payload.get("answers") or {}
