"""
ImpactReframer — transforms generic policy questions into persona-specific impact questions.

Translates abstract policy language into personal stakes by searching agent profiles
for the highest-relevance connection, then rewriting the question in the agent's
vocabulary, relationships, and recent memory.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


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
        layers.append(self._build_identity_lock(agent_profile))

        # Layer 2: Memory Tether (recent post)
        if recent_post:
            layers.append(f"\nYou recently said: '{recent_post}'\nStay consistent with that position.")

        # Layer 3: Seed Anchor (personal stake)
        if stake:
            layers.append(f"\n{stake}")

        # Layer 3b: fixed budget reality, computed from real persona data. Shown when
        # the product lens is in play — either as the primary mode, or as a secondary
        # lens layered onto a policy-primary converged run.
        if mode == "product" or secondary_lens == "product":
            budget_layer = self._build_budget_reality(agent_profile)
            if budget_layer:
                layers.append(f"\n{budget_layer}")

        # Layer 4: Impact Question (reframed), plus any additive secondary lens.
        impact_question = self._build_impact_question(
            user_question, agent_profile, domain, mode=mode, secondary_lens=secondary_lens
        )
        layers.append(f"\n{impact_question}")

        # Layer 5: Output constraints
        layers.append(self._build_constraints())

        return "\n".join(layers)

    def _build_budget_reality(self, profile: Dict[str, Any]) -> Optional[str]:
        """Render the persona's computed budget tier as a fixed constraint.

        The tier comes from mode_specs.budget_tier (real persona data, deterministic);
        this only verbalises it so the agent grounds desire against a budget it
        cannot wish away. Wanting and affording stay separate.
        """
        tier = profile.get("budget_tier")
        if not tier:
            return None
        from .mode_specs import BUDGET_TIER_GLOSS
        gloss = BUDGET_TIER_GLOSS.get(tier, BUDGET_TIER_GLOSS["moderate"])
        return (
            f"YOUR BUDGET REALITY (fixed — set by your real circumstances): {tier.upper()}. {gloss}\n"
            "You may WANT something and still not be able to justify the spend."
        )

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

        # Layer 1: interested_topics direct match
        topics = agent_profile.get("interested_topics", [])
        if topics:
            match = self._find_topic_match(question, topics)
            if match:
                return f"You care deeply about: {match}."

        # Layer 2: background_story keyword match
        bg = agent_profile.get("background_story", "")
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

    def _build_identity_lock(self, profile: Dict[str, Any]) -> str:
        """Layer 1: Force in-character response."""
        name = profile.get("name", "This person")
        persona = profile.get("persona", "")
        # First sentence of persona
        first_sentence = persona.split(".")[0] if persona else f"You are {name}."
        return (
            f"You are {name}. {first_sentence.strip()}.\n"
            "Respond in character. Do not speak as an analyst or observer. "
            "Use 'I', 'my', 'my family'. Never speak in generalities about 'the government should'."
        )

    def _build_impact_question(
        self,
        user_question: str,
        profile: Dict[str, Any],
        domain: str,
        mode: str = "policy",
        secondary_lens: Optional[str] = None,
    ) -> str:
        """Layer 4: Rewrite the question as a personal impact query.

        The primary `mode` chooses the main question. A `secondary_lens` (converged
        runs only) APPENDS a second sub-question — it never replaces the primary.
        """
        name = profile.get("name", "You")

        # Extract core event from user question
        event = self._extract_event(user_question)

        # Construct impact question
        lines = ["QUESTION:", ""]

        if event:
            lines.append(f"{event}")
        else:
            lines.append(f"{user_question}")

        lines.append("")
        if mode == "product":
            lines.append(
                f"How do you react to this pitch, {name}? "
                "Be specific: what works for you, what puts you off, and what would have to "
                "change for you to reconsider. Be honest about whether you could justify the "
                "spend — wanting it and affording it are different things."
            )
        else:
            lines.append(
                f"What does this mean for YOU, {name}? "
                "Be specific. Reference real people, real places, real moments from your life. "
                "What changes in your daily routine? What are you afraid of? What do you plan to do?"
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

    def _extract_event(self, question: str) -> Optional[str]:
        """Extract the hypothetical/counterfactual event from the question."""
        # Look for conditional phrasing
        patterns = [
            r"if\s+(.+?)(?:\?|$)",
            r"what\s+if\s+(.+?)(?:\?|$)",
            r"what\s+happens\s+if\s+(.+?)(?:\?|$)",
            r"how\s+does\s+(.+?)\s+affect",
            r"what\s+is\s+the\s+impact\s+of\s+(.+?)(?:\?|$)",
        ]
        for pat in patterns:
            m = re.search(pat, question, re.IGNORECASE)
            if m:
                event = m.group(1).strip()
                if event:
                    return event
        return None

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

    def _build_constraints(self) -> str:
        """Layer 5: Force specific, first-person output."""
        return (
            "\nRULES:\n"
            "1. Answer in first person ('I', 'my family', 'my street').\n"
            "2. Reference specific details from your background.\n"
            "3. Do not speak in generalities. Speak from YOUR experience.\n"
            "4. Keep it to 2-4 sentences. Be specific, not vague.\n"
            "5. Do NOT invent facts not in your background story.\n"
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
