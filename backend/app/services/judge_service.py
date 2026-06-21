"""
JudgeService — LLM-as-judge for simulation quality scoring.

Advisory only. Uses LLM_* (Plus/quality) tier to score outputs 1-10 and surface
the score to the UI. It does NOT reject or regenerate anything — the verdict is a
soft signal, not a gate. Disabled by default (Config.JUDGE_ENABLED): each judged
path costs an extra Plus-tier call, so only enable when evaluating output quality.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from typing import Callable, Tuple

from ..utils.llm_client import LLMClient
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.judge")


@dataclass
class JudgeResult:
    score: int
    pass_: bool
    reasoning: str
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "pass": self.pass_,
            "reasoning": self.reasoning,
            "evidence": self.evidence
        }


class JudgeService:
    """LLM-as-judge using Plus-tier model for advisory quality scoring."""

    MIN_PASS_SCORE = 7

    def __init__(self):
        self.client = self._create_client()

    def _create_client(self) -> LLMClient:
        """Create LLM client using Plus-tier (LLM_*) config."""
        return LLMClient(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_BASE_URL,
            model=Config.LLM_MODEL_NAME,
        )

    def judge(self, criteria: str, output: str, context: Dict[str, Any],
              threshold: int = None) -> JudgeResult:
        """Score `output` against `criteria`. Synchronous; advisory only."""
        threshold = threshold or self.MIN_PASS_SCORE

        prompt = self._build_prompt(criteria, output, context)

        try:
            # Match chat_json's Groq handling: Groq rejects response_format, so
            # only request JSON mode when the provider supports it.
            kwargs = dict(
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            if not self.client._is_groq():
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat(**kwargs)

            result = json.loads(response)
            score = int(result.get("score", 0))
            return JudgeResult(
                score=score,
                pass_=score >= threshold,
                reasoning=result.get("reasoning", ""),
                evidence=result.get("evidence", "")
            )

        except Exception as e:
            logger.warning(f"Judge evaluation failed: {e}")
            return JudgeResult(
                score=0,
                pass_=False,
                reasoning=f"Judge error: {e}",
                evidence=""
            )

    def _system_prompt(self) -> str:
        return """You are a rigorous quality evaluator for a South African policy/product simulation system.
Evaluate the output against the given criteria. Return ONLY valid JSON:
{"score": 1-10, "pass": true/false, "reasoning": "...", "evidence": "..."}

Score 1-10 where 10 = perfect. Be strict — a 7 is the minimum pass.
Evidence must quote specific parts of the output that support your score."""

    def _build_prompt(self, criteria: str, output: str, context: Dict[str, Any]) -> str:
        ctx = json.dumps(context, ensure_ascii=False) if context else "{}"
        return f"""CRITERIA:
{criteria}

CONTEXT:
{ctx}

OUTPUT TO EVALUATE:
{output[:8000]}

Return JSON only."""

    # ==================== Specific Judges ====================

    def judge_seed_briefing(self, briefing: str, mode: str, topic: str) -> JudgeResult:
        """Evaluate seed briefing quality."""
        criteria = self._seed_criteria(mode)
        return self.judge(criteria, briefing, {"mode": mode, "topic": topic})

    def _seed_criteria(self, mode: str) -> str:
        base = """Evaluate this seed briefing for a South African simulation.

REQUIRED:
1. South African specificity — real places, archetypes, constraints (data costs, load-shedding, income, trust)
2. No invented facts — all claims traceable to sources
3. Clear structure with required sections
4. ~1200-1800 words"""

        if mode == "product":
            return base + """

PRODUCT MODE ADDITIONAL:
5. Geographic priority — SA-local competitors primary, SA-present secondary, global marked as reference-only
6. Customer segments = REAL PEOPLE (not products/brands/apps)
7. Competitive landscape separated by tier
8. Barriers section lists concrete SA barriers"""
        else:
            return base + """

POLICY MODE ADDITIONAL:
5. Key actors = REAL HUMAN PEOPLE-TYPES (not orgs/campaigns/brands)
6. NON-AGENT RULE followed — programmes/campaigns are context only
7. Tensions/dynamics between actors identified
8. Policy environment section present"""

    def judge_personas(self, personas: List[Dict[str, Any]], topic: str) -> JudgeResult:
        """Evaluate generated persona quality."""
        criteria = """Evaluate these agent personas for a South African simulation.

REQUIRED:
1. Demographic realism — age, income, location, occupation match SA distributions
2. Economic grounding — "can afford it" derives from stated income/budget
3. Distinct voices — no two personas sound identical; different vocabularies, pain points
4. SA constraints appear naturally — data costs, load-shedding, trust deficit, informal economy
5. Archetype fidelity — spaza owner sounds like spaza owner, not generic citizen
6. No buy/no-buy verdicts — expresses objections/conditions/willingness
7. SA-grounded identity — every persona is a real South African person-type. No persona is
   a foreign product/brand wearing a human mask, and no foreign entity with no SA presence
   defines who the persona is (such material is context only, never identity)"""
        return self.judge(criteria, json.dumps(personas, ensure_ascii=False),
                          {"topic": topic, "count": len(personas)})

    def judge_agent_reaction(self, reaction: Dict[str, Any], persona: Dict[str, Any],
                             intervention: str) -> JudgeResult:
        """Evaluate agent reaction to intervention. (Not wired to live paths —
        kept for offline/manual evaluation use.)"""
        criteria = """Evaluate this agent's reaction to an intervention.

REQUIRED:
1. Stance shift plausibility — before→after makes sense given intervention + persona
2. Constraint awareness — references price in rands, offline need, trust barrier
3. No buy/no-buy verdict — expresses objections/conditions/confusion/willingness
4. Persona fidelity — voice, vocabulary, concerns match the persona
5. SA-specific reasoning — not generic; grounded in their economic reality"""
        return self.judge(criteria, json.dumps(reaction, ensure_ascii=False),
                          {"persona": persona, "intervention": intervention})

    def judge_competitor_tiering(self, competitors: List[Dict[str, Any]],
                                 document_text: str) -> JudgeResult:
        """Evaluate competitor tier classification."""
        criteria = """Evaluate competitor tier classifications.

REQUIRED:
1. Each competitor has: name, priority (local/present/context), reason
2. local = SA-based or primarily SA-focused (dominates sim)
3. present = confirmed SA operations/presence (significant weight)
4. context = foreign, no SA presence (reference only, does not dominate)
5. reason field explains WHY this tier (e.g., "WeWALK — customer reviews show blind users value obstacle detection")
6. Sorted: local first, then present, then context"""
        return self.judge(criteria, json.dumps(competitors, ensure_ascii=False),
                          {"document_excerpt": document_text[:2000]})


def judge_enabled() -> bool:
    """True when the advisory judge is switched on (Config.JUDGE_ENABLED).
    Call sites should short-circuit on this before constructing the service so a
    disabled judge costs nothing."""
    return Config.JUDGE_ENABLED


# Singleton
_judge_service: Optional[JudgeService] = None


def get_judge_service() -> JudgeService:
    global _judge_service
    if _judge_service is None:
        _judge_service = JudgeService()
    return _judge_service


def judge_best_of(
    generate: Callable[[Optional[JudgeResult]], Any],
    judge: Callable[[Any], JudgeResult],
    threshold: int = JudgeService.MIN_PASS_SCORE,
) -> Tuple[Any, Optional[JudgeResult], bool]:
    """Generate → judge, and regenerate ONCE if the score is below threshold,
    keeping whichever attempt scored higher.

    This is the only "self-correction" the judge does. It is deliberately narrow:
      - At most 2 generations (1 retry). Never loops.
      - The judge NEVER edits the output — it only scores. Correction happens by
        re-running the caller's own generator, so all content stays authored by
        the real generation path (important for the economic rules: this must not
        become a way for the judge to write persona/budget data).
      - `generate(prev_judge)` receives the first attempt's JudgeResult on the
        retry so the caller may pass its qualitative reasoning back as a hint.
        Callers must NOT use that hint to set affordability/budget numbers.

    Returns (best_output, best_judge_result, regenerated).

    When the judge is disabled, callers should not reach here — they should
    generate once directly. This helper always judges.
    """
    first_out = generate(None)
    first_res = judge(first_out)

    if first_res.pass_ or first_res.score >= threshold:
        return first_out, first_res, False

    logger.info(
        f"Judge score {first_res.score} < {threshold}; regenerating once. "
        f"Reason: {first_res.reasoning[:200]}"
    )

    try:
        second_out = generate(first_res)
        second_res = judge(second_out)
    except Exception as e:
        # Retry failed — keep the first attempt rather than dropping the result.
        logger.warning(f"Judge regeneration failed, keeping first attempt: {e}")
        return first_out, first_res, False

    if second_res.score > first_res.score:
        return second_out, second_res, True
    return first_out, first_res, True