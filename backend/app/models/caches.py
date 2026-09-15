"""Caches, logs and what the screen receives.

Python data models (Pydantic). The source of truth for these files in app/data/model,
which scripts/export_data_models.py writes from the classes. Generated once from the
JSON with every value copied, then maintained here.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import ConfigDict, Field, RootModel

from .base import DataModel, SqliteModel


class SaContextClaim(DataModel):
    """One dated, sourced claim about current South African conditions, as held in a context snapshot."""
    MODEL_NAME: ClassVar[str] = 'sa_context_claim'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'One dated, sourced claim about current South African conditions, as held in a '
                  'context snapshot.',
         'stored_in': "DATA_ROOT/sa_context_snapshot.json -> claims[] (or the cache's claims form)",
         'written_by': ['the SA context refresh (snapshot)'],
         'read_by': ['sa_context.format_snapshot', 'sa_context.detect_conflicts'],
         'rules': ['A claim past expires_at is dropped from prompts.']}
    text: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    date: str = Field(default=None, json_schema_extra={'when': 'optional'})
    source: str = Field(default=None, json_schema_extra={'when': 'optional'})
    scope: str = Field(default=None, json_schema_extra={'when': 'optional'})
    expires_at: Optional[float] = Field(default=None, json_schema_extra={'when': 'optional'})


class SaContextCache(DataModel):
    """The daily cache of current South African context from live web search: either a rendered block with its time, or a claims snapshot."""
    MODEL_NAME: ClassVar[str] = 'sa_context_cache'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'The daily cache of current South African context from live web search: either a '
                  'rendered block with its time, or a claims snapshot.',
         'stored_in': 'DATA_ROOT/cache/sa_context.json',
         'written_by': ['sa_context._write_cache'],
         'read_by': ['sa_context._read_cache', 'sa_context.current_sa_realities'],
         'rules': ['The model only summarises real search snippets; it never authors a claim '
                   '(sa-context-freshness).']}
    TOGETHER: ClassVar[List[List[str]]] = [['ts', 'block']]
    ts: float = Field(default=None, ge=0, json_schema_extra={'when': 'optional', 'note': 'Unix time the block was fetched.'})
    block: str = Field(default=None, json_schema_extra={'when': 'optional'})
    claims: List[SaContextClaim] = Field(default=None, json_schema_extra={'when': 'optional'})
    fetched_at: float = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    as_of: str = Field(default=None, json_schema_extra={'when': 'optional'})


class SaContextSnapshot(DataModel):
    """A pinned snapshot of current SA context claims, used instead of live search when fresh (and for historical backtests)."""
    MODEL_NAME: ClassVar[str] = 'sa_context_snapshot'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'A pinned snapshot of current SA context claims, used instead of live search when '
                  'fresh (and for historical backtests).',
         'stored_in': 'DATA_ROOT/sa_context_snapshot.json (or SA_CONTEXT_SNAPSHOT_PATH)',
         'written_by': ['the SA context refresh'],
         'read_by': ['sa_context._checked_snapshot', 'sa_context.format_snapshot']}
    claims: List[SaContextClaim] = Field(json_schema_extra={'when': 'always'})
    fetched_at: float = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    as_of: str = Field(default=None, json_schema_extra={'when': 'optional'})


class JudgeLogLine(DataModel):
    """One advisory quality judgement (LLM-as-judge) appended so scores survive the request that produced them."""
    MODEL_NAME: ClassVar[str] = 'judge_log_line'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'One advisory quality judgement (LLM-as-judge) appended so scores survive the '
                  'request that produced them.',
         'stored_in': 'DATA_ROOT/judge_log.jsonl',
         'written_by': ['judge_service.record_judgement'],
         'read_by': ['operator inspection'],
         'rules': ['Advisory only: a judgement never blocks or changes a run.']}
    ts: str = Field(json_schema_extra={'when': 'always'})
    kind: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    run_id: Optional[str] = Field(json_schema_extra={'when': 'always'})
    regenerated: bool = Field(json_schema_extra={'when': 'always'})
    score: int = Field(ge=0, le=10, json_schema_extra={'when': 'always'})
    pass_: bool = Field(alias='pass', json_schema_extra={'when': 'always'})
    reasoning: str = Field(json_schema_extra={'when': 'always'})
    evidence: str = Field(json_schema_extra={'when': 'always'})


class PersonaCacheEntryMeta(DataModel):
    entity: str = Field(default=None, json_schema_extra={'when': 'optional'})
    type: str = Field(default=None, json_schema_extra={'when': 'optional'})
    level: Literal['exact', 'archetype'] = Field(default=None, json_schema_extra={'when': 'optional'})


class PersonaCacheEntry(DataModel):
    """LEGACY: a persona generated by the model in the old graph era, cached per entity. No longer served."""
    MODEL_NAME: ClassVar[str] = 'persona_cache_entry'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'legacy': True,
         'about': 'LEGACY: a persona generated by the model in the old graph era, cached per entity. '
                  'No longer served by the API (2026-09-14): no persona is model-authored.',
         'stored_in': 'uploads/persona_cache/<hash>.json',
         'written_by': ['removed persona generation (no current writer)'],
         'read_by': ['nothing (kept on disk until the folder is deleted)'],
         'rules': ['No new entries should appear. The folder can be deleted once confirmed unneeded.']}
    meta: PersonaCacheEntryMeta = Field(json_schema_extra={'when': 'always'})
    profile: dict = Field(json_schema_extra={'when': 'always',
         'note': 'Old AgentProfile shape with model-written story, voice and tendencies.'})


class ApiAgentEntry(DataModel):
    """One person in a room as the results screen receives it (GET agents for a panel or sim). Carries only stored fields, so the receipt shows what the room was built from."""
    MODEL_NAME: ClassVar[str] = 'api_agent_entry'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'One person in a room as the results screen receives it (GET agents for a panel or '
                  'sim). Carries only stored fields, so the receipt shows what the room was built '
                  'from.',
         'stored_in': 'API response only (interview_service.list_agents)',
         'written_by': ['interview_service.list_agents'],
         'read_by': ['FlowResults.vue (normalizeAgent, receipt)',
                     'AgentInterviewPanel.vue',
                     'Step5Interaction.vue'],
         'rules': ['Income arrives as monthly_income_rand (room copy) or monthly_household_income_rand '
                   '(library); the screen reads both.']}
    id: int = Field(json_schema_extra={'when': 'always'})
    name: Optional[str] = Field(json_schema_extra={'when': 'always'})
    occupation: Optional[str] = Field(json_schema_extra={'when': 'always'})
    actor_archetype: Optional[str] = Field(json_schema_extra={'when': 'always'})
    group_affiliation: Optional[str] = Field(json_schema_extra={'when': 'always'})
    is_institutional: bool = Field(json_schema_extra={'when': 'always'})
    stance: Optional[str] = Field(json_schema_extra={'when': 'always'})
    base_radicalism: int = Field(json_schema_extra={'when': 'always'})
    interested_topics: List[str] = Field(json_schema_extra={'when': 'always'})
    opinions: list = Field(json_schema_extra={'when': 'always'})
    library_id: str = Field(default=None, pattern='^[0-9a-f]{16}$', json_schema_extra={'when': 'optional'})
    province: str = Field(default=None, json_schema_extra={'when': 'optional'})
    age: int = Field(default=None, json_schema_extra={'when': 'optional'})
    gender: str = Field(default=None, json_schema_extra={'when': 'optional'})
    persona: str = Field(default=None, json_schema_extra={'when': 'optional'})
    budget_tier: Literal['tight', 'moderate', 'loose'] = Field(default=None, json_schema_extra={'when': 'optional'})
    is_grant_dependent: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    grant_type: str = Field(default=None, json_schema_extra={'when': 'optional'})
    monthly_income_rand: float = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    monthly_household_income_rand: float = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    income_provenance: str = Field(default=None, json_schema_extra={'when': 'optional'})
    background_story: str = Field(default=None, json_schema_extra={'when': 'optional'})
    attitudes: list = Field(default=None, json_schema_extra={'when': 'optional'})
    research_context: str = Field(default=None, json_schema_extra={'when': 'optional'})
    research_citations: list = Field(default=None, json_schema_extra={'when': 'optional'})
    chat_state: dict = Field(default=None, json_schema_extra={'when': 'optional'})


class ApiPersonaListEntry(DataModel):
    """One row of the persona picker list (GET /api/research/personas): library personas only."""
    MODEL_NAME: ClassVar[str] = 'api_persona_list_entry'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'One row of the persona picker list (GET /api/research/personas): library personas only.',
         'stored_in': 'API response only (api/research.py list_personas)',
         'written_by': ['api/research.py list_personas'],
         'read_by': ['Home.vue', 'FlowHome.vue (cast picker)'],
         'rules': ["Only survey-grounded library personas are listed. The legacy model-generated cache "
                   "(persona_cache_entry) stopped being served on 2026-09-14."]}
    id: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    name: str = Field(json_schema_extra={'when': 'always'})
    archetype: str = Field(json_schema_extra={'when': 'always'})
    age: Optional[int] = Field(json_schema_extra={'when': 'always'})
    gender: Optional[str] = Field(json_schema_extra={'when': 'always'})
    occupation: Optional[str] = Field(json_schema_extra={'when': 'always'})
    province: Optional[str] = Field(json_schema_extra={'when': 'always'})
    fees_band: Optional[str] = Field(json_schema_extra={'when': 'always'})
    learner_fee_bands: List[str] = Field(json_schema_extra={'when': 'always'})
    lsm_proxy: Optional[dict] = Field(json_schema_extra={'when': 'always'})
    level: Literal['library'] = Field(json_schema_extra={'when': 'always'})


class ApiSegment(DataModel):
    """One group card the room picker shows (GET panel segments): its label, live library count and member ids."""
    MODEL_NAME: ClassVar[str] = 'api_segment'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'One group card the room picker shows (GET panel segments): its label, live library '
                  'count and member ids.',
         'stored_in': 'API response only (panel_service.list_segments)',
         'written_by': ['panel_service.list_segments'],
         'read_by': ['FlowHome.vue', 'PanelPitchPanel.vue', 'Home.vue']}
    id: str = Field(pattern='^[a-z_]+$', json_schema_extra={'when': 'always'})
    label: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    description: str = Field(json_schema_extra={'when': 'always'})
    topics: List[Literal['everyone', 'health', 'education', 'money', 'environment', 'food', 'government', 'safety']] = Field(min_length=1, json_schema_extra={'when': 'always'})
    kind: Literal['who', 'thinks'] = Field(json_schema_extra={'when': 'always'})
    attitude_dim: Optional[str] = Field(json_schema_extra={'when': 'always'})
    count: int = Field(ge=1, json_schema_extra={'when': 'always'})
    members: List[Annotated[str, Field(pattern='^[0-9a-f]{16}$')]] = Field(min_length=1, json_schema_extra={'when': 'always'})
    is_thin: bool = Field(json_schema_extra={'when': 'always'})
    note: str = Field(json_schema_extra={'when': 'always'})


#: Model name (app/data/model/<name>.json) -> class.
MODELS = {
    'sa_context_claim': SaContextClaim,
    'sa_context_cache': SaContextCache,
    'sa_context_snapshot': SaContextSnapshot,
    'judge_log_line': JudgeLogLine,
    'persona_cache_entry': PersonaCacheEntry,
    'api_agent_entry': ApiAgentEntry,
    'api_persona_list_entry': ApiPersonaListEntry,
    'api_segment': ApiSegment,
}
