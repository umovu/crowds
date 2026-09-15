"""
texture_generator — turn a mapped skeleton into a speakable persona (English only).

Stage 3 of the persona-library build, and the FIRST layer that uses the LLM. The
sampler + archetype_mapper produce demographically-honest bones; this writes the
human surface the sim needs to run an agent: name, persona sentence, background,
voice_guide, behavioral_tendencies, group_affiliation, interested_topics.

Design constraints (deliberate, and the reason this is the last LLM-touched layer):

  * **The skeleton is FIXED.** The prompt hands the model the demographic facts as
    immutable and forbids changing them. The model writes only texture, so the
    survey-grounded representativeness from stages 1–2 cannot be undone here.

  * **English only.** QLFS carries no language data, so any vernacular the model
    produced would be ungrounded (province != language; stereotype drift; not
    testable). We sidestep it: English register only — voice varies by archetype
    (vocab, formality, references, attitude), never by invented code-switching.
    Output is run through sanitize_language_drift() to strip any non-Latin leakage,
    and the validator asserts English-only. Multilingual is a future bolt-on
    (sample home language from Census, then constrain the model).

  * **Attitudes are EXPRESSED, not authored.** The model never invents a stance. But when
    the skeleton already carries measured attitudes (fused from Afrobarometer in the
    attitude_fuser stage), those are passed in as FIXED facts the voice/outlook must
    express — a survey-distrustful person must not be written as cheerful about
    government. The model still emits no attitudes/beliefs as JSON fields; it only lets
    them shape the prose. Scenario-specific stance is still layered at sim time on top of
    this measured baseline.

Uses the Plus tier (LLMClient default = LLM_*), since this is offline build, not the
sim hot path.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Optional

# Make backend importable when run as a script from backend/scripts/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.llm_client import LLMClient  # noqa: E402
import sa_names  # noqa: E402  — sibling script, LLM-free name pool
from sa_names import pick_unique_name  # noqa: E402

# Non-Latin script ranges — same set as document_context_engine.sanitize_language_drift.
# Inlined (not imported) so this offline build script doesn't pull the whole
# app.services package (and its agentsociety2 / env-var requirements) just for one
# regex. Keep in sync with document_context_engine if that set changes.
_NON_LATIN_RE = re.compile(
    "[一-鿿"
    "぀-ゟ"
    "゠-ヿ"
    "가-힯"
    "Ѐ-ӿ"
    "؀-ۿ"
    "ऀ-ॿ"
    "฀-๿"
    "]+"
)


def sanitize_language_drift(text: str, label: str = "") -> str:
    """Strip non-Latin script fragments that leak into English LLM output."""
    cleaned = _NON_LATIN_RE.sub(" ", text)
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    return cleaned

# Texture fields the model writes. Everything else on the persona comes from the
# skeleton (fixed) or a later stance pass. Kept explicit so the validator can check
# exactly these were produced and nothing demographic was overwritten.
# NOTE: "name" is deliberately NOT here. Names are assigned from a curated pool
# (sa_names.pick_unique_name), never authored by the LLM — independent LLM name
# generation mode-collapses onto a few prototypes (the "55 Thabo Mokoenas" bug).
TEXTURE_FIELDS = [
    "persona", "background_story",
    "group_affiliation", "interested_topics",
]
# voice_guide and behavioral_tendencies are no longer written here. They were the last
# persona fields with no survey data behind them, injected as orders into every answer.
# How a persona REACTS now comes from attitude_fuser._REACTION_PHRASING, read off the
# measured attitudes at prompt time. Existing values stay on old records untouched; the
# prompts no longer use them for library personas.
_RETIRED_TEXTURE_FIELDS = ("voice_guide", "behavioral_tendencies")

# Skeleton fields the model must NOT change (it may reference them, not rewrite them).
FROZEN_FIELDS = [
    "age", "gender", "province", "education", "occupation",
    "employment_status", "informal", "industry", "marriage_status",
    "is_neet", "actor_archetype", "race",
    # GHS education-build facts (absent on civic personas — None is skipped).
    # All REAL surveyed circumstances the texture must write around, not invent:
    "geotype", "home_language", "monthly_household_income_rand",
    "internet_at_home", "computer_in_home", "receives_grant",
    "ghs_role", "edu_institution", "current_grade", "fees_band",
    "time_to_school", "guardian_type", "learners_in_household",
    "learner_fee_bands", "guards_grandchildren", "occupation_provenance",
    # GHS health-build facts (absent where unasked — None is skipped). REAL reported
    # health circumstances the texture must write around, never contradict.
    "medical_aid", "self_rated_health", "has_disability",
    "usual_health_facility", "health_facility_sector",
    "transport_to_health_facility", "time_to_health_facility",
    "health_provenance",
    # Farmer-role facts (absent on non-farmer personas — None is skipped).
    "farm_market_orientation", "farm_products", "source_survey",
]

_SYSTEM = (
    "You are an expert in South African socio-economics writing realistic persona "
    "texture for a policy/product simulation. You are given FIXED demographic facts AND "
    "FIXED measured attitudes about a person and must write ONLY their human surface "
    "(a one-line summary and a background paragraph). You must NOT change, contradict, or "
    "restate-as-new any of "
    "the fixed facts. The measured attitudes are survey data, not yours to invent or "
    "override: write a voice and outlook that EXPRESS them — never a person who feels the "
    "opposite. Write in ENGLISH ONLY — no isiZulu, isiXhosa, Afrikaans, or other-language "
    "words or phrases. South Africans in this simulation converse in English; capture "
    "their distinct register, concerns, and references in English, not by code-switching. "
    "Return ONLY valid JSON."
)

# How a fused attitude stance reads as a fixed outlook the voice must express. Kept here
# (not sent as raw codes) so the model gets plain-language constraints, not a vocab it
# might mis-read. Only stances we carry appear; a missing dim simply isn't constrained.
_STANCE_GLOSS = {
    "gov_trust": {
        "low": "deeply distrusts government and officials",
        "mid": "is wary of government but not wholly cynical",
        "high": "broadly trusts government and local institutions",
    },
    "economic_optimism": {
        "pessimistic": "believes the economy and their own prospects are getting worse",
        "neutral": "sees the economy as flat — neither improving nor collapsing",
        "optimistic": "believes things are improving and they can get ahead",
    },
    "service_satisfaction": {
        "dissatisfied": "is frustrated that basic services in their area fail",
        "mixed": "finds local services patchy — some work, some don't",
        "satisfied": "finds basic services in their area mostly work",
    },
    "crime_fear": {
        "low": "does not see crime as a major daily worry",
        "mid": "is somewhat wary of crime",
        "high": "lives with crime as a constant daily threat",
    },
    "education_satisfaction": {
        "dissatisfied": "feels the education system is failing their community's children",
        "mixed": "sees both real effort and real failure in how local schools are run",
        "satisfied": "feels schools and education services are broadly doing their job",
    },
    # Health dimensions (Afrobarometer Q46G handling / Q37O_SAF trust).
    "health_service_satisfaction": {
        "dissatisfied": "feels public health services are failing people like them",
        "mixed": "sees public health care as patchy — some clinics deliver, some don't",
        "satisfied": "feels public health services broadly do their job",
    },
    "health_authority_trust": {
        "low": "does not trust the health department to look after patients",
        "mid": "is unsure whether the health department can be trusted",
        "high": "trusts the health department to do its job",
    },
    # Policy-mode dimensions (added with the WP2 attitude expansion).
    "councillor_responsiveness": {
        "low": "believes their local councillor never listens to people like them",
        "mid": "thinks their councillor listens only sometimes",
        "high": "feels their local councillor can be made to listen",
    },
    "official_responsiveness": {
        "low": "expects no help if they approach a government official",
        "mid": "is unsure whether officials would help if asked",
        "high": "believes officials would likely respond if they asked for help",
    },
    "crime_handling": {
        "dissatisfied": "thinks the government is handling crime very badly",
        "mixed": "sees the government's handling of crime as patchy",
        "satisfied": "thinks the government handles crime reasonably well",
    },
    "immigration_priority": {
        "low": "does not feel strongly that South Africans should be prioritised over immigrants",
        "mid": "has mixed feelings about prioritising South Africans over immigrants",
        "high": "strongly believes South Africans should be prioritised over immigrants for jobs and services",
    },
    # Product-mode dimensions.
    "pays_for_quality": {
        "no": "is not willing to pay more for better services — cost comes first",
        "mixed": "might pay more for better services, but only if convinced it's worth it",
        "yes": "is willing to pay more for a service that genuinely works better",
    },
    "business_trust": {
        "low": "assumes most companies and business executives are corrupt or out for themselves",
        "mid": "is cautious about companies but not wholly cynical",
        "high": "is relatively willing to trust reputable businesses",
    },
    "social_trust": {
        "low": "trusts other people very little — keeps their guard up with strangers and neighbours",
        "mid": "extends some trust to people they know, less to strangers",
        "high": "is fairly trusting of other people, including neighbours and strangers",
    },
    # Salience, not virtue — how near the issue sits to this person's life, never how
    # much they care about the planet. Matches the vocab's own framing in
    # attitude_donor_adapter.ATTITUDE_VOCAB.
    # Word of mouth, both directions. social_voice = whether they talk with others about
    # things that affect them and act with others (Q8 discuss politics + Q10B joined
    # others to raise an issue); neighbour_trust = whether a neighbour's word counts
    # (Q86C). Measured behaviour, never a personality claim.
    "social_voice": {
        "low": "keeps to themselves — rarely talks public matters over with others or joins "
               "others to raise an issue",
        "mid": "sometimes talks things over with others, and would join others to raise an "
               "issue if the chance came",
        "high": "often talks things over with others and has joined others to raise an issue",
    },
    "neighbour_trust": {
        "low": "does not trust their neighbours",
        "mid": "trusts their neighbours a little",
        "high": "trusts their neighbours",
    },
    "environment_priority": {
        "low": "has never had pollution or climate anywhere near their life — it is not "
               "something they think about",
        "mid": "notices waste and pollution around them, but it is not pressing",
        "high": "sees waste and pollution as a real problem where they live, and one "
                "ordinary people have to act on",
    },
}

# The measured circumstances, written as the sentences the PERSON would say. These are
# the raw material the background_story is assembled from: the model arranges and joins
# them, and may not add a fact that is not here (see _prompt). Only fields we carry
# appear; a field the donor didn't answer simply isn't stated.
#
# Two rules, and both matter more than they look:
#
#   1. State the fact, never judge it. No "unfortunately", no "at least", no
#      "struggles", no "comfortable". A fact carries no mood — only relevance.
#
#   2. State what IS, not what is absent. This table used to describe a person with
#      enough money as one who "has NOT gone without basic necessities", framing an
#      ordinary life in the vocabulary of hunger. Every positive band said what the
#      person lacked a lack of, so the model reached for hardship even when the record
#      held none. That was the single largest source of the library's negative skew.
_CIRCUMSTANCE_GLOSS = {
    "lived_poverty": {
        "none": "This year I've had enough for food, water and cash.",
        "low": "Once or twice this year I was short for something basic.",
        "moderate": "Several times this year I've been short for food, water or cash.",
        "high": "I'm often short for food, water or cash.",
    },
    "went_without_care": {
        "never": "I've been able to get medical care when I needed it.",
        "rarely": "Once or twice this year I couldn't get care I needed.",
        "sometimes": "Several times this year I couldn't get care I needed.",
        "often": "I often can't get medical care I need.",
    },
    "owns_vehicle": {
        "none": "There's no car in the house.",
        "household": "There's a car in the house I can use.",
        "own": "I have my own car.",
    },
    "owns_computer": {
        "none": "There's no computer in the house.",
        "household": "There's a computer in the house I share.",
        "own": "I have my own computer.",
    },
    "owns_bank_account": {
        "none": "I don't have a bank account.",
        "household": "I use someone else's account in the house.",
        "own": "I have my own bank account.",
    },
    "owns_television": {
        "none": "There's no TV in the house.",
        "household": "There's a TV in the house.",
        "own": "I have my own TV.",
    },
    "internet_use": {
        "never": "I don't use the internet.",
        "rarely": "I go online less than once a month.",
        "monthly": "I go online a few times a month.",
        "weekly": "I go online a few times a week.",
        "daily": "I'm online every day, mostly on my phone.",
    },
    "owns_phone": {
        "none": "There's no cellphone in the house.",
        "household": "I use a cellphone that someone else in the house owns.",
        "own": "I have my own cellphone.",
    },
    "phone_internet": {
        "no": "My phone can't go on the internet.",
        "yes": "My phone can go on the internet.",
    },
    "phone_use": {
        "never": "I never use a cellphone.",
        "rarely": "I hardly ever use a cellphone.",
        "monthly": "I use a cellphone now and then.",
        "weekly": "I use a cellphone most weeks.",
        "daily": "I use my cellphone every day.",
    },
    "electricity_reliability": {
        "never": "There's no reliable mains power where I live.",
        "occasional": "The power is on only now and then.",
        "half": "The power is on about half the time.",
        "most": "The power is on most of the time, with interruptions.",
        "always": "The power stays on where I live.",
    },
    "money_decision": {
        "self": "I decide how the money in my house is spent.",
        "joint": "We decide together how the money is spent.",
        "other": "Someone else decides how the money is spent.",
    },
    # Where a message can actually reach this person. Measured on every fused persona
    # and, until now, carried but never spoken.
    "news_radio": {
        "never": "I don't listen to the news on radio.",
        "rarely": "I hardly ever hear the news on radio.",
        "monthly": "I hear the radio news now and then.",
        "weekly": "I hear the radio news most weeks.",
        "daily": "The radio news is on every day.",
    },
    "news_tv": {
        "never": "I don't watch the news on TV.",
        "rarely": "I hardly ever watch the news on TV.",
        "monthly": "I see the TV news now and then.",
        "weekly": "I catch the TV news most weeks.",
        "daily": "I watch the TV news every day.",
    },
    "news_social": {
        "never": "I don't get news from social media.",
        "rarely": "I hardly ever see news on social media.",
        "monthly": "I see news on social media now and then.",
        "weekly": "I see news on social media most weeks.",
        "daily": "I see the news on social media every day.",
    },
    "news_internet": {
        "never": "I don't read news online.",
        "rarely": "I hardly ever read news online.",
        "monthly": "I read news online now and then.",
        "weekly": "I read news online most weeks.",
        "daily": "I read news online every day.",
    },
}


def _attitude_constraints(skeleton: Dict) -> List[str]:
    """Plain-language outlook lines from the skeleton's fused `attitudes`, for the prompt.
    Empty when no attitudes are attached (so this is a no-op on un-fused skeletons)."""
    lines = []
    for a in (skeleton.get("attitudes") or []):
        gloss = _STANCE_GLOSS.get(a.get("topic"), {}).get(a.get("stance"))
        if gloss:
            lines.append(f"- This person {gloss}.")
    return lines


# Measured, kept on the persona, but never handed to the story writer. These are REACH
# facts — which channel a message can arrive on — not autobiography. Left in the prompt
# they dominated it: every generated story ended in a media rundown, because a model
# given thirteen equal lines dutifully uses all thirteen. They stay on the record for
# targeting; they just don't belong in a paragraph about a life.
_STORY_EXCLUDED = {
    "news_radio", "news_tv", "news_social", "news_internet", "owns_television",
}


def _circumstance_constraints(skeleton: Dict) -> List[str]:
    """The person's own sentences for each measured circumstance, for the prompt.

    First person and already finished — the model arranges these, it does not
    re-describe them. Empty on un-fused skeletons or ones with no circumstances.
    """
    lines = []
    for c in (skeleton.get("circumstances") or []):
        if c.get("field") in _STORY_EXCLUDED:
            continue
        gloss = _CIRCUMSTANCE_GLOSS.get(c.get("field"), {}).get(c.get("value"))
        if gloss:
            lines.append(f"- {gloss}")
    return lines


def _prompt(skeleton: Dict) -> str:
    facts = {k: skeleton.get(k) for k in FROZEN_FIELDS if skeleton.get(k) is not None}
    attitude_lines = _attitude_constraints(skeleton)
    attitude_block = (
        "\nFIXED MEASURED ATTITUDES (survey data — the voice, background, and outlook you "
        "write MUST express these; do NOT write a person who feels the opposite, and do "
        "NOT restate them as new fields):\n" + "\n".join(attitude_lines) + "\n"
        if attitude_lines else ""
    )
    circumstance_lines = _circumstance_constraints(skeleton)
    circumstance_block = (
        "\nTHIS PERSON'S OWN SENTENCES (real survey facts, already written in their "
        "voice). These are the RAW MATERIAL for background_story: arrange them, join "
        "them, order them. Do not contradict one, and do not add a fact that is not "
        "here:\n" + "\n".join(circumstance_lines) + "\n"
        if circumstance_lines else ""
    )
    return f"""Write English-only persona texture for this South African individual.

FIXED FACTS (do not change, contradict, or invent around — write texture consistent
with exactly these):
{json.dumps(facts, ensure_ascii=False, indent=2)}

Unit note: fees_band / learner_fee_bands are ANNUAL school-fee amounts (per year);
monthly_household_income_rand is per month. If the texture mentions fees, it must
keep them annual — never restate a fee band as a monthly figure.
{attitude_block}{circumstance_block}
Produce a JSON object with ONLY these fields:
- persona: 1-2 sentences on who they are and their situation. Reference a real local
  setting consistent with the province. English only.
- background_story: ONE paragraph, 55-80 words, in FIRST PERSON ("I ..."), that ARRANGES
  the sentences you were given above into something a person would actually say aloud.
  Open with the fixed facts (age, schooling, work, province), then work the rest in.
  Three hard rules:
    * You may LEAVE OUT a fact that doesn't fit the flow. You may NEVER ADD one — no
      place, event, hardship, possession, service, employer or family member that is not
      in the lists above.
    * Do not choose what to include by whether it sounds good or bad. A comfortable
      record and a hard one both get written plainly.
    * No inventory sentences. Never list possessions ("I have my own car, my own
      computer, my own TV") and never string facts together with commas just to fit
      them all in. Fold them into natural speech, or leave them out.
  English only.
- group_affiliation: a plausible affiliation if the facts support one (e.g. a union,
  church, street committee, taxi association), else "".
- interested_topics: array of 3-5 topics this person cares about, in their words.

Do NOT output age, income, attitudes, beliefs, or emotions as JSON fields — those are
set elsewhere. (You must still let the measured attitudes shape the voice/outlook you
write above; just don't emit them as separate fields.)

HARD FENCE — nothing you write may name a thing this record does not contain. Before
mentioning load-shedding, water cuts, crime, taxis, grants, stokvels, hunger or a named
suburb, mall, employer or relative, check the lists above. If it is not there, leave it
out. A shorter true paragraph beats a vivid invented one; this record is the only South
Africa you know about.
Return ONLY the JSON object. English only."""


# ── Provenance fence ────────────────────────────────────────────────────────
# The prompt asks the model not to invent referents. Asking is not a rule, so this
# enforces it: a referent may appear in the texture only when a field in THIS person's
# record licenses it. Everything here is deterministic — the same discipline as
# attitude_fuser, applied to prose.
#
# The rules mirror backend/scripts/texture_provenance_audit.py, which audits the built
# library. Keep the two in step: the audit is the report, this is the gate.

def _circ(skeleton: Dict, field: str):
    for c in (skeleton.get("circumstances") or []):
        if c.get("field") == field:
            return c.get("value")
    return None


def _stance(skeleton: Dict, topic: str):
    for a in (skeleton.get("attitudes") or []):
        if a.get("topic") == topic:
            return a.get("stance")
    return None


# (pattern, label, license) — license(skeleton) is True when the record backs the claim.
_REFERENT_RULES = [
    (re.compile(r"load[- ]?shedding|power cuts?|rolling blackouts?", re.I), "load-shedding",
     lambda s: _circ(s, "electricity_reliability") in ("never", "occasional", "half", "most")),
    (re.compile(r"water outage|taps? run dry|water cuts?|no water", re.I), "water-outage",
     lambda s: False),  # nothing in the record measures water supply
    (re.compile(r"\bcrime\b|\bgangs?\b|robbery|hijack|mugg|break-?in", re.I), "crime",
     lambda s: _stance(s, "crime_fear") in ("mid", "high")
     or _stance(s, "crime_handling") == "dissatisfied"),
    (re.compile(r"\btaxis?\b|taxi rank|taxi fare", re.I), "taxi",
     lambda s: _circ(s, "owns_vehicle") == "none"
     or "taxi" in str(s.get("transport_to_health_facility") or "").lower()),
    (re.compile(r"\bgrants?\b|sassa", re.I), "grant",
     lambda s: bool(s.get("receives_grant"))),
    (re.compile(r"stokvel|society money", re.I), "stokvel",
     lambda s: False),  # nothing in the record measures savings-group membership
    (re.compile(r"\bhungry\b|went without food|skipped? meals?|go to bed hungry", re.I),
     "hunger",
     lambda s: _circ(s, "lived_poverty") in ("moderate", "high")),
]

# Every first name the pool can assign. The model is never told the person's name (it is
# picked after generation), so ANY of these appearing in the texture is an invented
# character — which is how 12 library personas ended up with a voice guide describing
# someone else.
_POOL_FIRST_NAMES = {
    n for bank in sa_names._BANKS.values()
    for key in ("female", "male")
    for n in bank.get(key, [])
}


# Only the prose THIS generator writes is gated. Retired fields (voice_guide,
# behavioral_tendencies) still sit on older records; checking them here would fail every
# regeneration of an old persona on text the model was never asked to produce.
_CHECKED_TEXT = [f for f in ("persona", "background_story") if f in TEXTURE_FIELDS]


def _texture_violations(merged: Dict) -> List[str]:
    """Everything in this persona's generated texture that its own record does not license."""
    problems: List[str] = []
    prose = " ".join(str(merged.get(f) or "") for f in _CHECKED_TEXT)

    for pattern, label, licensed in _REFERENT_RULES:
        if pattern.search(prose) and not licensed(merged):
            problems.append(f"unlicensed referent in prose: {label}")

    leaked = _POOL_FIRST_NAMES & set(re.findall(r"\b[A-Z][a-z]+\b", prose))
    if leaked:
        problems.append("invented person named: " + ", ".join(sorted(leaked)))
    return problems


def _strip_offending_sentences(merged: Dict) -> Dict:
    """Last resort when retries are exhausted: drop the sentences carrying an
    unlicensed referent rather than fail the persona or ship the claim."""
    bad = [p for p, _label, licensed in _REFERENT_RULES if not licensed(merged)]
    for field in _CHECKED_TEXT:
        text = str(merged.get(field) or "")
        if not text:
            continue
        keep = [s for s in re.split(r"(?<=[.!?])\s+", text)
                if not any(p.search(s) for p in bad)
                and not (_POOL_FIRST_NAMES & set(re.findall(r"\b[A-Z][a-z]+\b", s)))]
        merged[field] = " ".join(keep).strip()
    return merged


def _clean(value):
    """Sanitize a string (or list of strings) of any non-Latin drift."""
    if isinstance(value, str):
        return sanitize_language_drift(value, label="texture")
    if isinstance(value, list):
        return [sanitize_language_drift(str(v), label="texture") for v in value]
    return value


def generate_texture(
    skeleton: Dict,
    client: Optional[LLMClient] = None,
    max_retries: int = 2,
    used_names: Optional[set] = None,
    rng=None,
) -> Dict:
    """Return the skeleton merged with English-only texture fields.

    The returned dict preserves every FROZEN_FIELD verbatim (texture can reference but
    never overwrite them) and adds the TEXTURE_FIELDS. Raises on repeated LLM failure
    rather than silently returning an unusable persona.

    `name` is assigned from the curated pool (never the LLM), unique against the
    `used_names` set the caller passes (defaults to a fresh, call-local set — pass a
    shared set across a build to guarantee library-wide uniqueness).
    """
    client = client or LLMClient()
    used = used_names if used_names is not None else set()
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            raw = client.chat_json(
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _prompt(skeleton)},
                ],
                temperature=0.7,
                max_tokens=900,
            )
            if not isinstance(raw, dict) or not raw.get("persona"):
                raise ValueError("texture LLM returned no usable object")

            merged = dict(skeleton)  # frozen fields win — texture never overwrites them
            for f in TEXTURE_FIELDS:
                if f in raw:
                    merged[f] = _clean(raw[f])
            merged.setdefault("interested_topics", [])
            merged.setdefault("group_affiliation", "")
            # Name comes from the pool, not the model — unique across the build.
            # Provenance gate. A texture that claims something this person's record
            # does not license is a failed generation, not a stylistic quibble — retry
            # it. On the last attempt, strip the offending sentences instead of losing
            # the persona: a shorter true paragraph beats a vivid invented one.
            problems = _texture_violations(merged)
            if problems:
                if attempt < max_retries:
                    raise ValueError("texture failed provenance: " + "; ".join(problems))
                merged = _strip_offending_sentences(merged)
                print(f"[texture] stripped after {max_retries + 1} attempts: "
                      + "; ".join(problems), file=sys.stderr)

            merged["name"] = pick_unique_name(
                used,
                gender=merged.get("gender"),
                home_language=merged.get("home_language"),
                province=merged.get("province"),
                rng=rng,
            )
            return merged
        except Exception as e:  # noqa: BLE001 — retry then surface
            last_err = e
    raise RuntimeError(f"texture generation failed after {max_retries + 1} attempts: {last_err}")


def generate_batch(skeletons: List[Dict], client: Optional[LLMClient] = None) -> List[Dict]:
    """Generate texture for a list of mapped skeletons (sequential; this is offline)."""
    client = client or LLMClient()
    used_names: set = set()  # shared so names stay unique across the batch
    out = []
    for i, sk in enumerate(skeletons):
        try:
            out.append(generate_texture(sk, client=client, used_names=used_names))
        except Exception as e:  # noqa: BLE001
            print(f"[texture] skipped skeleton {i}: {e}", file=sys.stderr)
    return out


if __name__ == "__main__":
    from persona_sampler import sample_skeletons
    from archetype_mapper import map_skeletons

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    mapped = map_skeletons(sample_skeletons(n, seed=1), seed=1)
    for persona in generate_batch(mapped):
        print(json.dumps(persona, ensure_ascii=False, indent=2))
        print("-" * 60)
