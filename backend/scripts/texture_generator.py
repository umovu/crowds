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
TEXTURE_FIELDS = [
    "name", "persona", "background_story",
    "voice_guide", "behavioral_tendencies",
    "group_affiliation", "interested_topics",
]

# Skeleton fields the model must NOT change (it may reference them, not rewrite them).
FROZEN_FIELDS = [
    "age", "gender", "province", "education", "occupation",
    "employment_status", "informal", "industry", "marriage_status",
    "is_neet", "actor_archetype",
    # GHS education-build facts (absent on civic personas — None is skipped).
    # All REAL surveyed circumstances the texture must write around, not invent:
    "geotype", "home_language", "monthly_household_income_rand",
    "internet_at_home", "computer_in_home", "receives_grant",
    "ghs_role", "edu_institution", "current_grade", "fees_band",
    "time_to_school", "guardian_type", "learners_in_household",
    "learner_fee_bands", "guards_grandchildren", "occupation_provenance",
]

_SYSTEM = (
    "You are an expert in South African socio-economics writing realistic persona "
    "texture for a policy/product simulation. You are given FIXED demographic facts AND "
    "FIXED measured attitudes about a person and must write ONLY their human surface "
    "(name, voice, background). You must NOT change, contradict, or restate-as-new any of "
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


def _prompt(skeleton: Dict) -> str:
    facts = {k: skeleton.get(k) for k in FROZEN_FIELDS if skeleton.get(k) is not None}
    attitude_lines = _attitude_constraints(skeleton)
    attitude_block = (
        "\nFIXED MEASURED ATTITUDES (survey data — the voice, background, and outlook you "
        "write MUST express these; do NOT write a person who feels the opposite, and do "
        "NOT restate them as new fields):\n" + "\n".join(attitude_lines) + "\n"
        if attitude_lines else ""
    )
    return f"""Write English-only persona texture for this South African individual.

FIXED FACTS (do not change, contradict, or invent around — write texture consistent
with exactly these):
{json.dumps(facts, ensure_ascii=False, indent=2)}
{attitude_block}
Produce a JSON object with ONLY these fields:
- name: a realistic South African full name appropriate to the person. Must NOT be a
  real public figure. Province-plausible, but the name's language origin does not
  force non-English speech.
- persona: 1-2 sentences on who they are and their situation. Reference a real local
  setting consistent with the province. English only.
- background_story: ~120 words of life history consistent with the fixed facts
  (their work, household, pressures). Specific, not generic. English only.
- voice_guide: 2-3 sentences on HOW they speak IN ENGLISH — vocabulary, formality,
  what they reference (money in rands, load-shedding, transport, work), tone, and
  what they would never say. Their tone must be consistent with the measured attitudes
  above (e.g. a distrustful, pessimistic person does not sound upbeat about government).
  No other-language words.
- behavioral_tendencies: 2-3 sentences on what they tend to do in a group discussion
  (when they speak up, what they push back on), consistent with their archetype AND
  their measured attitudes.
- group_affiliation: a plausible affiliation if the facts support one (e.g. a union,
  church, street committee, taxi association), else "".
- interested_topics: array of 3-5 topics this person cares about, in their words.

Do NOT output age, income, attitudes, beliefs, or emotions as JSON fields — those are
set elsewhere. (You must still let the measured attitudes shape the voice/outlook you
write above; just don't emit them as separate fields.)
Return ONLY the JSON object. English only."""


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
) -> Dict:
    """Return the skeleton merged with English-only texture fields.

    The returned dict preserves every FROZEN_FIELD verbatim (texture can reference but
    never overwrite them) and adds the TEXTURE_FIELDS. Raises on repeated LLM failure
    rather than silently returning an unusable persona.
    """
    client = client or LLMClient()
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
            if not isinstance(raw, dict) or not raw.get("name"):
                raise ValueError("texture LLM returned no usable object")

            merged = dict(skeleton)  # frozen fields win — texture never overwrites them
            for f in TEXTURE_FIELDS:
                if f in raw:
                    merged[f] = _clean(raw[f])
            merged.setdefault("interested_topics", [])
            merged.setdefault("group_affiliation", "")
            return merged
        except Exception as e:  # noqa: BLE001 — retry then surface
            last_err = e
    raise RuntimeError(f"texture generation failed after {max_retries + 1} attempts: {last_err}")


def generate_batch(skeletons: List[Dict], client: Optional[LLMClient] = None) -> List[Dict]:
    """Generate texture for a list of mapped skeletons (sequential; this is offline)."""
    client = client or LLMClient()
    out = []
    for i, sk in enumerate(skeletons):
        try:
            out.append(generate_texture(sk, client=client))
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
