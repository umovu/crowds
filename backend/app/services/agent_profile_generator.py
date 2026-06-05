"""
Agent Profile Generator
Converts entities from the knowledge graph into AgentSociety OpinionAgent profiles.
Personas are grounded in South African socio-economic realities for policy simulation.
"""

import json
import re
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
    # e.g. "Gang member, Township, City"
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

    # Institutional / collective agent flag
    # True for organizations, government agencies, political parties, media outlets, gangs,
    # unions, NGOs — any entity that speaks as a collective/institutional voice rather than
    # an individual person. These agents use "we/our mandate" not "I/my opinion".
    is_institutional: bool = False

    # Core focus flag — when True, agent is guaranteed to participate every round
    # and receives higher influence weight (1.5x) in the simulation. Use for protagonist
    # or priority agents that should always be part of the narrative.
    is_core_focus: bool = False

    # === AgentSociety Psychological Architecture ===
    # Emotions (0-10 scale for each)
    emotions: Optional[Dict[str, float]] = None
    emotion_keyword: Optional[str] = None
    emotion_thought: Optional[str] = None
    
    # Needs (Maslow's hierarchy)
    needs: Optional[List[Dict]] = None
    
    # Cognition (attitudes toward topics)
    attitudes: Optional[List[Dict]] = None
    beliefs: Optional[List[str]] = None
    
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
            "is_core_focus": self.is_core_focus,
        }

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
        graph_id: Optional[str] = None,
        enrichment_data: Optional[Dict[str, str]] = None,
        mode: str = "policy",
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.storage = storage
        self.graph_id = graph_id
        self.enrichment_data = enrichment_data or {}
        # 'policy' (default) or 'product' — kept consistent with the rest of the
        # prepare pipeline (simulation_manager, DocumentContextEngine).
        self.mode = mode
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def get_usage_stats(self) -> dict:
        price_in = float(Config.LLM_PRICE_PROMPT_PER_1M or 0.14)
        price_out = float(Config.LLM_PRICE_COMPLETION_PER_1M or 0.28)
        cost = (
            self._usage["prompt_tokens"] / 1_000_000 * price_in +
            self._usage["completion_tokens"] / 1_000_000 * price_out
        )
        return {**self._usage, "estimated_cost_usd": round(cost, 6)}

    def _extra_kwargs(self) -> dict:
        """Provider-specific extras (e.g. disable Qwen thinking mode)."""
        extras = Config.llm_extra_body()
        return {"extra_body": extras} if extras else {}

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
            is_institutional=profile_data.get("is_institutional", False),
            # AgentSociety psychological architecture
            emotions=profile_data.get("emotions"),
            emotion_keyword=profile_data.get("emotion_keyword"),
            emotion_thought=profile_data.get("emotion_thought"),
            needs=profile_data.get("needs"),
            attitudes=profile_data.get("attitudes"),
            beliefs=profile_data.get("beliefs"),
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
    # Population expansion (LLM self-generation)
    # ──────────────────────────────────────────────────────────────

    def determine_required_agent_count(
        self,
        seed_profiles: List[AgentProfile],
        document_text: str,
    ) -> int:
        """
        Analyze document and seed profiles to determine appropriate agent count.
        
        Returns the target number of agents needed for a meaningful simulation.
        No fixed cap - determined by document richness and context.
        """
        if not seed_profiles:
            return 20
        
        if len(seed_profiles) >= 30:
            return len(seed_profiles)
        
        prompt = f"""Analyze this document and determine how many distinct agent personas are needed 
to create a meaningful simulation of the events described.

Seed entities from document: {len(seed_profiles)}
Document excerpt (first 2000 chars):
{document_text[:2000]}

Seed agent types (for reference):
{', '.join([f"{p.name} ({p.actor_archetype or 'unknown'})" for p in seed_profiles[:10]])}

Consider:
- How many distinct stakeholder groups are present? (e.g., protesters, police, victims, witnesses, officials, media)
- How complex is the event? (single incident vs. widespread unrest)
- What regions/locations are mentioned?

Return ONLY a number (integer) representing the recommended total agent count.
Think about the minimum needed to represent all perspectives fairly."""

        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You are a simulation design expert. Return only a number."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=10,
                    temperature=0.3,
                    **self._extra_kwargs(),
                )
                if response.usage:
                    self._usage["prompt_tokens"] += response.usage.prompt_tokens
                    self._usage["completion_tokens"] += response.usage.completion_tokens
                content = response.choices[0].message.content.strip()
                count = int(''.join(filter(str.isdigit, content)))
                if count >= len(seed_profiles):
                    return max(count, 10)
            except Exception as e:
                logger.warning(f"Agent count determination failed (attempt {attempt+1}): {e}")
        
        return max(len(seed_profiles) * 2, 15)

    def expand_population(
        self,
        seed_profiles: List[AgentProfile],
        document_text: str,
        target_count: Optional[int] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[AgentProfile]:
        """
        Expand agent population by synthesizing new agents based on document context.
        
        Args:
            seed_profiles: Original agents from extracted entities
            document_text: Original document text for context
            target_count: Target total (if None, determined by LLM analysis)
            progress_callback: Optional callback for progress updates
            
        Returns:
            Combined list of seed + expanded agents
        """
        if not seed_profiles:
            logger.warning("No seed profiles to expand from")
            return []
        
        if target_count is None:
            target_count = self.determine_required_agent_count(seed_profiles, document_text)
        
        current_count = len(seed_profiles)
        if current_count >= target_count:
            logger.info(f"Seed profiles ({current_count}) already meet target ({target_count}), no expansion needed")
            return seed_profiles
        
        to_generate = target_count - current_count
        logger.info(f"Expanding population: {current_count} -> {target_count} (generating {to_generate} new agents)")
        
        if progress_callback:
            progress_callback(0, to_generate, f"Generating {to_generate} additional agents...")
        
        # Extract context from seed profiles
        provinces = list(set(p.province for p in seed_profiles if p.province))
        topics = set()
        for p in seed_profiles:
            if p.interested_topics:
                topics.update(p.interested_topics)
        
        # Get archetype distribution from seed
        archetype_counts: Dict[str, int] = {}
        for p in seed_profiles:
            arch = p.actor_archetype or "civic_moderate"
            archetype_counts[arch] = archetype_counts.get(arch, 0) + 1
        
        seed_archetypes = list(archetype_counts.keys())
        
        context_summary = f"""
Document discusses: {', '.join(list(topics)[:10])}
Location(s): {', '.join(provinces) if provinces else 'South Africa'}
Number of seed agents: {current_count}
"""
        
        # Generate agents in batches
        expanded = []
        batch_size = 5
        for batch_start in range(0, to_generate, batch_size):
            batch_count = min(batch_size, to_generate - batch_start)
            
            try:
                batch_profiles = self._generate_expanded_batch(
                    count=batch_count,
                    context=context_summary,
                    seed_archetypes=seed_archetypes,
                    existing_names=[p.name for p in seed_profiles + expanded],
                    province=provinces[0] if provinces else None,
                )
                expanded.extend(batch_profiles)
                
                if progress_callback:
                    progress_callback(len(expanded), to_generate, f"Generated {len(expanded)}/{to_generate}")
                    
            except Exception as e:
                logger.warning(f"Batch generation failed: {e}")
                continue
        
        # Combine seed + expanded
        all_profiles = seed_profiles + expanded
        
        # Reassign IDs
        for i, profile in enumerate(all_profiles):
            profile.id = i
        
        logger.info(f"Population expansion complete: {len(seed_profiles)} seed + {len(expanded)} expanded = {len(all_profiles)} total")
        return all_profiles

    def _generate_expanded_batch(
        self,
        count: int,
        context: str,
        seed_archetypes: List[str],
        existing_names: List[str],
        province: Optional[str] = None,
    ) -> List[AgentProfile]:
        """Generate a batch of expanded agents."""
        
        province_str = province or "South Africa"
        
        prompt = f"""Generate {count} distinct South African citizen personas for a policy simulation.

CONTEXT FROM SEED DOCUMENT:
{context}

REQUIREMENTS:
1. Each person must be different from these existing names: {', '.join(existing_names[:20])}
2. Must be contextually appropriate for the document topic and location ({province_str})
3. Cover diverse archetypes - use these if available: {', '.join(seed_archetypes)}
4. Include full range: civic_moderate, political_activist, violent_agitator, opportunist_looter,
   mob_follower, conspiracy_spreader, community_leader, institutional_loyalist, disillusioned_dropout,
   criminal_opportunist, community_protector, grant_dependent_survivor, economic_migrant, whistleblower
5. Each persona must feel GROUNDED in a real SA place — name townships, suburbs, taxi ranks, spaza shops, etc.
6. Personas must take STANCES, not be neutral. They should have strong opinions shaped by their lived experience.

Return JSON array of {count} personas, each with:
- name: Full name
- persona: 1-2 sentences describing who they are. Include a local place name. Must take a stance, not be neutral.
- background_story: ~150 words. Include specific local details (streets, clinics, schools, events).
- age: integer (18-65)
- gender: "male" or "female"
- education: string
- occupation: string
- province: string (use {province_str})
- interested_topics: array of 3-5 topics relevant to this person
- actor_archetype: one of the archetypes listed above
- behavioral_tendencies: 2-3 sentences describing what they do in simulation
- voice_guide: 2-3 sentences of concrete speech instructions. Include SA slang, code-switching, emotional register, and what they would NEVER say.

Return ONLY valid JSON array, no explanation."""

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You generate realistic South African personas for policy simulation. Return ONLY JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                    max_tokens=2000,
                    **self._extra_kwargs(),
                )
                if response.usage:
                    self._usage["prompt_tokens"] += response.usage.prompt_tokens
                    self._usage["completion_tokens"] += response.usage.completion_tokens
                content = response.choices[0].message.content
                
                # Try to parse as array or extract array
                try:
                    data = json.loads(content)
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = data.get("personas", data.get("agents", [data]))
                    else:
                        continue
                except json.JSONDecodeError:
                    import re
                    arr_match = re.search(r'\[[\s\S]*\]', content)
                    if arr_match:
                        items = json.loads(arr_match.group())
                    else:
                        continue
                
                profiles = []
                for idx, item in enumerate(items):
                    if not item.get("name"):
                        continue
                    profile = AgentProfile(
                        id=idx,
                        name=item.get("name", f"Person_{idx}"),
                        persona=item.get("persona", "A South African citizen."),
                        background_story=item.get("background_story", ""),
                        age=item.get("age", random.randint(20, 50)),
                        gender=item.get("gender", random.choice(["male", "female"])),
                        education=item.get("education", "Matric"),
                        occupation=item.get("occupation", "Unemployed"),
                        province=item.get("province", province_str),
                        interested_topics=item.get("interested_topics", []),
                        actor_archetype=item.get("actor_archetype", "civic_moderate"),
                        behavioral_tendencies=item.get("behavioral_tendencies", ""),
                        voice_guide=item.get("voice_guide", ""),
                        group_affiliation=item.get("group_affiliation", ""),
                    )
                    profiles.append(profile)
                
                if profiles:
                    return profiles
                    
            except Exception as e:
                logger.warning(f"Expanded batch generation failed (attempt {attempt+1}): {e}")
                time.sleep(1)
        
        # Fallback: generate simple profiles
        fallback = []
        for i in range(count):
            fallback.append(AgentProfile(
                id=i,
                name=f"Generated_{i}_{random.randint(1000, 9999)}",
                persona=f"A resident in {province_str} affected by the events described.",
                background_story="A local resident who has been impacted by recent events in the area.",
                age=random.randint(20, 50),
                gender=random.choice(["male", "female"]),
                education="Matric",
                occupation=random.choice(["Unemployed", "Casual worker", "Small trader"]),
                province=province_str,
                interested_topics=["service delivery", "unemployment", "safety"],
                actor_archetype=random.choice(seed_archetypes) if seed_archetypes else "civic_moderate",
                behavioral_tendencies="Participates in discussions when prompted.",
            ))
        return fallback

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

    # Real first names are typically one word, capitalised, no digits.
    # An entity name is "abstract" (= a category, place, role, or fragment
    # rather than a real human's name) when:
    #   * it's plural ("representatives", "officers", "residents", "groups")
    #   * it's a job title / role only ("Administrator", "Spokesperson")
    #   * it's a place ("Western Cape", "Gauteng", "Soweto")
    #   * it's a single common word ("She", "They", "Government")
    #   * it has parenthetical descriptors ("(Government)")
    # When detected, the generator embodies the category as a specific
    # named individual (Sipho, Aisha, Thabo...) rather than treating the
    # label itself as an institutional voice. This avoids agents named
    # "Western Cape" or "Union representatives".
    _ABSTRACT_NAME_SUFFIXES = (
        "s", "es",
    )
    _ABSTRACT_NAME_TOKENS = {
        # generic plurals / collectives
        "representatives", "officers", "members", "residents", "officials",
        "leaders", "workers", "supporters", "voters", "spokespersons",
        "spokesperson", "administrator", "administrators", "delegate",
        "delegates", "committee", "council", "councillors", "councilor",
        "officers", "department", "team", "panel", "ministry", "group",
        "groups", "community", "communities", "agency", "office", "bureau",
        # pronouns / fragments
        "he", "she", "they", "them", "we", "us", "it",
        # generic descriptors
        "government", "opposition", "the", "various", "other", "unknown",
        # SA provinces / common geographic labels
        "gauteng", "limpopo", "mpumalanga", "kwazulu-natal", "kwazulu",
        "natal", "freestate", "free", "eastern", "western", "northern",
        "southern", "cape", "northwest", "north-west",
    }

    @classmethod
    def _is_abstract_name(cls, name: str) -> bool:
        """Detect names that look like a category/role/place/fragment rather
        than a real person, so the generator can embody them as a specific
        named human instead of treating the label as an institutional voice."""
        if not name:
            return True
        n = name.strip()
        if not n:
            return True
        # Single bare token: "She", "Government", "Gauteng"
        tokens = [t for t in n.replace("-", " ").split() if t]
        if len(tokens) == 1:
            if n.lower() in cls._ABSTRACT_NAME_TOKENS:
                return True
            # Single word but not a known abstract token: could still be a
            # plural ("Residents") or a role ("Administrator"). Flag if it
            # ends with a typical plural suffix and isn't capitalised oddly.
            low = n.lower()
            if low.endswith(("ives", "tives", "ators", "ents", "ies", "ans", "ions")) and len(n) > 5:
                return True
            return False
        # Multi-token: flag if any token is an abstract marker
        for t in tokens:
            if t.lower() in cls._ABSTRACT_NAME_TOKENS:
                return True
        # Parenthetical descriptors like "Mayor (DA)" are fine, but bare
        # "(Government)" wrappers aren't — strip and re-check
        if n.startswith("(") and n.endswith(")"):
            return cls._is_abstract_name(n[1:-1])
        return False

    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
    ) -> Dict[str, Any]:
        is_individual = self._is_individual_entity(entity_type)
        # If the entity has a categorical/abstract name (a role, plural,
        # place, or fragment instead of a real person's name) and isn't
        # already an individual, embody it as a specific named human via
        # the representative path. Avoids agents called "Western Cape" or
        # "Union representatives".
        is_representative = (not is_individual) and self._is_abstract_name(entity_name)

        # ── On-disk persona cache: two-level lookup.
        #   1. EXACT key (same project + entity) → re-runs of the same project
        #      reuse personas verbatim.
        #   2. ARCHETYPE key (same archetype + topic) → different projects on
        #      the same topic can share personas. E.g. any 'taxi_operator' in
        #      a Cape-Flats SANDF sim reuses the same persona pool.
        # Either hit skips the ~5-10k Plus tokens for this agent.
        from . import persona_cache
        enrichment_snippet = self._get_enrichment_block(entity_type, context)
        exact_key = persona_cache.make_key(
            model_name=self.model_name,
            entity_name=entity_name,
            entity_type=entity_type,
            entity_summary=entity_summary,
            entity_attributes=entity_attributes,
            context=context,
            enrichment_snippet=enrichment_snippet,
        )
        arch_key = persona_cache.make_archetype_key(
            model_name=self.model_name,
            entity_type=entity_type,
            enrichment_snippet=enrichment_snippet,
        )
        cached = persona_cache.get(exact_key) or persona_cache.get(arch_key)
        if cached is not None:
            return cached

        if is_representative:
            prompt_builder = self._build_representative_persona_prompt
        elif is_individual:
            prompt_builder = self._build_individual_persona_prompt
        else:
            prompt_builder = self._build_group_persona_prompt
        prompt = prompt_builder(entity_name, entity_type, entity_summary, entity_attributes, context)

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual, is_representative=is_representative)},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - attempt * 0.1,
                    **self._extra_kwargs(),
                )
                if response.usage:
                    self._usage["prompt_tokens"] += response.usage.prompt_tokens
                    self._usage["completion_tokens"] += response.usage.completion_tokens
                content = response.choices[0].message.content
                if response.choices[0].finish_reason == 'length':
                    content = self._fix_truncated_json(content)

                try:
                    result = json.loads(content)
                    if not result.get("persona"):
                        result["persona"] = f"A {entity_type} named {entity_name}."
                    if not result.get("background_story"):
                        result["background_story"] = entity_summary or f"{entity_name} is a {entity_type} in South Africa."
                    persona_cache.put(exact_key, result, meta={"entity": entity_name, "type": entity_type})
                    persona_cache.put(arch_key,  result, meta={"entity": entity_name, "type": entity_type, "level": "archetype"})
                    return result
                except json.JSONDecodeError as je:
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        persona_cache.put(exact_key, result, meta={"entity": entity_name, "type": entity_type, "fixed_json": True})
                        persona_cache.put(arch_key,  result, meta={"entity": entity_name, "type": entity_type, "level": "archetype", "fixed_json": True})
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

    def _get_system_prompt(self, is_individual: bool, is_representative: bool = False) -> str:
        if is_representative:
            entity_type_guidance = (
                "You are generating a profile for a SPECIFIC NAMED INDIVIDUAL who personally "
                "embodies a broader category, role, or constituency. The persona must be a real "
                "person with a real first + last name (e.g. 'Thabo Mokoena', not 'Union Representative'), "
                "lived experience, age, family, and a voice — even though they speak from within "
                "a wider group's perspective."
            )
        elif is_individual:
            entity_type_guidance = (
                "You are generating a profile for a South African individual citizen."
            )
        else:
            entity_type_guidance = (
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

CIVIC/ESTABLISHMENT VOICES:
- "civic_moderate"          — follows rules, engages through legitimate channels
- "community_leader"        — mobilises others, holds moral/social authority
- "institutional_loyalist"  — trusts and defends the system (government, police, church)

ACTIVISM/POLITICAL:
- "political_activist"      — party-driven, ideologically committed, vocal
- "student_activist"        — student movement, SASCO/PASMA, mobilisation potential

COMMUNITY/SOCIAL:
- "street_committee_chair"  — formal community leadership, interacts with ward councillors
- "traditional_authority"   — chief, induna, pastor, sheikh, elder, Ubuntu voice
- "community_organizer"     — calls meetings, mediates disputes, represents block/street
- "spaza_shop_owner"        — informal economy, community bulletin board, informal trader

ECONOMIC LIVELIHOOD:
- "taxi_operator"           — taxi association member, transport sector, strike potential
- "informal_trader"         — street vendor, survival economy
- "small_business_owner"    — employs others, formalizing economy
- "gig_worker"              — Uber, delivery, precarious economy
- "unemployed_youth"        — NEET, economic desperation, recruitment target

CRIMINAL/GANG:
- "gang_member"             — numbered gang (28s, 26, 27), turf protection, violence
- "syndicates"              — organized crime, smuggling, protection rackets
- "mob_follower"            — joins crowd actions when momentum builds, not a leader
- "opportunist_looter"      — takes material advantage during disorder or crisis
- "violent_agitator"        — actively incites or participates in violent protest/unrest
- "criminal_opportunist"    — engages in petty crime, scams, or survival crime regularly
- "community_protector"     — vigilante or informal enforcer protecting their turf

VULNERABLE/MARGINALIZED:
- "gbv_advocate"            — gender-based violence survivor/advocate
- "foreign_national"        — migrant, xenophobia target, survival focus
- "person_with_disability"  — accessible concerns, often overlooked
- "elderly_grant_recipient" — SASSA pension, healthcare access
- "grant_dependent_survivor" — SASSA grants are primary income, system dependency

DISENGAGED/DISTRUSTFUL:
- "disillusioned_dropout"   — disengaged, cynical, doesn't vote or participate
- "conspiracy_spreader"     — shares unverified claims, mistrusts official narratives
- "whistleblower"           — exposes wrongdoing, high personal risk tolerance

PROFESSIONAL/CIVIL SOCIETY:
- "nurse_healthcare_worker" — public sector, strike potential, healthcare access
- "teacher"                 — education sector, school safety, youth focus
- "community_journalist"    — ground-up news, information flow, misinformation
- "ngo_worker"              — civil society, service delivery advocacy

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
   then archetype-shaped worldview. Never sound generic or neutral. Include a LOCAL ANCHOR
   (township, suburb, or specific place) so they feel grounded in SA geography.
   Bad: "A South African citizen concerned about unemployment."
   Good: "A mob-follower from KwaMashu who joined the July 2021 looting after watching
         his neighbours, and now justifies it as the only language government understands."

2. background_story: ~500 words, continuous prose. Cover IN THIS ORDER:
   a) Group/archetype identity: what they belong to, how it defines them, what it costs them
   b) The specific events or conditions that shaped their position (looting, protest, joining a
      gang, losing a job, being displaced, police encounter, church conversion, etc.)
   c) Demographics: home language, province, township/suburb, race/ethnicity
   d) Socio-economic: employment, income, housing type, medical aid vs public clinic
   e) Daily pressures: load-shedding, water cuts, taxi fare increases, spaza shop prices, SASSA queues
   f) Political awareness: party alignment or rejection, stance on ANC/DA/EFF/MK, who they voted for or why they stopped
   g) Language texture: home language influence, SA slang, code-switching patterns
   h) Apartheid legacy's effect on their family
   i) LOCAL ANCHORS: Name specific streets, taxi ranks, schools, clinics, spaza shops, or events in their area. This makes the agent grounded in real South African geography.

3. group_affiliation: Precise description if applicable.
   Examples: "Gang member, Township, City"
             "EFF branch organiser, City"
             "Prison gang, Prison Area"
             "Political loyalist, Township"
             "Church deacon, Township"
             "Taxi association enforcer, Transport Hub"
   Return null if no clear group affiliation exists.

4. voice_guide: 3-5 sentences of CONCRETE speech instructions. Cover:
   - Vocabulary and slang specific to this persona (name actual words/phrases like "aybo", "sharp-sharp", "eita", "mos", "dagga", "kak", "lekker", "taxi rank", "spaza shop", "RDP house", "grant money")
   - What topics they always reference (territory, God, the struggle, the rand, load-shedding, water cuts, taxi wars, SASSA grants, etc.)
   - Emotional register (hot-headed, measured, conspiratorial, preachy, streetwise)
   - What this person would NEVER say (academic language, balanced policy analysis, "on the other hand", "studies show")
   - Any code-switching pattern (Zulu/English, Afrikaans/English, Sotho/English, Xhosa/English)
   - LOCAL ANCHORS: Reference specific places (township names, suburbs, taxi ranks, spaza shops, schools, clinics) and daily realities (queueing for grants, bucket toilets, no water for 3 days, cousin was hijacked, etc.)
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
actor_archetype and behavioral_tendencies are REQUIRED — never null.

D) EMOTIONAL STATE (6 core emotions, 0-10 scale):
   Based on the entity's life situation and archetype, rate initial emotions:
   - sadness: Feeling of loss, disappointment, hopelessness
   - joy: Happiness, satisfaction, optimism
   - fear: Perceived threat, danger, uncertainty about future
   - disgust: Moral opposition, revulsion, contempt for others
   - anger: Frustration, sense of injustice, rage at the system
   - surprise: Reaction to unexpected events or information
   
   Also provide:
   - emotion_keyword: Single word describing dominant emotional state (e.g., "frustrated", "hopeful", "resigned", "angry", "fearful")
   - emotion_thought: 1-sentence explanation of current emotional state
   
   Example: A "grant dependent" might have: sadness=6, joy=2, fear=4, disgust=5, anger=7, surprise=2, keyword="resented", thought="The system has failed me and my family for years."

E) CORE NEEDS (Maslow's Hierarchy - top 3 needs):
   Based on entity's situation, identify their top 3 needs with priority and current status:
   - need_type: One of [safety_physical, safety_economic, belonging, affection, respect, status, achievement, personal_growth]
   - priority: 0-1 (higher = more urgent based on Maslow level)
   - status: "met", "unmet", or "threatened"
   - intensity: 0-1 (how urgent RIGHT NOW)
   - description: Brief explanation
   
   Example: {"need_type": "safety_economic", "priority": 0.9, "status": "unmet", "intensity": 0.8, "description": "No regular income"}

F) ATTITUDE MEMORY (toward key topics, 0-10 scale):
   Rate initial attitudes toward topics this agent will encounter (derived from interested_topics):
   - 0: Strongly opposed, 5: Neutral, 10: Strongly supportive
   Structure: [{"topic": "topic_name", "rating": 5, "description": "reasoning sentence"}, ...]
   
   Also: List 2-3 core beliefs this agent holds.

Output ALL sections as JSON with fields:
- emotions: {sadness, joy, fear, disgust, anger, surprise} (0-10 ints)
- emotion_keyword: string
- emotion_thought: string  
- needs: [{need_type, priority, status, intensity, description}, ...] (top 3)
- attitudes: [{topic, rating, description}, ...]
- beliefs: [string, ...] (2-3 core beliefs)"""

        enrichment_block = self._get_enrichment_block(entity_type, context_str)
        if enrichment_block:
            return prompt + "\n\n" + enrichment_block
        return prompt

    @staticmethod
    def _normalize_archetype(t: str) -> str:
        """CamelCase / spaced type → snake_case for enrichment key matching."""
        s = re.sub(r'([A-Z])', r'_\1', t).lower().lstrip('_')
        return re.sub(r'[\s\-]+', '_', s.strip())

    def _get_enrichment_block(self, entity_type: str, context_str: str = "") -> str:
        """Get enrichment data block for this entity's archetype."""
        if not self.enrichment_data:
            return ""

        normalized = self._normalize_archetype(entity_type)

        # 1. Exact match on normalized key
        direct_match = self.enrichment_data.get(normalized)
        if direct_match:
            return f"""CURRENT REALITY (from live web research):
{direct_match}

USE THIS DATA TO GROUND YOUR PERSONA:
- Use actual numbers, prices, and statistics from this research
- Reference real recent events, quotes, and community positions
- Match the language patterns and vocabulary found in this research
- Ground the persona in specific places, costs, and conditions mentioned here"""

        # 2. Substring match — normalized key must be a whole-word substring
        for arch_key, arch_data in self.enrichment_data.items():
            norm_key = self._normalize_archetype(arch_key)
            if norm_key in normalized or normalized in norm_key:
                return f"""CURRENT REALITY (from live web research for {arch_key}):
{arch_data}

USE THIS DATA TO GROUND YOUR PERSONA:
- Use actual numbers, prices, and statistics from this research
- Reference real recent events, quotes, and community positions
- Match the language patterns and vocabulary found in this research
- Ground the persona in specific places, costs, and conditions mentioned here"""

        # 3. Fallback — concatenate first 3 entries as general SA context
        all_context = "\n\n".join([f"--- {k} ---\n{v[:800]}" for k, v in list(self.enrichment_data.items())[:3]])
        return f"""CURRENT REALITY CONTEXT (from live web research on related groups):
{all_context}

Use any relevant data from this research to ground your persona in current South African reality."""

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
        return f"""Generate a detailed South African INSTITUTIONAL / COLLECTIVE persona for this group entity.
This agent does NOT represent an individual person. It speaks as the OFFICIAL or COLLECTIVE voice
of the institution — like a press statement, spokesperson, or organizational position paper.

Entity Name: {entity_name}
Entity Type: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

Generate JSON with the following fields:

1. persona: 1-2 sentences capturing the institution's mandate and public stance.
   Must convey authority and collective identity. NEVER sound like an individual.
   Bad: "I am worried about crime in my neighborhood."
   Good: "The SAPS is the primary law enforcement agency mandated to maintain public order. We deploy resources based on threat assessment and community intelligence."

2. background_story: ~300 words continuous prose. Cover:
   - Organisation identity: full name, type, mandate, founding context
   - SA policy position: stance on relevant national issues
   - Constituency: who they represent or serve
   - Communication style: formal / populist / activist / technical / legalistic
   - Key policy battles and historical role
   - Current pressures: budget, political scrutiny, public trust, operational capacity

3. voice_guide: 3-5 sentences of CONCRETE speech instructions. CRITICAL — this shapes how the agent speaks in simulation:
   - Use "we/our mandate/this organization" NEVER "I/me/my personal view"
   - Reference official policies, mandates, legislation, or organizational resolutions
   - Tone must match the institution (police = measured/formal, EFF = fiery/populist, media = investigative/neutral, gang = territorial/threatening)
   - Use institutional vocabulary ("in terms of", "our mandate requires", "the organization notes", "we condemn", "operational directives")
   - What this institution would NEVER say (emotional personal stories, "I feel", family references, individual hardship)

4. actor_archetype: Choose based on institution type:
   - Government agency / military / police -> "institutional_loyalist"
   - Political party / activist group -> "political_activist"
   - Media outlet / whistleblower NGO -> "whistleblower"
   - Criminal organization / gang -> "criminal_opportunist" or "violent_agitator"
   - Religious / community NGO -> "community_leader"
   - University / research body -> "civic_moderate"
   - Trade union -> "political_activist"
   - Generic organization -> "institutional_loyalist"

5. behavioral_tendencies: 3-5 sentences describing how this institution behaves in a simulation:
   - Does it defend its record? Attack critics? Release data? Call for calm?
   - How does it respond to accusations? (deflection, admission, counter-attack, silence?)
   - What triggers it to post vs observe? (mentions of its name, policy areas in its mandate, crises)

6. is_institutional: true (required, boolean)

7. age: 30
8. gender: "other"
9. education: "Institutional"
10. occupation: Institutional role
11. marriage_status: "N/A"
12. mbti: MBTI describing institutional engagement style
13. country: "South Africa"
14. province: Primary province, or "National"
15. interested_topics: Policy areas this institution actively engages with

Important: All strings on a single line. country MUST be "South Africa". is_institutional MUST be true."""

        enrichment_block = self._get_enrichment_block(entity_type, context_str)
        if enrichment_block:
            return prompt + "\n\n" + enrichment_block
        return prompt

    def _build_representative_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str,
    ) -> str:
        """Prompt for entities whose name is a category/role/place rather than
        a real person ("Union representatives", "Western Cape", "She"). The
        generator invents a SPECIFIC named individual who embodies that
        category, rather than treating the label as an institutional voice."""
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "None"
        context_str = context[:3000] if context else "No additional context"
        prompt = f"""You are turning a categorical / abstract entity into a SPECIFIC SOUTH AFRICAN PERSON
who personally embodies it. The agent must speak as one real human, not as a press statement, not
as the official voice of a group, and not as a label.

ORIGINAL ENTITY LABEL: "{entity_name}"
Entity Type / Category: {entity_type}
Entity Summary: {entity_summary}
Entity Attributes: {attrs_str}

Context Information:
{context_str}

CRITICAL RULES:
- INVENT a realistic South African first + last name for this person. Do NOT keep the original
  label as the name. (e.g. label "Union representatives" → name "Sipho Khumalo"; label
  "Western Cape" → name "Aisha Davids"; label "Technocratic Administrator" → name "Reginald
  Naidoo"). Match plausible naming for the region/community implied by the entity.
- The person must PERSONALLY embody the category through their lived role:
  * "Union representatives" → a real shop steward at a named workplace, with years of service,
    specific grievances, kids in school, a daily commute.
  * "Western Cape" → a real resident of a specific town/township in the Western Cape, with an
    income, occupation, language, and family situation.
  * "Technocratic Administrator" → a real mid-career municipal manager at a named department,
    with a degree, a salary, and a view from the inside.
- They speak in FIRST PERSON ("I", "my", "we as workers", "in our office") with personal voice,
  not institutional voice. They have feelings, family, fatigue, hope, anger.
- Their views on the simulation topic must reflect the category they embody — they're not generic;
  they speak with the standpoint of "{entity_name}" but as one person within it.

Generate JSON with the following fields:

1. name: realistic SA first + last name. NEVER reuse the entity label.
2. persona: 2-4 sentences in third person introducing this specific person and how they embody
   "{entity_name}".
3. background_story: ~300 words. Cover:
   - Where they were born, where they live now, household composition
   - Education, current occupation, income range
   - How they came to embody "{entity_name}" (the role, the constituency, the place)
   - One or two formative personal experiences relevant to the simulation topic
   - Their daily life and frustrations
4. age: integer (realistic for the role — a shop steward isn't 22, a youth activist isn't 60)
5. gender: "male", "female", or "other"
6. education, occupation, marriage_status, mbti
7. country: MUST be "South Africa"
8. province, residence: specific SA province + town/suburb
9. religion, race: realistic for the persona
10. group_affiliation: the named group/party/organisation they belong to (the concrete one,
    not "Union representatives" — e.g. "COSATU shop steward at Sasol Secunda")
11. actor_archetype: pick from the standard archetype taxonomy
12. behavioral_tendencies: 2-3 sentences — how this person acts in a conversation
13. voice_guide: 3-5 sentences of speech instructions IN FIRST PERSON ("I speak slowly...",
    "I switch to isiZulu when angry...", "I quote my late mother..."). Personal, not institutional.
14. is_institutional: MUST be false (this is a person, not an institution)
15. interested_topics: array of policy areas they personally care about
16. emotions: object with sadness, joy, fear, disgust, anger, surprise (each 0-10)
17. emotion_keyword, emotion_thought
18. attitudes: array of {{"topic": "...", "rating": 0-10, "description": "..."}}
19. beliefs: array of strings — first-person convictions
20. needs: object mapping Maslow needs to intensity 0-100

Important: All string values on a single line, no unescaped newlines. is_institutional MUST be false.
The name field MUST be a personal name (first + last), not the original entity label."""

        enrichment_block = self._get_enrichment_block(entity_type, context_str)
        if enrichment_block:
            return prompt + "\n\n" + enrichment_block
        return prompt

    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
    ) -> Dict[str, Any]:
        province = random.choice(self.SA_PROVINCES)
        entity_type_lower = entity_type.lower()
        _enrichment_suffix = ""
        _enrichment_block = self._get_enrichment_block(entity_type)
        if _enrichment_block:
            _enrichment_suffix = "\n\n" + _enrichment_block[:500]

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
                "actor_archetype": "whistleblower",
                "voice_guide": "Speak as a media editorial desk. Use 'our investigation', 'reports indicate', 'sources confirm'. Neutral, factual, occasionally confrontational. Never say 'I feel' or 'my family'.",
                "is_institutional": True,
            }

        elif entity_type_lower in ["university", "governmentagency", "ngo", "organization"]:
            arch = "institutional_loyalist"
            voice = "Speak as an official spokesperson. Use 'our mandate', 'in terms of the act', 'the organization notes'. Formal, measured, bureaucratic. Never use personal pronouns."
            if "gang" in entity_name.lower() or "criminal" in entity_name.lower():
                arch = "criminal_opportunist"
                voice = "Speak as a collective. Use 'our turf', 'the organization protects its own'. Territorial, coded, threatening when challenged. No personal stories."
            elif "police" in entity_name.lower() or "saps" in entity_name.lower() or "defence" in entity_name.lower() or "army" in entity_name.lower() or "military" in entity_name.lower():
                arch = "institutional_loyalist"
                voice = "Speak as a police/military spokesperson. Use 'operational capacity', 'in accordance with', 'the public is assured'. Formal, defensive, data-driven. Never emotional."
            elif "eff" in entity_name.lower() or "anc" in entity_name.lower() or "da" in entity_name.lower() or "party" in entity_name.lower() or "union" in entity_name.lower():
                arch = "political_activist"
                voice = "Speak as a party/union spokesperson. Use 'the movement', 'our people demand', 'we will not rest'. Fiery, ideological, populist. Reference struggle history and mandates."
            elif "rights" in entity_name.lower() or "watch" in entity_name.lower() or "ngo" in entity_name.lower() or "commission" in entity_name.lower():
                arch = "whistleblower"
                voice = "Speak as a rights organization. Use 'we condemn', 'our findings indicate', 'the state must'. Principled, legalistic, unafraid to name failures."
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
                "actor_archetype": arch,
                "voice_guide": voice,
                "is_institutional": True,
            }

        else:
            profile = {
                "persona": f"A {entity_type.lower()} in South Africa shaped by unemployment, load-shedding, and inequality.",
                "background_story": (
                    entity_summary or
                    f"{entity_name} is a {entity_type.lower()} in South Africa, shaped by high unemployment, "
                    f"load-shedding, and inequality. They participate in public debates about policy."
                ) + _enrichment_suffix,
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
            return profile

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
