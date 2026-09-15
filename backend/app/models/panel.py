"""Panel data models: one person's answer, a round result, a saved round file, and
the fields a room adds to a seated person.

The source of truth for app/data/model/answer.json and room_seat.json (exported by
scripts/export_data_models.py). Generated once from that JSON, then maintained here.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import Field

from .base import DataModel, export_fields, export_model

ANSWER_HEADER = {'version': 1,
 'about': "What one person's answer in a panel round looks like, and the round file around it. "
          'Written by interview_service.batch_impact_interview and panel_service.save_round; '
          'read by the results screen, the follow-up report and the segment ranking. '
          'tests/test_answer_data_model.py checks real rows and saved rounds against this '
          'file.',
 'rules': ['Every key on an answer row must be listed under answer_row.fields. Unknown keys '
           'fail the tests.',
           'when: always = on every row; answered = on every row that has no error; failed = '
           'only on rows that have an error; optional = may be absent.',
           'A failed row must carry error and failed. Its response is a placeholder, never an '
           'opinion.',
           'Money fields on a row are copies of real persona data made by the room. The model '
           'never writes them.',
           'A reader that needs a key not listed here is reading something no row carries.']}


class AnswerRow(DataModel):
    """One person's answer in a round (or a failed interview in its place)."""
    EXPORT_TYPE: ClassVar[str] = "answer_row"
    agent_id: int = Field(json_schema_extra={'when': 'always',
         'note': 'Seat number in this room, not the library id.',
         'read_by': ['FlowResults.vue', 'panel_service.py', 'hypothesis_report.py']})
    response: str = Field(json_schema_extra={'when': 'always',
         'note': 'What the person said, stance line removed. Placeholder text on failed rows.',
         'read_by': ['FlowResults.vue',
                     'panel_service.py',
                     'hypothesis_report.py',
                     'objections.py']})
    original_question: str = Field(json_schema_extra={'when': 'always', 'note': 'The pitch or announcement as the user typed it.'})
    stance_before: Literal['support', 'neutral', 'concerned', 'oppose', 'resist'] = Field(default=None, json_schema_extra={'when': 'answered',
         'read_by': ['FlowResults.vue', 'panel_service.py', 'hypothesis_report.py']})
    stance_after: Literal['support', 'neutral', 'concerned', 'oppose', 'resist'] = Field(default=None, json_schema_extra={'when': 'answered',
         'read_by': ['FlowResults.vue', 'panel_service.py', 'hypothesis_report.py']})
    stance_changed: bool = Field(default=None, json_schema_extra={'when': 'answered',
         'read_by': ['FlowResults.vue', 'panel_service.py', 'hypothesis_report.py']})
    internal_state: dict = Field(default=None, json_schema_extra={'when': 'answered',
         'note': "Snapshot of the agent's state after answering (attitudes, stance, emotion)."})
    impact_metadata: dict = Field(default=None, json_schema_extra={'when': 'answered',
         'note': 'Keyword heuristics on the answer (granularity, predicted action). Carries a '
                 'nested error on failed rows.'})
    reframed_question: str = Field(default=None, json_schema_extra={'when': 'answered', 'note': 'The full prompt this person was given.'})
    agent_name: Optional[str] = Field(default=None, json_schema_extra={'when': 'answered', 'read_by': ['panel_service.py', 'hypothesis_report.py']})
    actor_archetype: Optional[str] = Field(default=None, json_schema_extra={'when': 'answered', 'read_by': ['panel_service.py']})
    group_affiliation: Optional[str] = Field(default=None, json_schema_extra={'when': 'answered'})
    question_archetype: str = Field(default=None, json_schema_extra={'when': 'answered'})
    timestamp: str = Field(default=None, json_schema_extra={'when': 'answered'})
    error: str = Field(default=None, json_schema_extra={'when': 'failed', 'read_by': ['FlowResults.vue', 'panel_service.py']})
    failed: Literal[True] = Field(default=None, json_schema_extra={'when': 'failed', 'read_by': ['FlowResults.vue']})
    library_id: str = Field(default=None, pattern='^[0-9a-f]{16}$', json_schema_extra={'when': 'optional',
         'note': "The persona's id in the library. Absent for custom agents."})
    budget_tier: Literal['tight', 'moderate', 'loose'] = Field(default=None, json_schema_extra={'when': 'optional',
         'note': 'Can afford it, computed from real income (mode_specs.budget_tier). Never '
                 'from the model.',
         'read_by': ['FlowResults.vue']})
    is_grant_dependent: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    grant_type: Optional[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    monthly_income_rand: float = Field(default=None, json_schema_extra={'when': 'optional',
         'note': 'Room copy of real monthly income (library monthly_household_income_rand, or '
                 'a detected grant amount).',
         'read_by': ['FlowResults.vue']})
    research_cards_used: List[str] = Field(default=None, json_schema_extra={'when': 'optional',
         'note': 'Ids of the research cards that reached this prompt. Absent for old profiles '
                 'with no citations.',
         'read_by': ['FlowResults.vue']})
    facts_used: List[str] = Field(default=None, json_schema_extra={'when': 'optional',
         'note': 'Persona facts that replaced the story in this prompt (persona_facts). '
                 'Present only when PERSONA_FACT_PROMPTS is on and the seat is a library '
                 'persona.'})

    @classmethod
    def cross_field_problems(cls, data, label):
        who = f"agent {data.get('agent_id')}"
        out = super().cross_field_problems(data, who)
        failed = "error" in data
        for name, info in cls.model_fields.items():
            when = (info.json_schema_extra or {}).get("when")
            if name not in data:
                if (when == "answered" and not failed) or (when == "failed" and failed):
                    out.append(f"{who}: missing {name!r}")
            elif when == "failed" and not failed:
                out.append(f"{who}: {name!r} is only for failed interviews")
        return out


class RoundResult(DataModel):
    """A batch interview result: a panel round, or a sim's impact_interviews.json."""
    EXPORT_TYPE: ClassVar[str] = "round_result"
    simulation_id: str = Field(json_schema_extra={'when': 'always'})
    original_question: str = Field(json_schema_extra={'when': 'always'})
    total_interviewed: int = Field(json_schema_extra={'when': 'always'})
    successful: int = Field(json_schema_extra={'when': 'always'})
    failed: int = Field(json_schema_extra={'when': 'always',
         'note': 'A count here. On an answer row, failed is a true/false flag.'})
    question_archetype: str = Field(json_schema_extra={'when': 'always'})
    impact_dashboard: dict = Field(json_schema_extra={'when': 'always'})
    results: List[AnswerRow] = Field(json_schema_extra={'when': 'always'})
    summary_narrative: Optional[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    by_segment: list = Field(default=None, json_schema_extra={'when': 'optional'})
    coverage: Optional[dict] = Field(default=None, json_schema_extra={'when': 'optional'})
    all_failed: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    unusable: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    failure_reason: str = Field(default=None, json_schema_extra={'when': 'optional'})

    @classmethod
    def cross_field_problems(cls, data, label):
        out = super().cross_field_problems(data, label)
        for row in data.get("results") or [] if isinstance(data.get("results"), list) else []:
            if isinstance(row, dict):
                out += AnswerRow.cross_field_problems(row, label)
        return out


class RoundFile(DataModel):
    """A saved panel round: the pitch as sent and the result."""
    round: int = Field(json_schema_extra={'when': 'always'})
    timestamp: str = Field(json_schema_extra={'when': 'always'})
    pitch: str = Field(json_schema_extra={'when': 'always'})
    framed_pitch: str = Field(json_schema_extra={'when': 'always'})
    agent_ids: Optional[List[int]] = Field(json_schema_extra={'when': 'always'})
    carried_probe: Optional[Any] = Field(default=None, json_schema_extra={'when': 'optional'})
    result: RoundResult = Field(json_schema_extra={'type': 'round_result', 'when': 'always'})

    @classmethod
    def cross_field_problems(cls, data, label):
        out = super().cross_field_problems(data, label)
        if isinstance(data.get("result"), dict):
            out += RoundResult.cross_field_problems(data["result"], f"{label}: result")
        return out


class RoomSeatResearchCitationsItem(DataModel):
    card_id: str = Field(json_schema_extra={'when': 'always'})
    citation: List[str] = Field(json_schema_extra={'when': 'always'})
    confidence: str = Field(json_schema_extra={'when': 'always'})


class RoomSeatLsmProxy(DataModel):
    score: float = Field(json_schema_extra={'when': 'always'})
    band: str = Field(json_schema_extra={'when': 'always'})
    band_meaning: str = Field(json_schema_extra={'when': 'always'})
    confidence: str = Field(json_schema_extra={'when': 'always'})


class RoomSeatChatState(DataModel):
    interview_memory: list = Field(json_schema_extra={'when': 'always'})
    interview_count: int = Field(ge=0, json_schema_extra={'when': 'always'})
    stance: str = Field(json_schema_extra={'when': 'always'})


class RoomSeat(DataModel):
    """The fields a room adds to a person when it is built. The person part is a
    LibraryPersona or a custom agent (see room_seat_problems in services/data_model)."""
    MODEL_NAME: ClassVar[str] = "room_seat"
    HEADER: ClassVar[Dict[str, Any]] = {'version': 1,
     'about': 'One seat in a panel or sim room: a person (library persona or custom agent) plus '
              'the fields the room adds when it is built. The person part is checked against '
              "model/persona.json or model/custom_agent.json; these are the room's own fields.",
     'stored_in': 'uploads/panel_sessions/<session_id>/agentsociety_profiles.json (list of seats)',
     'written_by': ['panel_service._build_profile',
                    'mechanism_card_service.attach_research_context',
                    'panel_service.add_segment',
                    'interview_service._persist_chat_state'],
     'read_by': ['interview_service.py',
                 'prompt_reframer.py',
                 'opinion_agent.py',
                 'panel_service.rank_by_segment',
                 'FlowResults.vue'],
     'rules': ['Money fields are computed from real persona data when the room is built, never by '
               'the model.',
               "A grant detected at room build writes income_provenance 'grant_schedule' over the "
               "persona's own; that value is a room value, not a persona one."],
     'room_income_provenance': ['grant_schedule']}
    TOGETHER: ClassVar[List[List[str]]] = [['is_grant_dependent', 'grant_type'], ['research_context', 'research_citations'], ['segment_id', 'segment_label']]
    id: int = Field(ge=0, json_schema_extra={'when': 'always', 'note': 'Seat number in this room. The library id is library_id.'})
    library_id: Optional[str] = Field(default=None, pattern='^[0-9a-f]{16}$', json_schema_extra={'when': 'optional'})
    stance: Optional[Literal['support', 'neutral', 'concerned', 'oppose', 'resist']] = Field(default=None, json_schema_extra={'when': 'optional'})
    is_institutional: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    country: Optional[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    budget_tier: Optional[Literal['tight', 'moderate', 'loose']] = Field(default=None, json_schema_extra={'when': 'optional'})
    is_grant_dependent: bool = Field(default=None, json_schema_extra={'when': 'optional'})
    grant_type: Optional[str] = Field(default=None, json_schema_extra={'when': 'optional'})
    monthly_income_rand: float = Field(default=None, ge=0, json_schema_extra={'when': 'optional'})
    research_context: str = Field(default=None, json_schema_extra={'when': 'optional'})
    research_citations: List[RoomSeatResearchCitationsItem] = Field(default=None, json_schema_extra={'when': 'optional'})
    lsm_proxy: RoomSeatLsmProxy = Field(default=None, json_schema_extra={'when': 'optional',
         'note': "Copied from the library's in-memory load stamp. Not read from seats."})
    segment_id: str = Field(default=None, json_schema_extra={'when': 'optional',
         'note': 'Which picked group seated this person (panel_service.SEGMENTS).'})
    segment_label: str = Field(default=None, json_schema_extra={'when': 'optional'})
    chat_state: RoomSeatChatState = Field(default=None, json_schema_extra={'when': 'optional',
         'note': 'Follow-up chat memory, kept apart so the person stays as built.'})


def export_answer():
    """The reviewable JSON form of app/data/model/answer.json."""
    return {
        **ANSWER_HEADER,
        "answer_row": {"fields": export_fields(AnswerRow)},
        "round_result": {"fields": export_fields(RoundResult)},
        "round_file": {"fields": export_fields(RoundFile)},
    }


def export_room_seat():
    return export_model(RoomSeat)
