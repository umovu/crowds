"""A library persona, as a Python data model.

What a persona IS: its field names, their Python types, and the rules that refuse a
persona which does not fit. No survey data lives here, and nothing reads a file.

The data lives in app/data/model/catalogue/persona.json: every allowed answer, the
attitude and circumstance tables, which personas carry which field, and where each
field came from. The answer lists Python needs at import are generated from it into
_persona_types.py by scripts/generate_model_types.py, and the reviewable
app/data/model/persona.json is merged from both halves by
app/repositories/model_catalogue_repository.py.

`carried_by` stays on the fields here because this class validates against it.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import Field

from .base import DataModel, export_fields
from ._persona_types import (ActorArchetype, AttitudeMatchQuality, CurrentGrade, 
    EduInstitution, Education, EmploymentStatus, EmploymentStatusProvenance, 
    FarmMarketOrientation, FarmProducts, FeesBand, Gender, Geotype, GhsRole, GuardianType, 
    HealthFacilitySector, HealthProvenance, HomeLanguage, IncomeProvenance, Industry, 
    MarriageStatus, Occupation, OccupationProvenance, Province, Race, SelfRatedHealth, 
    SourceEntityType, SourceSurvey, TimeToHealthFacility, TimeToSchool, 
    TransportToHealthFacility, UsualHealthFacility, CIRCUMSTANCES, DERIVED_FACTS, GROUPS, 
    TOPICS)

HEADER = {'version': 1}


#: Attitude topics: allowed stances, the survey items behind each, and literal answers seen.


#: Circumstance fields: allowed values, the survey items, and prompt wording.


#: Facts made at match time, never stored.





def in_group(persona, when):
    return all(persona.get(field) in allowed for field, allowed in when.items())


def _row_problems(who, rows, row_cls, key, table):
    if rows is None:
        return []
    if not isinstance(rows, list):
        return [f"{who}: {key} rows should be a list"]
    out, seen = [], []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get(key)
        seen.append(name)
        out += row_cls.cross_field_problems(row, f"{who}: {key} {name!r}")
    doubled = sorted({n for n in seen if seen.count(n) > 1 and n in table})
    # An optional entry was added after the library was built and is only carried where
    # it could be traced to the persona's own survey respondent.
    optional = {n for n, entry in table.items() if isinstance(entry, dict) and entry.get("optional")}
    absent = sorted(set(table) - set(seen) - optional)
    if doubled:
        out.append(f"{who}: {key} rows repeated: {doubled}")
    if absent:
        out.append(f"{who}: {key} rows missing: {absent}")
    return out


class AttitudeRow(DataModel):
    """One measured attitude: the band on a topic and, where the survey item allows,
    the respondent's literal answer to the one question behind it."""
    MEASURED_KEYS: ClassVar[tuple] = ('measured_question', 'measured_asked', 'measured_answer')

    topic: Literal['gov_trust', 'economic_optimism', 'service_satisfaction', 'crime_fear', 'education_satisfaction', 'health_service_satisfaction', 'health_authority_trust', 'councillor_responsiveness', 'official_responsiveness', 'crime_handling', 'immigration_priority', 'pays_for_quality', 'business_trust', 'social_trust', 'environment_priority', 'social_voice', 'neighbour_trust']
    stance: str
    source: Literal['afrobarometer_r9_sa', 'afrobarometer_r9_sa:students', 'afrobarometer_r9_sa:teacher_class_professionals']
    match_quality: Literal['age_backoff', 'education_backoff', 'exact', 'population_draw', 'province_backoff', 'race_only', 'status_race', 'population']
    measured_question: str = None
    measured_asked: str = None
    measured_answer: str = None

    @classmethod
    def cross_field_problems(cls, data, label):
        out = super().cross_field_problems(data, label)
        entry = TOPICS.get(data.get("topic"))
        if not entry:
            return out
        if "stance" in data and data["stance"] not in entry["stances"]:
            out.append(f"{label} has an answer not in the model: {data['stance']!r}")
        present = [k for k in cls.MEASURED_KEYS if k in data]
        if not present:
            return out
        source = entry["source"]
        if len(present) != len(cls.MEASURED_KEYS):
            out.append(f"{label} carries only part of a survey answer: {present}")
        elif "primary_item" not in source:
            out.append(f"{label} carries a survey answer but the model names no question for it")
        else:
            if data["measured_question"] != source["primary_item"]:
                out.append(f"{label} answer is from question {data['measured_question']!r}, "
                           f"model says {source['primary_item']!r}")
            if data["measured_asked"] != source["asked"]:
                out.append(f"{label} question wording differs from the model")
            if data["measured_answer"] not in entry.get("answers", []):
                out.append(f"{label} survey answer not in the model: {data['measured_answer']!r}")
        return out


class CircumstanceRow(DataModel):
    """One measured circumstance of the matched survey respondent (assets, access, poverty)."""
    field: Literal['lived_poverty', 'went_without_care', 'owns_vehicle', 'owns_computer', 'owns_bank_account', 'owns_television', 'internet_use', 'owns_phone', 'phone_internet', 'phone_use', 'electricity_reliability', 'money_decision', 'news_radio', 'news_tv', 'news_internet', 'news_social']
    value: str
    source: Literal['afrobarometer_r9_sa', 'afrobarometer_r9_sa:students', 'afrobarometer_r9_sa:teacher_class_professionals']
    match_quality: Literal['age_backoff', 'education_backoff', 'exact', 'population_draw', 'province_backoff', 'race_only', 'status_race', 'population']

    @classmethod
    def cross_field_problems(cls, data, label):
        out = super().cross_field_problems(data, label)
        entry = CIRCUMSTANCES.get(data.get("field"))
        if entry and "value" in data and data["value"] not in entry["values"]:
            out.append(f"{label} has an answer not in the model: {data['value']!r}")
        return out


class LibraryPersona(DataModel):
    """A library persona: identity and circumstances from national surveys, attitudes from
    one matched Afrobarometer respondent, and model-written texture that adds no facts."""
    MODEL_NAME: ClassVar[str] = "persona"
    id: str = Field(pattern='^[0-9a-f]{16}$', json_schema_extra={'carried_by': 'everyone'})
    name: str = Field(json_schema_extra={'carried_by': 'everyone'})
    source_entity_type: SourceEntityType = Field(json_schema_extra={'carried_by': 'everyone'})
    age: int = Field(ge=15, json_schema_extra={'carried_by': 'everyone'})
    gender: Gender = Field(json_schema_extra={'carried_by': 'everyone'})
    province: Province = Field(json_schema_extra={'carried_by': 'everyone'})
    education: Optional[Education] = Field(json_schema_extra={'carried_by': 'everyone'})
    occupation: Optional[Occupation] = Field(json_schema_extra={'carried_by': 'everyone'})
    employment_status: EmploymentStatus = Field(json_schema_extra={'carried_by': 'everyone'})
    informal: Optional[bool] = Field(json_schema_extra={'carried_by': 'everyone'})
    industry: Optional[Industry] = Field(json_schema_extra={'carried_by': 'everyone'})
    marriage_status: MarriageStatus = Field(json_schema_extra={'carried_by': 'everyone'})
    is_neet: Optional[bool] = Field(json_schema_extra={'carried_by': 'everyone'})
    race: Race = Field(json_schema_extra={'carried_by': 'everyone'})
    geotype: Geotype = Field(json_schema_extra={'carried_by': 'everyone'})
    attitudes: List[AttitudeRow] = Field(json_schema_extra={'type': 'attitude_rows', 'carried_by': 'everyone'})
    circumstances: List[CircumstanceRow] = Field(json_schema_extra={'type': 'circumstance_rows', 'carried_by': 'everyone'})
    beliefs: List[str] = Field(min_length=1, json_schema_extra={'carried_by': 'everyone'})
    actor_archetype: ActorArchetype = Field(json_schema_extra={'carried_by': 'everyone'})
    attitude_match_quality: AttitudeMatchQuality = Field(json_schema_extra={'carried_by': 'everyone'})
    survey_respondent: str = Field(pattern='^SAF\\d+$', json_schema_extra={'carried_by': 'everyone'})
    ghs_person_rows: Optional[List[str]] = Field(default=None, json_schema_extra={'carried_by': 'some'})
    persona: str = Field(json_schema_extra={'carried_by': 'everyone'})
    background_story: str = Field(json_schema_extra={'carried_by': 'everyone'})
    group_affiliation: str = Field(json_schema_extra={'carried_by': 'everyone'})
    interested_topics: List[str] = Field(json_schema_extra={'carried_by': 'everyone'})
    voice_guide: str = Field(json_schema_extra={'carried_by': 'everyone'})
    behavioral_tendencies: str = Field(json_schema_extra={'carried_by': 'everyone'})
    source_survey: SourceSurvey = Field(default=None, json_schema_extra={'carried_by': 'some'})
    occupation_provenance: OccupationProvenance = Field(default=None, json_schema_extra={'carried_by': 'some'})
    employment_status_provenance: EmploymentStatusProvenance = Field(default=None, json_schema_extra={'carried_by': 'some'})
    home_language: Optional[HomeLanguage] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    monthly_household_income_rand: Optional[float] = Field(default=None, ge=0, json_schema_extra={'carried_by': 'ghs_household'})
    income_provenance: Optional[IncomeProvenance] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    internet_at_home: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    computer_in_home: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    receives_grant: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    medical_aid: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    self_rated_health: Optional[SelfRatedHealth] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    has_disability: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    usual_health_facility: Optional[UsualHealthFacility] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    health_facility_sector: Optional[HealthFacilitySector] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    transport_to_health_facility: Optional[TransportToHealthFacility] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    time_to_health_facility: Optional[TimeToHealthFacility] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    health_provenance: HealthProvenance = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    household_farms: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household_build'})
    ghs_role: GhsRole = Field(default=None, json_schema_extra={'carried_by': 'ghs_role_build'})
    edu_institution: EduInstitution = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    current_grade: Optional[CurrentGrade] = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    fees_band: Optional[FeesBand] = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    time_to_school: Optional[TimeToSchool] = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    guardian_type: GuardianType = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    learners_in_household: int = Field(default=None, ge=0, json_schema_extra={'carried_by': 'guardian'})
    learner_fee_bands: List[Literal['No fees', 'R1 001–R2 000 per year', 'R101–R200 per year', 'R12 001–R16 000 per year', 'R1–R100 per year', 'R2 001–R3 000 per year', 'R20 001–R40 000 per year', 'R201–R300 per year', 'R3 001–R4 000 per year', 'R301–R500 per year', 'R40 001–R80 000 per year', 'R501–R1 000 per year', 'R8 001–R12 000 per year']] = Field(default=None, json_schema_extra={'carried_by': 'guardian'})
    guards_grandchildren: bool = Field(default=None, json_schema_extra={'carried_by': 'guardian'})
    farm_market_orientation: FarmMarketOrientation = Field(default=None, json_schema_extra={'carried_by': 'farmer'})
    farm_products: Optional[FarmProducts] = Field(default=None, json_schema_extra={'carried_by': 'farmer'})

    @classmethod
    def cross_field_problems(cls, data, label):
        who = str(data.get("name") or data.get("id") or label)
        out = super().cross_field_problems(data, who)
        for name, info in cls.model_fields.items():
            carried = (info.json_schema_extra or {}).get("carried_by")
            if carried in (None, "some", "everyone"):
                continue  # everyone-fields are required by type; "some" are free
            inside = in_group(data, GROUPS[carried]["when"])
            if name not in data:
                if inside:
                    out.append(f"{who}: missing {name!r} (group {carried!r} must carry it)")
            elif not inside:
                out.append(f"{who}: has {name!r}, which only {carried} personas carry")
        out += _row_problems(who, data.get("attitudes"), AttitudeRow, "topic", TOPICS)
        out += _row_problems(who, data.get("circumstances"), CircumstanceRow, "field", CIRCUMSTANCES)
        return out

    def fact(self, name: str) -> Any:
        """One fact by name: a field, an attitude stance or a circumstance value."""
        return fact_value(self, name)


# ── picking people by fact: names and answers checked against this model ─────

def fact_names() -> set:
    """Every fact a rule may name: fields, attitude topics, circumstances, derived facts."""
    return set(LibraryPersona.model_fields) | set(TOPICS) | set(CIRCUMSTANCES) | set(DERIVED_FACTS)


class _Facts:
    """`FACT.medical_aid` is "medical_aid". A name the model does not have raises at
    import, so a typo in a picker fails loudly instead of quietly matching nobody."""

    def __getattr__(self, name: str) -> str:
        if name.startswith("__"):
            raise AttributeError(name)
        if name in fact_names():
            return name
        raise AttributeError(f"a library persona has no fact {name!r}")


FACT = _Facts()


def allowed_answers(fact: str) -> Optional[List[Any]]:
    """The answers a persona can hold for a fact, or None when it is open-ended."""
    if fact in TOPICS:
        return list(TOPICS[fact]["stances"])
    if fact in CIRCUMSTANCES:
        return list(CIRCUMSTANCES[fact]["values"])
    if fact in DERIVED_FACTS:
        return list(DERIVED_FACTS[fact]["values"])
    info = LibraryPersona.model_fields.get(fact)
    if info is None:
        raise KeyError(f"a library persona has no fact {fact!r}")
    from .base import type_spec
    return type_spec(info.annotation).get("allowed")


def fact_value(record: Any, fact: str) -> Any:
    """A fact from a persona dict, a room seat or a LibraryPersona object."""
    def get(obj, key):
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

    if fact in TOPICS:
        rows, key, value = get(record, "attitudes"), "topic", "stance"
    elif fact in CIRCUMSTANCES:
        rows, key, value = get(record, "circumstances"), "field", "value"
    else:
        return get(record, fact)
    for row in rows or ():
        if get(row, key) == fact:
            return get(row, value)
    return None


def persona_is(fact: str, *answers: Any):
    """A picker: True when a persona's fact is one of `answers`.

    The fact and every answer are checked against this model when the picker is
    built (at import), so "Rural" or "actor_archtype" fails there, not in a room.
    """
    allowed = allowed_answers(fact)
    if allowed is not None:
        wrong = [a for a in answers if a not in allowed]
        if wrong:
            raise ValueError(f"{fact} has no answer {wrong}; allowed: {allowed}")
    wanted = set(answers)
    return lambda record: fact_value(record, fact) in wanted


def _row_section(row_cls, table_key, table, every_key):
    fields = row_cls.model_fields
    measured = list(getattr(row_cls, "MEASURED_KEYS", ()))
    section = {"required": [n for n, f in fields.items() if f.is_required()]}
    if measured:
        section["measured_answer_keys"] = measured
    section["sources"] = list(fields["source"].annotation.__args__)
    section["match_quality"] = list(fields["match_quality"].annotation.__args__)
    section[every_key] = True
    section[table_key] = table
    return section


def export():
    """The reviewable JSON form of this model (app/data/model/persona.json)."""
    return {
        **HEADER,
        "fields": export_fields(LibraryPersona),
        "attitude_row": _row_section(AttitudeRow, "topics", TOPICS, "every_topic_once"),
        "circumstance_row": _row_section(CircumstanceRow, "fields", CIRCUMSTANCES, "every_field_once"),
        "derived_facts": DERIVED_FACTS,
    }
