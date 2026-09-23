"""
ImpactReframer — transforms generic policy questions into persona-specific impact questions.

Translates abstract policy language into personal stakes by searching agent profiles
for the highest-relevance connection, then rewriting the question in the agent's
vocabulary, relationships, and recent memory.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger
from . import belief_relevance, mechanism_card_service, persona_facts
from .context_assembly import historical_mode
from .mode_specs import SHORT_ANSWER_SENTENCES, decision_question_on, word_of_mouth_ask

logger = get_logger("fub.prompt_reframer")


def _evidence_aware() -> bool:
    """Feature flag: evidence-aware wording (a persona may revise a view when the
    evidence supports it, and must say why) instead of the older "stay consistent"
    instruction. Default OFF — the old wording stays the baseline until the paid
    old-vs-new comparison validates the change."""
    return os.environ.get("EVIDENCE_AWARE_PROMPTS", "0").strip().lower() in (
        "1", "true", "on", "yes",
    )


def _render_research_layer() -> bool:
    """Feature flag: render the persona's research_context as an explicit
    prompt layer (next to the budget block) instead of relying on its
    presence inside the profile JSON the agent context carries. Default ON
    since the prompt-shape pilot (worktree, 2026-07): rendered identity +
    rendered research produced individually-voiced, mechanism-driven answers
    (e.g. reward-crowding reasoning surfacing as the persona's own opinion)
    where profile-JSON burial produced template arithmetic. Set to 0 to
    restore the buried behaviour."""
    return os.environ.get("RESEARCH_CONTEXT_RENDERED", "1").strip().lower() in (
        "1", "true", "on", "yes",
    )


class ImpactReframer:
    """Reframes generic questions as personal impact questions per agent."""

    # Layer priorities for finding personal stakes
    LAYER_PRIORITY = [
        "interested_topics",
        "background_story",
        "occupation",
        "income",
        "needs",
        "universal",
    ]

    # Keyword clusters for policy domain detection
    DOMAIN_KEYWORDS = {
        "security": ["soldier", "police", "army", "deployment", "gang", "violence", "crime", "safety", "protection", "patrol"],
        "economic": ["grant", "income", "money", "budget", "cost", "fee", "tax", "spend", "price", "job", "wage", "salary", "economy", "fiscal"],
        "housing": ["house", "home", "flat", "rent", "eviction", "landlord", "property", "shelter"],
        "education": ["school", "student", "teacher", "education", "learn", "university", "study"],
        "health": ["hospital", "clinic", "doctor", "health", "sick", "disease", "medicine"],
        "migration": ["immigrant", "foreign", "asylum", "refugee", "deportation", "border", "visa"],
        "political": ["government", "policy", "election", "party", "minister", "vote", "politician", "ANC", "DA", "EFF"],
    }

    def reframe(
        self,
        user_question: str,
        agent_profile: Dict[str, Any],
        mode: str = "policy",
        secondary_lens: Optional[str] = None,
        ask_word_of_mouth: bool = False,
    ) -> str:
        """
        Transform a generic user question into a persona-specific impact question.

        Steps:
        1. Detect policy domain from question keywords
        2. Search agent profile for highest-stake connection at multiple layers
        3. Build 4-layer prompt: Identity Lock + Memory Tether + Seed Anchor + Impact Question

        mode="product" swaps the impact question for pitch-reaction wording and, when
        the profile carries a computed budget_tier, injects it as a fixed budget
        reality (real-data constraint — never written by the LLM).

        secondary_lens (converged runs only) ADDS a second lens onto the primary mode
        WITHOUT replacing the primary question:
          - lens="product" on a policy primary: also injects the computed budget
            reality and appends an affordability sub-question.
          - lens="policy" on a product primary: appends a civic-impact sub-question.
        The lens is purely additive prompt text + the already-deterministic budget
        block; it never emits a number and never merges wanting with affording.
        """
        domain = self._detect_domain(user_question)
        stake = self._find_personal_stake(agent_profile, domain, user_question)
        recent_post = self._get_recent_post_excerpt(agent_profile)

        # Build the reframed prompt
        layers = []

        # Layer 1: Identity Lock
        layers.append(self._build_identity_lock(agent_profile, user_question))

        # Layer 2: Memory Tether (recent post) — evidence-aware: continuity of reasoning, not forced consistency
        if recent_post:
            if _evidence_aware():
                layers.append(f"\nYou recently said: '{recent_post}'\nConsider this alongside any new evidence; you may keep or change your view, but explain why.")
            else:
                layers.append(f"\nYou recently said: '{recent_post}'\nStay consistent with that position.")

        # Layer 3: Seed Anchor (personal stake)
        if stake:
            layers.append(f"\n{stake}")

        # Layer 3b: fixed budget reality, computed from real persona data. Shown when
        # the product lens is in play — either as the primary mode, or as a secondary
        # lens layered onto a policy-primary converged run.
        # A unified panel shows the budget reality only when the question states a
        # price: affordability is a real constraint on a priced offer, and noise on
        # an announcement that costs the listener nothing.
        priced = mode == "panel" and re.search(r"\bR\s?\d", user_question or "")
        if mode == "product" or secondary_lens == "product" or priced:
            budget_layer = self._build_budget_reality(agent_profile)
            if budget_layer:
                layers.append(f"\n{budget_layer}")

        # Layer 3c (flagged): research grounding rendered as an explicit layer.
        # The block is pre-rendered at cast build (mechanism_card_service) —
        # this only gives it prompt prominence instead of profile-JSON burial.
        # Only cards whose subject this question touches (mechanism_card_service
        # .cards_for_question). A legacy cast without citations keeps its stored block.
        if _render_research_layer() and agent_profile.get("research_context"):
            used = mechanism_card_service.cards_for_question(agent_profile, user_question)
            if used is None:
                layers.append(f"\n{agent_profile['research_context']}")
            elif used:
                layers.append(f"\n{mechanism_card_service.render_research_context(used)}")

        # Dated current conditions — same source as sim path, omitted in historical mode
        if not historical_mode():
            try:
                from .sa_context import current_sa_realities, relevant_realities
                current = relevant_realities(
                    current_sa_realities(snapshot=agent_profile.get("_current_snapshot")),
                    user_question)
                if current:
                    layers.append(f"\n{current}")
            except Exception as e:  # never let context-refresh break an interview
                logger.warning("Current context unavailable for reframe: %s", e)

        # Layer 4: Impact Question (reframed), plus any additive secondary lens.
        impact_question = self._build_impact_question(
            user_question, agent_profile, domain, mode=mode, secondary_lens=secondary_lens,
            ask_word_of_mouth=ask_word_of_mouth,
        )
        layers.append(f"\n{impact_question}")

        # Layer 5: Output constraints
        layers.append(self._build_constraints(mode))

        return "\n".join(layers)

    def _build_budget_reality(self, profile: Dict[str, Any]) -> Optional[str]:
        """Render the persona's computed budget tier as a fixed constraint,
        anchored by their OWN surveyed figures.

        The tier comes from mode_specs.budget_tier (real persona data, deterministic);
        this only verbalises it so the agent grounds desire against a budget it
        cannot wish away. The real-numbers block (same renderer as the sim path)
        pins income/fees so the agent reasons against surveyed figures instead of
        inventing them — the figures place the persona in an economic position;
        the research context describes how people in that position decide.
        Wanting and affording stay separate.
        """
        tier = profile.get("budget_tier")
        if not tier:
            return None
        from .mode_specs import BUDGET_TIER_GLOSS, _build_real_numbers_block
        gloss = BUDGET_TIER_GLOSS.get(tier, BUDGET_TIER_GLOSS["moderate"])
        real_numbers = _build_real_numbers_block({
            "real_household_income_rand": profile.get("monthly_household_income_rand"),
            "real_fees_band": profile.get("fees_band"),
            "real_learner_fee_bands": profile.get("learner_fee_bands"),
        })
        block = (
            f"YOUR BUDGET REALITY (fixed — set by your real circumstances): {tier.upper()}. {gloss}\n"
            "You may WANT something and still not be able to justify the spend."
        )
        if real_numbers:
            block += (
                f"\n{real_numbers}"
                "  These figures describe your economic position — where research context "
                "about people in your situation is provided, reason the way it documents "
                "people in your position actually deciding, not by arithmetic alone.\n"
            )
        return block

    def _detect_domain(self, question: str) -> str:
        """Detect policy domain from question text."""
        text = question.lower()
        scores = {}
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            scores[domain] = sum(1 for kw in keywords if kw in text)
        if scores:
            best = max(scores.items(), key=lambda x: x[1])
            if best[1] > 0:
                return best[0]
        return "general"

    def _find_personal_stake(self, agent_profile: Dict[str, Any], domain: str, question: str) -> Optional[str]:
        """
        Search agent profile for the highest-relevance personal connection.
        Returns a 'Seed Anchor' string or None.
        """
        profile_text = self._profile_to_text(agent_profile)

        # Layer 1: interested_topics direct match — custom agents only. On a library
        # persona the topics were written by the texture model, not measured (249 of 375
        # carried a "basic services" topic), and injected as "You care deeply about: …"
        # they steered every answer toward failing services whatever was asked. Library
        # personas already bring question-relevant beliefs and reactions from real data.
        topics = ([] if agent_profile.get("source_entity_type") == "library_persona"
                  else agent_profile.get("interested_topics", []))
        if topics:
            match = self._find_topic_match(question, topics)
            if match:
                return f"You care deeply about: {match}."

        # Layer 2: background_story keyword match. Not on a fact prompt: a story sentence
        # here would bring back the text the facts replaced.
        bg = "" if persona_facts.uses_facts(agent_profile) else agent_profile.get("background_story", "")
        if bg:
            anchor = self._extract_story_anchor(bg, domain)
            if anchor:
                return f"From your life: {anchor}"

        # Layer 3: occupation-based stake
        occupation = agent_profile.get("occupation", "")
        if occupation:
            occ_stake = self._occupation_stake(occupation, domain)
            if occ_stake:
                return f"As a {occupation}: {occ_stake}"

        # Layer 4: income / economic needs
        income = agent_profile.get("income", "")
        needs = agent_profile.get("needs", {})
        if domain == "economic" or domain == "general":
            if income:
                return f"Your income is {income}."
            if needs and isinstance(needs, dict):
                safety_econ = needs.get("safety_economic", 0)
                if safety_econ:
                    return f"Your economic security is a constant concern (need level: {safety_econ}/100)."

        # Layer 5: universal fallback — connect any policy to safety_economic
        if needs and isinstance(needs, dict):
            safety_econ = needs.get("safety_economic", 0)
            if safety_econ > 50:
                return "Every policy change touches your ability to survive."

        return None

    def _profile_to_text(self, profile: Dict[str, Any]) -> str:
        """Flatten profile into searchable text."""
        parts = [
            profile.get("persona", ""),
            profile.get("background_story", ""),
            profile.get("occupation", ""),
            " ".join(profile.get("interested_topics", [])),
        ]
        return " ".join(p for p in parts if p).lower()

    def _find_topic_match(self, question: str, topics: List[str]) -> Optional[str]:
        """Find an interested_topic that appears in the question."""
        q = question.lower()
        for topic in topics:
            if topic.lower() in q:
                return topic
        # Fallback: return first topic if none match directly
        return topics[0] if topics else None

    def _extract_story_anchor(self, background_story: str, domain: str) -> Optional[str]:
        """Extract a 1-sentence anchor from background story relevant to domain."""
        sentences = re.split(r'[.!?]+', background_story)
        domain_kws = self.DOMAIN_KEYWORDS.get(domain, [])
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 10:
                continue
            sent_lower = sent.lower()
            if any(kw in sent_lower for kw in domain_kws):
                # Truncate to ~120 chars
                if len(sent) > 120:
                    sent = sent[:120] + "..."
                return sent
        # Fallback: first sentence
        first = sentences[0].strip() if sentences else ""
        if len(first) > 120:
            first = first[:120] + "..."
        return first if first else None

    def _occupation_stake(self, occupation: str, domain: str) -> Optional[str]:
        """Map occupation to domain-specific stake."""
        occ_lower = occupation.lower()
        if domain == "security":
            if any(w in occ_lower for w in ["police", "security", "cpf", "community"]):
                return "your work is on the front line of safety."
            if any(w in occ_lower for w in ["teacher", "school"]):
                return "school safety is your daily reality."
        elif domain == "economic":
            if any(w in occ_lower for w in ["trader", "vendor", "business", "owner", "store"]):
                return "your livelihood depends on the trading environment."
            if any(w in occ_lower for w in ["worker", "unemployed"]):
                return "every policy change affects your income."
        elif domain == "political":
            if any(w in occ_lower for w in ["councillor", "politician", "official"]):
                return "you are accountable to voters for what happens next."
        return None

    def _get_recent_post_excerpt(self, agent_profile: Dict[str, Any]) -> Optional[str]:
        """Get last post content from profile (if loaded with posts_history)."""
        posts = agent_profile.get("posts_history", [])
        if posts:
            last = posts[-1]
            content = last.get("content", "") if isinstance(last, dict) else str(last)
            if len(content) > 150:
                content = content[:150] + "..."
            return content
        return None

    def _build_identity_lock(self, profile: Dict[str, Any], question: str = "") -> str:
        """Layer 1: render the FULL identity, not a one-sentence stub.

        The model reasons from whatever dominates its context. When identity is
        one sentence and instructions are 150 words, every persona converges on
        the same instruction-shaped answer (the prompt-shape pilot measured
        this: near-identical openers across a whole panel). Rendering the story,
        voice guide and beliefs makes each persona's own material the dominant
        content, so differentiation comes from data instead of sampling luck."""
        name = profile.get("name", "This person")
        if persona_facts.uses_facts(profile):
            # Survey answers picked by what the question touches, in place of the
            # model-written summary and story (see persona_facts).
            parts = [f"You are {name}."]
            facts = persona_facts.render(profile, question)
            if facts:
                parts.append(facts)
        else:
            parts = [f"You are {name}. {profile.get('persona', '').strip()}"]
            story = (profile.get("background_story") or "").strip()
            if story:
                parts.append(f"YOUR STORY: {story}")
        # How this person reacts, from their measured attitudes, chosen by the question.
        # Replaces the model-written voice_guide for library personas; custom agents
        # derive no reactions and keep the voice their author wrote.
        reaction_lines = belief_relevance.reactions_for(profile.get("attitudes"), question, 3)
        if reaction_lines:
            parts.append("HOW YOU REACT:\n" + "\n".join(f"- {r}" for r in reaction_lines))
        elif not belief_relevance.reactions(profile.get("attitudes")):
            # Custom agents only. A library persona whose reactions don't touch this
            # question gets nothing, never the retired voice guide.
            voice = (profile.get("voice_guide") or "").strip()
            if voice:
                parts.append(f"HOW YOU SPEAK: {voice}")
        # Chosen by what the question is ABOUT, not by position in the stored list.
        # Stored order is ATTITUDE_VOCAB order, whose first three entries are
        # gov_trust / economic_optimism / service_satisfaction — so the old `[:3]`
        # handed every persona their three biggest grievances and nothing else,
        # whatever was being asked.
        beliefs = belief_relevance.select(profile.get("beliefs") or [], question, 3)
        if beliefs:
            parts.append("WHAT YOU BELIEVE:\n" + "\n".join(f"- {b}" for b in beliefs))
        parts.append(
            "Respond in character. Do not speak as an analyst or observer. "
            "Use 'I', 'my', 'my family'. Never speak in generalities about 'the government should'."
        )
        return "\n\n".join(parts)

    def _build_impact_question(
        self,
        user_question: str,
        profile: Dict[str, Any],
        domain: str,
        mode: str = "policy",
        secondary_lens: Optional[str] = None,
        ask_word_of_mouth: bool = False,
    ) -> str:
        """Layer 4: Rewrite the question as a personal impact query.

        The primary `mode` chooses the main question. A `secondary_lens` (converged
        runs only) APPENDS a second sub-question — it never replaces the primary.
        """
        name = profile.get("name", "You")

        # Construct impact question. The persona always sees the user's FULL question.
        # This used to be replaced by the first "if ..." clause found anywhere in the
        # framed pitch — including its probes — so a whole pitch could be swapped for a
        # fragment: "Would you tell anyone about this? If so, who, and what would you
        # say?" turned an entire clinic pitch into the question "so, who, and what would
        # you say", and a panel of twelve answered a question nobody asked.
        lines = ["QUESTION:", ""]
        lines.append(self._with_word_of_mouth(user_question, profile, mode)
                     if ask_word_of_mouth else f"{user_question}")

        lines.append("")
        if mode == "product":
            # Open question, no response choreography: the old 3-beat wording
            # ("what works / what puts you off / what would change") made every
            # persona write the same three-slot essay. Structure for reports
            # lives in the ECONOMIC fields, not in the prose.
            lines.append(
                f"React as you actually would, {name} — in your own voice, leading with "
                "whatever hits you first. One concern is allowed to dominate; you do not "
                "need to cover everything, and you should not structure your answer the "
                "way anyone else would."
            )
        elif not (mode == "panel" and decision_question_on()):
            # (The decision question already asks what they would do; repeating it here
            # only lengthened the answer.)
            # Neutral on purpose. The old ending asked "What are you afraid of?" — a room
            # asked to name a fear finds one — and "Reference real people, real places,
            # real moments from your life", which invited invented relatives and suburbs
            # ("my sister in Tembisa") against the hard rule to speak only from the briefing.
            lines.append(
                f"What does this mean for you, {name}, in your own life? "
                "What, if anything, would you do about it?"
            )

        # Additive secondary lens for converged runs (never replaces the above).
        if secondary_lens == "product" and mode != "product":
            lines.append("")
            lines.append(
                "Also, separately: if this came at a real rand cost to you, could you "
                "justify the spend against your budget reality above? Wanting it and "
                "affording it are different things — speak to both."
            )
        elif secondary_lens == "policy" and mode != "policy":
            lines.append("")
            lines.append(
                "And separately: beyond your own wallet, how does this sit with you as a "
                "citizen and for your community? What would it mean if everyone around you "
                "faced the same thing?"
            )

        return "\n".join(lines)

    @staticmethod
    def _with_word_of_mouth(question: str, profile: Dict[str, Any], mode: str) -> str:
        """The room's question plus this person's word-of-mouth ask, when they get one.

        Panels only (the caller says so): a sim interview never carried the question.
        Placed before the length rule when the question has one, so the ask is not
        read as outside the answer it limits.
        """
        ask = word_of_mouth_ask(profile, mode)
        if not ask:
            return question
        marker = "\nAnswer in at most"
        if marker in question:
            head, tail = question.split(marker, 1)
            return f"{head}\n{ask}{marker}{tail}"
        return f"{question}\n\n{ask}"

    def _extract_proper_noun(self, text: str) -> Optional[str]:
        """Extract a capitalized proper noun from text."""
        if not text:
            return None
        matches = re.findall(r'\b[A-Z][a-z]+\b', text)
        skip = {"The", "This", "That", "These", "Those", "What", "When", "Where", "Why", "How",
                "But", "And", "Or", "If", "Then", "Than", "So", "Because", "Although", "You", "Your"}
        for m in matches:
            if m not in skip:
                return m
        return None

    def _build_constraints(self, mode: str = "policy") -> str:
        """Layer 5: Force specific, first-person output."""
        length = (f"at most {SHORT_ANSWER_SENTENCES} short sentences, under 60 words"
                  if mode == "panel" and decision_question_on() else "2-5 sentences")
        return (
            "\nHARD RULES (facts, not style):\n"
            "1. Answer in first person ('I', 'my family', 'my street').\n"
            f"2. Speak from YOUR experience, in YOUR voice — {length}.\n"
            "3. Never state a rand amount that is not in YOUR REAL NUMBERS or the "
            "question itself.\n"
            "4. Wanting something and affording it are different things — never merge them.\n"
            "5. Speak only from what is in your own briefing above — do not bring in "
            "outside conditions (electricity, water, crime) unless they appear there.\n"
            "6. Never state your own household income or school fees as figures — "
            "speak about them in your own words, not in rands.\n"
        )

    # ------------------------------------------------------------------
    # Utility: detect question archetype
    # ------------------------------------------------------------------

    QUESTION_ARCHETYPES = {
        "affective": ["feel", "feeling", "emotion", "scared", "afraid", "worried", "angry", "happy", "sad"],
        "cognitive": ["why", "reason", "think", "believe", "opinion", "view", "perspective"],
        "motivational": ["care", "matter", "important", "drive", "motivate", "stake", "interest"],
        "behavioral": ["do", "will you", "plan", "action", "next", "future", "going to", " intend"],
        "counterfactual": ["what if", "if", "would you", "change your mind", "different"],
    }

    def detect_archetype(self, question: str) -> str:
        """Auto-detect question archetype from text."""
        text = question.lower()
        scores = {}
        for archetype, keywords in self.QUESTION_ARCHETYPES.items():
            scores[archetype] = sum(1 for kw in keywords if kw in text)
        if scores:
            best = max(scores.items(), key=lambda x: x[1])
            if best[1] > 0:
                return best[0]
        return "general"
