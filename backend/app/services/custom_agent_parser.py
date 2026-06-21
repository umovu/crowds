"""
Custom Agent Parser
Parses user-provided agent definition documents (JSON or unstructured text)
and converts them into AgentProfile objects for simulation injection.
"""

import json
import os
from typing import Dict, Any, List, Optional
from dataclasses import asdict

from .agent_profile_generator import AgentProfile
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..config import Config

logger = get_logger('fub.custom_agent_parser')


class CustomAgentParser:
    """
    Parses custom agent definitions from documents or raw data.

    Supports:
    - JSON files (direct AgentProfile-compatible arrays)
    - Unstructured text (PDF, MD, TXT) via LLM extraction
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME

    AGENTS_MARKER = "# Agents"

    @classmethod
    def extract_agents_from_text(cls, text: str, simulation_requirement: str = "", use_llm: bool = True) -> List[AgentProfile]:
        """
        Scan text for an '# Agents' marker and extract agent definitions from the section that follows.

        Supports:
        - Explicit JSON block inside the section
        - Unstructured bullet points (parsed via LLM)

        Args:
            text: Full document text
            simulation_requirement: Optional context for LLM parsing
            use_llm: Whether to fall back to LLM for unstructured text

        Returns:
            List of AgentProfile objects
        """
        if not text or len(text.strip()) < 50:
            return []

        # Find the marker (case-insensitive, supports leading # or ##)
        marker_pos = cls._find_agents_marker(text)
        if marker_pos == -1:
            logger.debug("No '# Agents' marker found in document text")
            return []

        section = text[marker_pos:]

        # Try JSON block first
        agents = cls._try_parse_json_block(section)
        if agents:
            # Mark source
            for a in agents:
                a.source_entity_type = "custom_seed_document"
            logger.info(f"Extracted {len(agents)} agents from JSON block in '# Agents' section")
            return agents

        # Fall back to LLM extraction
        if use_llm:
            try:
                instance = cls()
                agents = instance._parse_agents_section_with_llm(section, simulation_requirement)
                if agents:
                    # Mark source
                    for a in agents:
                        a.source_entity_type = "custom_seed_document"
                    logger.info(f"LLM extracted {len(agents)} agents from '# Agents' section")
                    return agents
            except Exception as e:
                logger.warning(f"LLM extraction from '# Agents' section failed: {e}")

        return []

    @classmethod
    def _find_agents_marker(cls, text: str) -> int:
        """Find position of '# Agents' marker, case-insensitive. Supports #, ##, ### or plain 'Agents:'."""
        import re
        # Match lines starting with 1-3 # then 'Agents' or just 'Agents:' at start of line
        pattern = re.compile(r'^[ \t]*#{1,3}\s*[Aa]gents\b|^Agents:', re.MULTILINE)
        match = pattern.search(text)
        if match:
            return match.start()
        return -1

    @classmethod
    def _try_parse_json_block(cls, section: str) -> List[AgentProfile]:
        """Try to find and parse a JSON array block from the agents section."""
        import re
        # Look for JSON block between triple backticks or raw JSON array
        json_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', section)
        if json_block_match:
            json_text = json_block_match.group(1).strip()
        else:
            # Try raw JSON array at start of section
            bracket_match = re.search(r'(\[[\s\S]*\])', section)
            if bracket_match:
                json_text = bracket_match.group(1).strip()
            else:
                return []

        try:
            data = json.loads(json_text)
            if isinstance(data, dict):
                items = data.get("agents", data.get("personas", data.get("profiles", [data])))
            elif isinstance(data, list):
                items = data
            else:
                return []

            parser = cls()
            profiles = []
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                profile = parser._dict_to_profile(item, idx)
                if profile:
                    profiles.append(profile)
            return profiles
        except Exception as e:
            logger.debug(f"JSON block parsing failed: {e}")
            return []

    def _parse_agents_section_with_llm(self, section: str, simulation_requirement: str = "") -> List[AgentProfile]:
        """Use LLM to parse unstructured agent descriptions from the section."""
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("OpenAI client required for LLM parsing")

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        prompt = f"""The following text is an '# Agents' section extracted from a simulation document. Parse each agent described into structured JSON.

SIMULATION CONTEXT:
{simulation_requirement or 'A multi-agent policy simulation.'}

AGENTS SECTION:
{section[:6000]}

For each agent, produce a structured profile with:
- name: Full name or identifier
- persona: 2-4 sentences describing who they are
- background_story: 1-2 paragraphs of life history
- age: integer
- gender: "male", "female", or "other"
- education: e.g. "Matric"
- occupation: e.g. "Taxi driver"
- country, province, residence, religion, race
- mbti: e.g. "INFJ"
- skills: array of strings
- personality_traits: string description
- group_affiliation, actor_archetype, behavioral_tendencies, voice_guide, is_institutional

STATUS:
- income, currency_balance
- relationships: {{"family": [{{"name":"...","strength":50}}], "friends": [...], "colleagues": [...]}}
- needs: {{"physiological_hunger": 50, ...}} (all 11 Maslow needs 0-100)

MENTAL:
- emotions: {{"sadness": 0, "joy": 0, "fear": 0, "disgust": 0, "anger": 0, "surprise": 0}} (0-10)
- emotion_keyword, emotion_thought
- attitudes: [{{"topic": "...", "rating": 5, "description": "..."}}]
- beliefs: ["..."]

Return ONLY a valid JSON array of agent objects. No explanation."""

        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": "You extract structured agent personas from documents. Return ONLY valid JSON array."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=4000,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)

        if isinstance(parsed, dict):
            items = parsed.get("agents", parsed.get("personas", parsed.get("profiles", [parsed])))
        elif isinstance(parsed, list):
            items = parsed
        else:
            return []

        profiles = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            profile = self._dict_to_profile(item, idx)
            if profile:
                profiles.append(profile)
        return profiles

    def parse_doc(self, file_path: str, simulation_requirement: str = "") -> List[AgentProfile]:
        """
        Parse an agent definition document.

        Args:
            file_path: Path to the uploaded document
            simulation_requirement: Optional simulation context for LLM parsing

        Returns:
            List of AgentProfile objects
        """
        suffix = os.path.splitext(file_path)[1].lower()

        if suffix == '.json':
            return self._parse_json(file_path)
        else:
            return self._parse_text_with_llm(file_path, simulation_requirement)

    def parse_raw(self, raw_data: List[Dict[str, Any]]) -> List[AgentProfile]:
        """
        Parse raw agent data from frontend directly.

        Args:
            raw_data: List of agent dicts from frontend form

        Returns:
            List of AgentProfile objects
        """
        profiles = []
        for idx, item in enumerate(raw_data):
            if not isinstance(item, dict):
                continue
            profile = self._dict_to_profile(item, idx)
            if profile:
                # Mark manually added agents
                if not profile.source_entity_type or not profile.source_entity_type.startswith("custom"):
                    profile.source_entity_type = "custom_manual"
                profiles.append(profile)
        return profiles

    def _parse_json(self, file_path: str) -> List[AgentProfile]:
        """Parse a JSON file containing agent definitions."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, dict):
            items = data.get("agents", data.get("personas", data.get("profiles", [data])))
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError("JSON file must contain an array or object with agents/personas key")

        profiles = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            profile = self._dict_to_profile(item, idx)
            if profile:
                profiles.append(profile)

        logger.info(f"Parsed {len(profiles)} agents from JSON file")
        return profiles

    def _parse_text_with_llm(self, file_path: str, simulation_requirement: str = "") -> List[AgentProfile]:
        """Parse unstructured text using LLM extraction."""
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("OpenAI client required for LLM parsing")

        text = FileParser.extract_text(file_path)
        if not text or len(text.strip()) < 50:
            raise ValueError("Document too short or empty")

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        prompt = f"""You are an expert simulation designer. Extract agent personas from the following research document.

SIMULATION CONTEXT:
{simulation_requirement or 'A multi-agent policy simulation.'}

DOCUMENT CONTENT:
{text[:8000]}

Extract ALL distinct agents or stakeholder personas described in this document. For each agent, produce a structured profile with the following fields:

- name: Full name or identifier
- persona: 2-4 sentences describing who they are, their worldview, and their role
- background_story: 1-2 paragraphs of life history and formative experiences
- age: integer
- gender: "male", "female", or "other"
- education: e.g. "Matric", "BSc Computer Science"
- occupation: e.g. "Taxi driver", "Student"
- country: e.g. "South Africa"
- province: e.g. "Gauteng", "Western Cape"
- residence: e.g. "Soweto, Johannesburg"
- religion: e.g. "Christian", "Muslim"
- race: e.g. "Black African", "White"
- mbti: e.g. "INFJ", "ESTP"
- skills: array of strings
- personality_traits: string description
- group_affiliation: e.g. "ANC member", "EFF supporter", "Stokvel treasurer"
- actor_archetype: a short free-text label for how this agent behaves in the simulation.
  Use whatever fits the document — a market segment ("early_adopter", "budget_holder"),
  a stakeholder role, or any precise descriptor. These policy examples are NOT a closed
  list, only illustrations: civic_moderate, political_activist, community_leader,
  institutional_loyalist, grant_dependent_survivor, whistleblower. Prefer the label the
  document actually implies over forcing one of these.
- behavioral_tendencies: 2-3 sentences describing how they act in simulations. This is
  what drives their behaviour, so make it concrete and specific to this agent.
- voice_guide: 2-3 sentences of speech style instructions
- is_institutional: true/false

STATUS (Dynamic Attributes):
- income: string, e.g. "R12,000/month"
- currency_balance: string, e.g. "R3,500"
- relationships: object with keys "family", "friends", "colleagues". Each is an array of {{"name": "...", "strength": 0-100}}
- needs: object mapping Maslow need types to intensity 0-100. Use keys: physiological_hunger, physiological_tired, safety_physical, safety_economic, belonging, affection, respect, status, achievement, personal_growth, purpose

MENTAL PROCESS:
- emotions: object with keys sadness, joy, fear, disgust, anger, surprise. Each value 0-10.
- emotion_keyword: single word e.g. "anxious", "hopeful"
- emotion_thought: one-sentence explanation of emotional state
- attitudes: array of {{"topic": "...", "rating": 0-10, "description": "..."}}
- beliefs: array of strings

Return ONLY a valid JSON array of agent objects. No explanation outside the JSON."""

        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You extract structured agent personas from documents. Return ONLY valid JSON array."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.4,
                    max_tokens=4000,
                )
                content = response.choices[0].message.content
                parsed = json.loads(content)

                if isinstance(parsed, dict):
                    items = parsed.get("agents", parsed.get("personas", parsed.get("profiles", [parsed])))
                elif isinstance(parsed, list):
                    items = parsed
                else:
                    continue

                profiles = []
                for idx, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    profile = self._dict_to_profile(item, idx)
                    if profile:
                        profiles.append(profile)

                if profiles:
                    logger.info(f"LLM extracted {len(profiles)} agents from text document")
                    return profiles

            except Exception as e:
                logger.warning(f"LLM parse attempt {attempt+1} failed: {e}")

        raise RuntimeError("Failed to parse agent document after 3 attempts")

    def _dict_to_profile(self, data: Dict[str, Any], idx: int) -> Optional[AgentProfile]:
        """Convert a raw dict to an AgentProfile, handling frontend field names."""
        if not isinstance(data, dict) or not data.get("name"):
            return None

        # Normalize needs from flat object or array format
        needs = data.get("needs")
        if isinstance(needs, dict):
            needs = [{"need_type": k, "intensity": v} for k, v in needs.items()]
        elif isinstance(needs, list):
            pass
        else:
            needs = None

        # Normalize relationships into a structured format if needed
        relationships = data.get("relationships", {})

        # Normalize emotions
        emotions = data.get("emotions")
        if emotions and isinstance(emotions, dict):
            # Ensure all 6 keys exist
            for key in ["sadness", "joy", "fear", "disgust", "anger", "surprise"]:
                if key not in emotions:
                    emotions[key] = 0.0

        # Normalize attitudes
        attitudes = data.get("attitudes")
        if attitudes and isinstance(attitudes, list):
            attitudes = [{"topic": a.get("topic", ""), "rating": a.get("rating", 5), "description": a.get("description", "")} for a in attitudes]

        # Normalize beliefs
        beliefs = data.get("beliefs")
        if beliefs and isinstance(beliefs, str):
            beliefs = [b.strip() for b in beliefs.split("\n") if b.strip()]
        elif not beliefs:
            beliefs = []

        # Normalize skills
        skills = data.get("skills", [])
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]

        # Build persona from bio if missing
        persona = data.get("persona", data.get("bio", ""))
        if not persona and data.get("personality_traits"):
            persona = f"{data.get('name')} — {data.get('personality_traits')}"

        # Build background story
        background_story = data.get("background_story", "")

        return AgentProfile(
            id=idx,
            name=data.get("name", f"Agent_{idx}"),
            persona=persona or f"A participant named {data.get('name', '')}.",
            background_story=background_story or "",
            age=data.get("age"),
            gender=data.get("gender"),
            education=data.get("education"),
            occupation=data.get("occupation"),
            marriage_status=data.get("marriage_status"),
            mbti=data.get("mbti"),
            country=data.get("country"),
            province=data.get("province"),
            interested_topics=data.get("interested_topics", []),
            group_affiliation=data.get("group_affiliation"),
            voice_guide=data.get("voice_guide"),
            actor_archetype=data.get("actor_archetype"),
            behavioral_tendencies=data.get("behavioral_tendencies"),
            is_institutional=data.get("is_institutional", False),
            is_core_focus=data.get("is_core_focus", False),
            stance=data.get("stance"),
            emotions=emotions,
            emotion_keyword=data.get("emotion_keyword"),
            emotion_thought=data.get("emotion_thought"),
            needs=needs,
            attitudes=attitudes,
            beliefs=beliefs,
            source_entity_uuid=None,
            source_entity_type="custom",
        )

    @staticmethod
    def merge_profiles(auto_profiles, custom_profiles) -> List[Dict[str, Any]]:
        """
        Merge auto-generated and custom agent profiles.
        Custom agents override auto-generated ones by name (case-insensitive).

        Accepts either List[AgentProfile] or List[Dict] for either side — the
        simulation manager passes a list of dicts (from panel_service._build_profile)
        for the auto side and a list of AgentProfile (from parse_raw) for the custom
        side. Always returns a list of plain dicts so the caller can json.dump it
        straight to disk; the AgentProfile side is normalised via to_agentsociety_format,
        and dataclass-side mutations (custom.id = auto.id) are mirrored as dict writes.

        Args:
            auto_profiles: Auto-generated profiles (dict or AgentProfile list)
            custom_profiles: User-provided custom profiles (dict or AgentProfile list)

        Returns:
            Merged list of plain-dict profiles with custom priority
        """
        def _to_dict(p):
            if isinstance(p, dict):
                return dict(p)
            if isinstance(p, AgentProfile):
                return p.to_agentsociety_format()
            raise TypeError(f"merge_profiles: unsupported profile type {type(p).__name__}")

        def _name_of(p):
            if isinstance(p, dict):
                return (p.get("name") or "").strip().lower()
            return (getattr(p, "name", "") or "").strip().lower()

        if not custom_profiles:
            return [_to_dict(p) for p in auto_profiles]

        # Build name -> custom dict map
        custom_by_name = {_name_of(c): _to_dict(c) for c in custom_profiles}

        merged: List[Dict[str, Any]] = []
        overridden: set = set()

        for auto in auto_profiles:
            key = _name_of(auto)
            if key in custom_by_name:
                # Preserve the auto-generated ID but use the custom data
                replacement = custom_by_name[key]
                replacement["id"] = _to_dict(auto).get("id", len(merged))
                merged.append(replacement)
                overridden.add(key)
            else:
                merged.append(_to_dict(auto))

        # Append customs that didn't override anyone
        for c in custom_profiles:
            key = _name_of(c)
            if key not in overridden:
                d = custom_by_name[key]
                d["id"] = len(merged)
                merged.append(d)

        # Reassign sequential IDs so the cast reads 0..N-1 cleanly
        for i, profile in enumerate(merged):
            profile["id"] = i

        logger.info(f"Merged profiles: {len(auto_profiles)} auto + {len(custom_profiles)} custom = {len(merged)} total ({len(overridden)} overrides)")
        return merged
