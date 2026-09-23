"""Word of mouth is asked only of the people whose answer can count. LLM-off.

objections.word_of_mouth counts "would tell" and "would warn off" only where the
person's measured social_voice is mid or high. The question used to be appended to
the whole room's pitch: the rest were asked too, their answers were thrown away, and
on the R150 clinic panel 12 of 12 answers ended on "I'd tell my ...".

Now the room's shared question carries no ask, and the reframer adds it per person.
"""
import json
import os

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

import pytest  # noqa: E402

from app.services import belief_relevance, mode_specs, panel_service  # noqa: E402
from app.services.prompt_reframer import ImpactReframer  # noqa: E402

PITCH = ("A private clinic chain wants to launch a R150 pay-per-visit nurse service. "
         "You book on WhatsApp and see a nurse the same day.")
VOCAB = os.path.join(os.path.dirname(__file__), "..", "app", "data", "objection_vocab.json")


def _person(voice):
    attitudes = [{"topic": "social_voice", "stance": voice}] if voice else []
    return {"name": "Thandi", "age": 40, "attitudes": attitudes}


@pytest.fixture(params=["0", "1"], ids=["review", "decision"])
def framing(request, monkeypatch):
    monkeypatch.setenv("PANEL_DECISION_QUESTION", request.param)
    return request.param


def test_the_rooms_shared_question_carries_no_ask(framing):
    for mode in ("panel", "product", "policy"):
        assert "tell anyone" not in panel_service.frame_pitch(PITCH, mode)


def test_the_ask_follows_the_grounds_that_count_it():
    # If the vocab ever changes who can be counted, who gets asked must follow.
    vocab = json.load(open(VOCAB, encoding="utf-8"))

    def grounds(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("would_recommend", "would_warn_others"):
                    yield value["grounds"]
                else:
                    yield from grounds(value)

    found = list(grounds(vocab))
    assert len(found) == 2
    for rule in found:
        assert rule == [{"social_voice": list(mode_specs.WORD_OF_MOUTH_VOICES)}]


@pytest.mark.parametrize("voice,asked", [("high", True), ("mid", True), ("low", False), (None, False)])
def test_only_a_voice_that_can_count_is_asked(framing, voice, asked):
    framed = panel_service.frame_pitch(PITCH, "panel")
    prompt = ImpactReframer().reframe(framed, _person(voice), mode="panel", ask_word_of_mouth=True)
    assert ("tell anyone" in prompt) is asked


def test_a_sim_interview_is_never_asked(framing):
    prompt = ImpactReframer().reframe(PITCH, _person("high"), mode="policy", ask_word_of_mouth=False)
    assert "tell anyone" not in prompt


def test_the_ask_sits_before_the_length_rule(monkeypatch):
    monkeypatch.setenv("PANEL_DECISION_QUESTION", "1")
    framed = panel_service.frame_pitch(PITCH, "panel")
    prompt = ImpactReframer().reframe(framed, _person("high"), mode="panel", ask_word_of_mouth=True)
    assert prompt.index(mode_specs.WORD_OF_MOUTH_ASK) < prompt.index("Answer in at most")


def test_attitudes_as_a_plain_mapping_are_read_too():
    assert mode_specs.word_of_mouth_ask({"attitudes": {"social_voice": "high"}}, "product")
    assert not mode_specs.word_of_mouth_ask({"attitudes": {"social_voice": "low"}}, "product")


def test_the_shared_question_no_longer_reads_as_a_social_voice_subject(framing):
    # "tell anyone" is a social_voice trigger word, so our own boilerplate used to
    # spend a reaction slot on it for every persona, whatever was pitched.
    framed = panel_service.frame_pitch(PITCH, "panel")
    assert "social_voice" not in belief_relevance.relevant_dimensions(framed)
