"""
mode_detector — infer simulation mode ('policy' vs 'product') from the user's seed
text (+ optional uploaded document), so users don't have to remember the toggle.

Two-stage, deliberately LLM-optional:

  1. score_modes()  — pure keyword scorer. Returns a distribution, not a label.
  2. decide_mode()  — 3-outcome decision (policy / product / converged) with a
                      conservative convergence bar.
  3. llm_tiebreak() — only when the keyword margin is thin AND a client is passed.
                      With no client (or any failure) it is a pass-through, so the
                      keyword path is the full, testable code path with the LLM off.

The discriminative signal for policy-vs-product is *intent* vocabulary
("price", "subscribe", "launch" vs "announcement", "government", "ban"), not topic
words like "health" or "housing" which occur in both modes. We therefore keep
curated intent families here rather than harvesting the topic-oriented templates in
document_context_engine — those would add noise, not signal.

Detection is a prepare-time research concern: callers pass the LLM_* tier client,
never SIM_LLM_*.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --- Tunable decision boundaries (module constants so tests can assert exactly) ---
# Convergence is a "both modes are independently strong" signal, NOT "the split is
# balanced" — a genuinely dual seed can still lean one way. We therefore gate
# convergence on distinct keyword families per mode (conservative), not on the
# normalized score split. The normalized scores only choose which mode is primary.
MARGIN = 0.15               # |policy - product| <= MARGIN => "thin" (LLM tiebreak)
MIN_FAMILIES = 3            # each mode must hit >= this many distinct families to converge
SEED_WEIGHT = 1.0           # the seed is explicit user intent
DOC_WEIGHT = 0.5            # the uploaded doc is supporting context, weighted lower

# --- Keyword families. A "family" is one list; hitting any word in it counts the
# family once for the min-families check, and every hit counts toward the weight. ---
POLICY_FAMILIES: Dict[str, List[str]] = {
    "governance": [
        "government", "minister", "department", "parliament", "national assembly",
        "cabinet", "presidency", "municipality", "state", "official",
    ],
    "policy_act": [
        "policy", "announcement", "announce", "regulation", "regulate", "bill",
        "legislation", "law", "mandate", "deploy", "deployment", "ban", "tax",
        "levy", "subsidy", "grant", "reform", "crackdown", "amendment",
    ],
    "civic": [
        "citizens", "public", "community", "residents", "voters", "protest",
        "react to", "backlash", "consultation", "constituency",
    ],
    "politics": [
        "ANC", "DA", "EFF", "opposition", "election", "party", "coalition",
    ],
}

PRODUCT_FAMILIES: Dict[str, List[str]] = {
    "offering": [
        "product", "app", "platform", "service", "feature", "mvp", "prototype",
        "tool", "software", "subscription", "plan",
    ],
    "commercial": [
        "price", "pricing", "r/month", "per month", "monthly fee", "free tier",
        "paywall", "cost per", "willing to pay", "willingness to pay", "afford",
        "value for money", "discount",
    ],
    "go_to_market": [
        "launch", "rollout", "roll out", "sign up", "sign-up", "onboard",
        "early adopter", "go to market", "pilot", "beta", "waitlist",
    ],
    "market": [
        "customer", "customers", "users", "market", "competitor", "competitors",
        "churn", "retention", "conversion", "adoption", "target market",
        "switch", "switching",
    ],
}


def _count_hits(text: str, families: Dict[str, List[str]]) -> Dict[str, int]:
    """Per-family hit counts (number of keyword occurrences) for one text block."""
    lowered = text.lower()
    out: Dict[str, int] = {}
    for fam, words in families.items():
        n = 0
        for w in words:
            # \b doesn't play nicely with multi-word / slash phrases, so use a
            # boundary-aware search that still matches phrases like "r/month".
            pattern = r"(?<![a-z0-9])" + re.escape(w.lower()) + r"(?![a-z0-9])"
            n += len(re.findall(pattern, lowered))
        if n:
            out[fam] = n
    return out


def _weighted(seed_hits: Dict[str, int], doc_hits: Dict[str, int]) -> float:
    return SEED_WEIGHT * sum(seed_hits.values()) + DOC_WEIGHT * sum(doc_hits.values())


def score_modes(seed_text: str, document_text: str = "") -> Dict[str, Any]:
    """Keyword distribution over the two modes. No LLM, no I/O — pure + testable.

    Returns policy_score / product_score normalized to sum to 1.0 (0.5/0.5 when there
    is no signal at all), the raw weighted totals, and a per-source family breakdown
    for debugging conflicts (seed says product, doc says policy, etc.).
    """
    seed_text = seed_text or ""
    document_text = document_text or ""

    seed_pol = _count_hits(seed_text, POLICY_FAMILIES)
    seed_pro = _count_hits(seed_text, PRODUCT_FAMILIES)
    doc_pol = _count_hits(document_text, POLICY_FAMILIES)
    doc_pro = _count_hits(document_text, PRODUCT_FAMILIES)

    pol_w = _weighted(seed_pol, doc_pol)
    pro_w = _weighted(seed_pro, doc_pro)
    total = pol_w + pro_w

    if total <= 0:
        policy_score = product_score = 0.5
    else:
        policy_score = pol_w / total
        product_score = pro_w / total

    # Distinct families that fired across both sources, for the conservative bar.
    pol_families = set(seed_pol) | set(doc_pol)
    pro_families = set(seed_pro) | set(doc_pro)

    return {
        "policy_score": policy_score,
        "product_score": product_score,
        "raw": {"policy": pol_w, "product": pro_w},
        "families": {"policy": len(pol_families), "product": len(pro_families)},
        "signal": {
            "seed": {"policy": seed_pol, "product": seed_pro},
            "doc": {"policy": doc_pol, "product": doc_pro},
        },
    }


def decide_mode(
    scores: Dict[str, Any],
    *,
    margin: float = MARGIN,
    min_families: int = MIN_FAMILIES,
) -> Dict[str, Any]:
    """Turn a score distribution into the 3-outcome decision.

    - clear policy / clear product → single mode, no lens
    - both strong (>= min_families distinct families each) → converged: primary =
      higher score, secondary_lens = the other. This is the conservative bar — it
      fires only when each mode is independently well-evidenced, regardless of which
      one dominates.
    - thin margin → confidence='thin' (caller may run the LLM tiebreak)
    """
    policy_score = scores["policy_score"]
    product_score = scores["product_score"]
    pol_families = scores.get("families", {}).get("policy", 0)
    pro_families = scores.get("families", {}).get("product", 0)

    primary = "policy" if policy_score >= product_score else "product"
    thin = abs(policy_score - product_score) <= margin

    converged = pol_families >= min_families and pro_families >= min_families

    secondary_lens = None
    if converged:
        secondary_lens = "product" if primary == "policy" else "policy"

    return {
        "mode": primary,
        "converged": converged,
        "secondary_lens": secondary_lens,
        "confidence": "thin" if thin and not converged else "clear",
        "scores": {"policy": policy_score, "product": product_score},
    }


_TIEBREAK_PROMPT = (
    "Classify the simulation intent of the text below. The two modes are:\n"
    "- policy: citizens/the public reacting to a government policy, announcement, "
    "law, or political event.\n"
    "- product: a market of consumers/businesses reacting to a product, app, price, "
    "or feature idea.\n"
    "If the text genuinely tests BOTH at once (e.g. a state-subsidised product with a "
    "real price), set converged true and pick the dominant one as mode.\n"
    'Respond with STRICT JSON only: {"mode": "policy"|"product", "converged": true|false}.\n\n'
    "TEXT:\n{snippet}\n"
)


def llm_tiebreak(
    seed_text: str,
    document_text: str,
    decision: Dict[str, Any],
    *,
    llm_client: Any = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Break a thin keyword margin with the LLM. Pass-through when not applicable.

    Only does anything when decision['confidence']=='thin' and a client is supplied.
    Any missing client, error, timeout, or unparseable output returns `decision`
    unchanged — so the keyword decision is always a safe fallback and the LLM-off
    path is fully exercised by tests.
    """
    if decision.get("confidence") != "thin" or llm_client is None or not model_name:
        return decision

    snippet = (seed_text or "")[:1500]
    if document_text:
        snippet += "\n\n[CONTEXT DOCUMENT]\n" + document_text[:1500]

    try:
        resp = llm_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": _TIEBREAK_PROMPT.format(snippet=snippet)}],
            temperature=0,
            max_tokens=60,
        )
        raw = resp.choices[0].message.content or ""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return decision
        parsed = json.loads(match.group(0))
        mode = str(parsed.get("mode", "")).strip().lower()
        if mode not in ("policy", "product"):
            return decision
        converged = bool(parsed.get("converged", False))
        secondary = None
        if converged:
            secondary = "product" if mode == "policy" else "policy"
        return {
            "mode": mode,
            "converged": converged,
            "secondary_lens": secondary,
            "confidence": "clear",
            "scores": decision.get("scores", {}),
            "used_llm_tiebreak": True,
        }
    except Exception as e:  # noqa: BLE001 — detection must never break prepare
        logger.warning(f"mode_detector LLM tiebreak failed, using keyword result: {e}")
        return decision


def detect(
    seed_text: str,
    document_text: str = "",
    *,
    llm_client: Any = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Full pipeline: score -> decide -> optional LLM tiebreak.

    Always returns a dict with keys: mode, converged, secondary_lens, confidence,
    scores, used_llm_tiebreak.
    """
    scores = score_modes(seed_text, document_text)
    decision = decide_mode(scores)
    decision.setdefault("used_llm_tiebreak", False)
    result = llm_tiebreak(
        seed_text, document_text, decision,
        llm_client=llm_client, model_name=model_name,
    )
    result.setdefault("used_llm_tiebreak", False)
    return result
