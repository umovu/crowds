"""The topic map is a judgement call — so hold it to the checks that CAN be made.

Which people are in a group is data (a predicate over real fields). Which topic
you FIND that group under is hand-authored, and nothing measures whether it is
"right". What can be asserted is that the arrangement is complete, consistent
and honest about itself — which is what catches the mistakes that actually
happen: a group filed nowhere, a topic that leads to an empty shelf, an
attitude card dressed up as a demographic one.

No LLM, no library rebuild.
"""
import pytest

from app.services import panel_service
from app.services.panel_service import SEGMENTS, SEGMENT_TOPICS


TOPIC_IDS = {t["id"] for t in SEGMENT_TOPICS}


def test_every_segment_is_filed_somewhere():
    """A group under no topic is unreachable in the picker — invisible, not gone."""
    orphans = [sid for sid, seg in SEGMENTS.items() if not seg.get("topics")]
    assert not orphans, f"segments with no topic: {orphans}"


def test_every_topic_a_segment_names_actually_exists():
    """A typo in the map files a card under a heading the picker never renders."""
    for sid, seg in SEGMENTS.items():
        unknown = set(seg.get("topics") or []) - TOPIC_IDS
        assert not unknown, f"{sid} claims unknown topic(s): {unknown}"


def test_every_topic_has_at_least_one_group():
    """An empty heading promises a room we cannot build."""
    for topic in TOPIC_IDS:
        members = [s for s in SEGMENTS.values() if topic in (s.get("topics") or [])]
        assert members, f"topic '{topic}' has no groups"


def test_topic_ids_are_unique():
    ids = [t["id"] for t in SEGMENT_TOPICS]
    assert len(ids) == len(set(ids))


def test_every_segment_declares_what_kind_it_is():
    """A measured attitude must never read as a demographic fact, so the picker
    badges them — which only works if every card says which it is."""
    for sid, seg in SEGMENTS.items():
        assert seg.get("kind") in ("who", "thinks"), f"{sid} has no kind"


def test_attitude_groups_are_backed_by_a_measured_dimension():
    """A 'what they think' card must filter on a real survey-decoded stance.

    This is the check that keeps the attitude family honest: if a group claims
    to be a measured view, some persona in the library must actually hold it.
    """
    library = panel_service.get_library().all()
    if not library:
        pytest.skip("library not built")
    for sid, seg in SEGMENTS.items():
        if seg.get("kind") != "thinks":
            continue
        pred = seg["predicate"]
        assert any(pred(p) for p in library), f"{sid} matches nobody in the library"


def test_the_pitch_word_lists_point_at_topics_that_exist():
    """The picker opens a topic from words in the pitch. A word list naming a
    topic that isn't in SEGMENT_TOPICS silently opens nothing."""
    # Mirrors TOPIC_WORDS in FlowHome.vue — kept here so a rename on either side
    # fails a test instead of quietly doing nothing.
    frontend_topics = {"health", "education", "environment",
                       "food", "safety", "government", "money"}
    assert frontend_topics <= TOPIC_IDS, frontend_topics - TOPIC_IDS


def test_list_segments_carries_the_map_to_the_ui():
    rows = panel_service.list_segments()
    assert rows, "no segments"
    for row in rows:
        assert row["topics"], f"{row['id']} reached the UI with no topic"
        assert row["kind"] in ("who", "thinks")


def test_a_single_tier_string_is_not_read_letter_by_letter():
    """`budget_tiers="loose"` is a plausible caller shape. Iterating the string
    would validate 'l', 'o', 'o'… and fail the whole session."""
    meta = panel_service.create_session(
        pitch="A home biodigester, R40 000 fitted",
        n=2, budget_tiers="loose", seed=1,
    )
    assert meta["budget_tier_filter"] == ["loose"]


def test_all_switches_the_affordability_lens_off():
    """The picker's "show everyone instead" — the operator's only say in it."""
    meta = panel_service.create_session(
        pitch="A home biodigester, R40 000 fitted",
        n=2, budget_tiers="all", seed=1,
    )
    assert "budget_tier_filter" not in meta
