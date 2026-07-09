"""
prompt_hardening_pilot — A/B test for remediation Fix 0 + Fix 1 deterministic checks.

Tests the PERSONA_REMEDIATION_PLAN (main repo, local doc) claims that are measurable
without any schema/data work:

  Fix 0: the current texture prompt ("this South African individual" + json.dumps
         fact blob) lets the model backfill hardship onto affluent seeds (the Naledi
         case). A hardened prompt (specific-person framing, economic-fidelity clause,
         invention prohibition, rendered fact briefing) should cut hardship-framing
         markers on manager/professional seeds while leaving genuinely poor seeds
         honest.
  Fix 1: two deterministic post-texture checks are cheap and catch real leaks:
         (a) a name from the curated pool appearing in prose that isn't the assigned
             name (the Thandiwe/Naledi bug), and
         (b) invented currency figures when the seed carries no income field.

Design mirrors context_grounding_pilot_v2: bare LLM calls (the prompt is the only
variable), real QLFS skeletons (borrowed from the MAIN repo's microdata — this
worktree has no data dir), deterministic scoring, JSON output. Both arms use the
same model so the comparison is apples-to-apples. Texture is normally built on the
LLM_* Plus tier, but per this worktree's rule pilots run on the SIM_LLM_* tier —
fine here, since the measurement is old-vs-new on the SAME model, not absolute
quality.

Run from the worktree root:
  D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/prompt_hardening_pilot.py

Cost: (N_AFFLUENT + N_CONTROL) * 2 arms LLM calls (default 16).
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv  # noqa: E402

# Worktree has no .env — borrow the main repo's (same pattern as pilot v2).
load_dotenv(r"D:\Fub-agentsociety\.env")

from app.utils.llm_client import LLMClient  # noqa: E402
import sa_names  # noqa: E402
import texture_generator as tg  # noqa: E402
from archetype_mapper import map_skeletons  # noqa: E402
from persona_sampler import sample_skeletons  # noqa: E402

# The worktree carries no microdata — borrow the main repo's QLFS file.
_MAIN_REPO_DTA = r"D:\Fub-agentsociety\backend\data\microdata\qlfs-2026-q1-v1\qlfs-2026-q1-v1.dta"

AFFLUENT_OCCS = {"Legislators; senior officials and managers", "Professionals"}
N_AFFLUENT = 6   # plan says 20 for the real gate; 6 keeps a pilot run cheap
N_CONTROL = 2    # genuinely poor seeds — hardened prompt must NOT sanitise these
SEED = 7
OUT_PATH = os.path.join(os.path.dirname(__file__), "prompt_hardening_pilot_output.json")

# ── Arm B: the hardened prompt (Fix 0, items 1-4) ───────────────────────────

_SYSTEM_NEW = (
    "You are an expert socio-economic researcher writing realistic persona texture "
    "for a policy/product simulation. You are given FIXED demographic facts AND FIXED "
    "measured attitudes about a person and must write ONLY their human surface "
    "(voice, background). You must NOT change, contradict, or restate-as-new any of the "
    "fixed facts. Reflect this person's ACTUAL economic position as implied by their "
    "occupation, industry, and employment status. Do NOT default to financial hardship, "
    "precarity, scarcity, or survival framing unless the fixed facts imply it — a senior "
    "manager is written as a senior manager. Do not invent income circumstances, "
    "safety-net status, housing situations, or names beyond the fixed facts; where a "
    "fact is absent, write texture that is neutral to it rather than assuming the worst "
    "case. The measured attitudes are survey data, not yours to invent or override: "
    "write a voice and outlook that EXPRESS them — never a person who feels the "
    "opposite. Write in ENGLISH ONLY — no isiZulu, isiXhosa, Afrikaans, or "
    "other-language words or phrases; capture their register in English, not by "
    "code-switching. Return ONLY valid JSON."
)


def _briefing(facts: Dict) -> str:
    """Fix 0 item 4: rendered one-line-per-field briefing instead of a JSON blob."""
    return "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in facts.items())


def _prompt_new(skeleton: Dict) -> str:
    facts = {k: skeleton.get(k) for k in tg.FROZEN_FIELDS if skeleton.get(k) is not None}
    attitude_lines = tg._attitude_constraints(skeleton)
    attitude_block = (
        "\nFIXED MEASURED ATTITUDES (survey data — the voice, background, and outlook you "
        "write MUST express these; do NOT write a person who feels the opposite, and do "
        "NOT restate them as new fields):\n" + "\n".join(attitude_lines) + "\n"
        if attitude_lines else ""
    )
    return f"""Write English-only persona texture for this specific person.

FIXED FACTS — a briefing on exactly who this person is. Do not change, contradict,
or invent around any line; write texture consistent with exactly these:
{_briefing(facts)}
{attitude_block}
Produce a JSON object with ONLY these fields:
- persona: 1-2 sentences on who they are and their situation. Reference a real local
  setting consistent with the province. English only.
- background_story: ~120 words of life history consistent with the fixed facts
  (their work, household, pressures). Specific, not generic. English only.
- voice_guide: 2-3 sentences on HOW they speak IN ENGLISH — vocabulary, formality,
  what they reference, tone, and what they would never say. Their tone must be
  consistent with the measured attitudes above. No other-language words.
- behavioral_tendencies: 2-3 sentences on what they tend to do in a group discussion
  (when they speak up, what they push back on), consistent with their archetype AND
  their measured attitudes.
- group_affiliation: a plausible affiliation if the facts support one (e.g. a
  professional body, union, church, residents' association), else "".
- interested_topics: array of 3-5 topics this person cares about, in their words.

Do NOT output age, income, attitudes, beliefs, emotions, or a name as JSON fields or
inside the prose — those are set elsewhere. Return ONLY the JSON object. English only."""


# ── Scoring: hardship-framing markers (deterministic) ────────────────────────

HARDSHIP_MARKERS = [
    r"\bsurviv\w*", r"\bstruggl\w*", r"\bprecari\w*", r"\bhustl\w*",
    r"\bscrap(e|ing) by\b", r"\bmake ends meet\b", r"\bhand.to.mouth\b",
    r"\bno safety net\b", r"\bpiece job\w*", r"\bsassa\b", r"\bgrant\b",
    r"\bshack\b", r"\binformal settlement\b", r"\bdebt collector\w*",
    r"\bgoes? hungry\b", r"\bskip\w* meals?\b", r"\bcan'?t afford\b",
    r"\bbarely\b", r"\bdesperat\w*",
]
_MARKER_RES = [re.compile(p, re.IGNORECASE) for p in HARDSHIP_MARKERS]


def _texture_text(persona: Dict) -> str:
    parts = []
    for f in tg.TEXTURE_FIELDS:
        v = persona.get(f, "")
        parts.append(" ".join(v) if isinstance(v, list) else str(v))
    return " ".join(parts)


def hardship_score(persona: Dict) -> Dict:
    text = _texture_text(persona)
    hits = {}
    for pat, rx in zip(HARDSHIP_MARKERS, _MARKER_RES):
        n = len(rx.findall(text))
        if n:
            hits[pat] = n
    return {"total": sum(hits.values()), "hits": hits}


# ── Fix 1 deterministic checks ───────────────────────────────────────────────

def _pool_first_names() -> set:
    """Flatten every first name in the curated banks (leak detection lexicon)."""
    names: set = set()

    def walk(node):
        if isinstance(node, str):
            names.add(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(sa_names._BANKS)
    # Drop pool entries that collide with common English words to avoid false hits.
    return {n for n in names if len(n) > 3}


_POOL_NAMES = _pool_first_names()
# The pool lexicon only catches leaks of curated names; the Thandiwe bug was a
# model-INVENTED name, which no lexicon covers. This catches the explicit form
# ("her name is Thandiwe"); implicit inventions are the LLM-judge's job (Fix 1b).
_NAMING_PHRASE_RE = re.compile(
    r"\b(?:name is|named|called|known as)\s+([A-Z][a-z]+)")
_CURRENCY_RE = re.compile(r"\bR\s?\d[\d\s,.]*\b")
_INCOME_FIELDS = ("monthly_household_income_rand", "fees_band", "learner_fee_bands")


def consistency_checks(persona: Dict, skeleton: Dict) -> Dict:
    text = _texture_text(persona)
    assigned = (persona.get("name") or "").split()
    leaked = sorted(
        n for n in _POOL_NAMES
        if n not in assigned and re.search(rf"\b{re.escape(n)}\b", text)
    )
    leaked += [n for n in _NAMING_PHRASE_RE.findall(text)
               if n not in assigned and n not in leaked]
    seed_has_income = any(skeleton.get(f) is not None for f in _INCOME_FIELDS)
    currency = _CURRENCY_RE.findall(text)
    return {
        "name_leak": leaked,
        "invented_currency": currency if not seed_has_income else [],
        "pass": not leaked and (seed_has_income or not currency),
    }


# ── Texture call (bare, so the prompt is the only variable) ──────────────────

def texture(skeleton: Dict, system: str, user: str, client: LLMClient,
            used_names: set) -> Dict:
    raw = client.chat_json(
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.7,
        max_tokens=900,
    )
    if not isinstance(raw, dict) or not raw.get("persona"):
        raise ValueError("texture LLM returned no usable object")
    merged = dict(skeleton)
    for f in tg.TEXTURE_FIELDS:
        if f in raw:
            merged[f] = tg._clean(raw[f])
    merged["name"] = sa_names.pick_unique_name(
        used_names, gender=merged.get("gender"), province=merged.get("province"))
    return merged


# ── Seed selection ────────────────────────────────────────────────────────────

def select_seeds() -> Dict[str, List[Dict]]:
    pool = map_skeletons(
        sample_skeletons(600, seed=SEED, dta_path=_MAIN_REPO_DTA), seed=SEED)
    affluent = [s for s in pool
                if s.get("occupation") in AFFLUENT_OCCS
                and s.get("employment_status") == "Employed"][:N_AFFLUENT]
    control = [s for s in pool
               if s.get("employment_status") in ("Unemployed", "Discouraged job seeker")
               ][:N_CONTROL]
    if len(affluent) < N_AFFLUENT:
        print(f"[warn] only {len(affluent)} affluent seeds in a 600-draw sample",
              file=sys.stderr)
    return {"affluent": affluent, "control": control}


def main() -> None:
    client = LLMClient(
        api_key=os.environ.get("SIM_LLM_API_KEY") or os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("SIM_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL"),
        model=os.environ.get("SIM_LLM_MODEL") or os.environ.get("LLM_MODEL_NAME"),
    )
    print(f"[pilot] model: {client.model}")
    seeds = select_seeds()
    arms = {
        "old": (tg._SYSTEM, tg._prompt),
        "new": (_SYSTEM_NEW, _prompt_new),
    }
    results = []
    used_names: set = set()
    for group, skels in seeds.items():
        for i, sk in enumerate(skels):
            row = {"group": group, "seed_index": i,
                   "occupation": sk.get("occupation"),
                   "employment_status": sk.get("employment_status"),
                   "archetype": sk.get("actor_archetype"),
                   "province": sk.get("province"), "arms": {}}
            for arm, (system, prompt_fn) in arms.items():
                try:
                    p = texture(sk, system, prompt_fn(sk), client, used_names)
                    row["arms"][arm] = {
                        "hardship": hardship_score(p),
                        "consistency": consistency_checks(p, sk),
                        "texture": {f: p.get(f) for f in tg.TEXTURE_FIELDS},
                        "name": p["name"],
                    }
                    print(f"[{group} #{i}] {arm}: hardship="
                          f"{row['arms'][arm]['hardship']['total']} "
                          f"consistency={'PASS' if row['arms'][arm]['consistency']['pass'] else 'FAIL'}")
                except Exception as e:  # noqa: BLE001 — record and continue
                    row["arms"][arm] = {"error": str(e)}
                    print(f"[{group} #{i}] {arm}: ERROR {e}", file=sys.stderr)
            results.append(row)

    def arm_total(group: str, arm: str) -> int:
        return sum(r["arms"].get(arm, {}).get("hardship", {}).get("total", 0)
                   for r in results if r["group"] == group)

    summary = {g: {a: arm_total(g, a) for a in arms} for g in seeds}
    print("\n=== hardship-marker totals ===")
    for g, t in summary.items():
        print(f"  {g:9s} old={t['old']:3d}  new={t['new']:3d}")
    print("Fix 0 is supported if 'new' drops materially on affluent seeds "
          "while control stays roughly level (poor seeds must stay honest).")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f,
                  ensure_ascii=False, indent=2)
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
