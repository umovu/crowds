"""
DocumentContextEngine — extracts domain-specific context from graph storage
and generates dynamic event rules/prompts rooted in the uploaded document.

This ensures simulations are not just "SA-flavored" but actually driven by
the specific policy document being tested.
"""

import json
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from ..utils.entity_resolver import quick_resolve_lists

logger = get_logger("fub.document_context")


# Domain-specific event templates keyed by detected domain keywords
DOMAIN_EVENT_TEMPLATES = {
    "farm": {
        "category": "rural_security",
        "triggers": ["farm", "farmer", "agriculture", "rural", "land", "attack", "murder", "security"],
        "events": [
            {
                "id": "farm_attack_escalation",
                "trigger": {"type": "topic_mention_count", "topics": ["farm", "attack", "murder", "security"], "min_count": 4},
                "event": {
                    "type": "institutional_response",
                    "source": "TAU SA",
                    "title": "Agricultural Union Demands Emergency Security Summit",
                    "content": "TAU SA and other agricultural unions have called for an emergency rural security summit, citing a sharp increase in reported attacks on farming communities. They are demanding increased SAPS rural deployment and the revival of the commando system.",
                    "affected_archetypes": ["community_protector", "institutional_loyalist", "civic_moderate", "whistleblower"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            },
            {
                "id": "afriforum_mobilization",
                "trigger": {"type": "topic_mention_count", "topics": ["farm", "murder", "white", "minority"], "min_count": 3},
                "event": {
                    "type": "political_response",
                    "source": "AfriForum",
                    "title": "AfriForum Launches International Awareness Campaign",
                    "content": "AfriForum has released a new report on farm attacks and is briefing international diplomats and media. The organization claims the government is downplaying the crisis and has failed to protect minority farming communities.",
                    "affected_archetypes": ["political_activist", "institutional_loyalist", "economic_migrant", "conspiracy_spreader"],
                    "severity": "medium",
                    "persist_rounds": 3
                }
            },
            {
                "id": "government_dismissal",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.7, "min_proportion": 0.2},
                "event": {
                    "type": "institutional_response",
                    "source": "Police Ministry",
                    "title": "Government Rejects Claims of Rural Security Crisis",
                    "content": "The Police Ministry has rejected claims of a rural security crisis, stating that farm attacks are part of broader crime patterns and that dedicated rural safety structures are being strengthened. Critics say this response ignores the unique vulnerabilities of remote farms.",
                    "affected_archetypes": ["institutional_loyalist", "civic_moderate", "political_activist", "whistleblower"],
                    "severity": "medium",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "police": {
        "category": "security_reform",
        "triggers": ["police", "SAPS", "crime", "violence", "brutality", "corruption", "reform"],
        "events": [
            {
                "id": "ipid_investigation",
                "trigger": {"type": "topic_mention_count", "topics": ["police", "brutality", "corruption", "SAPS"], "min_count": 4},
                "event": {
                    "type": "institutional_response",
                    "source": "IPID",
                    "title": "Independent Police Investigative Directorate Opens Probe",
                    "content": "IPID has announced a formal investigation into allegations of police misconduct raised in community consultations. The directorate has called for witnesses to come forward and assured protection for whistleblowers.",
                    "affected_archetypes": ["whistleblower", "institutional_loyalist", "community_protector", "civic_moderate"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            },
            {
                "id": "police_union_resistance",
                "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.6, "min_proportion": 0.25},
                "event": {
                    "type": "institutional_response",
                    "source": "POPCRU",
                    "title": "Police Unions Push Back Against Reform Proposals",
                    "content": "Police and Prisons Civil Rights Union (POPCRU) has strongly opposed proposed policing reforms, arguing they will demoralize officers and reduce operational effectiveness. The union has threatened industrial action if its concerns are not addressed.",
                    "affected_archetypes": ["institutional_loyalist", "community_protector", "political_activist", "civic_moderate"],
                    "severity": "high",
                    "persist_rounds": 2
                }
            }
        ]
    },
    "health": {
        "category": "health_policy",
        "triggers": ["health", "hospital", "NHI", "medical", "doctor", "clinic", "disease"],
        "events": [
            {
                "id": "nhi_backlash",
                "trigger": {"type": "topic_mention_count", "topics": ["NHI", "health", "hospital"], "min_count": 4},
                "event": {
                    "type": "political_response",
                    "source": "Healthcare Workers",
                    "title": "Healthcare Workers Express Concern Over NHI Implementation",
                    "content": "Healthcare worker unions and professional associations have raised serious concerns about NHI readiness, citing understaffed facilities, medicine stockouts, and the potential for a mass exodus of skilled professionals. They demand a phased rollout with proper funding.",
                    "affected_archetypes": ["civic_moderate", "institutional_loyalist", "whistleblower", "economic_migrant"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "education": {
        "category": "education_policy",
        "triggers": ["education", "school", "university", "student", "teacher", "curriculum", "fee"],
        "events": [
            {
                "id": "student_protest_threat",
                "trigger": {"type": "topic_mention_count", "topics": ["education", "fee", "student", "university"], "min_count": 4},
                "event": {
                    "type": "civil_unrest",
                    "source": "Student Representative Councils",
                    "title": "Student Leaders Threaten National Shutdown",
                    "content": "Student representative councils across multiple universities have threatened a coordinated national shutdown if tuition fee increases and funding cuts proceed. They cite the ongoing student debt crisis and the failure of NSFAS to cover basic needs.",
                    "affected_archetypes": ["political_activist", "violent_agitator", "civic_moderate", "disillusioned_dropout"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "housing": {
        "category": "housing_policy",
        "triggers": ["housing", "land", "eviction", "informal settlement", "RDP", "title deed"],
        "events": [
            {
                "id": "land_invasion_response",
                "trigger": {"type": "topic_mention_count", "topics": ["housing", "land", "eviction", "settlement"], "min_count": 4},
                "event": {
                    "type": "civil_unrest",
                    "source": "Community Land Activists",
                    "title": "Land Occupations Escalate in Major Cities",
                    "content": "Community land activists have coordinated a wave of land occupations in Cape Town, Johannesburg, and Durban, demanding immediate housing provision. Municipalities have responded with eviction notices, sparking confrontations between residents and law enforcement.",
                    "affected_archetypes": ["violent_agitator", "community_leader", "political_activist", "economic_migrant"],
                    "severity": "critical",
                    "persist_rounds": 4
                }
            }
        ]
    },
    "mining": {
        "category": "labour_policy",
        "triggers": ["mining", "mine", "NUM", "AMCU", "labour", "strike", "wage"],
        "events": [
            {
                "id": "mine_strike_threat",
                "trigger": {"type": "topic_mention_count", "topics": ["mining", "strike", "wage", "union"], "min_count": 4},
                "event": {
                    "type": "civil_unrest",
                    "source": "AMCU",
                    "title": "Mining Unions Issue Strike Notice",
                    "content": "AMCU and NUM have issued a joint strike notice across multiple platinum and gold mines, demanding wage increases above inflation and improved safety conditions. The Chamber of Mines warns prolonged action could devastate the sector and trigger job losses.",
                    "affected_archetypes": ["political_activist", "economic_migrant", "disillusioned_dropout", "institutional_loyalist"],
                    "severity": "high",
                    "persist_rounds": 3
                }
            }
        ]
    },
    "immigration": {
        "category": "migration_policy",
        "triggers": ["immigration", "foreign", "xenophobia", "migrant", "refugee", "border", "documentation"],
        "events": [
            {
                "id": "xenophobic_violence_spike",
                "trigger": {"type": "topic_mention_count", "topics": ["foreign", "xenophobia", "immigrant", "attack"], "min_count": 3},
                "event": {
                    "type": "civil_unrest",
                    "source": "Human Rights Watch",
                    "title": "Xenophobic Attacks Reported in Multiple Townships",
                    "content": "Reports of xenophobic violence have emerged from Alexandra, Khayelitsha, and Durban townships, with foreign-owned shops looted and families displaced. Community leaders and human rights organizations are calling for urgent government intervention and police protection.",
                    "affected_archetypes": ["economic_migrant", "community_protector", "violent_agitator", "community_leader"],
                    "severity": "critical",
                    "persist_rounds": 4
                }
            }
        ]
    }
}

# Generic fallback events for any domain
GENERIC_EVENTS = [
    {
        "id": "generic_sentiment_spike",
        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.7, "min_proportion": 0.25},
        "event": {
            "type": "institutional_response",
            "source": "Government",
            "title": "Official Response to Public Concerns",
            "content": "The relevant government department has issued a statement acknowledging public concerns raised during consultations. Officials承诺承诺 to review submissions and report back within 30 days, but critics dismiss this as standard delay tactics.",
            "affected_archetypes": ["civic_moderate", "institutional_loyalist", "political_activist", "whistleblower"],
            "severity": "medium",
            "persist_rounds": 2
        }
    },
    {
        "id": "generic_opposition_response",
        "trigger": {"type": "threshold", "metric": "pct_agents_with_impact_above", "value": 0.85, "min_proportion": 0.1},
        "event": {
            "type": "political_response",
            "source": "Opposition",
            "title": "Opposition Parties Demand Urgent Action",
            "content": "Opposition parties have seized on widespread public dissatisfaction, calling for immediate policy revisions and accusing the government of failing to consult meaningfully. Parliamentary debates are being scheduled.",
            "affected_archetypes": ["political_activist", "institutional_loyalist", "civic_moderate"],
            "severity": "medium",
            "persist_rounds": 2
        }
    }
]


class DocumentContextEngine:
    """
    Extracts domain-specific context from graph entities and generates
    dynamic event rules + prompt context rooted in the uploaded document.
    """

    def __init__(self, graph_storage=None):
        self.storage = graph_storage
        self.domain: Optional[str] = None
        self.domain_profile: Dict[str, Any] = {}
        self.dynamic_rules: List[Dict[str, Any]] = []
        self.document_context_block: str = ""

    def build_from_graph(self, graph_id: str) -> Dict[str, Any]:
        """
        Main entry point: read graph entities, detect domain, build context.
        """
        if not self.storage:
            logger.warning("No graph storage provided — using generic context")
            self._build_generic()
            return self.domain_profile

        try:
            entities = self._read_graph_entities(graph_id)
            self._detect_domain(entities)
            self._build_domain_profile(entities)
            self._generate_dynamic_rules()
            self._build_document_context_block()
            logger.info(f"DocumentContextEngine built domain profile: {self.domain}")
            return self.domain_profile
        except Exception as e:
            logger.error(f"Failed to build document context: {e}")
            self._build_generic()
            return self.domain_profile

    def _read_graph_entities(self, graph_id: str) -> List[Dict[str, Any]]:
        """Read all nodes from the graph."""
        nodes = self.storage.get_all_nodes(graph_id)
        logger.info(f"Read {len(nodes)} nodes from graph {graph_id}")
        return nodes

    def _detect_domain(self, entities: List[Dict[str, Any]]) -> None:
        """
        Detect the primary domain by matching entity names/summaries/labels
        against domain trigger keywords.
        """
        # Collect all text from entities
        all_text = " ".join([
            f"{e.get('name', '')} {e.get('summary', '')} {' '.join(e.get('labels', []))}"
            for e in entities
        ]).lower()

        # Score each domain
        domain_scores = {}
        for domain_key, template in DOMAIN_EVENT_TEMPLATES.items():
            score = sum(1 for trigger in template["triggers"] if trigger.lower() in all_text)
            if score > 0:
                domain_scores[domain_key] = score

        if domain_scores:
            self.domain = max(domain_scores, key=domain_scores.get)
            logger.info(f"Detected domain: {self.domain} (score: {domain_scores[self.domain]})")
        else:
            self.domain = "generic"
            logger.info("No specific domain detected — using generic context")

    def _build_domain_profile(self, entities: List[Dict[str, Any]]) -> None:
        """
        Build a structured profile of the document domain:
        - Top entities (people, organizations, locations)
        - Key topics
        - Related institutions
        - Emotional triggers
        """
        # Extract entity types
        entity_by_type = {}
        for e in entities:
            labels = [l for l in e.get("labels", []) if l not in ("Entity", "Node")]
            for label in labels:
                if label not in entity_by_type:
                    entity_by_type[label] = []
                entity_by_type[label].append(e)

        # Top organizations and people
        raw_organizations = [
            e.get("name", "") for e in entity_by_type.get("Organization", [])
        ][:10]
        raw_people = [
            e.get("name", "") for e in entity_by_type.get("Person", [])
        ][:10]
        raw_locations = [
            e.get("name", "") for e in entity_by_type.get("Location", [])
        ][:10]

        # Deduplicate near-duplicate names (e.g. "Julius Malema" vs "Malema")
        organizations, people, locations = quick_resolve_lists(
            raw_organizations, raw_people, raw_locations, threshold=0.75
        )

        # Extract topics from entity names and summaries
        topic_counter = Counter()
        for e in entities:
            name = e.get("name", "").lower()
            summary = e.get("summary", "").lower()
            # Simple keyword extraction
            words = re.findall(r'\b[a-z]{4,}\b', name + " " + summary)
            for word in words:
                if word not in ("this", "that", "with", "from", "have", "been", "were", "they", "their", "what", "when", "where", "which", "while", "about", "would", "could", "should"):
                    topic_counter[word] += 1

        top_topics = [t for t, _ in topic_counter.most_common(15)]

        # Domain-specific topics
        domain_topics = []
        if self.domain and self.domain in DOMAIN_EVENT_TEMPLATES:
            domain_topics = DOMAIN_EVENT_TEMPLATES[self.domain]["triggers"]

        self.domain_profile = {
            "domain": self.domain,
            "organizations": organizations,
            "people": people,
            "locations": locations,
            "top_topics": top_topics,
            "domain_topics": domain_topics,
            "entity_counts": {k: len(v) for k, v in entity_by_type.items()},
            "total_entities": len(entities),
        }

    def _generate_dynamic_rules(self) -> None:
        """Generate event rules based on detected domain."""
        rules = []

        # Add domain-specific rules
        if self.domain and self.domain in DOMAIN_EVENT_TEMPLATES:
            for event_def in DOMAIN_EVENT_TEMPLATES[self.domain]["events"]:
                rule = {
                    "id": event_def["id"],
                    "description": f"Domain-specific trigger for {self.domain}",
                    "category": DOMAIN_EVENT_TEMPLATES[self.domain]["category"],
                    "trigger": event_def["trigger"],
                    "event": event_def["event"],
                    "cooldown_rounds": 4,
                    "max_triggers_per_simulation": 2,
                }
                rules.append(rule)

        # Add generic fallback rules
        for event_def in GENERIC_EVENTS:
            rule = {
                "id": event_def["id"],
                "description": "Generic fallback trigger",
                "category": "general",
                "trigger": event_def["trigger"],
                "event": event_def["event"],
                "cooldown_rounds": 5,
                "max_triggers_per_simulation": 2,
            }
            rules.append(rule)

        self.dynamic_rules = rules
        logger.info(f"Generated {len(rules)} dynamic event rules")

    def _build_document_context_block(self) -> None:
        """
        Build the document-context prompt block injected into agent prompts.
        This replaces/supplements the generic SA_POLICY_CONTEXT.
        """
        dp = self.domain_profile
        domain = dp.get("domain", "general")

        lines = [
            "=" * 60,
            "DOCUMENT-SPECIFIC SIMULATION CONTEXT",
            "=" * 60,
            "",
            f"THIS SIMULATION IS SPECIFICALLY ABOUT: {domain.replace('_', ' ').title()} policy.",
            "",
            "The following real-world actors, organizations, and locations were extracted from",
            "the uploaded policy document. Ground your opinions and reactions in THIS specific",
            "context — not generic South African issues unless they directly intersect.",
            "",
        ]

        if dp.get("organizations"):
            lines.extend([
                "KEY ORGANIZATIONS & INSTITUTIONS:",
                ", ".join(dp["organizations"]),
                "",
            ])

        if dp.get("people"):
            lines.extend([
                "KEY PEOPLE MENTIONED:",
                ", ".join(dp["people"]),
                "",
            ])

        if dp.get("locations"):
            lines.extend([
                "RELEVANT LOCATIONS:",
                ", ".join(dp["locations"]),
                "",
            ])

        if dp.get("domain_topics"):
            lines.extend([
                "CORE TOPICS OF THIS POLICY:",
                ", ".join(dp["domain_topics"]),
                "",
            ])

        lines.extend([
            "INSTRUCTION:",
            "- Reference specific organizations, people, and locations from the document when relevant.",
            "- Your reactions should reflect how THIS policy affects YOUR specific life situation.",
            "- If the policy directly mentions your community, profession, or location, say so explicitly.",
            "- Do not drift into generic SA issues (Eskom, taxi violence, etc.) unless the document connects them.",
            "",
            "=" * 60,
        ])

        self.document_context_block = "\n".join(lines)

    def extract_facts(self, document_text: str, llm_client=None, model_name: str = "") -> List[str]:
        """Extract key factual claims from the document text using LLM."""
        if not document_text or not llm_client:
            return []
        
        try:
            prompt = f"""Extract the 10-15 most important factual claims from this policy document.
These must be OBJECTIVE facts that all agents should know when debating this policy.

DOCUMENT:
{document_text[:8000]}

RULES:
1. Only extract claims that are explicitly stated in the document.
2. Include WHO did WHAT, WHEN, and WHERE if mentioned.
3. Include specific numbers, dates, and named actors.
4. Do NOT include opinions or interpretations.
5. Format as a flat JSON array of strings.

Example good facts:
- "President announced the deployment of forces to the region on 18 July 2017."
- "The deployment was authorised under Section 201 of the Constitution."
- "The opposition party opposed the deployment, calling it political posturing."

Return ONLY a JSON array of strings. No explanation."""

            response = llm_client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract factual claims from documents. Return ONLY JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1500,
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            if isinstance(data, list):
                facts = data
            elif isinstance(data, dict):
                facts = data.get("facts", data.get("claims", []))
            else:
                facts = []
            
            logger.info(f"Extracted {len(facts)} factual claims from document")
            return facts[:20]
        except Exception as e:
            logger.warning(f"Fact extraction failed: {e}")
            return []

    def _build_generic(self) -> None:
        """Build generic fallback profile."""
        self.domain = "generic"
        self.domain_profile = {
            "domain": "generic",
            "organizations": [],
            "people": [],
            "locations": [],
            "top_topics": [],
            "domain_topics": [],
            "entity_counts": {},
            "total_entities": 0,
        }
        self._generate_dynamic_rules()
        self.document_context_block = ""  # No document-specific context

    # ── Public API ──────────────────────────────────────────────

    def get_document_context_block(self) -> str:
        """Return the document context block for prompt injection."""
        return self.document_context_block

    def get_dynamic_rules(self) -> List[Dict[str, Any]]:
        """Return dynamically generated event rules."""
        return self.dynamic_rules

    def get_domain_profile(self) -> Dict[str, Any]:
        """Return the full domain profile."""
        return self.domain_profile

    def should_override_generic_context(self) -> bool:
        """Whether document context should replace (not just supplement) generic SA context."""
        return self.domain != "generic" and self.domain_profile.get("total_entities", 0) > 5
