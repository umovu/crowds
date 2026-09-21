"""Review findings, encoded as tests.

Every test in this file exists because a review found the behaviour wrong in
real output. These are the contract, not suggestions.

LOCKED. The executor may not edit, weaken, skip or delete anything in this
file. If a test here is believed to be wrong, say so in the proof-of-work
under `disputed` and leave it red. Making the gate green by changing the
test is the one failure mode this file exists to prevent.

Each test names the round it came from and the real output that failed.
"""

import importlib.util
import os
import sys

HERE = os.path.dirname(__file__)
PATH = os.path.normpath(os.path.join(HERE, "..", "app", "services", "poster_scoring.py"))

# Filler words that are not objections. A trust blocker built from these is
# noise dressed up as a finding.
STOPWORDS = {
    "they", "them", "this", "that", "there", "would", "could", "should",
    "know", "think", "just", "very", "really", "thing", "things", "does",
    "have", "with", "from", "about", "what", "when", "then", "than", "want",
    "like", "make", "made", "your", "youre", "dont", "cant", "wont", "some",
    "much", "more", "also", "even", "into", "over", "been", "being", "which",
}


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


# --- Round 2, blocker 1 -----------------------------------------------------
# Real output on the answers below was:
#   ['holds money', 'they they', 'know they']
# Two of three are word fragments nobody said. A founder reading "they they"
# as a top trust blocker stops believing the whole screen.

TRUST_ANSWERS = [
    "I do not know who they are or who holds the money.",
    "I would want to know who is behind this and who holds my money.",
    "They do not say who they are. I would need proof.",
    "I do not trust it because they do not say who they are.",
    "There is no data cost mentioned and my data is expensive.",
    "It does not say what happens to my data bundle.",
]


def test_trust_blockers_are_not_stopword_noise():
    """No blocker may be built only from filler words."""
    for blocker in ps.trust_blockers(TRUST_ANSWERS):
        text = blocker if isinstance(blocker, str) else blocker.get("text", "")
        words = [w for w in text.lower().split() if w.isalpha()]
        assert words, f"empty trust blocker: {blocker!r}"
        assert not all(w in STOPWORDS for w in words), (
            f"trust blocker is filler, not an objection: {blocker!r}"
        )


def test_trust_blockers_repeat_a_word_the_people_actually_used():
    """A blocker must echo a content word from the answers it groups."""
    joined = " ".join(TRUST_ANSWERS).lower()
    for blocker in ps.trust_blockers(TRUST_ANSWERS):
        text = blocker if isinstance(blocker, str) else blocker.get("text", "")
        content = [
            w for w in text.lower().split()
            if w.isalpha() and len(w) > 3 and w not in STOPWORDS
        ]
        assert content, f"trust blocker has no content word: {blocker!r}"
        assert any(w in joined for w in content), (
            f"trust blocker uses words nobody said: {blocker!r}"
        )


def test_trust_blockers_surface_the_two_real_objections():
    """The two objections in TRUST_ANSWERS are 'who holds the money' and
    'data cost'. Both must appear."""
    blob = " ".join(
        b if isinstance(b, str) else b.get("text", "")
        for b in ps.trust_blockers(TRUST_ANSWERS)
    ).lower()
    assert "money" in blob or "holds" in blob, "missed the 'who holds the money' objection"
    assert "data" in blob, "missed the 'data cost' objection"


# --- Round 2, blocker 2 -----------------------------------------------------
# label_action_from_text broke ties by ACTION_KEYWORDS insertion order, and
# "buy" was first. Real output:
#   "It wants me to sign up and pay R50 a month" -> buy
# On a poster whose only ask is sign_up, everyone who mentions the price is
# then counted as a misread. The number moves down when the poster gets
# clearer — the tool punishes the fix.

def test_mixed_answer_prefers_the_named_action_over_the_price():
    assert ps.label_action_from_text(
        "It wants me to sign up and pay R50 a month"
    ) == "sign_up"


def test_mixed_answer_word_order_does_not_decide():
    assert ps.label_action_from_text(
        "It wants me to pay R50 a month and sign up"
    ) == "sign_up"


def test_price_alone_is_still_buy():
    """The fix must not swing the other way: a pure price answer is buy."""
    assert ps.label_action_from_text(
        "It is asking me to pay R50 every month"
    ) == "buy"


def test_label_is_not_decided_by_dict_order():
    """Two answers naming different single actions must not collapse onto
    whichever label happens to be declared first."""
    assert ps.label_action_from_text("It wants me to vote") == "vote"
    assert ps.label_action_from_text("It wants me to donate") == "donate"
    assert ps.label_action_from_text("It wants me to attend on Saturday") == "attend"


# --- Round 2, blocker 3 -----------------------------------------------------
# "r50" was hardcoded into ACTION_KEYWORDS["buy"] — the example poster's own
# price baked into the scorer. It makes one poster behave differently from
# every other one, silently.

def test_no_example_poster_words_hardcoded():
    source = open(PATH, encoding="utf-8").read().lower()
    for banned in ("r50", "r500", "thuto", "thutor", "r7 000", "r7000"):
        assert banned not in source, (
            f"example poster's own words hardcoded in the scorer: {banned!r}"
        )


def test_currency_amounts_are_matched_by_shape_not_by_value():
    """Whatever replaces the hardcoded price must work on any amount."""
    assert ps.label_action_from_text("It wants R20 a month from me") == "buy"
    assert ps.label_action_from_text("It wants R1 250 up front") == "buy"


# --- Round 2, carried non-blocker -------------------------------------------
# claims_stated kept the "States outright:" prompt scaffolding, which the
# human then sees in the edit box.

def test_claims_stated_has_no_prompt_scaffolding():
    # poster_service uses relative imports, so it loads as part of the package.
    backend = os.path.normpath(os.path.join(HERE, ".."))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
    from app.services import poster_service as mod

    brief = (
        "TEXT ON THE POSTER\nSubscribe at the site.\n\n"
        "WHAT IS PICTURED\nA learner.\n\n"
        "LAYOUT\nHeadline first.\n\n"
        "CLAIMS\nStates outright: lessons are aligned to the curriculum. "
        "Implies: the coins can be turned into cash.\n\n"
        "THE ASK\nSubscribe on the website.\n\n"
        "PRICE SHOWN\nnone\n"
    )
    fields = mod.parse_brief(brief)
    assert not fields["claims_stated"].lower().startswith("states outright"), (
        "prompt scaffolding leaked into the field the human edits"
    )
    assert "curriculum" in fields["claims_stated"]
    assert "cash" in fields["claims_implied"]


# --- Round 7, live run: the prompt, not the parser --------------------------
# First real vision call, on the Thuto poster. The plumbing held: all seven
# fields populated, claims_implied non-empty, price clean, headings parsed.
# What failed was READ_PROMPT — it never teaches the model the rules we wrote
# down in the plan. These tests assert the prompt carries the rule. They cannot
# assert the model obeys it; only a live run can do that.

def _read_prompt() -> str:
    backend = os.path.normpath(os.path.join(HERE, ".."))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
    from app.services import poster_service
    return poster_service.READ_PROMPT


# Live output: "secondary action: none" on a poster whose R50 price bubble is
# the second-largest element. My hand analysis says secondary is `buy`.
# Cause: the prompt lists the labels but never says WHEN a secondary applies.
# Effect: everyone who says "it wants R50 a month" is scored as a misread —
# the round 4 false-misread bug arriving through a different door.

def _labels_section(prompt: str) -> str:
    """Only the LABELS block. Scoping matters: 'separately' appears in CLAIMS
    and 'three' appears in 'exactly three lines', so an unscoped search passes
    for the wrong reason. A test that passes by accident is worse than none."""
    return prompt.lower().split("labels")[-1]


def test_prompt_says_when_a_secondary_action_applies():
    section = _labels_section(_read_prompt())
    assert "secondary" in section
    # It must describe the trigger, not just permit the field.
    assert any(w in section for w in ("prominent", "separate place", "its own",
                                      "second place", "own spot", "elsewhere")), (
        "the LABELS section never says when a secondary action applies"
    )


def test_prompt_names_a_price_as_a_possible_second_ask():
    """The most common real case: a button says join, a bubble shows a price."""
    p = _read_prompt().lower()
    assert "price" in p.split("labels")[-1] or "amount" in p.split("labels")[-1], (
        "the LABELS section never mentions a price as a possible second ask"
    )


def test_prompt_caps_secondary_at_one():
    section = _labels_section(_read_prompt())
    assert any(w in section for w in ("more than two", "three things", "three asks",
                                      "two asks", "only one second", "never more")), (
        "the LABELS section does not say what to do when a poster asks three things"
    )


# Live output for the implied half was:
#   "the app helps improve school performance and builds financial skills"
# That is close to a restatement of what the poster says outright. The real
# implications — coins convert to cash, you might earn back more than you pay,
# "most rewarding" reads as proven, "from only" hides the real price — were all
# missed. This is the highest-value output in the feature.

def test_prompt_pushes_for_unstated_inference_not_restatement():
    p = _read_prompt().lower()
    claims = p.split("claims")[-1].split("the ask")[0]
    assert "implies" in claims or "imply" in claims
    assert any(w in claims for w in ("not stated", "does not say", "never says",
                                     "without saying", "unstated")), (
        "CLAIMS section does not push for what the poster avoids saying outright"
    )


def test_prompt_forbids_repeating_a_stated_claim_as_implied():
    p = _read_prompt().lower()
    claims = p.split("claims")[-1].split("the ask")[0]
    assert any(w in claims for w in ("do not repeat", "must not repeat",
                                     "not the same", "different from")), (
        "nothing stops the model listing a stated claim again as an implication"
    )


# Live output: PRICE SHOWN returned "R50" and dropped "per month". A recurring
# charge and a once-off are different decisions for a person.

def test_prompt_asks_for_the_period_with_the_amount():
    p = _read_prompt().lower()
    price = p.split("price shown")[-1].split("labels")[0]
    assert any(w in price for w in ("per month", "how often", "period",
                                    "recurring", "once")), (
        "PRICE SHOWN does not ask whether an amount repeats"
    )


# --- Round 9, bake-off: temperature, not the model -------------------------
# Two rounds were spent chasing an unstable read. Same poster, same prompt,
# four live reads: secondary came back `buy` twice and `none` twice, and one
# implied half came back empty (round 1's original bug, unprompted).
#
# A ten-read bake-off at temperature 0 settled it:
#
#   qwen3-vl-235b-a22b-thinking   sign_up | buy | website   5/5 identical
#   qwen3-vl-32b-instruct         unclear | none | website  5/5 identical
#
# The instability was randomness we were asking for. Temperature was 0.2 on a
# copy-what-you-see job that needs none. The instruct model was stable too, and
# transcribed roughly twice as much text (1143-1203 chars vs 520-645) — but it
# called the ask `unclear` on a poster with a button reading "Subscribe at
# thuto.io", five times out of five. Getting the ask wrong is disqualifying.
#
# Cost: $0.0088/read thinking, $0.0043/read instruct.

def test_vision_reader_temperature_is_zero():
    """A poster read has one right answer on the page. No creativity dial."""
    backend = os.path.normpath(os.path.join(HERE, ".."))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
    from app.services.poster_service import VisionPosterReader

    reader = VisionPosterReader()
    assert reader.temperature == 0, (
        f"vision reads must be deterministic; temperature is {reader.temperature}. "
        "At 0.2 the same poster returned different labels across reads."
    )


def test_vision_reader_temperature_default_in_signature():
    """The default itself must be 0 — not 0 passed in by one caller."""
    import inspect
    backend = os.path.normpath(os.path.join(HERE, ".."))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
    from app.services.poster_service import VisionPosterReader

    sig = inspect.signature(VisionPosterReader.__init__)
    assert sig.parameters["temperature"].default == 0, (
        "the default must be 0 so a new call site cannot reintroduce drift"
    )
