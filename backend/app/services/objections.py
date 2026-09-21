"""What a panel response pushes against, and what it leans toward — LLM-free.

Two layers, both deterministic, both reading the same data file
(`app/data/objection_vocab.json`):

**Mention layer — `classify` / `tally` / `top` / `is_condition`.**
Detects what a response TALKS ABOUT, not how it feels about it. A response
mentioning "branch" raises `no_human_support` whether it wants one or is glad to
skip it. This is the scoring path for the segment-contrast benchmark
(`backend/scripts/classify_objections.py`, pinned by
`tests/test_classifier_reproduction.py`), so its behaviour must not drift: the
published table was computed with exactly these words and exactly this matching.

**Reading layer — `read` / `top_walls` / `top_pulls`.**
What the product surfaces (fit card, hypothesis report) use. Mention-counting
logged five of six plain compliments as complaints ("I love that it's free" →
"watching the fees"), so a wall here needs three things:

  1. **A cue in the sentence**, not somewhere in the paragraph. A complaint in line
     one and praise in line five no longer blur into one lump.
  2. **A mood beside it.** A wall needs a leaning-away marker in that sentence
     (a condition, a refusal, a worry); a benefit needs no wall marker. A sentence
     with neither is not counted as a complaint — silence beats a wrong label.
  3. **Grounds in the person's own record**, when a profile is supplied. A persona
     who owns a car and lives in a metro has no grounds for "costs something just
     to reach it", however the model phrased their answer.

Pulls are the same method pointed the other way, so praise has somewhere to land.

Every type is keyed to a person's situation, never a sector. The vocabulary is data:
new types from fieldwork are new rows in the JSON file, not code.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

_VOCAB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "objection_vocab.json")

with open(_VOCAB_PATH, encoding="utf-8") as _fh:
    _DATA = json.load(_fh)

# ── Tables, in file order (the UI tie-break and the benchmark row order) ─────
# A wall marked `reading_only` exists for the product screens and is kept OUT of the
# mention layer, so adding one never moves the benchmark table.
OBJECTION_TYPES: Tuple[str, ...] = tuple(
    k for k, v in _DATA["walls"].items() if not v.get("reading_only"))
READING_WALL_TYPES: Tuple[str, ...] = tuple(_DATA["walls"])
LABELS: Dict[str, str] = {k: v["label"] for k, v in _DATA["walls"].items()}
VOCAB: Dict[str, List[str]] = {k: list(v["cues"]) for k, v in _DATA["walls"].items()}

PULL_TYPES: Tuple[str, ...] = tuple(_DATA["pulls"])
PULL_LABELS: Dict[str, str] = {k: v["label"] for k, v in _DATA["pulls"].items()}
PULL_VOCAB: Dict[str, List[str]] = {k: list(v["cues"]) for k, v in _DATA["pulls"].items()}

GROUNDS: Dict[str, List[Dict[str, List[str]]]] = {
    **{k: v.get("grounds", []) for k, v in _DATA["walls"].items()},
    **{k: v.get("grounds", []) for k, v in _DATA["pulls"].items()},
}

_CONDITION_MARKERS: Tuple[str, ...] = tuple(_DATA["markers"]["condition"])


# ── Mention layer (benchmark contract — do not change its behaviour) ─────────

def classify(text: str) -> List[str]:
    """Objection types this one response mentions, in OBJECTION_TYPES order."""
    if not text:
        return []
    lower = text.lower()
    return [
        otype for otype in OBJECTION_TYPES
        if any(word in lower for word in VOCAB[otype])
    ]


def tally(responses: List[str]) -> Dict[str, int]:
    """How many of these responses mention each objection type.

    Only types that actually appear are keys — a zero row carries no signal.
    """
    counts: Dict[str, int] = {}
    for text in responses:
        for otype in classify(text):
            counts[otype] = counts.get(otype, 0) + 1
    return counts


def top(responses: List[str], limit: int = 3) -> List[Dict[str, object]]:
    """The objection types this room kept mentioning, most-raised first.

    Returns `[{"id", "label", "count"}]`. Ties break on OBJECTION_TYPES order so
    the same round always renders the same card.
    """
    return _rank(tally(responses), OBJECTION_TYPES, LABELS, limit)


def is_condition(text: str) -> bool:
    """True when the response frames its objection as a condition to satisfy."""
    if not text:
        return False
    lower = text.lower()
    return any(marker in lower for marker in _CONDITION_MARKERS)


# ── Grounds: which measured facts entitle a person to a wall or a pull ───────

def persona_facts(profile: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Flatten one persona to {field: value} over circumstances + attitudes + geotype."""
    facts: Dict[str, str] = {}
    if not isinstance(profile, dict):
        return facts
    for row in profile.get("circumstances") or []:
        if isinstance(row, dict) and row.get("field"):
            facts[row["field"]] = str(row.get("value"))
    for row in profile.get("attitudes") or []:
        if isinstance(row, dict) and row.get("topic") and row.get("stance"):
            facts[row["topic"]] = str(row["stance"])
    if profile.get("geotype"):
        facts["geotype"] = str(profile["geotype"])
    return facts


def has_grounds(type_id: str, facts: Dict[str, str]) -> Optional[bool]:
    """True/False if the person is entitled to this type; None if untestable.

    Clauses are OR: any one satisfied is grounds. Untestable means there is no rule,
    or the person carries none of the fields the rule reads — and an untestable type
    is kept, never dropped, because absence of data is not evidence against them.
    """
    clauses = GROUNDS.get(type_id)
    if not clauses:
        return None
    seen_any_field = False
    for clause in clauses:
        for field, allowed in clause.items():
            if field in facts:
                seen_any_field = True
                if facts[field] in allowed:
                    return True
    return False if seen_any_field else None


# ── Reading layer ────────────────────────────────────────────────────────────

def _compile(words) -> "re.Pattern[str]":
    """Match at a word START (so 'reliab' still finds 'reliable') but never inside a
    word — the mention layer's plain substring match found 'rate' in 'great' and
    'fare' in 'welfare'."""
    alternation = "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))
    return re.compile(r"(?<![a-z0-9])(?:" + alternation + r")")


_WALL_STRONG = _compile(_DATA["markers"]["wall_strong"])
_PULL = _compile(_DATA["markers"]["pull"])
_WALL_WEAK = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(re.escape(w) for w in _DATA["markers"]["wall_weak"])
    + r")(?![a-z0-9])")
_WALL_CUES = {t: _compile(VOCAB[t]) for t in READING_WALL_TYPES}
_PULL_CUES = {t: _compile(PULL_VOCAB[t]) for t in PULL_TYPES}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Model output uses typographic apostrophes (I’d, can’t) while every cue and
# marker is typed with a straight one, so without this "I'd tell", "can't" and
# "won't" silently never matched.
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})

# An explicit refusal to pass something on. Word of mouth is read by what the person
# says they would DO, so "I'd keep it to myself rather than tell anyone" must not
# count as telling, whatever the rest of the sentence leans.
_WOM_REFUSAL = re.compile(
    r"(?<![a-z0-9])(?:wouldn't|would not|won't|will not|not|never|rather than)\s+"
    r"(?:\w+\s+){0,2}(?:tell|mention|recommend|share|spread)"
    r"|keep (?:it|this|my thoughts|my views) to myself")


def _mood(sentence: str) -> str:
    """'wall', 'pull' or 'none' for one lowercased sentence.

    Order matters and is deliberate: a strong leaning-away marker (a condition, a
    refusal, a worry) wins outright; then a leaning-in marker; then a bare negation
    or requirement ("no branch", "I need someone"). "No monthly fee" is listed as a
    pull marker so it is read before the bare "no" can turn it into a complaint.
    """
    if _WALL_STRONG.search(sentence):
        return "wall"
    if _PULL.search(sentence):
        return "pull"
    if _WALL_WEAK.search(sentence):
        return "wall"
    return "none"


def read(text: str, facts: Optional[Dict[str, str]] = None) -> Dict[str, List[str]]:
    """The walls and pulls one response actually expresses.

    A wall needs a wall-mood sentence containing its cue. A pull needs its cue in a
    sentence that is NOT leaning away — a plain "it's close by" reads as a benefit.
    With `facts`, types the person has no grounds for are dropped.
    """
    walls, pulls = set(), set()
    for raw in _SENTENCE_SPLIT.split(text or ""):
        sentence = raw.strip().lower().translate(_APOSTROPHES)
        if not sentence:
            continue
        if _mood(sentence) == "wall":
            walls.update(t for t, cue in _WALL_CUES.items() if cue.search(sentence))
        else:
            pulls.update(t for t, cue in _PULL_CUES.items()
                         if t != "would_recommend" and cue.search(sentence))
        # Word of mouth follows the stated action, not the sentence's general mood:
        # "I'd tell my sister, just to ask if she's heard of it — not to send her
        # blindly" hedges around telling; it is not a complaint. A warning or an
        # explicit refusal is never counted as telling.
        if (_PULL_CUES["would_recommend"].search(sentence)
                and not _WALL_CUES["would_warn_others"].search(sentence)
                and not _WOM_REFUSAL.search(sentence)):
            pulls.add("would_recommend")
    if facts is not None:
        walls = {t for t in walls if has_grounds(t, facts) is not False}
        pulls = {t for t in pulls if has_grounds(t, facts) is not False}
    return {
        "walls": [t for t in READING_WALL_TYPES if t in walls],
        "pulls": [t for t in PULL_TYPES if t in pulls],
    }


def _read_all(kind: str, responses: List[str],
              profiles: Optional[List[Optional[Dict[str, Any]]]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for i, text in enumerate(responses or []):
        profile = profiles[i] if profiles and i < len(profiles) else None
        facts = persona_facts(profile) if profile else None
        for t in read(text, facts)[kind]:
            counts[t] = counts.get(t, 0) + 1
    return counts


def top_walls(responses: List[str],
              profiles: Optional[List[Optional[Dict[str, Any]]]] = None,
              limit: int = 3) -> List[Dict[str, object]]:
    """The walls this room kept hitting — mood-aware, and grounded when `profiles`
    (a list parallel to `responses`) is supplied. Same shape as `top`."""
    return _rank(_read_all("walls", responses, profiles), READING_WALL_TYPES, LABELS, limit)


def top_pulls(responses: List[str],
              profiles: Optional[List[Optional[Dict[str, Any]]]] = None,
              limit: int = 3) -> List[Dict[str, object]]:
    """What drew this room in — the same method as `top_walls`, pointed the other way."""
    return _rank(_read_all("pulls", responses, profiles), PULL_TYPES, PULL_LABELS, limit)


def word_of_mouth(responses: List[str],
                  profiles: Optional[List[Optional[Dict[str, Any]]]] = None) -> Dict[str, int]:
    """How many people said they would pass it on, and how many would warn others off.

    A plain count of what people said, never a likelihood. Both halves are grounded in
    the person's measured `social_voice` (Afrobarometer Q8 + Q10B): someone whose record
    shows they never talk things over with others is not counted as spreading the word,
    however their answer was phrased. `heard` is answers read, not seats.
    """
    tell = warn = heard = 0
    for i, text in enumerate(responses or []):
        if not (text or "").strip():
            continue
        heard += 1
        profile = profiles[i] if profiles and i < len(profiles) else None
        reading = read(text, persona_facts(profile) if profile else None)
        tell += "would_recommend" in reading["pulls"]
        warn += "would_warn_others" in reading["walls"]
    return {"would_tell": tell, "would_warn": warn, "heard": heard}


def _rank(counts: Dict[str, int], order_types: Tuple[str, ...],
          labels: Dict[str, str], limit: int) -> List[Dict[str, object]]:
    order = {t: i for i, t in enumerate(order_types)}
    ranked = sorted(counts, key=lambda t: (-counts[t], order[t]))
    return [{"id": t, "label": labels[t], "count": counts[t]} for t in ranked[:limit]]
