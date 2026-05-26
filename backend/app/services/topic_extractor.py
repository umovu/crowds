"""
TopicExtractor - Context-aware topic and entity extraction service.

Extracts topics from user queries using LLM, fetches related knowledge graph
entities, and provides persona-topic matching for the opinion block.
"""

import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from openai import AsyncOpenAI

from ..config import Config
from ..storage import GraphStorage
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .entity_reader import EntityNode

logger = get_logger("fub.topic_extractor")

TOPIC_EXTRACTION_PROMPT = """Extract the key policy/topics from this user query. 
Focus on South African policy issues, social concerns, economic matters, or governance topics.

User Query: {query}

Respond with a JSON array of 3-5 topic keywords or short phrases (max 3 words each).
Example: ["healthcare", "education funding", "economic development"]

Return ONLY the JSON array, no explanation."""

PERSONA_TOPIC_MATCH_PROMPT = """Given an agent's background and a list of topics, 
determine which topic(s) this agent would most likely engage with.

Agent Profile:
- Name: {agent_name}
- Occupation: {occupation}
- Province: {province}
- Persona: {persona}
- Interested Topics: {agent_topics}

Query Topics: {query_topics}

Respond with JSON: {{"primary_topic": "...", "reason": "..."}}
Choose the primary_topic from query_topics that best matches the agent's profile.
If no query topic is relevant, return null."""

ENTITY_EXTRACTION_PROMPT = """Extract named entities (people, organizations, parties, places, events) from this user query.

User Query: {query}

Respond with a JSON array of entity objects. Each object should have:
- "name": The entity name
- "type": One of: person, organization, party, place, event

Example: [{{"name": "Julius Malema", "type": "person"}}, {{"name": "EFF", "type": "party"}}]

Return ONLY the JSON array, no explanation."""


class TopicExtractor:
    """
    Extracts topics from queries and fetches related KG entities.
    
    Provides:
    - Topic extraction via LLM
    - Entity grounding from Neo4j/graph storage
    - Persona-topic matching for agents
    """

    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        model_name: Optional[str] = None,
    ):
        self._llm = llm_client or self._create_default_llm()
        self._model = model_name or Config.LLM_MODEL_NAME

    def _create_default_llm(self) -> AsyncOpenAI:
        return AsyncOpenAI(
            api_key=Config.LLM_API_KEY or "ollama",
            base_url=Config.LLM_BASE_URL,
        )

    async def extract_topics(self, query: str) -> List[str]:
        """
        Extract key topics from a user query using LLM.
        
        Args:
            query: The user's question or prompt
            
        Returns:
            List of 3-5 topic keywords/phrases
        """
        if not query or not query.strip():
            return []

        prompt = TOPIC_EXTRACTION_PROMPT.format(query=query)
        
        try:
            resp = await self._llm.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.3,
            )
            raw = resp.choices[0].message.content or "[]"
            topics = self._parse_json_array(raw)
            
            if not topics:
                logger.warning(f"Topic extraction returned empty for: {query[:50]}")
                return self._fallback_extract_topics(query)
            
            logger.debug(f"Extracted topics: {topics}")
            return topics
            
        except Exception as e:
            logger.warning(f"Topic extraction failed: {e}, using fallback")
            return self._fallback_extract_topics(query)

    def _fallback_extract_topics(self, query: str) -> List[str]:
        """Fallback keyword-based topic extraction."""
        keywords = [
            "healthcare", "education", "economy", "jobs", "employment",
            "housing", "infrastructure", "transport", "water", "electricity",
            "crime", "security", "police", "gbv", "gender", "violence",
            "politics", "election", "government", "ANC", "DA", "EFF",
            "development", "mining", "agriculture", "tourism",
            "social grants", "pension", "unemployment", "poverty",
            "land reform", "environment", "climate", "health",
        ]
        
        query_lower = query.lower()
        found = []
        
        for kw in keywords:
            if kw in query_lower:
                found.append(kw)
        
        if len(found) < 2:
            found.append("general policy")
        
        return found[:5]

    def _parse_json_array(self, raw: str) -> List[str]:
        """Parse JSON array from LLM response."""
        raw = raw.strip()
        
        if not raw:
            return []
        
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw).strip()
        raw = raw.strip("`").strip()
        
        try:
            parsed = eval(raw)
            if isinstance(parsed, list):
                return [str(t).strip() for t in parsed if t]
        except Exception:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                try:
                    parsed = eval(match.group())
                    if isinstance(parsed, list):
                        return [str(t).strip() for t in parsed if t]
                except Exception:
                    pass
        
        return []

    async def fetch_entities(
        self,
        storage: GraphStorage,
        graph_id: str,
        topics: List[str],
        max_entities: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Fetch knowledge graph entities related to extracted topics.
        
        Uses GraphStorage abstraction - works with either:
        - Neo4jStorage (production)
        - KGLiteStorage (on-device/embedded)
        
        Args:
            storage: GraphStorage instance (abstracted - Neo4j or KGLite)
            graph_id: The graph to search in
            topics: Topics to match against entities
            max_entities: Maximum number of entities to return
            
        Returns:
            List of entity dictionaries with name, type, description
        """
        if not topics or not storage or not graph_id:
            return []

        entities = []
        
        for topic in topics[:3]:
            try:
                results = storage.search(
                    graph_id=graph_id,
                    query=topic,
                    limit=max_entities // 2,
                    scope="nodes",
                )
                
                if results and "nodes" in results:
                    for node in results["nodes"][:max_entities // 2]:
                        if node not in entities:
                            entities.append(node)
                            
            except Exception as e:
                logger.warning(f"Entity search failed for topic '{topic}': {e}")
                continue
        
        entity_contexts = []
        for e in entities[:max_entities]:
            entity_contexts.append({
                "name": e.get("name", ""),
                "type": e.get("type", e.get("labels", ["Unknown"])[0] if e.get("labels") else "Unknown"),
                "description": e.get("description", e.get("summary", str(e.get("properties", "")))[:200]),
                "uuid": e.get("uuid", ""),
            })
        
        logger.debug(f"Fetched {len(entity_contexts)} entities for topics: {topics}")
        return entity_contexts

    def build_entity_context(
        self,
        entities: List[Dict[str, Any]],
        max_count: int = 6,
    ) -> str:
        """
        Format entities into a context string for prompts.
        
        Args:
            entities: List of entity dictionaries
            max_count: Maximum entities to include
            
        Returns:
            Formatted context string
        """
        if not entities:
            return ""

        selected = entities[:max_count]
        lines = ["\n\nRelevant local context:"]
        
        for e in selected:
            name = e.get("name", "Unknown")
            etype = e.get("type", "")
            desc = e.get("description", "")[:150]
            
            type_prefix = f"[{etype}] " if etype else ""
            lines.append(f"- {type_prefix}{name}: {desc}")

        context = "\n".join(lines)
        
        if len(context) > 600:
            context = context[:600] + "\n... (additional context truncated)"
        
        return context

    async def match_topic_to_persona(
        self,
        agent_name: str,
        agent_persona: str,
        agent_occupation: str,
        agent_province: str,
        agent_topics: List[str],
        query_topics: List[str],
    ) -> Optional[str]:
        """
        Match query topics to agent persona using LLM.
        
        Args:
            agent_name: Agent's name
            agent_persona: Agent's persona description
            agent_occupation: Agent's occupation
            agent_province: Agent's province
            agent_topics: Agent's pre-configured interested topics
            query_topics: Topics extracted from user query
            
        Returns:
            Best matching topic or None
        """
        if not query_topics:
            return None

        if len(query_topics) == 1:
            return query_topics[0]

        prompt = PERSONA_TOPIC_MATCH_PROMPT.format(
            agent_name=agent_name,
            occupation=agent_occupation or "unspecified",
            province=agent_province or "unspecified",
            persona=agent_persona or "",
            agent_topics=", ".join(agent_topics) if agent_topics else "general",
            query_topics=", ".join(query_topics),
        )

        try:
            resp = await self._llm.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3,
            )
            raw = resp.choices[0].message.content or ""
            
            match = re.search(r'"primary_topic"\s*:\s*"([^"]+)"', raw)
            if match:
                topic = match.group(1).strip()
                if topic in query_topics:
                    logger.debug(f"Matched topic '{topic}' to agent '{agent_name}'")
                    return topic
                    
        except Exception as e:
            logger.warning(f"Persona-topic matching failed: {e}")

        return self._fallback_match_topic(query_topics, agent_topics, agent_occupation, agent_province)

    def _fallback_match_topic(
        self,
        query_topics: List[str],
        agent_topics: List[str],
        occupation: str,
        province: str,
    ) -> Optional[str]:
        """Fallback keyword-based topic matching."""
        if not query_topics:
            return None

        occupation_lower = (occupation or "").lower()
        
        occupation_keywords = {
            "teacher": "education",
            "nurse": "healthcare",
            "doctor": "healthcare",
            "farmer": "agriculture",
            "business": "economy",
            "lawyer": "justice",
            "police": "crime",
            "engineer": "infrastructure",
        }
        
        agent_concern = None
        for kw, topic in occupation_keywords.items():
            if kw in occupation_lower:
                agent_concern = topic
                break
        
        if agent_concern and agent_concern in query_topics:
            return agent_concern
        
        common = set(query_topics) & set(agent_topics)
        if common:
            return list(common)[0]
        
        return query_topics[0]

    async def extract_query_entities(self, query: str) -> List[Dict[str, str]]:
        """
        Extract named entities from user query.

        Args:
            query: The user's question

        Returns:
            List of entity dicts with name and type
        """
        if not query or not query.strip():
            return []

        prompt = ENTITY_EXTRACTION_PROMPT.format(query=query)

        try:
            resp = await self._llm.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            raw = resp.choices[0].message.content or "[]"
            entities = self._parse_json_array(raw, parse_dicts=True)

            if entities:
                logger.debug(f"Extracted entities: {entities}")
                return entities

        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")

        return []

    def _parse_json_array(self, raw: str, parse_dicts: bool = False) -> Any:
        """Parse JSON array from LLM response."""
        raw = raw.strip()

        if not raw:
            return []

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw).strip()
        raw = raw.strip("`").strip()

        try:
            parsed = eval(raw)
            if isinstance(parsed, list):
                if parse_dicts:
                    # Validate dict structure
                    valid = []
                    for item in parsed:
                        if isinstance(item, dict) and "name" in item:
                            valid.append({
                                "name": str(item.get("name", "")),
                                "type": str(item.get("type", "unknown"))
                            })
                    return valid
                return [str(t).strip() for t in parsed if t]
        except Exception:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                try:
                    parsed = eval(match.group())
                    if isinstance(parsed, list):
                        if parse_dicts:
                            valid = []
                            for item in parsed:
                                if isinstance(item, dict) and "name" in item:
                                    valid.append({
                                        "name": str(item.get("name", "")),
                                        "type": str(item.get("type", "unknown"))
                                    })
                            return valid
                        return [str(t).strip() for t in parsed if t]
                except Exception:
                    pass

        return []

    async def extract_query_context(
        self,
        query: str,
        storage: Optional[GraphStorage],
        graph_id: Optional[str],
    ) -> Dict[str, Any]:
        """
        Full context extraction pipeline.

        Extracts both topics AND entities from the query, then fetches
        related KG entities for grounding.

        Args:
            query: User's question
            storage: GraphStorage instance
            graph_id: Graph to search in

        Returns:
            Dict with:
            - topics: List of topic strings
            - query_entities: List of entities extracted from query
            - entities: KG entities related to query
            - entity_context: Formatted string for prompts
            - query: Original query
        """
        # Extract topics from query
        topics = await self.extract_topics(query)

        # Extract named entities from query
        query_entities = await self.extract_query_entities(query)

        # Fetch KG entities related to topics
        kg_entities = []
        if storage and graph_id:
            kg_entities = await self.fetch_entities(storage, graph_id, topics)

        # Merge query entities with KG entities (avoid duplicates)
        all_entities = self._merge_entities(query_entities, kg_entities)

        entity_context = self.build_entity_context(all_entities)

        return {
            "topics": topics,
            "query_entities": query_entities,
            "entities": all_entities,
            "entity_context": entity_context,
            "query": query,
        }

    def _merge_entities(
        self,
        query_entities: List[Dict[str, str]],
        kg_entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge query entities with KG entities, avoiding duplicates."""
        seen = set()
        merged = []

        # Add query entities first (higher priority)
        for entity in query_entities:
            name = entity.get("name", "").lower()
            if name and name not in seen:
                seen.add(name)
                merged.append({
                    "name": entity.get("name", ""),
                    "type": entity.get("type", "unknown"),
                    "description": "",
                    "source": "query"
                })

        # Add KG entities that aren't duplicates
        for entity in kg_entities:
            name = entity.get("name", "").lower()
            if name and name not in seen:
                seen.add(name)
                merged.append(entity)

        return merged
