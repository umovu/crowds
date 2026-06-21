"""
world_facts — curated South African world-facts layer.

Real current costs (fuel, data, taxi fare, grants) that agents reason AGAINST,
so they never invent a magnitude (the "two tanks" failure: an agent claiming
R100 = two full tanks when R100 of petrol is ~4.5 litres).

Design (matches the agreed plan):
  - Facts live in app/data/sa_world_facts.json — inspectable, hand-authored.
  - Every fact carries a numeric value + unit, so it is VALIDATABLE with the LLM
    off (consistent with the product-economy hard rule). Facts that don't parse
    into number+unit are dropped, not trusted.
  - provenance: 'curated' (authoritative, wins on conflict) | 'web' (harvested,
    overridable) | 'discovered' (promoted from a sim fact-gap).
  - render_block() produces the text injected into document_context, so the
    facts are part of the shared world every agent sees each round — NOT pasted
    into per-persona prompts (that path authored slop; this one grounds the
    scenario).

Pure/LLM-free: load, validate, render, promote are all deterministic.
"""

import json
import os
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("fub.world_facts")

_FACTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sa_world_facts.json")

# Conflict order: a higher-priority provenance overrides a lower one for the same
# item. Curated is authoritative (you hand-set it); discovered (you promoted it)
# beats a raw web harvest.
_PROVENANCE_PRIORITY = {"curated": 3, "discovered": 2, "web": 1}


def _facts_path() -> str:
    return os.path.abspath(_FACTS_PATH)


def is_valid_fact(fact: Dict[str, Any]) -> bool:
    """A fact is usable only if it has an item, a numeric value, and a unit.

    This is the guard that stops the world-facts layer from becoming a new slop
    pipe: a scraped 'R100 = two tanks' has no clean value+unit and is rejected.
    """
    if not isinstance(fact, dict):
        return False
    item = (fact.get("item") or "").strip()
    unit = (fact.get("unit") or "").strip()
    value = fact.get("value")
    if not item or not unit:
        return False
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_facts(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load curated facts from disk, keeping only valid ones, with the
    highest-priority provenance winning per item. Loaded fresh each call so an
    edit / promote takes effect on the next run with no code change.

    Returns [] (never raises) if the file is missing or unreadable — the world
    is simply ungrounded for that run, same as before this layer existed.
    """
    p = os.path.abspath(path) if path else _facts_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"world-facts: could not load {p}: {e}")
        return []

    raw = data.get("facts", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    best: Dict[str, Dict[str, Any]] = {}
    dropped = 0
    for fact in raw:
        if not is_valid_fact(fact):
            dropped += 1
            continue
        item = fact["item"].strip()
        prov = (fact.get("provenance") or "web").strip().lower()
        rank = _PROVENANCE_PRIORITY.get(prov, 0)
        cur = best.get(item)
        if cur is None or rank > _PROVENANCE_PRIORITY.get((cur.get("provenance") or "web").lower(), 0):
            best[item] = fact
    if dropped:
        logger.info(f"world-facts: dropped {dropped} fact(s) lacking a numeric value+unit")
    return list(best.values())


def _format_fact_line(fact: Dict[str, Any]) -> str:
    """One human-readable line: the number, its unit, and the derived consequence."""
    value = fact["value"]
    # Drop a trailing .0 so 'R22/litre' reads cleanly, keep real decimals.
    num = int(value) if float(value).is_integer() else value
    unit = fact["unit"]
    # Units like 'R/litre' already carry the currency — write 'R22/litre', not
    # 'R22 R/litre'. Units without it (e.g. 'kWh') get the leading 'R'.
    amount = f"R{num}{unit[1:]}" if unit.startswith("R/") else f"R{num} {unit}"
    line = f"- {fact['item'].replace('_', ' ')}: {amount}"
    derived = (fact.get("derived") or "").strip()
    if derived:
        line += f" — {derived}"
    return line


def render_block(facts: Optional[List[Dict[str, Any]]] = None) -> str:
    """Render the world-facts block for injection into document_context.

    Returns "" when there are no valid facts, so the document context is
    unchanged in that case.
    """
    facts = load_facts() if facts is None else facts
    if not facts:
        return ""
    lines = [_format_fact_line(f) for f in facts]
    return (
        "\n" + "=" * 60 + "\n"
        "WORLD FACTS — real current South African costs. Reason AGAINST these.\n"
        "These are true figures. Do NOT invent your own prices, and never claim a\n"
        "rand amount buys more than these figures allow. Weigh them against YOUR\n"
        "own income and budget in your own words.\n"
        + "=" * 60 + "\n"
        + "\n".join(lines)
        + "\n" + "=" * 60 + "\n"
    )


def promote_fact(
    item: str,
    value: float,
    unit: str,
    source: str = "",
    derived: str = "",
    as_of: str = "",
    provenance: str = "curated",
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """Add or replace a fact in the curated file (used by the gap-promote step).

    Validates before writing, so a malformed fact can never enter the layer.
    Replaces any existing entry for the same item. Returns the written fact.
    """
    fact = {
        "item": item.strip(),
        "value": value,
        "unit": unit.strip(),
        "derived": derived.strip(),
        "source": source.strip(),
        "as_of": as_of.strip(),
        "provenance": provenance.strip().lower() or "curated",
    }
    if not is_valid_fact(fact):
        raise ValueError(f"promote_fact: invalid fact (need item + numeric value + unit): {fact!r}")

    p = os.path.abspath(path) if path else _facts_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {"version": 1, "currency": "ZAR", "facts": []}
    if not isinstance(data, dict):
        data = {"version": 1, "currency": "ZAR", "facts": list(data) if isinstance(data, list) else []}

    facts = data.setdefault("facts", [])
    facts[:] = [f for f in facts if (f.get("item") or "").strip() != fact["item"]]
    facts.append(fact)

    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"world-facts: promoted '{fact['item']}' = R{value} {unit} ({provenance})")
    return fact
