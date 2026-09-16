"""Simulations: lifecycle and run state, config, the IPC files, action log, databases and reports.

Python data models (Pydantic). The source of truth for these files in app/data/model,
which scripts/export_data_models.py writes from the classes. Generated once from the
JSON with every value copied, then maintained here.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import ConfigDict, Field, RootModel

from .base import DataModel, SqliteModel
from ._simulation_types import (IpcCommandCommandType, IpcResponseStatus, SimActionActionType, 
    SimActionPlatform, SimDocumentContextMode, SimDocumentContextSecondaryLens, 
    SimLogMarkerEventType, SimReportProgressStatus, SimReportStatus, SimRunStateRunnerStatus, 
    SimStateStatus)


class SimAction(DataModel):
    """One agent action in a simulation: a line in actions.jsonl, and an entry in run_state recent_actions."""
    MODEL_NAME: ClassVar[str] = 'sim_action'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    round_num: int = Field(ge=0, json_schema_extra={'when': 'always'})
    timestamp: str = Field(json_schema_extra={'when': 'always'})
    platform: SimActionPlatform = Field(json_schema_extra={'when': 'always'})
    agent_id: int = Field(json_schema_extra={'when': 'always'})
    agent_name: str = Field(json_schema_extra={'when': 'always'})
    action_type: SimActionActionType = Field(json_schema_extra={'when': 'always'})
    action_args: dict = Field(json_schema_extra={'when': 'always'})
    result: Optional[Any] = Field(json_schema_extra={'when': 'always'})
    success: bool = Field(json_schema_extra={'when': 'always'})
    reason: str = Field(json_schema_extra={'when': 'always'})
    internal_thought: str = Field(json_schema_extra={'when': 'always'})
    impact_score: float = Field(json_schema_extra={'when': 'always'})
    economic_reasoning: Optional[Any] = Field(default=None, json_schema_extra={'when': 'optional'})
    prompt_tokens: int = Field(ge=0, json_schema_extra={'when': 'always'})
    completion_tokens: int = Field(ge=0, json_schema_extra={'when': 'always'})
    estimated_cost_usd: float = Field(ge=0, json_schema_extra={'when': 'always'})


class SimLogMarker(DataModel):
    """A marker line in actions.jsonl: the end of a round, or the end of the simulation with its token and cost totals."""
    MODEL_NAME: ClassVar[str] = 'sim_log_marker'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    event_type: SimLogMarkerEventType = Field(json_schema_extra={'when': 'always'})
    round: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    simulated_hours: float = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    total_rounds: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    total_actions: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    model: str = Field(default=None, json_schema_extra={'when': 'optional'})
    pricing: dict = Field(default=None, json_schema_extra={'when': 'optional'})
    total_prompt_tokens: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    total_completion_tokens: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    total_tokens: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    estimated_cost_usd: float = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})


class SimState(DataModel):
    """A simulation's lifecycle state: status, cast size, config flag, prepare cost, and whether its credit was charged."""
    MODEL_NAME: ClassVar[str] = 'sim_state'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    simulation_id: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    project_id: str = Field(json_schema_extra={'when': 'always'})
    graph_id: str = Field(json_schema_extra={'when': 'always'})
    status: SimStateStatus = Field(json_schema_extra={'when': 'always'})
    entities_count: int = Field(ge=0, json_schema_extra={'when': 'always'})
    profiles_count: int = Field(ge=0, json_schema_extra={'when': 'always'})
    entity_types: List[str] = Field(json_schema_extra={'when': 'always'})
    config_generated: bool = Field(json_schema_extra={'when': 'always'})
    config_reasoning: str = Field(json_schema_extra={'when': 'always'})
    current_round: int = Field(ge=0, json_schema_extra={'when': 'always'})
    created_at: str = Field(json_schema_extra={'when': 'always'})
    updated_at: str = Field(json_schema_extra={'when': 'always'})
    error: Optional[str] = Field(json_schema_extra={'when': 'always'})
    user_id: Optional[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    prepare_prompt_tokens: int = Field(ge=0, json_schema_extra={'when': 'always'})
    prepare_completion_tokens: int = Field(ge=0, json_schema_extra={'when': 'always'})
    prepare_cost_usd: float = Field(ge=0, json_schema_extra={'when': 'always'})
    credit_charged: bool = Field(default=None, json_schema_extra={'when': 'optional'})


class SimConfigTimeConfig(DataModel):
    total_simulation_hours: float = Field(ge=0, json_schema_extra={'when': 'always'})
    minutes_per_round: float = Field(ge=1, json_schema_extra={'when': 'always'})
    agents_per_hour_min: int = Field(ge=0, json_schema_extra={'when': 'always'})
    agents_per_hour_max: int = Field(ge=0, json_schema_extra={'when': 'always'})
    peak_hours: List[Annotated[int, Field(ge=0, le=23)]] = Field(json_schema_extra={'when': 'always'})
    peak_activity_multiplier: float = Field(ge=0, json_schema_extra={'when': 'always'})
    off_peak_hours: List[Annotated[int, Field(ge=0, le=23)]] = Field(json_schema_extra={'when': 'always'})
    off_peak_activity_multiplier: float = Field(ge=0, json_schema_extra={'when': 'always'})
    morning_hours: List[Annotated[int, Field(ge=0, le=23)]] = Field(json_schema_extra={'when': 'always'})
    morning_activity_multiplier: float = Field(ge=0, json_schema_extra={'when': 'always'})
    work_hours: List[Annotated[int, Field(ge=0, le=23)]] = Field(json_schema_extra={'when': 'always'})
    work_activity_multiplier: float = Field(ge=0, json_schema_extra={'when': 'always'})


class SimConfigAgentConfigsItem(DataModel):
    agent_id: int = Field(ge=0, json_schema_extra={'when': 'always'})
    entity_uuid: str = Field(json_schema_extra={'when': 'always'})
    entity_name: str = Field(json_schema_extra={'when': 'always'})
    entity_type: str = Field(json_schema_extra={'when': 'always'})
    activity_level: float = Field(ge=0, le=1, json_schema_extra={'when': 'always'})
    posts_per_hour: float = Field(ge=0, json_schema_extra={'when': 'always'})
    comments_per_hour: float = Field(ge=0, json_schema_extra={'when': 'always'})
    active_hours: List[Annotated[int, Field(ge=0, le=23)]] = Field(json_schema_extra={'when': 'always'})
    response_delay_min: int = Field(ge=0, json_schema_extra={'when': 'always'})
    response_delay_max: int = Field(ge=0, json_schema_extra={'when': 'always'})
    sentiment_bias: float = Field(ge=-1, le=1, json_schema_extra={'when': 'always'})
    stance: str = Field(json_schema_extra={'when': 'always'})
    influence_weight: float = Field(ge=0, json_schema_extra={'when': 'always'})


class SimConfigEventConfig(DataModel):
    initial_posts: list = Field(json_schema_extra={'when': 'always'})
    scheduled_events: list = Field(json_schema_extra={'when': 'always'})
    hot_topics: List[str] = Field(json_schema_extra={'when': 'always'})
    narrative_direction: str = Field(json_schema_extra={'when': 'always'})


class SimConfig(DataModel):
    """The run configuration a simulation starts from: time pacing, one activity config per agent, and the opening events."""
    MODEL_NAME: ClassVar[str] = 'sim_config'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    simulation_id: str = Field(json_schema_extra={'when': 'always'})
    project_id: str = Field(json_schema_extra={'when': 'always'})
    graph_id: str = Field(json_schema_extra={'when': 'always'})
    simulation_requirement: str = Field(json_schema_extra={'when': 'always'})
    time_config: SimConfigTimeConfig = Field(json_schema_extra={'when': 'always'})
    agent_configs: List[SimConfigAgentConfigsItem] = Field(json_schema_extra={'when': 'always'})
    event_config: SimConfigEventConfig = Field(json_schema_extra={'when': 'always'})
    llm_model: str = Field(json_schema_extra={'when': 'always'})
    llm_base_url: str = Field(json_schema_extra={'when': 'always'})
    generated_at: str = Field(json_schema_extra={'when': 'always'})
    generation_reasoning: str = Field(json_schema_extra={'when': 'always'})
    max_agents_per_round: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    min_agents_per_round: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})


class SimRunState(DataModel):
    """Live progress of a running simulation, polled by the screen."""
    MODEL_NAME: ClassVar[str] = 'sim_run_state'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    simulation_id: str = Field(json_schema_extra={'when': 'always'})
    runner_status: SimRunStateRunnerStatus = Field(json_schema_extra={'when': 'always'})
    current_round: int = Field(ge=0, json_schema_extra={'when': 'always'})
    total_rounds: int = Field(ge=0, json_schema_extra={'when': 'always'})
    simulated_hours: float = Field(ge=0, json_schema_extra={'when': 'always'})
    total_simulation_hours: float = Field(ge=0, json_schema_extra={'when': 'always'})
    progress_percent: float = Field(ge=0, json_schema_extra={'when': 'always'})
    simulation_running: bool = Field(json_schema_extra={'when': 'always'})
    simulation_completed: bool = Field(json_schema_extra={'when': 'always'})
    simulation_actions_count: int = Field(ge=0, json_schema_extra={'when': 'always'})
    total_actions_count: int = Field(ge=0, json_schema_extra={'when': 'always'})
    started_at: Optional[str] = Field(json_schema_extra={'when': 'always'})
    updated_at: str = Field(json_schema_extra={'when': 'always'})
    completed_at: Optional[str] = Field(json_schema_extra={'when': 'always'})
    error: Optional[str] = Field(json_schema_extra={'when': 'always'})
    process_pid: Optional[int] = Field(json_schema_extra={'when': 'always'})
    recent_actions: List[SimAction] = Field(max_length=50, json_schema_extra={'when': 'always'})
    rounds_count: int = Field(ge=0, json_schema_extra={'when': 'always'})


class SimEnvStatus(DataModel):
    """The heartbeat the sim subprocess writes so the app can tell it is alive, running, paused or gone."""
    MODEL_NAME: ClassVar[str] = 'sim_env_status'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    status: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    timestamp: str = Field(json_schema_extra={'when': 'always'})
    total_agents: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    agents_expressed_count: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    agents_expressed: list = Field(default=None, json_schema_extra={'when': 'optional'})
    current_round: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    total_rounds: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    simulation_actions_count: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    events_injected_this_round: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    total_events_injected: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    error: str = Field(default=None, json_schema_extra={'when': 'optional'})
    message: str = Field(default=None, json_schema_extra={'when': 'optional'})


class IpcCommand(DataModel):
    """A command the app drops for the sim subprocess (interview, pause, intervention)."""
    MODEL_NAME: ClassVar[str] = 'ipc_command'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    command_id: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    command_type: IpcCommandCommandType = Field(json_schema_extra={'when': 'always'})
    args: dict = Field(json_schema_extra={'when': 'always'})
    timestamp: str = Field(json_schema_extra={'when': 'always'})


class IpcResponse(DataModel):
    """The sim subprocess's answer to one command."""
    MODEL_NAME: ClassVar[str] = 'ipc_response'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    command_id: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    status: IpcResponseStatus = Field(json_schema_extra={'when': 'always'})
    result: Optional[dict] = Field(json_schema_extra={'when': 'always'})
    error: Optional[str] = Field(json_schema_extra={'when': 'always'})
    timestamp: str = Field(json_schema_extra={'when': 'always'})


class SimDocumentContextModeDetection(DataModel):
    scores: dict = Field(json_schema_extra={'when': 'always'})
    decided_mode: Optional[str] = Field(json_schema_extra={'when': 'always'})
    confidence: Optional[str] = Field(json_schema_extra={'when': 'always'})
    used_llm_tiebreak: bool = Field(json_schema_extra={'when': 'always'})
    manual_override: bool = Field(json_schema_extra={'when': 'always'})


class SimDocumentContext(DataModel):
    """What a simulation knows about its scenario: the decided mode, the domain, facts pulled from the document, and the operator's business briefing."""
    MODEL_NAME: ClassVar[str] = 'sim_document_context'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    mode: SimDocumentContextMode = Field(json_schema_extra={'when': 'always'})
    converged: bool = Field(json_schema_extra={'when': 'always'})
    secondary_lens: Optional[SimDocumentContextSecondaryLens] = Field(json_schema_extra={'when': 'always'})
    mode_detection: SimDocumentContextModeDetection = Field(json_schema_extra={'when': 'always'})
    domain: Optional[str] = Field(json_schema_extra={'when': 'always'})
    domain_profile: Optional[dict] = Field(json_schema_extra={'when': 'always'})
    document_context_block: Optional[str] = Field(json_schema_extra={'when': 'always'})
    dynamic_rules: Optional[list] = Field(json_schema_extra={'when': 'always'})
    facts: list = Field(json_schema_extra={'when': 'always'})
    competitive_landscape: list = Field(json_schema_extra={'when': 'always'})
    operator_context: Optional[str] = Field(max_length=1500, json_schema_extra={'when': 'always'})


class SimEnrichment(RootModel[Dict[str, str]]):
    """Web research per archetype for a simulation: archetype name -> research text. Context only, never persona material."""
    MODEL_NAME: ClassVar[str] = 'sim_enrichment'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    model_config = ConfigDict(strict=True)


class SimReplayDb(SqliteModel):
    """The replay database of a simulation: metadata, every action, injected events, per-round sentiment and the cast."""
    MODEL_NAME: ClassVar[str] = 'sim_replay_db'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1, 'kind': 'sqlite'}
    TABLES: ClassVar[Dict[str, List[str]]] = {'simulation_meta': ['simulation_id',
                             'project_id',
                             'started_at',
                             'completed_at',
                             'total_rounds',
                             'total_agents',
                             'llm_model',
                             'config_json'],
         'opinion_actions': ['id',
                             'simulation_id',
                             'round_num',
                             'agent_id',
                             'agent_name',
                             'archetype',
                             'action_type',
                             'content',
                             'topics_json',
                             'impact_score',
                             'internal_thought',
                             'reason',
                             'opinion_id',
                             'target_opinion_id',
                             'target_agent_name',
                             'economic_reasoning',
                             'created_at'],
         'injected_events': ['id',
                             'simulation_id',
                             'event_id',
                             'rule_id',
                             'round_injected',
                             'event_type',
                             'category',
                             'source',
                             'title',
                             'content',
                             'affected_archetypes_json',
                             'severity',
                             'persist_rounds',
                             'trigger_metrics_json',
                             'created_at'],
         'sentiment_snapshots': ['id',
                                 'simulation_id',
                                 'round_num',
                                 'total_actions',
                                 'avg_impact_score',
                                 'pct_high_impact',
                                 'avg_radicalism',
                                 'non_participation_count',
                                 'non_participation_pct',
                                 'top_topics_json',
                                 'active_archetypes_json',
                                 'events_injected_count',
                                 'distinct_positions',
                                 'new_positions',
                                 'position_spread',
                                 'created_at'],
         'agent_profiles': ['simulation_id',
                            'agent_id',
                            'name',
                            'archetype',
                            'persona',
                            'province',
                            'age',
                            'gender',
                            'occupation',
                            'education',
                            'stance',
                            'base_radicalism',
                            'interested_topics_json',
                            'group_affiliation',
                            'background_story']}


class SimOpinionDb(SqliteModel):
    """The live opinion space of a running simulation: opinions, responses and per-round activity."""
    MODEL_NAME: ClassVar[str] = 'sim_opinion_db'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1, 'kind': 'sqlite'}
    TABLES: ClassVar[Dict[str, List[str]]] = {'opinion': ['id',
                     'agent_id',
                     'agent_name',
                     'content',
                     'topics',
                     'round_num',
                     'created_at',
                     'reason',
                     'internal_thought',
                     'impact_score',
                     'economic_reasoning'],
         'opinion_response': ['id',
                              'agent_id',
                              'agent_name',
                              'opinion_id',
                              'content',
                              'round_num',
                              'created_at',
                              'reason',
                              'internal_thought',
                              'impact_score'],
         'agent_round_activity': ['id',
                                  'agent_id',
                                  'agent_name',
                                  'action_type',
                                  'round_num',
                                  'created_at',
                                  'reason',
                                  'internal_thought',
                                  'impact_score',
                                  'content',
                                  'topics']}


class SimReportOutlineSectionsItem(DataModel):
    title: str = Field(json_schema_extra={'when': 'always'})
    content: str = Field(json_schema_extra={'when': 'always'})


class SimReportOutline(DataModel):
    """A simulation report's outline: title, summary and sections."""
    MODEL_NAME: ClassVar[str] = 'sim_report_outline'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    title: str = Field(json_schema_extra={'when': 'always'})
    summary: str = Field(json_schema_extra={'when': 'always'})
    sections: List[SimReportOutlineSectionsItem] = Field(json_schema_extra={'when': 'always'})


class SimReport(DataModel):
    """A simulation report's saved record: status, the outline and the full markdown."""
    MODEL_NAME: ClassVar[str] = 'sim_report'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    report_id: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    simulation_id: str = Field(json_schema_extra={'when': 'always'})
    graph_id: str = Field(json_schema_extra={'when': 'always'})
    simulation_requirement: str = Field(json_schema_extra={'when': 'always'})
    status: SimReportStatus = Field(json_schema_extra={'when': 'always'})
    outline: Optional[SimReportOutline] = Field(json_schema_extra={'when': 'always'})
    markdown_content: str = Field(json_schema_extra={'when': 'always'})
    created_at: str = Field(json_schema_extra={'when': 'always'})
    completed_at: str = Field(json_schema_extra={'when': 'always'})
    error: Optional[str] = Field(json_schema_extra={'when': 'always'})


class SimReportProgress(DataModel):
    """Live progress of report generation, polled by the screen."""
    MODEL_NAME: ClassVar[str] = 'sim_report_progress'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    status: SimReportProgressStatus = Field(json_schema_extra={'when': 'always'})
    progress: int = Field(ge=-1, le=100, json_schema_extra={'when': 'always'})
    message: str = Field(json_schema_extra={'when': 'always'})
    current_section: Optional[str] = Field(json_schema_extra={'when': 'always'})
    completed_sections: List[str] = Field(json_schema_extra={'when': 'always'})
    updated_at: str = Field(json_schema_extra={'when': 'always'})


class ReportLogLine(DataModel):
    """One step the report agent took: a line in the report's agent_log.jsonl."""
    MODEL_NAME: ClassVar[str] = 'report_log_line'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1}
    timestamp: str = Field(json_schema_extra={'when': 'always'})
    elapsed_seconds: float = Field(ge=0, json_schema_extra={'when': 'always'})
    report_id: str = Field(json_schema_extra={'when': 'always'})
    action: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    stage: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    section_title: Optional[str] = Field(json_schema_extra={'when': 'always'})
    section_index: Optional[int] = Field(ge=0, json_schema_extra={'when': 'always'})
    details: dict = Field(json_schema_extra={'when': 'always'})


#: Model name (app/data/model/<name>.json) -> class.
MODELS = {
    'sim_action': SimAction,
    'sim_log_marker': SimLogMarker,
    'sim_state': SimState,
    'sim_config': SimConfig,
    'sim_run_state': SimRunState,
    'sim_env_status': SimEnvStatus,
    'ipc_command': IpcCommand,
    'ipc_response': IpcResponse,
    'sim_document_context': SimDocumentContext,
    'sim_enrichment': SimEnrichment,
    'sim_replay_db': SimReplayDb,
    'sim_opinion_db': SimOpinionDb,
    'sim_report_outline': SimReportOutline,
    'sim_report': SimReport,
    'sim_report_progress': SimReportProgress,
    'report_log_line': ReportLogLine,
}
