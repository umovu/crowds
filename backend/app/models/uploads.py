"""Panel sessions, uploaded agents, projects, research cards, follow-up reports, posters and saved papers.

Python data models (Pydantic). The source of truth for these files in app/data/model,
which scripts/export_data_models.py writes from the classes. Generated once from the
JSON with every value copied, then maintained here.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import ConfigDict, Field, RootModel

from .base import DataModel, SqliteModel
from ._uploads_types import (CustomAgentSourceEntityType, CustomAgentStance, 
    HypothesisReportMode, HypothesisReportMovementPeopleItemDirection, 
    LocalPapersPapersItemSource, MechanismCardClaimType, MechanismCardCombGaps, 
    MechanismCardEconomicTags, PanelContextMode, PanelContextPanelSession, 
    PanelSessionAffordabilityFromPriceTiers, PanelSessionBudgetTierFilter, PanelSessionMode, 
    PanelSessionPlaceLevel, PanelSessionSlotsProbesItemConfidence, PosterMimeType, ProjectStatus)


class PanelContext(DataModel):
    """The context file a panel session carries so the interview service knows it is a panel and what was pitched."""
    MODEL_NAME: ClassVar[str] = 'panel_context'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    mode: PanelContextMode = Field(json_schema_extra={'when': 'always'})
    panel_session: PanelContextPanelSession = Field(json_schema_extra={'when': 'always'})
    pitch: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    operator_context: str = Field(default=None, json_schema_extra={'when': 'optional'})


class PanelSessionAffordabilityFromPrice(DataModel):
    amount: float = Field(ge=0, json_schema_extra={'when': 'always'})
    monthly: bool = Field(json_schema_extra={'when': 'always'})
    tiers: List[PanelSessionAffordabilityFromPriceTiers] = Field(json_schema_extra={'when': 'always'})


class PanelSessionPlace(DataModel):
    """Where a room is set, and how sure that is.

    `level` is the rung the cast picker actually used, not the one the pitch
    asked for: a thin metro falls back to its province, and the label has to
    follow the seats. `measured_seats` is how many of those locals came off a
    survey row that named the place, as opposed to being placed there by the
    imputation pass — without it, "7 of 12 in Tshwane" reads as a fact."""
    label: str = Field(json_schema_extra={'when': 'always'})
    level: PanelSessionPlaceLevel = Field(json_schema_extra={'when': 'always'})
    metro: Optional[str] = Field(json_schema_extra={'when': 'always'})
    province: Optional[str] = Field(json_schema_extra={'when': 'always'})
    seats: int = Field(ge=0, json_schema_extra={'when': 'always'})
    of: int = Field(ge=0, json_schema_extra={'when': 'always'})
    measured_seats: int = Field(ge=0, json_schema_extra={'when': 'always'})


class PanelSessionSlotsProbesItem(DataModel):
    id: str = Field(json_schema_extra={'when': 'always'})
    label: str = Field(json_schema_extra={'when': 'always'})
    question: str = Field(json_schema_extra={'when': 'always'})
    active: bool = Field(json_schema_extra={'when': 'always'})
    base: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    confidence: PanelSessionSlotsProbesItemConfidence = Field(json_schema_extra={'when': 'always'})


class PanelSessionSlots(DataModel):
    probes: List[PanelSessionSlotsProbesItem] = Field(default=None, json_schema_extra={'when': 'optional'})
    announcement: str = Field(default=None, json_schema_extra={'when': 'optional'})
    audience: str = Field(default=None, json_schema_extra={'when': 'optional'})
    version_a: str = Field(default=None, json_schema_extra={'when': 'optional'})
    version_b: str = Field(default=None, json_schema_extra={'when': 'optional'})
    worry: str = Field(default=None, json_schema_extra={'when': 'optional'})


class PanelSession(DataModel):
    """A panel session: the pitch, the room that was picked, and how it was filtered. One panel_session.json per session folder."""
    MODEL_NAME: ClassVar[str] = 'panel_session'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    TOGETHER: ClassVar[List[List[str]]] = [['budget_tier_filter', 'affordability_pool_size'], ['attitude_filter', 'attitude_pool_size']]
    session_id: str = Field(pattern='^panel_[0-9a-f]{12}$', json_schema_extra={'when': 'always'})
    user_id: Optional[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    pitch: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    operator_context: Optional[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    mode: PanelSessionMode = Field(json_schema_extra={'when': 'always'})
    segments: List[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    segment: str = Field(json_schema_extra={'when': 'always'})
    picked_segments: List[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    segment_label: str = Field(json_schema_extra={'when': 'always'})
    segment_allocation: Dict[str, Annotated[int, Field(ge=0)]] = Field(default=None, json_schema_extra={'when': 'optional'})
    cast_size: int = Field(ge=0, json_schema_extra={'when': 'always'})
    requested_size: int = Field(ge=1, json_schema_extra={'when': 'always'})
    seed: int = Field(json_schema_extra={'when': 'always'})
    province: Optional[str] = Field(json_schema_extra={'when': 'always'})
    created_at: str = Field(json_schema_extra={'when': 'always'})
    rounds_run: int = Field(ge=0, json_schema_extra={'when': 'always'})
    archetype_distribution: Dict[str, Annotated[int, Field(ge=0)]] = Field(json_schema_extra={'when': 'always'})
    province_distribution: Dict[str, Annotated[int, Field(ge=0)]] = Field(json_schema_extra={'when': 'always'})
    budget_tier_distribution: Dict[str, Annotated[int, Field(ge=0)]] = Field(default=None, json_schema_extra={'when': 'optional'})
    budget_tier_filter: List[PanelSessionBudgetTierFilter] = Field(default=None, json_schema_extra={'when': 'optional'})
    affordability_pool_size: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    affordability_from_price: PanelSessionAffordabilityFromPrice = Field(default=None, json_schema_extra={'when': 'optional'})
    attitude_filter: Dict[str, List[str]] = Field(default=None, json_schema_extra={'when': 'optional'})
    attitude_pool_size: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    pointer: str = Field(default=None, json_schema_extra={'when': 'optional'})
    slots: PanelSessionSlots = Field(default=None, json_schema_extra={'when': 'optional'})
    place: Optional[PanelSessionPlace] = Field(default=None, json_schema_extra={'when': 'optional'})


class CustomAgentNeedsItem(DataModel):
    need_type: str = Field(json_schema_extra={'when': 'always'})
    intensity: float = Field(ge=0, le=100, json_schema_extra={'when': 'always'})


class CustomAgentAttitudesItem(DataModel):
    topic: str = Field(json_schema_extra={'when': 'always'})
    rating: float = Field(ge=0, le=10, json_schema_extra={'when': 'always'})
    description: str = Field(json_schema_extra={'when': 'always'})


class CustomAgent(DataModel):
    """An agent a user brings in: parsed from an uploaded document's '# Agents' section, a JSON file, or the manual form. This is the parsed shape (AgentProfile.to_agentsociety_format) stored in project.json custom_agents and seated in sim rooms. Outside data: it is checked every time it is parsed."""
    MODEL_NAME: ClassVar[str] = 'custom_agent'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    id: int = Field(ge=0, json_schema_extra={'when': 'always'})
    name: str = Field(min_length=1, max_length=200, json_schema_extra={'when': 'always'})
    persona: str = Field(max_length=2000, json_schema_extra={'when': 'always'})
    background_story: str = Field(max_length=6000, json_schema_extra={'when': 'always'})
    age: Optional[int] = Field(ge=0, le=120, json_schema_extra={'when': 'always'})
    gender: Optional[str] = Field(json_schema_extra={'when': 'always'})
    education: Optional[str] = Field(json_schema_extra={'when': 'always'})
    occupation: Optional[str] = Field(json_schema_extra={'when': 'always'})
    marriage_status: Optional[str] = Field(json_schema_extra={'when': 'always'})
    province: Optional[str] = Field(json_schema_extra={'when': 'always'})
    interested_topics: List[str] = Field(json_schema_extra={'when': 'always'})
    group_affiliation: Optional[str] = Field(max_length=500, json_schema_extra={'when': 'always'})
    voice_guide: Optional[str] = Field(max_length=3000, json_schema_extra={'when': 'always'})
    actor_archetype: Optional[str] = Field(json_schema_extra={'when': 'always'})
    behavioral_tendencies: Optional[str] = Field(max_length=3000, json_schema_extra={'when': 'always'})
    is_institutional: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    is_core_focus: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    stance: Optional[CustomAgentStance] = Field(default=None, json_schema_extra={'when': 'optional'})
    source_entity_uuid: Optional[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    source_entity_type: CustomAgentSourceEntityType = Field(json_schema_extra={'when': 'always'})
    created_at: str = Field(json_schema_extra={'when': 'always'})
    needs: List[CustomAgentNeedsItem] = Field(default=None, json_schema_extra={'when': 'optional'})
    attitudes: List[CustomAgentAttitudesItem] = Field(default=None, json_schema_extra={'when': 'optional'})
    beliefs: List[str] = Field(default=None, json_schema_extra={'when': 'optional'})


class ProjectFilesItem(DataModel):
    filename: str = Field(json_schema_extra={'when': 'always'})
    size: int = Field(ge=0, json_schema_extra={'when': 'always'})
    path: str = Field(default=None, json_schema_extra={'when': 'optional'})
    synthetic: bool = Field(default=None, json_schema_extra={'when': 'optional'})


class ProjectOntology(DataModel):
    entity_types: list = Field(json_schema_extra={'when': 'always'})
    edge_types: list = Field(json_schema_extra={'when': 'always'})


class ProjectSavedPapersItem(DataModel):
    id: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    title: str = Field(json_schema_extra={'when': 'always'})
    authors: List[str] = Field(json_schema_extra={'when': 'always'})
    year: Optional[Any] = Field(json_schema_extra={'when': 'always'})
    source: str = Field(json_schema_extra={'when': 'always'})
    abstract: str = Field(json_schema_extra={'when': 'always'})
    url: str = Field(json_schema_extra={'when': 'always'})


class Project(DataModel):
    """A project: the uploaded documents, ontology and graph behind a simulation, plus custom agents and saved papers. One project.json per project folder."""
    MODEL_NAME: ClassVar[str] = 'project'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    project_id: str = Field(pattern='^proj_[0-9a-f]{12}$', json_schema_extra={'when': 'always'})
    name: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    status: ProjectStatus = Field(json_schema_extra={'when': 'always'})
    created_at: str = Field(json_schema_extra={'when': 'always'})
    updated_at: str = Field(json_schema_extra={'when': 'always'})
    files: List[ProjectFilesItem] = Field(json_schema_extra={'when': 'always'})
    total_text_length: int = Field(ge=0, json_schema_extra={'when': 'always'})
    ontology: Optional[ProjectOntology] = Field(json_schema_extra={'when': 'always'})
    analysis_summary: Optional[str] = Field(json_schema_extra={'when': 'always'})
    graph_id: Optional[str] = Field(json_schema_extra={'when': 'always'})
    graph_build_task_id: Optional[str] = Field(json_schema_extra={'when': 'always'})
    custom_agents: List[CustomAgent] = Field(default=None, json_schema_extra={'when': 'optional'})
    custom_agents_enabled: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    enrichment_data: Dict[str, str] = Field(default=None, json_schema_extra={'when': 'optional'})
    saved_papers: List[ProjectSavedPapersItem] = Field(default=None, json_schema_extra={'when': 'optional'})
    simulation_requirement: Optional[str] = Field(json_schema_extra={'when': 'always'})
    chunk_size: int = Field(ge=1, json_schema_extra={'when': 'always'})
    chunk_overlap: int = Field(ge=0, json_schema_extra={'when': 'always'})
    error: Optional[str] = Field(json_schema_extra={'when': 'always'})


class MechanismCardClaim(DataModel):
    text: str = Field(min_length=1, max_length=600, json_schema_extra={'when': 'always'})
    needs: List[Dict[str, Annotated[list, Field(min_length=1)]]] = Field(json_schema_extra={'when': 'always'})
    chain_id: str = Field(json_schema_extra={'when': 'always'})
    passages: List[str] = Field(min_length=1, json_schema_extra={'when': 'always'})
    evaluative_rules: List[Annotated[str, Field(min_length=1)]] = Field(default=None, json_schema_extra={'when': 'optional'})
    objections: List[Annotated[str, Field(min_length=1)]] = Field(json_schema_extra={'when': 'always'})
    vocabulary: List[Annotated[str, Field(min_length=1)]] = Field(json_schema_extra={'when': 'always'})


class MechanismCard(DataModel):
    """A research mechanism card: how people in a situation reason, distilled from South African qualitative research. Stored one per file in app/data/mechanism_cards/<id>.json. Written by scripts/extract_card.py (draft) and a human reviewer; read by mechanism_card_service (binding, prompt block, citations). Checked by data_model.mechanism_card_problems."""
    MODEL_NAME: ClassVar[str] = 'mechanism_card'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    id: str = Field(pattern='^[a-z0-9]+(-[a-z0-9]+)*$', json_schema_extra={'when': 'always'})
    subject: str = Field(default=None, min_length=1, max_length=300, json_schema_extra={
        'when': 'optional',
        'note': ("One human-written line saying what this research is about, in plain words, "
                 "for the typed reader in card_subjects to match a pitch against. Falls back "
                 "to topic_tags when absent, which reads as keywords and scores like keywords. "
                 "Never shown to a persona — the prompt block is built from claims."),
    })
    claim_type: MechanismCardClaimType = Field(json_schema_extra={'when': 'always'})
    claims: List[MechanismCardClaim] = Field(min_length=1, max_length=5, json_schema_extra={'when': 'always'})
    citation: List[Annotated[str, Field(min_length=1)]] = Field(min_length=1, json_schema_extra={'when': 'always'})
    year_range: Optional[str] = Field(pattern='^\\d{4}(-\\d{4})?$', json_schema_extra={'when': 'always'})
    year_note: str = Field(default=None, json_schema_extra={'when': 'optional'})
    region: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    confidence: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    segment_tags: List[str] = Field(min_length=1, json_schema_extra={'when': 'always'})
    economic_tags: List[MechanismCardEconomicTags] = Field(default=None, json_schema_extra={'when': 'optional'})
    topic_tags: List[Annotated[str, Field(pattern='^[a-z][a-z -]*$')]] = Field(min_length=1, json_schema_extra={'when': 'always'})
    comb_gaps: List[MechanismCardCombGaps] = Field(json_schema_extra={'when': 'always'})
    applies_when: List[Dict[str, Annotated[list, Field(min_length=1)]]] = Field(json_schema_extra={'when': 'always'})


class HypothesisReportRoomCoverage(DataModel):
    segments_compared: int = Field(ge=0, json_schema_extra={'when': 'always'})
    segments_available: int = Field(ge=0, json_schema_extra={'when': 'always'})


class HypothesisReportRoom(DataModel):
    seats: int = Field(ge=0, json_schema_extra={'when': 'always'})
    heard: int = Field(ge=0, json_schema_extra={'when': 'always'})
    budget_tiers: Dict[str, Annotated[int, Field(ge=0)]] = Field(json_schema_extra={'when': 'always'})
    coverage: HypothesisReportRoomCoverage = Field(json_schema_extra={'when': 'always'})


class HypothesisReportMovementPeopleItem(DataModel):
    agent_id: Any = Field(json_schema_extra={'when': 'always'})
    name: str = Field(json_schema_extra={'when': 'always'})
    from_: str = Field(alias='from', json_schema_extra={'when': 'always'})
    to: str = Field(json_schema_extra={'when': 'always'})
    direction: HypothesisReportMovementPeopleItemDirection = Field(json_schema_extra={'when': 'always'})
    round: Optional[int] = Field(json_schema_extra={'when': 'always'})


class HypothesisReportMovement(DataModel):
    people: List[HypothesisReportMovementPeopleItem] = Field(json_schema_extra={'when': 'always'})
    moved_count: int = Field(ge=0, json_schema_extra={'when': 'always'})
    warmer: int = Field(ge=0, json_schema_extra={'when': 'always'})
    cooler: int = Field(ge=0, json_schema_extra={'when': 'always'})
    answers_considered: int = Field(ge=0, json_schema_extra={'when': 'always'})


class HypothesisReportWallsItem(DataModel):
    id: str = Field(json_schema_extra={'when': 'always'})
    label: str = Field(json_schema_extra={'when': 'always'})
    count: int = Field(ge=1, json_schema_extra={'when': 'always'})


class HypothesisReportPullsItem(DataModel):
    id: str = Field(json_schema_extra={'when': 'always'})
    label: str = Field(json_schema_extra={'when': 'always'})
    count: int = Field(ge=1, json_schema_extra={'when': 'always'})


class HypothesisReportWordOfMouth(DataModel):
    would_tell: int = Field(ge=0, json_schema_extra={'when': 'always'})
    would_warn: int = Field(ge=0, json_schema_extra={'when': 'always'})
    heard: int = Field(ge=0, json_schema_extra={'when': 'always'})


class HypothesisReportConditionsItem(DataModel):
    name: str = Field(json_schema_extra={'when': 'always'})
    stance: str = Field(json_schema_extra={'when': 'always'})
    quote: str = Field(max_length=401, json_schema_extra={'when': 'always'})


class HypothesisReportHypothesesItem(DataModel):
    claim: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    test: str = Field(min_length=1, json_schema_extra={'when': 'always'})


class HypothesisReport(DataModel):
    """The follow-up report for a panel session: computed facts about how the room reacted, plus two or three testable guesses about why."""
    MODEL_NAME: ClassVar[str] = 'hypothesis_report'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    session_id: str = Field(pattern='^panel_[0-9a-f]{12}$', json_schema_extra={'when': 'always'})
    pitch: str = Field(json_schema_extra={'when': 'always'})
    mode: HypothesisReportMode = Field(json_schema_extra={'when': 'always'})
    segment_label: str = Field(json_schema_extra={'when': 'always'})
    created_at: Optional[str] = Field(json_schema_extra={'when': 'always'})
    rounds: int = Field(ge=0, json_schema_extra={'when': 'always'})
    room: HypothesisReportRoom = Field(json_schema_extra={'when': 'always'})
    stance_split: Dict[str, Annotated[int, Field(ge=0)]] = Field(json_schema_extra={'when': 'always'})
    movement: HypothesisReportMovement = Field(json_schema_extra={'when': 'always'})
    walls: List[HypothesisReportWallsItem] = Field(max_length=4, json_schema_extra={'when': 'always'})
    pulls: List[HypothesisReportPullsItem] = Field(max_length=4, json_schema_extra={'when': 'always'})
    word_of_mouth: HypothesisReportWordOfMouth = Field(json_schema_extra={'when': 'always'})
    conditions: List[HypothesisReportConditionsItem] = Field(max_length=5, json_schema_extra={'when': 'always'})
    by_segment: list = Field(json_schema_extra={'when': 'always'})
    room_read: str = Field(json_schema_extra={'when': 'always'})
    hypotheses: List[HypothesisReportHypothesesItem] = Field(max_length=3, json_schema_extra={'when': 'always'})
    generated_at: str = Field(json_schema_extra={'when': 'always'})


class Poster(DataModel):
    """An uploaded poster or advert, and the text brief the vision model read from it."""
    MODEL_NAME: ClassVar[str] = 'poster'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    poster_id: str = Field(pattern='^poster_\\d{8}_\\d{6}_[0-9a-f]{6}$', json_schema_extra={'when': 'always'})
    filename: str = Field(json_schema_extra={'when': 'always'})
    mime_type: PosterMimeType = Field(json_schema_extra={'when': 'always'})
    bytes: int = Field(ge=1, le=8388608, json_schema_extra={'when': 'always'})
    image_path: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    created_at: str = Field(json_schema_extra={'when': 'always'})
    brief: Optional[str] = Field(json_schema_extra={'when': 'always'})
    read_at: str = Field(default=None, json_schema_extra={'when': 'optional'})


class LocalPapersPapersItem(DataModel):
    id: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    title: str = Field(json_schema_extra={'when': 'always'})
    authors: List[str] = Field(json_schema_extra={'when': 'always'})
    year: Optional[int] = Field(json_schema_extra={'when': 'always'})
    abstract: str = Field(json_schema_extra={'when': 'always'})
    source: LocalPapersPapersItemSource = Field(json_schema_extra={'when': 'always'})
    url: str = Field(json_schema_extra={'when': 'always'})
    citations: Optional[int] = Field(ge=0, json_schema_extra={'when': 'always'})
    doi: Optional[str] = Field(json_schema_extra={'when': 'always'})
    local_path: Optional[str] = Field(json_schema_extra={'when': 'always'})


class LocalPapers(DataModel):
    """Papers a user uploaded or kept locally for literature search. Papers saved onto a project use the slimmer project saved_papers shape (model/project.json)."""
    MODEL_NAME: ClassVar[str] = 'local_papers'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    papers: List[LocalPapersPapersItem] = Field(json_schema_extra={'when': 'always'})


#: Model name (app/data/model/<name>.json) -> class.
MODELS = {
    'panel_context': PanelContext,
    'panel_session': PanelSession,
    'custom_agent': CustomAgent,
    'project': Project,
    'mechanism_card': MechanismCard,
    'hypothesis_report': HypothesisReport,
    'poster': Poster,
    'local_papers': LocalPapers,
}
