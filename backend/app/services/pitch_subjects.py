"""What a pitch is about — keywords first, a typed reader as backup.

Three things downstream need the same answer to the same question:

  * which of a persona's measured facts reach their prompt (persona_facts)
  * what the local "NEAR YOU" search asks about (query_context)
  * which bound research cards survive the prompt-time filter (mechanism cards)

All three ask "what is this pitch about", and all three answered it by matching
word lists. Measured over 19 realistic pitches, the word lists missed 5 of the
11 that had a clear subject — and two of those misses were WRONG rather than
empty ("helping matriculants find their first pay cheque" read as cost, not
work), which is worse: the local search then goes and asks about the wrong
thing.

The misses are all the same shape. A founder writes "when the lights go out",
not "load-shedding"; "taps have been dry for weeks", not "water supply";
"scared to walk home after dark", not "crime". The subject is obvious to a
person and invisible to a word list.

So the word lists stay, and a typed reader (Jev) is asked the same question in
parallel. It is a CLASSIFIER and nothing else: it picks from a fixed list of
eight subjects and returns a probability per subject. It never writes a fact,
never decides who is in the room, and never says anything about a persona.

Union, never replacement: the reader can ADD a subject the words missed, but it
cannot take one away. A subject is a widening — one more thing the prompt may
mention, one more thing the search may ask about — so a false positive costs a
little relevance and a false negative costs the whole point. And it means the
keyword answer is a floor: with the reader off, broken, or unconfident, every
caller gets exactly what it got before.
"""

from __future__ import annotations

import os
from typing import List, Optional, Set

from ..utils.logger import get_logger

logger = get_logger("fub.pitch_subjects")

# A subject needs at least this much of the reader's probability to be added.
# High on purpose: the word lists already catch the obvious cases, so the reader
# is only here for the ones it is sure about.
MIN_PROBABILITY = 0.7

# What each subject means, in the reader's own terms. These descriptions ARE the
# classifier — a vague one ("money") invites everything, so each says what would
# make it true and the eight are written to be mutually distinguishable.
_SUBJECT_MEANINGS = {
    "health": "clinics, hospitals, illness, medicine, care, or a person's health",
    "work": "jobs, hiring, wages, being employed or unemployed, or earning a living",
    "cost": "prices, affordability, fees, or households managing money",
    "power": "electricity, blackouts, load-shedding, or keeping the lights on",
    "water": "water supply, taps, pipes, or sanitation",
    "safety": "crime, feeling safe, policing, or security",
    "migration": "foreigners, migrants, borders, or tension between communities",
    "poverty": "poverty, grants, going without, or people with very little",
}


def _typesafe():
    """The typed tier, or None. Imported the same lazy way `objections` does it,
    so a benchmark script that loads this module standalone still works."""
    try:
        from ..utils import typesafe_client
    except (ImportError, ValueError):
        return None
    return typesafe_client


def typed_subjects_enabled() -> bool:
    """OFF unless FUB_TYPED_SUBJECTS is set and a key exists.

    Opt-in for the same reason the typed wall reader is: `Config` loads the repo
    `.env` at import, so a key sitting in a developer's file would otherwise put
    every test run on the network — non-deterministic, slow and billed. The
    keyword path stays the default everywhere.
    """
    if (os.environ.get("FUB_TYPED_SUBJECTS") or "").strip().lower() not in (
            "1", "true", "yes", "on"):
        return False
    ts = _typesafe()
    return bool(ts and ts.enabled())


def read_subjects(text: str, vocabulary: Optional[List[str]] = None) -> Set[str]:
    """The subjects a typed reader is confident this pitch touches.

    One noul (is-this-true) question per subject, all in one request — the
    questions share the state, so asking eight costs barely more than asking
    one. Returns an empty set when the reader is off, fails, or is unsure;
    the caller's word list is what actually guarantees an answer.
    """
    if not text or not typed_subjects_enabled():
        return set()
    ts = _typesafe()
    if not ts:
        return set()

    wanted = [s for s in (vocabulary or list(_SUBJECT_MEANINGS))
              if s in _SUBJECT_MEANINGS]
    questions = {
        subject: ts.noul_question(
            f"This pitch is about {_SUBJECT_MEANINGS[subject]}.",
            when_true=f"The pitch clearly touches {subject}, even if it never uses that word.",
            when_false=f"The pitch does not really touch {subject}.",
        )
        for subject in wanted
    }

    try:
        answers = ts.ask(text, questions)
    except Exception as e:  # noqa: BLE001 — a reader that cannot be reached is a reader that is off
        logger.warning("Typed subject read failed: %s", e)
        return set()
    if not answers:
        return set()

    found = {s for s in wanted
             if (answers.get(s) or {}).get("noul", 0.0) >= MIN_PROBABILITY}
    if found:
        logger.info("Typed subjects: %s", ", ".join(sorted(found)))
    return found


def subjects(text: str, keyword_subjects: Set[str],
             vocabulary: Optional[List[str]] = None) -> Set[str]:
    """The word list's answer, widened by anything the reader is sure it missed.

    `keyword_subjects` is passed in rather than computed here so each caller
    keeps its own word list as the floor — this module adds, it does not own.
    """
    return set(keyword_subjects) | read_subjects(text, vocabulary)
