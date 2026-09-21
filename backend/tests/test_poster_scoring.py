"""Model-off tests for deterministic poster scoring."""

import importlib.util
import os
import sys

HERE = os.path.dirname(__file__)
PATH = os.path.normpath(os.path.join(HERE, "..", "app", "services", "poster_scoring.py"))


def _load():
    name = "poster_scoring_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ps = _load()


def test_no_llm_import():
    assert ps.module_has_no_llm_import() is True


def test_counts_exact_and_repeatable():
    labels = [
        {"label": "sign_up", "words": "join"},
        {"label": "buy", "words": "pay R50"},
        {"label": "visit", "words": "go online"},
        {"label": "sign_up", "words": "subscribe"},
    ]
    a = ps.score_ask_recall("sign_up", "buy", labels)
    b = ps.score_ask_recall("sign_up", "buy", labels)
    assert a == b
    assert a["understood"] == 3
    assert a["total"] == 4
    assert a["split"] is True


def test_primary_or_secondary_match_both_ways():
    labels = [{"label": "buy", "words": "x"}, {"label": "sign_up", "words": "y"}]
    out = ps.score_ask_recall("sign_up", "buy", labels)
    assert out["understood"] == 2
    out2 = ps.score_ask_recall("buy", "sign_up", labels)
    assert out2["understood"] == 2


def test_no_percentage_keys():
    findings = ps.build_findings(
        primary="sign_up",
        secondary="buy",
        persona_labels=[{"label": "visit", "words": "go", "name": "A", "segment": "youth"}],
        claims_implied="a December payout",
        claim_answers=["I saw the December payout"],
        trust_answers=["I do not trust the brand name"],
        attention_answers=["I would stop scrolling for this"],
    )
    blob = str(findings).lower()
    assert "percent" not in blob
    assert "probability" not in blob
    assert "rating" not in blob
    assert findings["understood"] == 0
    assert findings["total"] == 1
    assert findings["attention"]["said_they_would_stop"] == 1
    assert "does not predict sales" in findings["caveat"]


def test_label_action_from_text():
    assert ps.label_action_from_text("I think it wants me to subscribe") == "sign_up"
    assert ps.label_action_from_text("") == "unclear"


# Ten answers, five distinct objections. Union-find chaining used to collapse
# four people into a price complaint three of them never made, and the data
# cost objection vanished. Groups must not chain through a third answer.
CHAIN_ANSWERS = [
    "From only R50 is a trick — what is the real price?",
    "The price looks fake. From only is a trick.",
    "I do not know who holds the money.",
    "Who holds the money if something goes wrong?",
    "There is no word on data costs.",
    "My data is expensive and they never mention data costs.",
    "Are they registered with anyone?",
    "I want to know if they are registered.",
    "I would need proof before I trust this.",
    "No proof, no trust from me.",
]


def test_trust_blockers_do_not_chain_distinct_objections():
    """Chaining used to merge four people into a price complaint three of them
    never made ('4 of 10') and drop the data cost objection. Counts must stay
    honest: a group may not claim more people than share a content word in its
    name, and the known two-person objections must not inflate past 2.
    """
    blockers = ps.trust_blockers(CHAIN_ANSWERS)
    assert blockers, "expected at least one trust blocker group"
    for b in blockers:
        text = b if isinstance(b, str) else b.get("text", "")
        assert " — " in text, f"blocker missing count suffix: {b!r}"
        name, rest = text.rsplit(" — ", 1)
        count = int(rest.split()[0])
        low = name.lower()
        # The specific inflated groups from the round-5 failure.
        if "price" in low or "trick" in low:
            assert count == 2, f"price group chained: {b!r}"
        if "money" in low or "holds" in low:
            assert count == 2, f"money group chained: {b!r}"
        if "data" in low or "cost" in low:
            assert count == 2, f"data group chained: {b!r}"
        name_words = {
            w for w in low.split()
            if w.isalpha() and len(w) > 3
            and w not in (
                "with", "from", "this", "that", "they", "them",
                "know", "want", "need", "would", "only", "real",
            )
        }
        assert name_words, f"group name has no content word: {b!r}"
        hits = max(sum(1 for a in CHAIN_ANSWERS if w in a.lower()) for w in name_words)
        assert count <= hits, (
            f"group claims {count} people but its words only cover {hits}: {b!r}"
        )


def test_trust_blockers_tie_break_prefers_earlier_objections():
    """Equal counts must not fall to alphabet. Earliest voice in the room wins,
    so the price and money objections beat later ones of the same size."""
    blockers = ps.trust_blockers(CHAIN_ANSWERS)
    blob = " ".join(blockers).lower()
    assert "price" in blob or "trick" in blob or "fake" in blob, (
        f"earliest (price) objection lost the tie: {blockers}"
    )
    assert "money" in blob or "holds" in blob, (
        f"early money objection lost the tie: {blockers}"
    )


def test_trust_blockers_reports_total_groups_found():
    """Top three is a cut, not the whole room. Founders must see how many
    groups existed."""
    blockers = ps.trust_blockers(CHAIN_ANSWERS)
    assert getattr(blockers, "total_groups", 0) >= 5, (
        f"expected ≥5 groups on the chain fixture, got "
        f"{getattr(blockers, 'total_groups', None)}; top3={blockers}"
    )
    findings = ps.build_findings(
        primary="sign_up",
        persona_labels=[{"label": "sign_up", "words": "join"}],
        trust_answers=CHAIN_ANSWERS,
    )
    assert findings["trust_groups_found"] >= 5
    assert len(findings["trust_blockers"]) <= 3
