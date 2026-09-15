"""Data we maintain by hand: grants, SA costs, event rules, B2B frames and word lists.

Python data models (Pydantic). The source of truth for these files in app/data/model,
which scripts/export_data_models.py writes from the classes. Generated once from the
JSON with every value copied, then maintained here.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import ConfigDict, Field, RootModel

from .base import DataModel, SqliteModel


class GrantScheduleGrantsValue(DataModel):
    label: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    monthly_amount: int = Field(ge=1, json_schema_extra={'when': 'always'})
    older_than_75_amount: int = Field(default=None, ge=1, json_schema_extra={'when': 'optional'})
    keywords: List[Annotated[str, Field(min_length=1)]] = Field(json_schema_extra={'when': 'always'})


class GrantSchedule(DataModel):
    """The published SASSA grant schedule: the monthly amount per grant type, used as known income for grant-dependent personas."""
    MODEL_NAME: ClassVar[str] = 'grant_schedule'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'The published SASSA grant schedule: the monthly amount per grant type, used as '
                  'known income for grant-dependent personas.',
         'stored_in': 'backend/data/sa_grant_amounts.json',
         'written_by': ['hand-maintained from the SASSA / DSD schedule'],
         'read_by': ['income_seeder.detect_grant',
                     'income_seeder.grant_label',
                     'panel_service._economic_fields'],
         'rules': ['Amounts are real published policy, never estimates. They feed budget tiers.',
                   "A 'generic' grant must exist: it is the fallback when a persona is grant-dependent "
                   'but the type is unknown.',
                   'Update effective_date and amounts together when SASSA publishes a new schedule.']}
    source: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    effective_date: str = Field(pattern='^\\d{4}-\\d{2}-\\d{2}$', json_schema_extra={'when': 'always'})
    currency: Literal['ZAR'] = Field(json_schema_extra={'when': 'always'})
    note: str = Field(default=None, json_schema_extra={'when': 'optional'})
    grants: Dict[str, GrantScheduleGrantsValue] = Field(json_schema_extra={'when': 'always'})


class WorldFactsFactsItem(DataModel):
    item: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    value: float = Field(ge=0, json_schema_extra={'when': 'always'})
    unit: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    derived: str = Field(default=None, json_schema_extra={'when': 'optional'})
    source: str = Field(json_schema_extra={'when': 'always'})
    as_of: str = Field(pattern='^(\\d{4}(-\\d{2})?)?$', json_schema_extra={'when': 'always'})
    provenance: Literal['curated', 'discovered', 'web'] = Field(json_schema_extra={'when': 'always'})


class WorldFacts(DataModel):
    """Curated South African everyday costs (fuel, data, taxi, grants) agents reason against so they never invent a magnitude."""
    MODEL_NAME: ClassVar[str] = 'world_facts'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'Curated South African everyday costs (fuel, data, taxi, grants) agents reason '
                  'against so they never invent a magnitude.',
         'stored_in': 'backend/app/data/sa_world_facts.json',
         'written_by': ['hand-curated', 'world_facts.promote_fact'],
         'read_by': ['world_facts.load_facts', 'world_facts.render_block'],
         'rules': ['Every fact has a numeric value and a unit, so it can be checked with the model '
                   'off.',
                   'Each item appears once; provenance decides which wins if two sources disagree '
                   '(curated > discovered > web).']}
    README_: str = Field(default=None, alias='_README', json_schema_extra={'when': 'optional'})
    version: int = Field(ge=1, json_schema_extra={'when': 'always'})
    currency: Literal['ZAR'] = Field(json_schema_extra={'when': 'always'})
    facts: List[WorldFactsFactsItem] = Field(json_schema_extra={'when': 'always'})


class EventRulesRulesItemTrigger(DataModel):
    type: Literal['threshold', 'topic_mention_count', 'archetype_interaction', 'sustained_non_participation', 'non_participation_reason_threshold', 'radicalism_drift', 'archetype_impact_threshold', 'archetype_response_count', 'scheduled'] = Field(json_schema_extra={'when': 'always'})
    metric: Literal['pct_agents_with_impact_above'] = Field(default=None, json_schema_extra={'when': 'optional'})
    value: float = Field(default=None, json_schema_extra={'when': 'optional'})
    min_proportion: float = Field(default=None, ge=0, le=1, json_schema_extra={'when': 'optional'})
    window_rounds: int = Field(default=None, ge=1, json_schema_extra={'when': 'optional'})
    topics: List[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    min_count: int = Field(default=None, ge=1, json_schema_extra={'when': 'optional'})
    primary_archetype: str = Field(default=None, json_schema_extra={'when': 'optional'})
    secondary_archetypes: List[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    min_secondary_count: int = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    reason_category: Literal['distrust', 'fear', 'time_constraints', 'apathy', 'other'] = Field(default=None, json_schema_extra={'when': 'optional'})
    min_proportion_of_non_participants: float = Field(default=None, ge=0, le=1, json_schema_extra={'when': 'optional'})
    from_max: float = Field(default=None, json_schema_extra={'when': 'optional'})
    to_min: float = Field(default=None, json_schema_extra={'when': 'optional'})
    archetype: str = Field(default=None, json_schema_extra={'when': 'optional'})
    min_impact_score: float = Field(default=None, ge=0, le=1, json_schema_extra={'when': 'optional'})
    min_responses: int = Field(default=None, ge=1, json_schema_extra={'when': 'optional'})
    rounds: List[Annotated[int, Field(ge=0)]] = Field(default=None, json_schema_extra={'when': 'optional'})
    consecutive_rounds: int = Field(default=None, ge=1, json_schema_extra={'when': 'optional'})
    count_action_types: List[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    require_action_types: List[str] = Field(default=None, json_schema_extra={'when': 'optional'})


class EventRulesRulesItemEvent(DataModel):
    type: str = Field(json_schema_extra={'when': 'always'})
    source: str = Field(json_schema_extra={'when': 'always'})
    title: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    content: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    affected_archetypes: List[str] = Field(json_schema_extra={'when': 'always'})
    severity: Literal['low', 'medium', 'high', 'critical'] = Field(json_schema_extra={'when': 'always'})
    persist_rounds: int = Field(ge=1, json_schema_extra={'when': 'always'})


class EventRulesRulesItem(DataModel):
    id: str = Field(pattern='^[a-z0-9_]+$', json_schema_extra={'when': 'always'})
    description: str = Field(json_schema_extra={'when': 'always'})
    category: str = Field(json_schema_extra={'when': 'always'})
    applies_to_modes: List[Literal['policy', 'product']] = Field(default=None, json_schema_extra={'when': 'optional', 'note': 'Unset means policy only.'})
    trigger: EventRulesRulesItemTrigger = Field(json_schema_extra={'when': 'always'})
    event: EventRulesRulesItemEvent = Field(json_schema_extra={'when': 'always'})
    cooldown_rounds: int = Field(ge=0, json_schema_extra={'when': 'always'})
    max_triggers_per_simulation: int = Field(ge=1, json_schema_extra={'when': 'always'})


class EventRules(DataModel):
    """Reactive and scheduled event rules for policy simulations: when a trigger fires, an event is injected into the opinion space."""
    MODEL_NAME: ClassVar[str] = 'event_rules'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'Reactive and scheduled event rules for policy simulations: when a trigger fires, an '
                  'event is injected into the opinion space.',
         'stored_in': 'backend/app/config/event_rules.json',
         'written_by': ['hand-authored'],
         'read_by': ['event_rule_engine.EventRuleEngine'],
         'rules': ['Rule ids are unique.',
                   'trigger.type is one the engine evaluates; the other trigger fields are the '
                   'parameters that type reads.']}
    version: str = Field(json_schema_extra={'when': 'always'})
    description: str = Field(json_schema_extra={'when': 'always'})
    rules: List[EventRulesRulesItem] = Field(json_schema_extra={'when': 'always'})


class B2bSectorsSectorsValue(DataModel):
    label: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    qlfs_industry: str = Field(json_schema_extra={'when': 'always'})
    qlfs_industry_shared_with: str = Field(default=None, json_schema_extra={'when': 'optional'})
    assign_split: str = Field(default=None, json_schema_extra={'when': 'optional'})
    bodies_available: Any = Field(json_schema_extra={'when': 'always'})
    regulator: str = Field(json_schema_extra={'when': 'always'})
    incentive_levers: List[str] = Field(json_schema_extra={'when': 'always'})
    scoreable_levers: list = Field(default=None, json_schema_extra={'when': 'optional'})
    deal_must_respect: List[str] = Field(json_schema_extra={'when': 'always'})
    decision_lens: Literal['commercial', 'procedural'] = Field(json_schema_extra={'when': 'always'})
    decision_provenance: str = Field(default=None, json_schema_extra={'when': 'optional'})
    governance_frame: str = Field(default=None, json_schema_extra={'when': 'optional'})
    in_org_interest_means: str = Field(default=None, json_schema_extra={'when': 'optional'})
    risk_committee_gate: str = Field(default=None, json_schema_extra={'when': 'optional'})
    notes: str = Field(json_schema_extra={'when': 'always'})


class B2bSectors(DataModel):
    """The planned B2B layer (sectors half): the SA context a decision-maker in each sector carries — regulator, incentive levers, what a deal must respect."""
    MODEL_NAME: ClassVar[str] = 'b2b_sectors'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'The planned B2B layer (sectors half): the SA context a decision-maker in each '
                  'sector carries — regulator, incentive levers, what a deal must respect.',
         'stored_in': 'backend/app/data/persona_library/b2b_sectors.json',
         'written_by': ['hand-authored from QLFS industry counts and sector regulator frames'],
         'read_by': ['scripts/preview_b2b_persona.py'],
         'rules': ['Not wired into rooms yet (b2b-persona-layer plan). bodies_available is a QLFS '
                   'count, or a note when two sectors share one QLFS industry.']}
    README_: str = Field(default=None, alias='_README', json_schema_extra={'when': 'optional'})
    provenance_: str = Field(alias='_provenance', json_schema_extra={'when': 'always'})
    version: int = Field(ge=0, json_schema_extra={'when': 'always'})
    sectors: Dict[str, B2bSectorsSectorsValue] = Field(json_schema_extra={'when': 'always'})


class B2bFunctionsFunctionsValue(DataModel):
    label: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    ofo_family: str = Field(json_schema_extra={'when': 'always'})
    mandate: str = Field(json_schema_extra={'when': 'always'})
    decision_criteria: List[str] = Field(json_schema_extra={'when': 'always'})
    typical_objections: List[str] = Field(json_schema_extra={'when': 'always'})
    budget_authority_band: str = Field(json_schema_extra={'when': 'always'})
    what_wins_them: str = Field(json_schema_extra={'when': 'always'})
    dmu_role: str = Field(default=None, json_schema_extra={'when': 'optional'})
    dmu_mandate: str = Field(default=None, json_schema_extra={'when': 'optional'})
    consensus_behaviour: str = Field(default=None, json_schema_extra={'when': 'optional'})
    stalls_deal_when: list = Field(default=None, json_schema_extra={'when': 'optional'})
    decision_provenance: str = Field(default=None, json_schema_extra={'when': 'optional'})


class B2bFunctions(DataModel):
    """The planned B2B layer (functions half): the sector-agnostic decision seats a B2B persona can occupy — mandate, criteria, objections, budget authority."""
    MODEL_NAME: ClassVar[str] = 'b2b_functions'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'The planned B2B layer (functions half): the sector-agnostic decision seats a B2B '
                  'persona can occupy — mandate, criteria, objections, budget authority.',
         'stored_in': 'backend/app/data/persona_library/b2b_functions.json',
         'written_by': ['hand-authored from the DHET OFO register and standard buying-committee roles'],
         'read_by': ['scripts/preview_b2b_persona.py'],
         'rules': ['Not wired into rooms yet (b2b-persona-layer plan).']}
    README_: str = Field(default=None, alias='_README', json_schema_extra={'when': 'optional'})
    provenance_: str = Field(alias='_provenance', json_schema_extra={'when': 'always'})
    version: int = Field(ge=0, json_schema_extra={'when': 'always'})
    functions: Dict[str, B2bFunctionsFunctionsValue] = Field(json_schema_extra={'when': 'always'})


class ObjectionVocabWallsValue(DataModel):
    label: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    source: str = Field(json_schema_extra={'when': 'always'})
    cues: List[Annotated[str, Field(min_length=1)]] = Field(min_length=1, json_schema_extra={'when': 'always'})
    grounds: List[Dict[str, Annotated[list, Field(min_length=1)]]] = Field(json_schema_extra={'when': 'always'})
    reading_only: bool = Field(default=None, json_schema_extra={'when': 'optional'})


class ObjectionVocabPullsValue(DataModel):
    label: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    source: str = Field(json_schema_extra={'when': 'always'})
    cues: List[Annotated[str, Field(min_length=1)]] = Field(min_length=1, json_schema_extra={'when': 'always'})
    grounds: List[Dict[str, Annotated[list, Field(min_length=1)]]] = Field(json_schema_extra={'when': 'always'})


class ObjectionVocabMarkers(DataModel):
    condition: List[str] = Field(min_length=1, json_schema_extra={'when': 'always'})
    wall_strong: List[str] = Field(min_length=1, json_schema_extra={'when': 'always'})
    pull: List[str] = Field(min_length=1, json_schema_extra={'when': 'always'})
    wall_weak: List[str] = Field(min_length=1, json_schema_extra={'when': 'always'})


class ObjectionVocab(DataModel):
    """What a panel answer pushes against (walls) or leans toward (pulls), the words that signal each, and the persona facts that entitle someone to raise it."""
    MODEL_NAME: ClassVar[str] = 'objection_vocab'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'What a panel answer pushes against (walls) or leans toward (pulls), the words that '
                  'signal each, and the persona facts that entitle someone to raise it.',
         'stored_in': 'backend/app/data/objection_vocab.json',
         'written_by': ['hand-authored (walls from the TymeBank segment benchmark; pulls authored, '
                        'unvalidated)'],
         'read_by': ['objections.py', 'hypothesis_report.py', 'panel_service.rank_by_segment'],
         'rules': ['Grounds name persona facts and answers (checked against model/persona.json in '
                   'test_persona_data_model).',
                   'A wall marked reading_only is read from sentences but never counted in the '
                   'benchmark mention layer.']}
    version: int = Field(ge=1, json_schema_extra={'when': 'always'})
    about: str = Field(json_schema_extra={'when': 'always'})
    walls: Dict[str, ObjectionVocabWallsValue] = Field(json_schema_extra={'when': 'always'})
    pulls: Dict[str, ObjectionVocabPullsValue] = Field(json_schema_extra={'when': 'always'})
    markers: ObjectionVocabMarkers = Field(json_schema_extra={'when': 'always'})


class PitchPartsPartsValue(DataModel):
    label: str = Field(min_length=1, json_schema_extra={'when': 'always'})
    price: bool = Field(default=None, json_schema_extra={'when': 'optional', 'note': 'True when a stated rand price also counts as touching this part.'})
    words: List[Annotated[str, Field(pattern='^[a-z][a-z -]*\\*?$')]] = Field(min_length=1, json_schema_extra={'when': 'always'})


class PitchParts(DataModel):
    """The parts of life a pitch can touch, and the words that signal each. A persona fact tagged with a part reaches a fact prompt when the pitch mentions it."""
    MODEL_NAME: ClassVar[str] = 'pitch_parts'
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
         'about': 'The parts of life a pitch can touch, and the words that signal each. A persona fact '
                  'tagged with a part reaches a fact prompt when the pitch mentions it.',
         'stored_in': 'backend/app/data/pitch_parts.json',
         'written_by': ['hand-authored'],
         'read_by': ['persona_facts.pitch_parts'],
         'rules': ['Words name subject matter only, never good or bad. A word ending in * matches any '
                   'ending.',
                   'Every part is used by at least one persona fact (test_persona_fact_prompts).']}
    version: int = Field(ge=1, json_schema_extra={'when': 'always'})
    about: str = Field(json_schema_extra={'when': 'always'})
    parts: Dict[str, PitchPartsPartsValue] = Field(json_schema_extra={'when': 'always'})


#: Model name (app/data/model/<name>.json) -> class.
MODELS = {
    'grant_schedule': GrantSchedule,
    'world_facts': WorldFacts,
    'event_rules': EventRules,
    'b2b_sectors': B2bSectors,
    'b2b_functions': B2bFunctions,
    'objection_vocab': ObjectionVocab,
    'pitch_parts': PitchParts,
}
