"""
Agent Profile Generator
Converts entities from the knowledge graph into AgentSociety OpinionAgent profiles.
Personas are grounded in South African socio-economic realities for policy simulation.
"""

import json
import random
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .entity_reader import EntityNode
from ..storage import GraphStorage

logger = get_logger('fub.agent_profile')


@dataclass
class AgentProfile:
    """Profile data structure consumed by OpinionAgent (AgentSociety-compatible)."""
    id: int
    name: str
    persona: str
    background_story: str

    # AgentSociety core fields
    age: Optional[int] = None
    gender: Optional[str] = None
    education: Optional[str] = None
    occupation: Optional[str] = None
    marriage_status: Optional[str] = None

    # Extended attributes
    mbti: Optional[str] = None
    country: Optional[str] = None
    province: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)

    # Group identity — injected into every simulation prompt as a first-class signal.
    # Works for ANY group: gang, political movement, church, taxi association, etc.
    # e.g. "Hard Living gang member, Manenberg, Cape Flats"
    group_affiliation: Optional[str] = None
    # How this persona speaks — injected verbatim into LLM prompts.
    # Covers vocabulary, attitude, what they reference, what they would never say.
    voice_guide: Optional[str] = None
    # Where on the spectrum from civic to extreme this actor sits.
    # e.g. "civic_moderate", "political_activist", "opportunist_looter",
    #       "conspiracy_spreader", "mob_follower", "institutional_loyalist",
    #       "violent_agitator", "criminal_opportunist", "community_protector"
    actor_archetype: Optional[str] = None
    # Specific behavioral tendencies relevant to simulation actions.
    # e.g. "Joins crowd actions when momentum builds. Spreads unverified information
    #       as fact. Takes material advantage during disorder. Defers to dominant voice."
    behavioral_tendencies: Optional[str] = None

    # Source entity tracing
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def to_agentsociety_format(self) -> Dict[str, Any]:
        """Serialise to the format read by run_simulation_as.py / OpinionAgent."""
        profile: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "persona": self.persona,
            "background_story": self.background_story,
            "interested_topics": self.interested_topics or [],
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }
        for attr in ("age", "gender", "education", "occupation", "marriage_status",
                     "mbti", "country", "province", "group_affiliation", "voice_guide",
                     "actor_archetype", "behavioral_tendencies"):
            val = getattr(self, attr, None)
            if val is not None:
                profile[attr] = val
        return profile

    def to_dict(self) -> Dict[str, Any]:
        """Full dict (useful for debugging / logging)."""
        return {
            "id": self.id,
            "name": self.name,
            "persona": self.persona,
            "background_story": self.background_story,
            "age": self.age,
            "gender": self.gender,
            "education": self.education,
            "occupation": self.occupation,
            "marriage_status": self.marriage_status,
            "mbti": self.mbti,
            "country": self.country,
            "province": self.province,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class AgentProfileGenerator:
    """
    Converts knowledge-graph entities into AgentSociety OpinionAgent profiles.

    Pipeline:
    1. Enrich each entity with hybrid vector + BM25 graph search context.
    2. Use LLM (or rule-based fallback) to generate a detailed SA persona.
    3. Return / save as agentsociety_profiles.json.
    """

    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]

    COUNTRIES = ["South Africa"]

    SA_PROVINCES = [
        "Gauteng", "Western Cape", "KwaZulu-Natal", "Eastern Cape",
        "Limpopo", "Mpumalanga", "North West", "Free State", "Northern Cape"
    ]

    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure",
        "expert", "faculty", "official", "journalist", "activist"
    ]

    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo",
        "mediaoutlet", "company", "institution", "group", "community"
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        storage: Optional[GraphStorage] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.storage = storage
        self.graph_id = graph_id

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def generate_profile_from_entity(
        self,
        entity: EntityNode,
        user_id: int,
        use_llm: bool = True
    ) -> AgentProfile:
        """Generate one OpinionAgent profile from a graph entity."""
        entity_type = entity.get_entity_type() or "Entity"
        name = entity.name
        user_name = self._generate_username(name)
        context = self._build_entity_context(entity)

        if use_llm:
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context,
            )
        else:
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
            )

        return AgentProfile(
            id=user_id,
            name=name,
            persona=profile_data.get("persona", f"A {entity_type} named {name}."),
            background_story=profile_data.get("background_story", entity.summary or f"{name} is a {entity_type} in South Africa."),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            education=profile_data.get("education"),
            occupation=profile_data.get("occupation"),
            marriage_status=profile_data.get("marriage_status"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            province=profile_data.get("province"),
            interested_topics=profile_data.get("interested_topics", []),
            group_affiliation=profile_data.get("group_affiliation") or None,
            voice_guide=profile_data.get("voice_guide") or None,
            actor_archetype=profile_data.get("actor_archetype") or None,
            behavioral_tendencies=profile_data.get("behavioral_tendencies") or None,
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )

    def set_graph_id(self, graph_id: str):
        self.graph_id = graph_id

    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 5,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "opinion_space",
    ) -> List[AgentProfile]:
        """
        Generate OpinionAgent profiles in batch (parallel).

        Args:
            entities: Entity list
            use_llm: Whether to use LLM for detailed persona generation
            progress_callback: (current, total, message) callback
            graph_id: Graph ID for hybrid-search context enrichment
            parallel_count: Number of parallel LLM threads
            realtime_output_path: If provided, write agentsociety_profiles.json after each profile
            output_platform: Ignored — always writes agentsociety format

        Returns:
            List of AgentProfile objects
        """
        import concurrent.futures
        from threading import Lock

        if graph_id:
            self.graph_id = graph_id

        total = len(entities)
        profiles: List[Optional[AgentProfile]] = [None] * total
        completed_count = [0]
        lock = Lock()

        def save_realtime():
            if not realtime_output_path:
                return
            with lock:
                existing = [p for p in profiles if p is not None]
                if not existing:
                    return
                try:
                    data = [p.to_agentsociety_format() for p in existing]
                    with open(realtime_output_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.warning(f"Real-time profile save failed: {e}")

        def generate_one(idx: int, entity: EntityNode):
            entity_type = entity.get_entity_type() or "Entity"
            try:
                profile = self.generate_profile_from_entity(entity=entity, user_id=idx, use_llm=use_llm)
                self._print_generated_profile(entity.name, entity_type, profile)
                return idx, profile, None
            except Exception as e:
                logger.error(f"Failed to generate persona for {entity.name}: {e}")
                fallback = AgentProfile(
                    id=idx,
                    name=entity.name,
                    persona=f"A {entity_type} participant in policy discussions.",
                    background_story=entity.summary or f"{entity.name} is a {entity_type} in South Africa.",
                    source_entity_uuid=entity.uuid,
                    source_entity_type=entity_type,
                )
                return idx, fallback, str(e)

        logger.info(f"Starting parallel generation of {total} agent personas (workers: {parallel_count})")
        print(f"\n{'='*60}\nGenerating {total} agent personas (parallel={parallel_count})\n{'='*60}\n")

        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            futures = {executor.submit(generate_one, idx, entity): (idx, entity)
                       for idx, entity in enumerate(entities)}

            for future in concurrent.futures.as_completed(futures):
                idx, entity = futures[future]
                entity_type = entity.get_entity_type() or "Entity"
                try:
                    result_idx, profile, error = future.result()
                    profiles[result_idx] = profile
                    with lock:
                        completed_count[0] += 1
                        current = completed_count[0]
                    save_realtime()
                    if progress_callback:
                        progress_callback(current, total, f"{current}/{total}: {entity.name} ({entity_type})")
                    if error:
                        logger.warning(f"[{current}/{total}] {entity.name} used fallback: {error}")
                    else:
                        logger.info(f"[{current}/{total}] Generated: {entity.name} ({entity_type})")
                except Exception as e:
                    logger.error(f"Exception processing {entity.name}: {e}")
                    with lock:
                        completed_count[0] += 1
                    profiles[idx] = AgentProfile(
                        id=idx,
                        name=entity.name,
                        persona=f"A {entity_type} participant in policy discussions.",
                        background_story=entity.summary or f"{entity.name} is a {entity_type} in South Africa.",
                        source_entity_uuid=entity.uuid,
                        source_entity_type=entity_type,
                    )
                    save_realtime()

        print(f"\n{'='*60}\nGeneration complete — {len([p for p in profiles if p])} agents\n{'='*60}\n")
        return profiles

    def save_profiles(
        self,
        profiles: List[AgentProfile],
        file_path: str,
        platform: str = "opinion_space",
    ):
        """Save profiles as agentsociety_profiles.json (platform param ignored)."""
        data = [p.to_agentsociety_format() for p in profiles]
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(profiles)} agent profiles to {file_path}")

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    def _generate_username(self, name: str) -> str:
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        return f"{username}_{random.randint(100, 999)}"

    def _search_graph_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        if not self.storage or not self.graph_id:
            return {"facts": [], "node_summaries": [], "context": ""}

        results: Dict[str, Any] = {"facts": [], "node_summaries": [], "context": ""}
        query = f"All information, activities, events, relationships and background about {entity.name}"

        try:
            edge_results = self.storage.search(graph_id=self.graph_id, query=query, limit=30, scope="edges")
            all_facts: set = set()
            if isinstance(edge_results, dict) and 'edges' in edge_results:
                for edge in edge_results['edges']:
                    fact = edge.get('fact', '')
                    if fact:
                        all_facts.add(fact)
            results["facts"] = list(all_facts)

            node_results = self.storage.search(graph_id=self.graph_id, query=query, limit=20, scope="nodes")
            all_summaries: set = set()
            if isinstance(node_results, dict) and 'nodes' in node_results:
                for node in node_results['nodes']:
                    summary = node.get('summary', '')
                    if summary:
                        all_summaries.add(summary)
                    node_name = node.get('name', '')
                    if node_name and node_name != entity.name:
                        all_summaries.add(f"Related Entity: {node_name}")
            results["node_summaries"] = list(all_summaries)

            parts = []
            if results["facts"]:
                parts.append("Fact Information:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                parts.append("Related Entities:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(parts)

            logger.info(f"Graph search: {entity.name} — {len(results['facts'])} facts, {len(results['node_summaries'])} nodes")
        except Exception as e:
            logger.warning(f"Graph search failed ({entity.name}): {e}")

        return results

    def _build_entity_context(self, entity: EntityNode) -> str:
        parts = []

        if entity.attributes:
            attrs = [f"- {k}: {v}" for k, v in entity.attributes.items() if v and str(v).strip()]
            if attrs:
                parts.append("### Entity Attributes\n" + "\n".join(attrs))

        existing_facts: set = set()
        if entity.related_edges:
            rels = []
            for edge in entity.related_edges:
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                if fact:
                    rels.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    arrow = f"{entity.name} --[{edge_name}]--> (Related)" if direction == "outgoing" else f"(Related) --[{edge_name}]--> {entity.name}"
                    rels.append(f"- {arrow}")
            if rels:
                parts.append("### Related Facts and Relationships\n" + "\n".join(rels))

        if entity.related_nodes:
            related = []
            for node in entity.related_nodes:
                node_name = node.get("name", "")
                labels = [l for l in node.get("labels", []) if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(labels)})" if labels else ""
                summary = node.get("summary", "")
                related.append(f"- **{node_name}**{label_str}: {summary}" if summary else f"- **{node_name}**{label_str}")
            if related:
                parts.append("### Related Entity Information\n" + "\n".join(related))

        graph = self._search_graph_for_entity(entity)
        new_facts = [f for f in graph.get("facts", []) if f not in existing_facts]
        if new_facts:
            parts.append("### Facts from Knowledge Graph\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        if graph.get("node_summaries"):
            parts.append("### Related Nodes from Knowledge Graph\n" + "\n".join(f"- {s}" for s in graph["node_summaries"][:10]))

        return "\n\n".join(parts)

    def _is_individual_entity(self, entity_type: str) -> bool:
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES

    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
    ) -> Dict[str, Any]:
        is_individual = self._is_individual_entity(entity_type)
        prompt = (self._build_individual_persona_prompt if is_individual else self._build_group_persona_prompt)(
            entity_name, entity_type, entity_summary, entity_attributes, context
        )

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - attempt * 0.1,
                )
                content = response.choices[0].message.content
                if response.choices[0].finish_reason == 'length':
                    content = self._fix_truncated_json(content)

                try:
                    result = json.loads(content)
                    if not result.get("persona"):
                        result["persona"] = f"A {entity_type} named {entity_name}."
                    if not result.get("background_story"):
                        result["background_story"] = entity_summary or f"{entity_name} is a {entity_type} in South Africa."
                    return result
                except json.JSONDecodeError as je:
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result

            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                time.sleep(attempt + 1)

        return self._generate_profile_rule_based(entity_name, entity_type, entity_summary, entity_attributes)

    def _fix_truncated_json(self, content: str) -> str:
        content = content.strip()
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        if content and content[-1] not in '",}]':
            content += '"'
        content += ']' * open_brackets
        content += '}' * open_braces
        return content

    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        import re
        content = self._fix_truncated_json(content)
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"',
                              lambda m: m.group(0).replace('\n', ' ').replace('\r', ' '),
                              json_str)
            for cleaner in [lambda s: s, lambda s: re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', re.sub(r'\s+', ' ', s))]:
                try:
                    result = json.loads(cleaner(json_str))
                    result["_fixed"] = True
                    return result
                except json.JSONDecodeError:
                    pass

        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)
        background_match = re.search(r'"background_story"\s*:\s*"([^"]*)', content)
        if persona_match or background_match:
            return {
                "persona": persona_match.group(1) if persona_match else f"A {entity_type} named {entity_name}.",
                "background_story": background_match.group(1) if background_match else (entity_summary or f"{entity_name} is a {entity_type} in South Africa."),
                "_fixed": True,
            }

        return {
            "persona": f"A {entity_type} named {entity_name}.",
            "background_story": entity_summary or f"{entity_name} is a {entity_type} in South Africa.",
        }

    def _get_system_prompt(self, is_individual: bool) -> str:
        entity_type_guidance = (
            "You are generating a profile for a South African individual citizen."
            if is_individual else
            "You are generating a profile for a South African institution, organisation, or community group."
        )
        return f"""You are an expert in South African socio-economics, public policy, and demography.
Your task is to generate deeply realistic personas for a POLICY SIMULATION — digital agents that
represent South African people or institutions so that policies can be tested on them BEFORE
being implemented on actual citizens.

{entity_type_guidance}

The personas you generate must accurately reflect South African lived realities:
- The full socio-economic spectrum: from informal settlement residents to middle-class suburbanites
  to rural farming communities
- South Africa's 11-language landscape (isiZulu, isiXhosa, Afrikaans, Sesotho, English, etc.)
  — note the character's home language and how it shapes their expression
- The nine provinces and the very different conditions in each
  (e.g., Limpopo poverty vs Western Cape tourism economy vs Gauteng urban inequality)
- Key SA pressures: load-shedding, unemployment (~32%), social grants (SRD/SASSA),
  land reform, BEE, NHI, crime, GBV, housing backlogs, water access
- Political awareness: ANC, DA, EFF, MK Party loyalties and disillusionment
- Ubuntu values, community solidarity, religious influence (Christianity dominant,
  also Islam in Cape Malay communities, Hindu in KZN)
- The legacy of apartheid on spatial planning, economic access, and identity
- Youth demographics (60%+ youth unemployment) vs pension-age grant recipients

Generate valid JSON only. All string values must contain no unescaped newlines. Use English."""

    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
    ) -> str:
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No additional context"
        return f"""Generate a detailed South African citizen persona for this individual entity.
This persona will be used as a digital agent in a policy simulation that must represent the FULL
spectrum of South African society — from civic moderates to political extremists, from community
leaders to opportunist looters. Accurate edge-case representation is as important as mainstream
representation. Policy proposals must be stress-tested against ALL actor types.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

STEP 1 — DETECT IDENTITY ANCHORS (read context carefully):

A) GROUP AFFILIATION: Does this entity belong to any gang, faction, political movement,
   religious congregation, criminal network, taxi association, civic group, sports crew,
   youth brigade, or any other tight-knit identity group?
   Signals: "MEMBER_OF", "AFFILIATED_WITH", "PART_OF", "BELONGS_TO", "ASSOCIATED_WITH"
   relationships, or direct mentions in summary/attributes.
   → If yes: that group is the MOST IMPORTANT fact. It shapes voice, values, and all opinions.
   → Groups include (non-exhaustive): street gangs, the Numbers (26s/27s/28s), EFF/MK/PAC
     branches, Zuma loyalists, taxi associations, church congregations, SAPS/military,
     ANC Youth League, student movements (SASCO, PASMA), community policing forums,
     foreign national networks, faith-healing movements, informal settlement committees,
     drug networks, vigilante groups.

B) ACTOR ARCHETYPE: Where does this person sit on the civic-to-extreme spectrum?
   Choose the single best fit from this list (or create a precise variant):
   - "civic_moderate"          — follows rules, engages through legitimate channels
   - "community_leader"        — mobilises others, holds moral/social authority
   - "political_activist"      — party-driven, ideologically committed, vocal
   - "institutional_loyalist"  — trusts and defends the system (government, police, church)
   - "disillusioned_dropout"   — disengaged, cynical, doesn't vote or participate
   - "conspiracy_spreader"     — shares unverified claims, mistrusts official narratives
   - "mob_follower"            — joins crowd actions when momentum builds, not a leader
   - "opportunist_looter"      — takes material advantage during disorder or crisis
   - "violent_agitator"        — actively incites or participates in violent protest/unrest
   - "criminal_opportunist"    — engages in petty crime, scams, or survival crime regularly
   - "community_protector"     — vigilante or informal enforcer protecting their turf
   - "economic_migrant"        — foreign national focused on survival, targets of xenophobia
   - "whistleblower"           — exposes wrongdoing, high personal risk tolerance
   - "grant_dependent_survivor" — SASSA grants are primary income, system dependency shapes worldview
   If none fit, invent a precise 2-word archetype. This is a required field.

C) BEHAVIORAL TENDENCIES: Based on archetype + group, list 3-5 specific behavioral patterns
   this agent exhibits IN a simulation involving opinions, social pressure, and unrest topics.
   Examples:
   - "Shares rumours as fact when the crowd is with them."
   - "Stays silent in calm rounds but amplifies dominant voices during tension."
   - "Frames every policy question through 'what's in it for my people'."
   - "Would physically join a looting event if peers were already doing it."
   - "Deflects blame to foreign nationals when community resources are scarce."

Generate JSON with the following fields:

1. persona: 1-2 sentences capturing who this person IS. Lead with group identity if present,
   then archetype-shaped worldview. Never sound generic or neutral.
   Bad: "A South African citizen concerned about unemployment."
   Good: "A mob-follower from KwaMashu who joined the July 2021 looting after watching
         his neighbours, and now justifies it as the only language government understands."

2. background_story: ~500 words, continuous prose. Cover IN THIS ORDER:
   a) Group/archetype identity: what they belong to, how it defines them, what it costs them
   b) The specific events or conditions that shaped their position (looting, protest, joining a
      gang, losing a job, being displaced, police encounter, church conversion, etc.)
   c) Demographics: home language, province, township/suburb, race/ethnicity
   d) Socio-economic: employment, income, housing type, medical aid vs public clinic
   e) Daily pressures: load-shedding, water, transport, food security
   f) Political awareness: party alignment or rejection, stance on ANC/DA/EFF/MK
   g) Language texture: home language influence, SA slang, code-switching patterns
   h) Apartheid legacy's effect on their family

3. group_affiliation: Precise description if applicable.
   Examples: "Hard Living gang member, Manenberg, Cape Flats"
             "EFF branch organiser, Tshwane"
             "28s Numbers gang, Pollsmoor-adjacent"
             "Zuma MK loyalist, KwaMashu"
             "Pentecostal church deacon, Soweto"
             "Taxi association enforcer, OR Tambo rank"
   Return null if no clear group affiliation exists.

4. voice_guide: 3-5 sentences of CONCRETE speech instructions. Cover:
   - Vocabulary and slang specific to this persona (name actual words/phrases)
   - What topics they always reference (territory, God, the struggle, the rand, etc.)
   - Emotional register (hot-headed, measured, conspiratorial, preachy, streetwise)
   - What this person would NEVER say (academic language, balanced policy analysis, etc.)
   - Any code-switching pattern (Zulu/English, Afrikaans/English, Sotho/English)
   Return null only if no distinguishing voice pattern exists.

5. actor_archetype: Single archetype string from the list above (required, no null).

6. behavioral_tendencies: 3-5 sentences describing specific behaviors in simulation context.
   Must describe what they DO (share rumours, join crowds, loot, inform, protect, deflect)
   not what they believe. Required, no null.

7. age: Integer (SA median age ~28; adjust to fit archetype — looters skew younger, elders older)
8. gender: "male" or "female"
9. education: Highest qualification
10. occupation: Job title or status
11. marriage_status: One of "Single", "Married", "Divorced", "Widowed", "Cohabiting"
12. mbti: MBTI type
13. country: "South Africa"
14. province: One of the 9 SA provinces
15. interested_topics: Topics THIS specific persona actually cares about — shaped by archetype.
    A looter cares about: ["looting", "unemployment", "food prices", "police brutality", "inequality"]
    A conspiracy spreader: ["state capture", "5G", "white monopoly capital", "deep state", "media lies"]
    NOT a generic SA policy list.

Important: All strings on a single line. country MUST be "South Africa". age must be integer.
actor_archetype and behavioral_tendencies are REQUIRED — never null."""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
    ) -> str:
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No additional context"
        return f"""Generate a detailed South African institutional persona for this group entity.
This profile will be used as a digital agent in a South African policy simulation.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

Generate JSON with the following fields:

1. persona: Short institutional role descriptor (1-2 sentences). Captures the organisation's
   mandate and stance (e.g., "A government department responsible for housing delivery,
   perpetually under-resourced and politically scrutinised.").

2. background_story: Detailed institutional profile (~500 words continuous prose). Must cover:
   - Organisation identity: full name, type, mandate, founding context (often post-1994)
   - SA policy position: stance on NHI, land reform, BEE, grants, load-shedding, GBV
   - Constituency: who they represent or serve
   - Communication style: formal/populist/activist, languages used
   - SA-specific pressures: budget cuts, cadre deployment, accountability, community trust
   - Key policy battles and historical role (Marikana, State Capture, COVID, July 2021 unrest)

3. age: 30 (institutional account placeholder)
4. gender: "other"
5. education: "Institutional"
6. occupation: Institutional role (e.g., "Government Department", "Civil Society NGO",
   "Trade Union", "Academic Institution")
7. marriage_status: "N/A"
8. mbti: MBTI type describing engagement style
9. country: "South Africa"
10. province: Primary province, or "National"
11. interested_topics: SA policy areas the institution actively engages with

Important: All strings on a single line. country MUST be "South Africa". age must be integer 30."""

    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
    ) -> Dict[str, Any]:
        province = random.choice(self.SA_PROVINCES)
        entity_type_lower = entity_type.lower()

        if entity_type_lower in ["student", "alumni"]:
            return {
                "persona": f"A {entity_type.lower()} from {province} navigating high youth unemployment and an under-resourced education system.",
                "background_story": (
                    f"{entity_name} is a {entity_type.lower()} from {province}, South Africa. "
                    f"They rely on NSFAS or family support, face load-shedding that disrupts study, and are acutely "
                    f"aware of the gap between post-1994 promises and daily reality. Youth unemployment at 60%+ "
                    f"looms over every career decision."
                ),
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "education": "Matric",
                "occupation": "Student",
                "marriage_status": "Single",
                "mbti": random.choice(self.MBTI_TYPES),
                "country": "South Africa",
                "province": province,
                "interested_topics": ["education fees", "youth unemployment", "NSFAS", "social grants", "load-shedding"],
            }

        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "persona": f"A recognised {entity_type.lower()} and public voice on South African policy and socio-economic issues.",
                "background_story": (
                    f"{entity_name} is a recognised {entity_type.lower()} based in South Africa, "
                    f"with expertise intersecting the country's most pressing policy debates — inequality, "
                    f"state capacity, BEE, NHI, and land reform."
                ),
                "age": random.randint(35, 60),
                "gender": random.choice(["male", "female"]),
                "education": "Postgraduate degree",
                "occupation": entity_attributes.get("occupation", "Policy Expert"),
                "marriage_status": random.choice(["Married", "Single", "Divorced"]),
                "mbti": random.choice(["ENTJ", "INTJ", "ENTP", "INTP"]),
                "country": "South Africa",
                "province": province,
                "interested_topics": ["land reform", "BEE", "NHI", "inequality", "state capture", "economic policy"],
            }

        elif entity_type_lower in ["mediaoutlet", "socialmediaplatform"]:
            return {
                "persona": f"A South African media entity covering national affairs, policy debates, and community issues.",
                "background_story": (
                    f"{entity_name} is a South African media entity covering national affairs, "
                    f"policy debates, and community issues — load-shedding, service delivery, "
                    f"political accountability, and social justice."
                ),
                "age": 30,
                "gender": "other",
                "education": "Institutional",
                "occupation": "Media Organisation",
                "marriage_status": "N/A",
                "mbti": "ISTJ",
                "country": "South Africa",
                "province": "National",
                "interested_topics": ["service delivery", "political accountability", "social justice", "load-shedding"],
            }

        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            return {
                "persona": f"A South African institution navigating transformation mandates, budget constraints, and service delivery expectations.",
                "background_story": (
                    f"{entity_name} is a South African institution operating in the post-apartheid landscape. "
                    f"It navigates tensions between transformation mandates, budget constraints, "
                    f"and service delivery expectations."
                ),
                "age": 30,
                "gender": "other",
                "education": "Institutional",
                "occupation": entity_type,
                "marriage_status": "N/A",
                "mbti": "ISTJ",
                "country": "South Africa",
                "province": province,
                "interested_topics": ["public policy", "service delivery", "transformation", "community development"],
            }

        else:
            return {
                "persona": f"A {entity_type.lower()} in South Africa shaped by unemployment, load-shedding, and inequality.",
                "background_story": (
                    entity_summary or
                    f"{entity_name} is a {entity_type.lower()} in South Africa, shaped by high unemployment, "
                    f"load-shedding, and inequality. They participate in public debates about policy."
                ),
                "age": random.randint(25, 50),
                "gender": random.choice(["male", "female"]),
                "education": random.choice(["Matric", "Diploma", "Bachelor's degree"]),
                "occupation": entity_type,
                "marriage_status": random.choice(["Single", "Married", "Cohabiting"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": "South Africa",
                "province": province,
                "interested_topics": ["service delivery", "unemployment", "inequality", "social grants"],
            }

    def _print_generated_profile(self, entity_name: str, entity_type: str, profile: AgentProfile):
        sep = "-" * 70
        topics_str = ', '.join(profile.interested_topics) if profile.interested_topics else 'None'
        print(
            f"\n{sep}\n[Generated] {entity_name} ({entity_type}) — ID: {profile.id}\n{sep}\n"
            f"[Persona]\n{profile.persona}\n\n"
            f"[Background Story]\n{profile.background_story}\n\n[Attributes]\n"
            f"Age: {profile.age} | Gender: {profile.gender} | MBTI: {profile.mbti}\n"
            f"Education: {profile.education} | Occupation: {profile.occupation} | "
            f"Marriage: {profile.marriage_status} | Province: {profile.province}\n"
            f"Topics: {topics_str}\n{sep}"
        )
