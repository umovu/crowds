"""belief_relevance — pick WHICH measured beliefs and reactions a persona brings to THIS question.

A fused persona carries a belief for every non-neutral attitude it holds — after the
belief-phrasing gap was closed, around eleven of them — and now a matching REACTION for
each. A prompt cannot take all of them, so both call sites used to truncate: the sim took
`beliefs[:8]`, the panel `beliefs[:3]`.

That is selection by POSITION, and beliefs render in ATTITUDE_VOCAB order, whose first
three entries are gov_trust, economic_optimism and service_satisfaction. So every persona
arrived at a panel holding exactly their three biggest grievances and nothing else, and
"I'll pay more if the service is genuinely better" — measured on 211 of 375 personas —
reached the panel prompt for none of them.

The fix is not a bigger cap. It is choosing by what the question is about:

  * **Relevance, never valence.** An item is selected because the question touches the
    thing it measures, not because it is encouraging or discouraging. The trigger words
    below name subject matter only.
  * **Balanced fill.** When fewer items match than the cap allows, the remainder is
    filled by alternating the person's own remaining items from each pole. An unmatched
    fill can no longer be all-grievance by accident.
  * **Deterministic.** No model, no weights to tune. The same (persona, question) always
    yields the same items, so a room is reproducible and this is assertable with the LLM
    switched off.

Nothing here writes, reorders or rewrites a sentence a persona holds. It only chooses
which of their own measured sentences are worth the prompt space for the question asked.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Subject matter each attitude dimension is about. Deliberately NOT sector-shaped: a
# question about a clinic, a bank and a school all reach `pays_for_quality` through the
# same price words, because what makes a fact relevant is the situation it describes,
# not the industry it came from.
_DIM_TRIGGERS: Dict[str, Tuple[str, ...]] = {
    "gov_trust": (
        "government", "state", "official", "department", "minister", "municipal",
        "municipality", "policy", "public sector", "sassa", "home affairs",
    ),
    "economic_optimism": (
        "afford", "income", "salary", "wage", "job", "work", "unemploy", "earn",
        "economy", "budget", "money", "grocer",
    ),
    "service_satisfaction": (
        "service", "water", "electricity", "power", "delivery", "refuse", "rubbish",
        "road", "sanitation", "municipal",
    ),
    "crime_fear": (
        "safe", "safety", "crime", "security", "theft", "steal", "rob", "danger",
        "walk home", "at night",
    ),
    "education_satisfaction": (
        "school", "learner", "pupil", "teacher", "class", "education", "matric",
        "study", "tutor", "homework", "bursary", "college", "university",
    ),
    "health_service_satisfaction": (
        "clinic", "hospital", "doctor", "nurse", "medicine", "medication", "health",
        "treatment", "medical", "patient", "diabet", "chronic", "prescription",
    ),
    "health_authority_trust": (
        "health department", "department of health", "clinic", "hospital", "vaccine",
        "medicine", "medication", "patient", "health",
    ),
    "councillor_responsiveness": (
        "councillor", "ward", "community meeting", "local government", "complain",
        "petition", "protest",
    ),
    "official_responsiveness": (
        "official", "department", "apply", "application", "register", "registration",
        "complain", "queue", "government office", "paperwork", "documents",
    ),
    "crime_handling": (
        "police", "crime", "safety", "security", "saps", "law enforcement",
    ),
    "immigration_priority": (
        "immigrant", "foreigner", "foreign national", "border", "nationals",
        "south africans first",
    ),
    "pays_for_quality": (
        "pay", "price", "cost", "fee", "charge", "afford", "month", "subscription",
        "premium", "worth", "cheap", "expensive", "r5", "r1", "r2", "r3", "r4",
        "rand", "free",
    ),
    "business_trust": (
        "company", "business", "brand", "startup", "private", "provider", "firm",
        "shop", "retailer", "insurer", "bank", "app",
    ),
    "social_trust": (
        "neighbour", "neighbor", "community", "friend", "family", "refer", "referral",
        "word of mouth", "recommend", "group", "stokvel",
    ),
    "environment_priority": (
        "waste", "recycl", "pollution", "green", "solar", "climate", "energy",
        "environment", "compost", "biodigester", "clean",
    ),
    # Word of mouth, and raising things with others — the second half is what makes
    # this land on service-delivery questions (who you complain to, who you rally).
    "social_voice": (
        "tell anyone", "tell others", "tell people", "word of mouth", "recommend",
        "spread the word", "share it", "raise it", "raise this", "complain", "report",
        "community meeting", "petition", "organise", "organize", "get together",
    ),
    "neighbour_trust": (
        "neighbour", "neighbor", "street", "next door", "word of mouth", "heard from",
        "people around", "recommend",
    ),
}

# Which band of each dimension is the discouraging one. Used ONLY to alternate the
# balanced fill — never to prefer one pole over the other, and never to score relevance.
_NEGATIVE_BAND = {
    "gov_trust": "low", "economic_optimism": "pessimistic",
    "service_satisfaction": "dissatisfied", "crime_fear": "high",
    "education_satisfaction": "dissatisfied", "health_service_satisfaction": "dissatisfied",
    "health_authority_trust": "low", "councillor_responsiveness": "low",
    "official_responsiveness": "low", "crime_handling": "dissatisfied",
    "business_trust": "low", "social_trust": "low", "pays_for_quality": "no",
    "neighbour_trust": "low",
}


def _load_tables() -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    """The build-time belief and reaction phrasing tables, imported lazily and tolerantly.

    `attitude_fuser` lives in backend/scripts (a build-time module, not part of the app
    package). Import failure is not fatal: with no tables every belief counts as unmapped
    and no reactions are derived, which degrades to order-preserving beliefs and the
    persona's own written text rather than an error in a sim.
    """
    try:
        import os
        import sys
        scripts = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "scripts"))
        if scripts not in sys.path:
            sys.path.append(scripts)
        from attitude_fuser import _BELIEF_PHRASING, _REACTION_PHRASING  # type: ignore
        return _BELIEF_PHRASING, _REACTION_PHRASING
    except Exception:  # noqa: BLE001 — absence is a degraded mode, not a failure
        return {}, {}


_TABLES: Optional[Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]] = None
_SENTENCE_DIM: Optional[Dict[str, Tuple[str, str]]] = None


def _tables():
    global _TABLES
    if _TABLES is None:
        _TABLES = _load_tables()
    return _TABLES


def _sentence_dim() -> Dict[str, Tuple[str, str]]:
    """Belief sentence -> (dimension, stance). Beliefs are stored as bare strings, so
    this is how a sentence is traced back to the thing it measures."""
    global _SENTENCE_DIM
    if _SENTENCE_DIM is None:
        _SENTENCE_DIM = {
            sentence: (dim, stance)
            for dim, bands in _tables()[0].items()
            for stance, sentence in bands.items()
        }
    return _SENTENCE_DIM


def dimension_of(belief: str) -> Optional[Tuple[str, str]]:
    """(dimension, stance) for a table-written belief, else None."""
    return _sentence_dim().get(belief)


def relevant_dimensions(question: str) -> List[str]:
    """Every attitude dimension whose subject matter the question mentions."""
    text = (question or "").lower()
    return [dim for dim, words in _DIM_TRIGGERS.items()
            if any(w in text for w in words)]


def _choose(items: List[Tuple[str, Optional[Tuple[str, str]]]],
            question: str, limit: int) -> List[str]:
    """Shared selection over (sentence, (dimension, stance) | None) pairs.

    Matched first, in stored order so the result is stable; then a balanced fill
    alternating poles. An item with no dimension — prose a human wrote — always counts
    as matched: nothing here may silently drop a sentence a person authored.
    """
    if limit <= 0 or not items:
        return []
    if len(items) <= limit:
        return [text for text, _pair in items]

    hot = set(relevant_dimensions(question))
    matched, negatives, positives = [], [], []
    for text, pair in items:
        if pair is None or pair[0] in hot:
            matched.append(text)
        elif pair[1] == _NEGATIVE_BAND.get(pair[0]):
            negatives.append(text)
        else:
            positives.append(text)

    chosen = matched[:limit]
    i = 0
    while len(chosen) < limit and (i < len(positives) or i < len(negatives)):
        for pool in (positives, negatives):
            if i < len(pool) and len(chosen) < limit:
                chosen.append(pool[i])
        i += 1
    return chosen


def select(beliefs: List[str], question: str, limit: int) -> List[str]:
    """The `limit` beliefs this persona should bring to this question."""
    beliefs = [b for b in (beliefs or []) if isinstance(b, str) and b.strip()]
    return _choose([(b, dimension_of(b)) for b in beliefs], question, limit)


def _stances(attitudes: Any) -> List[Tuple[str, str]]:
    """(dimension, stance) pairs from the library's attitude shapes, in stored order.

    Library rows are {topic, stance, ...}; a plain {topic: stance} dict is accepted too.
    Custom-agent rows carry a 0-10 rating and no vocab stance, so they yield nothing here
    and those agents keep the text their author wrote.
    """
    if isinstance(attitudes, dict):
        return [(str(k), str(v)) for k, v in attitudes.items() if v is not None]
    out: List[Tuple[str, str]] = []
    for row in attitudes or []:
        if isinstance(row, dict) and row.get("topic") and row.get("stance"):
            out.append((str(row["topic"]), str(row["stance"])))
    return out


def reactions(attitudes: Any) -> List[Tuple[str, Tuple[str, str]]]:
    """Every behaviour sentence this persona's measured attitudes produce, with its
    (dimension, stance). Neutral middles produce nothing. Read at prompt time — never
    stored — so a reworded sentence reaches every persona on the next run."""
    table = _tables()[1]
    return [(table[dim][stance], (dim, stance))
            for dim, stance in _stances(attitudes)
            if stance in table.get(dim, {})]


def reactions_for(attitudes: Any, question: str, limit: int) -> List[str]:
    """The reactions this persona brings to this question — ONLY the ones it touches.

    No balanced fill, unlike beliefs. A belief fill guards against an all-grievance
    outlook; a reaction is an instruction about what to DO, and an off-topic one is noise
    the model will try to act on ("safety rarely decides things for you", attached to a
    pitch that never mentions safety). A question that touches none of a persona's
    measured behaviour gets no reactions, and that is the honest answer.
    """
    if limit <= 0:
        return []
    hot = set(relevant_dimensions(question))
    return [text for text, (dim, _stance) in reactions(attitudes) if dim in hot][:limit]
