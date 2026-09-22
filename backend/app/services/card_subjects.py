"""Which mechanism cards a pitch is about — topic tags first, a typed reader as backup.

`mechanism_card_service.topic_matches` decides, at prompt time, which of a
persona's bound cards survive. It looks for a card's `topic_tags` as whole words
in the pitch text. That is the same shape of filter `pitch_subjects` replaced
upstream, and it fails the same way.

Measured on the R150 clinic panel (panel_1a164ba02f62): the word lists admitted
the four health cards and dropped `youth-phone-safety-cost-economics`, whose
research is about what it costs someone to use their phone for something. The
pitch opens "You book on WhatsApp". A person sees that instantly; a list of tags
that says "phone, cellphone, smartphone, data" cannot, because the pitch never
uses any of those words. Asked the same question, the typed reader scored that
card 0.83 and every farming and schooling card below 0.02.

The discipline is exactly `pitch_subjects`:

  * **Union, never replacement.** The reader can ADD a card the tags missed; it
    can never remove one they found. A false positive costs a slot the cap was
    going to spend anyway. A false negative costs a persona their whole grounding
    on the question being asked, which is how a room ends up sounding invented.
  * **Off by default.** No key, no flag, or a failed call, and every caller gets
    precisely what the tags gave it before. Nothing here may become load-bearing.
  * **One read per pitch.** Twelve personas ask the same question about the same
    text, so the answer is memoized on the pitch rather than re-bought per agent.

A card is described to the reader by its `subject` line when it has one, and by
its topic tags otherwise. The line is human-authored and says what the research
is about in a sentence — the same job `_SUBJECT_MEANINGS` does in
`pitch_subjects`, and worth writing for the same reason: a bare tag dump reads
as keywords and scores like keywords.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set

from ..utils.logger import get_logger

logger = get_logger("fub.card_subjects")

# A card needs at least this much of the reader's probability to be added. Same
# floor as pitch_subjects, and high for the same reason: the tags already catch
# the obvious cases, so the reader is only here for the ones it is sure about.
MIN_PROBABILITY = 0.7

# Cards read in one request. All questions share the state, so the cost is the
# pitch plus a line per card — but a request carries one 32k budget, and a room
# should never spend it on cards nobody is bound to.
MAX_CARDS_PER_READ = 64

# question key -> answer, keyed by the pitch text. One pitch is read once, then
# every persona in the room reuses it.
_memo: Dict[str, Set[str]] = {}


def _typesafe():
    """The typed tier, or None. Imported the same lazy way `pitch_subjects` does
    it, so a script that loads this module standalone still works."""
    try:
        from ..utils import typesafe_client
    except (ImportError, ValueError):
        return None
    return typesafe_client


def typed_cards_enabled() -> bool:
    """OFF unless FUB_TYPED_CARDS is set and a key exists.

    Opt-in for the reason `pitch_subjects.typed_subjects_enabled` gives: `Config`
    loads the repo `.env` at import, so a key in a developer's file would put
    every test run on the network. The topic-tag path stays the default.
    """
    if (os.environ.get("FUB_TYPED_CARDS") or "").strip().lower() not in (
            "1", "true", "yes", "on"):
        return False
    ts = _typesafe()
    return bool(ts and ts.enabled())


def describe(card: Dict) -> str:
    """What this card is about, in the reader's terms.

    The human-written `subject` when the card has one; otherwise its topic tags,
    which is a weaker question and says so in the text it produces.
    """
    subject = (card.get("subject") or "").strip()
    if subject:
        return subject
    tags = [str(t) for t in (card.get("topic_tags") or []) if str(t).strip()]
    return ", ".join(tags[:8])


def read_cards(text: str, cards: List[Dict]) -> Set[str]:
    """The ids of cards a typed reader is confident this pitch touches.

    One noul (is-this-true) question per card, all in one request. Returns an
    empty set when the reader is off, fails, or is unsure — the caller's topic
    tags are what actually guarantee an answer.
    """
    if not text or not cards or not typed_cards_enabled():
        return set()
    ts = _typesafe()
    if not ts:
        return set()

    askable = [c for c in cards if c.get("id") and describe(c)][:MAX_CARDS_PER_READ]
    if not askable:
        return set()

    memo_key = f"{text}\x00{','.join(sorted(c['id'] for c in askable))}"
    if memo_key in _memo:
        return set(_memo[memo_key])

    questions = {
        card["id"]: ts.noul_question(
            f"This pitch involves {describe(card)}.",
            when_true="The pitch clearly involves that subject, even if it never "
                      "uses those exact words.",
            when_false="The pitch does not really involve that subject.",
        )
        for card in askable
    }

    try:
        answers = ts.ask(text, questions)
    except Exception as e:  # noqa: BLE001 — a reader that cannot be reached is a reader that is off
        logger.warning("Typed card read failed: %s", e)
        return set()
    if not answers:
        return set()

    found = {cid for cid in questions
             if (answers.get(cid) or {}).get("noul", 0.0) >= MIN_PROBABILITY}
    _memo[memo_key] = set(found)
    if found:
        logger.info("Typed cards: %s", ", ".join(sorted(found)))
    return set(found)


def widen(text: str, cards: List[Dict], tag_matched: Set[str],
          reader: Optional[Set[str]] = None) -> Set[str]:
    """The topic tags' answer, widened by anything the reader is sure they missed.

    `tag_matched` is passed in rather than computed here so the caller keeps its
    own tag match as the floor — this module adds, it does not own. `reader`
    overrides the read (the room-level path reads once and passes it down).
    """
    found = reader if reader is not None else read_cards(text, cards)
    return set(tag_matched) | set(found)


def reset_memo() -> None:
    """Forget every cached read. For tests, and for a long-lived process that
    should not hold pitch text indefinitely."""
    _memo.clear()
