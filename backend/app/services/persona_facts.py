"""persona_facts — a library persona's prompt from their measured facts, picked by the pitch.

The model-written summary and background story sat in every prompt whatever was asked,
with wording and emphasis no survey backed. This builds the same slot from survey answers
instead, behind PERSONA_FACT_PROMPTS until a side-by-side run shows it helps:

  1. pitch_parts(question)       which parts of life the pitch touches (app/data/pitch_parts.json)
  2. picked_facts(profile, q)    the always-on facts, plus every fact tagged with one of those
                                 parts (tags and wording: model/persona.json, "prompt" blocks)
  3. render(profile, q)          each picked fact as one plain sentence

A pitch is read by every part it touches, not one subject: "a clinic, R150, book on
WhatsApp" pulls health AND money AND online facts, so adoption facts are not lost to a
health label. Relevance, never valence: a fact is picked because the pitch touches its
subject, not because it helps or hurts. No model writes or chooses anything here, and
there are no app imports, so it loads anywhere.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Pattern, Set, Tuple

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
_cache: Dict[str, Any] = {}
_PRICE_RE = re.compile(r"\bR\s?\d")

# Model-written text a fact prompt replaces. Custom agents are never touched.
STORY_FIELDS = ("persona", "background_story", "group_affiliation", "interested_topics",
                "voice_guide", "behavioral_tendencies")
HEADER = "WHAT IS TRUE ABOUT YOU (your own answers in national surveys):"
# A fact left out does not stay unknown: the model fills the gap with the most typical
# picture. A learner told "someone else decides the money" but not who, answered "my
# mother" in both runs, while her record says she lives with her grandparent. Who a
# person lives with is now always said (core), and this line closes the rest.
NO_GUESSING = ("Only what is listed here is known about your life. Do not invent family "
               "members or people you live with who are not listed.")


def _load(name: str) -> Dict[str, Any]:
    if name not in _cache:
        with open(os.path.join(_DATA, name), encoding="utf-8") as fh:
            _cache[name] = json.load(fh)
    return _cache[name]


def enabled() -> bool:
    return os.environ.get("PERSONA_FACT_PROMPTS", "0").strip().lower() in ("1", "true", "yes", "on")


def uses_facts(profile: Any) -> bool:
    return (enabled() and isinstance(profile, dict)
            and profile.get("source_entity_type") == "library_persona")


def _pattern(word: str) -> Pattern[str]:
    if word.endswith("*"):
        return re.compile(r"\b" + re.escape(word[:-1].lower()))
    return re.compile(r"\b" + re.escape(word.lower()) + r"s?\b")


def _part_patterns() -> List[Tuple[str, bool, List[Pattern[str]]]]:
    if "_patterns" not in _cache:
        _cache["_patterns"] = [
            (part, bool(spec.get("price")), [_pattern(w) for w in spec["words"]])
            for part, spec in _load("pitch_parts.json")["parts"].items()
        ]
    return _cache["_patterns"]


def pitch_parts(question: str) -> List[str]:
    """Every part of life the pitch mentions, in pitch_parts.json order."""
    raw = question or ""
    text = raw.lower()
    return [part for part, price, patterns in _part_patterns()
            if (price and _PRICE_RE.search(raw)) or any(p.search(text) for p in patterns)]


def _candidates(profile: Dict[str, Any]) -> List[Tuple[str, Any, Dict[str, Any]]]:
    """(field, value, prompt block) for every fact this persona carries that can be said."""
    schema = _load("model/persona.json")
    out = []
    for name, spec in schema["fields"].items():
        block = spec.get("prompt")
        if block and profile.get(name) not in (None, "", []):
            out.append((name, profile[name], block))
    circumstances = schema["circumstance_row"]["fields"]
    for row in profile.get("circumstances") or []:
        if not isinstance(row, dict):
            continue
        block = circumstances.get(row.get("field"), {}).get("prompt")
        if not block or row.get("value") is None:
            continue
        # Circumstances come from the matched survey respondent, a different real
        # person from the household survey. Where the household survey answered the
        # same thing ("no computer at home"), it wins, or the prompt holds both.
        if profile.get(block.get("replaced_by")) is not None:
            continue
        out.append((row["field"], row["value"], block))
    return out


def say(value: Any, block: Dict[str, Any]) -> str:
    """One fact as its plain sentence, or "" when the model says nothing for this answer."""
    if str(value) in block.get("skip", []):
        return ""
    wording = block.get("say")
    if isinstance(wording, dict):
        key = str(value).lower() if isinstance(value, bool) else str(value)
        return wording.get(key, "")
    if not isinstance(wording, str):
        return ""
    if isinstance(value, list):
        shown = "; ".join(str(v) for v in value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        shown = f"{value:,.0f}".replace(",", " ")
    else:
        shown = str(value)
    return wording.format(value=shown)


def picked_facts(profile: Dict[str, Any], question: str) -> List[Dict[str, str]]:
    """{field, line, why} for each fact this persona brings to this question.

    why is "always" for the core facts, otherwise the pitch part that pulled it in.
    Core facts first, then schema order, so the same (persona, question) always gives
    the same lines.
    """
    parts = pitch_parts(question)
    core, tagged = [], []
    for field, value, block in _candidates(profile):
        if block.get("core"):
            why = "always"
        else:
            why = next((p for p in parts if p in block.get("about", [])), "")
        line = say(value, block) if why else ""
        if line:
            (core if why == "always" else tagged).append({"field": field, "line": line, "why": why})
    return core + tagged


def fields_used(profile: Dict[str, Any], question: str) -> List[str]:
    return [f["field"] for f in picked_facts(profile, question)]


def render(profile: Dict[str, Any], question: str) -> str:
    lines = [f["line"] for f in picked_facts(profile, question)]
    if not lines:
        return ""
    return HEADER + "\n" + "\n".join(f"- {line}" for line in lines) + "\n" + NO_GUESSING


def left_out(profile: Dict[str, Any], question: str) -> Set[str]:
    """Facts this persona carries that could be said but were not picked for this question."""
    used = set(fields_used(profile, question))
    return {field for field, _value, _block in _candidates(profile)} - used


def trim(mapping: Dict[str, Any], profile: Dict[str, Any], question: str) -> Dict[str, Any]:
    """A copy of a profile or agent-state dict without the story or the left-out facts.

    The agent framework serialises the whole profile and state into the system prompt,
    so leaving a fact out of the rendered lines is not enough on its own.
    """
    drop = left_out(profile, question)
    out = {k: v for k, v in mapping.items() if k not in drop and k not in STORY_FIELDS}
    if isinstance(out.get("circumstances"), list):
        out["circumstances"] = [r for r in out["circumstances"]
                                if not (isinstance(r, dict) and r.get("field") in drop)]
    return out
