"""A library persona, as a Python data model.

What a persona IS: its fields, their types, the answers each one allows, and the rules
that refuse a persona that does not fit. Nothing here reads or writes a file.

Where each field CAME FROM — its survey, question codes, and how it reaches a prompt —
lives in app/data/model/notes/persona.json. The two halves are merged into the
reviewable app/data/model/persona.json by app/repositories/model_catalogue_repository.py
(run scripts/export_data_models.py after changing either half).

Two keys stay here rather than in the notes, because the app acts on them:
`carried_by` (which personas must have a field — checked below in `_problems`) and
`type` (the short type name the exported file carries for a rows field).
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional

from pydantic import Field

from .base import DataModel, export_fields

HEADER = {'version': 1,
 'groups': {'everyone': {'when': {}, 'about': 'Every library persona.'},
            'ghs_household': {'when': {'source_survey': ['ghs_2025']},
                              'about': 'Built from the GHS 2025 household files.'},
            'ghs_household_build': {'when': {'source_survey': ['ghs_2025'], 'ghs_role': [None]},
                                    'about': 'GHS households sampled by money and land '
                                             '(affluent, comfortable, landholding).'},
            'ghs_role_build': {'when': {'source_survey': ['ghs_2025'],
                                        'ghs_role': ['learner',
                                                     'guardian_parent',
                                                     'gogo_guardian']},
                               'about': 'GHS learners and the adults who look after them.'},
            'learner': {'when': {'ghs_role': ['learner']},
                        'about': 'School and college learners.'},
            'guardian': {'when': {'ghs_role': ['guardian_parent', 'gogo_guardian']},
                         'about': 'Parents and grandparents with learners at home.'},
            'farmer': {'when': {'actor_archetype': ['communal_farmer',
                                                    'smallholder_emerging_farmer']},
                       'about': 'QLFS farm-module samples.'}}}

#: Attitude topics: allowed stances, the survey items behind each, and literal answers seen.
TOPICS = {'gov_trust': {'stances': ['low', 'mid', 'high'],
               'source': {'survey': 'afrobarometer_r9_sa',
                          'items': ['Q37A', 'Q37D'],
                          'primary_item': 'Q37A',
                          'asked': 'how much you trust the President'},
               'answers': ['A lot', 'Just a little', 'Not at all', 'Somewhat']},
 'economic_optimism': {'stances': ['pessimistic', 'neutral', 'optimistic'],
                       'source': {'survey': 'afrobarometer_r9_sa',
                                  'items': ['Q4A', 'Q4B'],
                                  'primary_item': 'Q4A',
                                  'asked': 'the present economic condition of the country'},
                       'answers': ['Fairly bad',
                                   'Fairly good',
                                   'Neither good nor bad',
                                   'Very bad',
                                   'Very good']},
 'service_satisfaction': {'stances': ['dissatisfied', 'mixed', 'satisfied'],
                          'source': {'survey': 'afrobarometer_r9_sa',
                                     'items': ['Q46I', 'Q46L'],
                                     'primary_item': 'Q46I',
                                     'asked': 'how government is handling water and '
                                              'sanitation'},
                          'answers': ['Fairly badly',
                                      'Fairly well',
                                      'Very badly',
                                      'Very well']},
 'crime_fear': {'stances': ['low', 'mid', 'high'],
                'source': {'survey': 'afrobarometer_r9_sa',
                           'items': ['Q7A', 'Q7B'],
                           'primary_item': 'Q7A',
                           'asked': 'how often you felt unsafe walking in your neighbourhood'},
                'answers': ['Always',
                            'Just once or twice',
                            'Many times',
                            'Never',
                            'Several times']},
 'education_satisfaction': {'stances': ['dissatisfied', 'mixed', 'satisfied'],
                            'source': {'survey': 'afrobarometer_r9_sa',
                                       'items': ['Q46H'],
                                       'primary_item': 'Q46H',
                                       'asked': 'how government is handling educational needs'},
                            'answers': ['Fairly badly',
                                        'Fairly well',
                                        'Very badly',
                                        'Very well']},
 'health_service_satisfaction': {'stances': ['dissatisfied', 'mixed', 'satisfied'],
                                 'source': {'survey': 'afrobarometer_r9_sa',
                                            'items': ['Q46G'],
                                            'primary_item': 'Q46G',
                                            'asked': 'how government is handling basic health '
                                                     'services'},
                                 'answers': ['Fairly badly',
                                             'Fairly well',
                                             'Very badly',
                                             'Very well']},
 'health_authority_trust': {'stances': ['low', 'mid', 'high'],
                            'source': {'survey': 'afrobarometer_r9_sa',
                                       'items': ['Q37O_SAF'],
                                       'primary_item': 'Q37O_SAF',
                                       'asked': 'how much you trust the Department of Health'},
                            'answers': ['A lot', 'Just a little', 'Not at all', 'Somewhat']},
 'councillor_responsiveness': {'stances': ['low', 'mid', 'high'],
                               'source': {'survey': 'afrobarometer_r9_sa',
                                          'items': ['Q34B'],
                                          'primary_item': 'Q34B',
                                          'asked': 'how much your local councillor listens'},
                               'answers': ['Always', 'Never', 'Often', 'Only sometimes']},
 'official_responsiveness': {'stances': ['low', 'mid', 'high'],
                             'source': {'survey': 'afrobarometer_r9_sa',
                                        'items': ['Q36A'],
                                        'primary_item': 'Q36A',
                                        'asked': 'how much government officials listen'},
                             'answers': ['Not at all likely',
                                         'Not very likely',
                                         'Somewhat likely',
                                         'Very likely']},
 'crime_handling': {'stances': ['dissatisfied', 'mixed', 'satisfied'],
                    'source': {'survey': 'afrobarometer_r9_sa',
                               'items': ['Q46F'],
                               'primary_item': 'Q46F',
                               'asked': 'how government is handling crime'},
                    'answers': ['Fairly badly', 'Fairly well', 'Very badly', 'Very well']},
 'immigration_priority': {'stances': ['low', 'mid', 'high'],
                          'source': {'survey': 'afrobarometer_r9_sa',
                                     'items': ['Q82C_SAF'],
                                     'primary_item': 'Q82C_SAF',
                                     'asked': 'whether foreign nationals take jobs from '
                                              'locals'},
                          'answers': ['Agree',
                                      'Disagree',
                                      'Neither agree nor disagree',
                                      'Strongly agree',
                                      'Strongly disagree']},
 'pays_for_quality': {'stances': ['no', 'mixed', 'yes'],
                      'source': {'survey': 'afrobarometer_r9_sa',
                                 'items': ['Q80C_SAF'],
                                 'primary_item': 'Q80C_SAF',
                                 'asked': 'paying more for a better service'},
                      'answers': ['Agree',
                                  'Disagree',
                                  'Neither agree nor disagree',
                                  'Strongly agree',
                                  'Strongly disagree']},
 'business_trust': {'stances': ['low', 'mid', 'high'],
                    'source': {'survey': 'afrobarometer_r9_sa',
                               'items': ['Q38J'],
                               'primary_item': 'Q38J',
                               'asked': 'how much you trust private businesses'},
                    'answers': ['All of them', 'Most of them', 'None', 'Some of them']},
 'social_trust': {'stances': ['low', 'mid', 'high'],
                  'source': {'survey': 'afrobarometer_r9_sa',
                             'items': ['Q86A'],
                             'primary_item': 'Q86A',
                             'asked': 'whether most people can be trusted'},
                  'answers': ['A lot', 'Just a little', 'Not at all', 'Somewhat']},
 'environment_priority': {'stances': ['low', 'mid', 'high'],
                          'source': {'survey': 'afrobarometer_r9_sa',
                                     'items': ['Q67A', 'Q72A', 'Q72D']}},
 'social_voice': {'stances': ['low', 'mid', 'high'],
                  'source': {'survey': 'afrobarometer_r9_sa',
                             'items': ['Q8', 'Q10B'],
                             'primary_item': 'Q10B',
                             'asked': 'whether you have joined others to raise an issue'},
                  'answers': ['No, would do it if I had the chance',
                              'No, would never do this',
                              'Yes, often',
                              'Yes, once or twice',
                              'Yes, several times']},
 'neighbour_trust': {'stances': ['low', 'mid', 'high'],
                     'source': {'survey': 'afrobarometer_r9_sa',
                                'items': ['Q86C'],
                                'primary_item': 'Q86C',
                                'asked': 'how much you trust your neighbours'},
                     'answers': ['A lot', 'Just a little', 'Not at all', 'Somewhat']}}

#: Circumstance fields: allowed values, the survey items, and prompt wording.
CIRCUMSTANCES = {'lived_poverty': {'values': ['none', 'low', 'moderate', 'high'],
                   'source': {'survey': 'afrobarometer_r9_sa',
                              'items': ['Q6A', 'Q6B', 'Q6C', 'Q6D', 'Q6E']},
                   'prompt': {'core': True,
                              'say': {'none': 'This year you have had enough food, water and '
                                              'cash.',
                                      'low': 'Once or twice this year you were short of '
                                             'something basic.',
                                      'moderate': 'Several times this year you were short of '
                                                  'food, water or cash.',
                                      'high': 'You are often short of food, water or cash.'}}},
 'went_without_care': {'values': ['never', 'rarely', 'sometimes', 'often'],
                       'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q6C']},
                       'prompt': {'about': ['health'],
                                  'say': {'never': 'You have been able to get medical care '
                                                   'when you needed it.',
                                          'rarely': 'Once or twice this year you could not get '
                                                    'medical care you needed.',
                                          'sometimes': 'Several times this year you could not '
                                                       'get medical care you needed.',
                                          'often': 'You often cannot get the medical care you '
                                                   'need.'}}},
 'owns_vehicle': {'values': ['none', 'household', 'own'],
                  'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q90C']},
                  'prompt': {'about': ['getting_there'],
                             'say': {'none': 'There is no car in your household.',
                                     'household': 'There is a car in your household you can '
                                                  'use.',
                                     'own': 'You have your own car.'}}},
 'owns_computer': {'values': ['none', 'household', 'own'],
                   'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q90D']},
                   'prompt': {'about': ['online'],
                              'say': {'none': 'There is no computer in your household.',
                                      'household': 'There is a computer in your household that '
                                                   'you share.',
                                      'own': 'You have your own computer.'},
                              'replaced_by': 'computer_in_home'}},
 'owns_bank_account': {'values': ['none', 'household', 'own'],
                       'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q90E']},
                       'prompt': {'about': ['money'],
                                  'say': {'none': 'You do not have a bank account.',
                                          'household': "You use someone else's bank account in "
                                                       'your household.',
                                          'own': 'You have your own bank account.'}}},
 'owns_television': {'values': ['none', 'household', 'own'],
                     'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q90B']},
                     'prompt': {'about': ['media'],
                                'say': {'none': 'There is no TV in your household.',
                                        'household': 'There is a TV in your household.',
                                        'own': 'You have your own TV.'}}},
 'internet_use': {'values': ['never', 'rarely', 'monthly', 'weekly', 'daily'],
                  'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q90I']},
                  'note': 'What the person calls "the internet". In R9 SA, 240 of the 360 who '
                          'said never own a mobile phone and 206 use one every day, so never '
                          'here is not "no WhatsApp". The phone facts carry that.',
                  'prompt': {'about': ['online', 'media'],
                             'say': {'never': 'You say you never use the internet.',
                                     'rarely': 'You go online less than once a month.',
                                     'monthly': 'You go online a few times a month.',
                                     'weekly': 'You go online a few times a week.',
                                     'daily': 'You go online every day.'}}},
 'owns_phone': {'values': ['none', 'household', 'own'],
                'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q90F']},
                'optional': True,
                'note': 'Added after the library was built. Only a persona whose survey '
                        'respondent still gives every other circumstance it carries has it '
                        '(scripts/attach_phone_facts.py).',
                'prompt': {'about': ['online'],
                           'say': {'none': 'No one in your household has a mobile phone.',
                                   'household': 'You have no mobile phone of your own; someone '
                                                'else in your household has one.',
                                   'own': 'You have your own mobile phone.'}}},
 'phone_internet': {'values': ['no', 'yes'],
                    'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q90G']},
                    'optional': True,
                    'note': 'Only asked of people who own a phone themselves.',
                    'prompt': {'about': ['online'],
                               'say': {'no': 'Your phone cannot get on the internet.',
                                       'yes': 'Your phone can get on the internet.'}}},
 'phone_use': {'values': ['never', 'rarely', 'monthly', 'weekly', 'daily'],
               'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q90H']},
               'optional': True,
               'prompt': {'about': ['online'],
                          'say': {'never': 'You never use a mobile phone.',
                                  'rarely': 'You use a mobile phone less than once a month.',
                                  'monthly': 'You use a mobile phone a few times a month.',
                                  'weekly': 'You use a mobile phone a few times a week.',
                                  'daily': 'You use a mobile phone every day.'}}},
 'electricity_reliability': {'values': ['never', 'occasional', 'half', 'most', 'always'],
                             'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q92B']},
                             'prompt': {'about': ['services'],
                                        'say': {'never': 'There is no reliable mains power '
                                                         'where you live.',
                                                'occasional': 'The power is on only now and '
                                                              'then.',
                                                'half': 'The power is on about half the time.',
                                                'most': 'The power is on most of the time, '
                                                        'with interruptions.',
                                                'always': 'The power stays on where you '
                                                          'live.'}}},
 'money_decision': {'values': ['self', 'joint', 'other', 'none'],
                    'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q93C']},
                    'prompt': {'about': ['money'],
                               'say': {'self': 'You decide how the money in your household is '
                                               'spent.',
                                       'joint': 'You and others in your household decide '
                                                'together how money is spent.',
                                       'other': 'Someone else in your household decides how '
                                                'money is spent.',
                                       'none': 'You have no say in how money is spent.'}}},
 'news_radio': {'values': ['never', 'rarely', 'monthly', 'weekly', 'daily'],
                'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q74A']},
                'prompt': {'about': ['media'],
                           'say': {'never': 'You never hear news on the radio.',
                                   'rarely': 'You hear news on the radio less than once a '
                                             'month.',
                                   'monthly': 'You hear news on the radio a few times a month.',
                                   'weekly': 'You hear news on the radio a few times a week.',
                                   'daily': 'You hear news on the radio every day.'}}},
 'news_tv': {'values': ['never', 'rarely', 'monthly', 'weekly', 'daily'],
             'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q74B']},
             'prompt': {'about': ['media'],
                        'say': {'never': 'You never watch news on TV.',
                                'rarely': 'You watch news on TV less than once a month.',
                                'monthly': 'You watch news on TV a few times a month.',
                                'weekly': 'You watch news on TV a few times a week.',
                                'daily': 'You watch news on TV every day.'}}},
 'news_internet': {'values': ['never', 'rarely', 'monthly', 'weekly', 'daily'],
                   'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q74D']},
                   'prompt': {'about': ['media', 'online'],
                              'say': {'never': 'You never read news on the internet.',
                                      'rarely': 'You read news on the internet less than once '
                                                'a month.',
                                      'monthly': 'You read news on the internet a few times a '
                                                 'month.',
                                      'weekly': 'You read news on the internet a few times a '
                                                'week.',
                                      'daily': 'You read news on the internet every day.'}}},
 'news_social': {'values': ['never', 'rarely', 'monthly', 'weekly', 'daily'],
                 'source': {'survey': 'afrobarometer_r9_sa', 'items': ['Q74E']},
                 'prompt': {'about': ['media', 'online'],
                            'say': {'never': 'You never get news from social media.',
                                    'rarely': 'You get news from social media less than once a '
                                              'month.',
                                    'monthly': 'You get news from social media a few times a '
                                               'month.',
                                    'weekly': 'You get news from social media a few times a '
                                              'week.',
                                    'daily': 'You get news from social media every day.'}}}}

#: Facts made at match time, never stored.
DERIVED_FACTS = {'age_band': {'values': ['15-24', '25-34', '35-59', '60+'],
              'from': 'age',
              'note': 'Made at match time by mechanism_card_service._age_band. Not stored.'}}

GROUPS = HEADER["groups"]


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
    source_entity_type: Literal['library_persona'] = Field(json_schema_extra={'carried_by': 'everyone'})
    age: int = Field(ge=15, json_schema_extra={'carried_by': 'everyone'})
    gender: Literal['Female', 'Male'] = Field(json_schema_extra={'carried_by': 'everyone'})
    province: Literal['Eastern Cape', 'Free State', 'Gauteng', 'KwaZulu-Natal', 'Limpopo', 'Mpumalanga', 'North West', 'Northern Cape', 'Western Cape'] = Field(json_schema_extra={'carried_by': 'everyone'})
    education: Optional[Literal['Less than primary completed', 'No schooling', 'Other', 'Primary', 'Primary completed', 'Secondary completed', 'Secondary not completed', 'Tertiary']] = Field(json_schema_extra={'carried_by': 'everyone'})
    occupation: Optional[Literal['Clerks', 'Clerks (informal)', 'Craft and related trades workers', 'Craft and related trades workers (informal)', 'Discouraged job seeker', 'Domestic workers (informal)', 'Elementary Occupation', 'Elementary Occupation (informal)', 'Employed', 'Learner (School)', 'Learner (TVET college)', 'Legislators; senior officials and managers', 'Legislators; senior officials and managers (informal)', 'Other not economically active', 'Plant and machine operators and assemblers', 'Plant and machine operators and assemblers (informal)', 'Professionals', 'School teacher', 'Service workers and shop and market sales workers', 'Service workers and shop and market sales workers (informal)', 'Skilled agricultural and fishery workers', 'Skilled agricultural and fishery workers (informal)', 'Technical and associate professionals', 'Technical and associate professionals (informal)', 'Unemployed', 'Unspecified']] = Field(json_schema_extra={'carried_by': 'everyone'})
    employment_status: Literal['Discouraged job seeker', 'Employed', 'Other not economically active', 'Unemployed'] = Field(json_schema_extra={'carried_by': 'everyone'})
    informal: Optional[bool] = Field(json_schema_extra={'carried_by': 'everyone'})
    industry: Optional[Literal['Agriculture; hunting; forestry and fishing', 'Community; social and personal services', 'Construction', 'Financial intermediation; insurance; real estate and business services', 'Manufacturing', 'Mining and quarrying', 'Private households', 'Transport; storage and communication', 'Wholesale and retail trade']] = Field(json_schema_extra={'carried_by': 'everyone'})
    marriage_status: Literal['Divorced', 'Divorced or separated', 'Legally married', 'Living together like husband and wife', 'Living together like husband and wife/partners', 'Married', 'Never married', 'Single and have never been married/never lived together as husband/wife before', 'Single, but have lived together with someone as husband/wife before', 'Widow/Widower', 'Widowed'] = Field(json_schema_extra={'carried_by': 'everyone'})
    is_neet: Optional[bool] = Field(json_schema_extra={'carried_by': 'everyone'})
    race: Literal['African/Black', 'Coloured', 'Indian/Asian', 'White'] = Field(json_schema_extra={'carried_by': 'everyone'})
    geotype: Literal['Farms', 'Traditional', 'Urban'] = Field(json_schema_extra={'carried_by': 'everyone'})
    attitudes: List[AttitudeRow] = Field(json_schema_extra={'type': 'attitude_rows', 'carried_by': 'everyone'})
    circumstances: List[CircumstanceRow] = Field(json_schema_extra={'type': 'circumstance_rows', 'carried_by': 'everyone'})
    beliefs: List[str] = Field(min_length=1, json_schema_extra={'carried_by': 'everyone'})
    actor_archetype: Literal['affluent_agricultural_household', 'affluent_urban_household', 'civic_moderate', 'comfortable_household', 'communal_farmer', 'community_leader', 'disillusioned_dropout', 'educator', 'gogo_guardian', 'grant_dependent_survivor', 'guardian_parent', 'informal_trader', 'institutional_loyalist', 'learner', 'rural_landholding_household', 'small_business_owner', 'smallholder_emerging_farmer', 'unemployed_youth', 'urban_professional'] = Field(json_schema_extra={'carried_by': 'everyone'})
    attitude_match_quality: Literal['age_backoff', 'education_backoff', 'exact', 'province_backoff', 'status_race', 'race_only', 'population'] = Field(json_schema_extra={'carried_by': 'everyone'})
    survey_respondent: str = Field(pattern='^SAF\\d+$', json_schema_extra={'carried_by': 'everyone'})
    ghs_person_rows: Optional[List[str]] = Field(default=None, json_schema_extra={'carried_by': 'some'})
    persona: str = Field(json_schema_extra={'carried_by': 'everyone'})
    background_story: str = Field(json_schema_extra={'carried_by': 'everyone'})
    group_affiliation: str = Field(json_schema_extra={'carried_by': 'everyone'})
    interested_topics: List[str] = Field(json_schema_extra={'carried_by': 'everyone'})
    voice_guide: str = Field(json_schema_extra={'carried_by': 'everyone'})
    behavioral_tendencies: str = Field(json_schema_extra={'carried_by': 'everyone'})
    source_survey: Literal['ghs_2025', 'qlfs_2026_q1'] = Field(default=None, json_schema_extra={'carried_by': 'some'})
    occupation_provenance: Literal['role_assigned'] = Field(default=None, json_schema_extra={'carried_by': 'some'})
    employment_status_provenance: Literal['ghs_2025:employ_Status2'] = Field(default=None, json_schema_extra={'carried_by': 'some'})
    home_language: Optional[Literal['Afrikaans', 'English', 'IsiNdebele', 'IsiXhosa', 'IsiZulu', 'Other language not specified', 'Sepedi', 'Sesotho', 'Setswana', 'SiSwati', 'Tshivenda', 'Xitsonga']] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    monthly_household_income_rand: Optional[float] = Field(default=None, ge=0, json_schema_extra={'carried_by': 'ghs_household'})
    income_provenance: Optional[Literal['ghs_2025_reported']] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    internet_at_home: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    computer_in_home: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    receives_grant: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    medical_aid: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    self_rated_health: Optional[Literal['Excellent', 'Fair', 'Good', 'Poor', 'Very good']] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    has_disability: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    usual_health_facility: Optional[Literal['Private sector: Clinic', 'Private sector: Hospital', 'Private sector: Pharmacy/chemist', 'Private sector: Private doctor/specialist', 'Private sector: Traditional healer', 'Public sector: Clinic', 'Public sector: Hospital']] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    health_facility_sector: Optional[Literal['private', 'public']] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    transport_to_health_facility: Optional[Literal['Bus', 'Minibus taxi/sedan taxi/bakkie taxi', 'Other means of transport to nearest facility', 'Own transport', 'Walking']] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    time_to_health_facility: Optional[Literal['15–29 minutes', '30–89 minutes', '90 minutes and more', 'Less than 15 minutes']] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    health_provenance: Literal['ghs_2025_reported'] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household'})
    household_farms: Optional[bool] = Field(default=None, json_schema_extra={'carried_by': 'ghs_household_build'})
    ghs_role: Literal['gogo_guardian', 'guardian_parent', 'learner'] = Field(default=None, json_schema_extra={'carried_by': 'ghs_role_build'})
    edu_institution: Literal['School', 'TVET college'] = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    current_grade: Optional[Literal['Grade 10', 'Grade 11', 'Grade 12/Matric', 'Grade 7', 'Grade 8', 'Grade 9', 'Not applicable']] = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    fees_band: Optional[Literal['No fees', 'R1 001–R2 000 per year', 'R12 001–R16 000 per year', 'R16 001–R20 000 per year', 'R2 001–R3 000 per year', 'R201–R300 per year', 'R301–R500 per year', 'R4 001–R8 000 per year']] = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    time_to_school: Optional[Literal['15-30 minutes', '31-60 minutes', '61-90 minutes', 'under 15 minutes']] = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    guardian_type: Literal['grandparent', 'other relative', 'parent'] = Field(default=None, json_schema_extra={'carried_by': 'learner'})
    learners_in_household: int = Field(default=None, ge=0, json_schema_extra={'carried_by': 'guardian'})
    learner_fee_bands: List[Literal['No fees', 'R1 001–R2 000 per year', 'R101–R200 per year', 'R12 001–R16 000 per year', 'R1–R100 per year', 'R2 001–R3 000 per year', 'R20 001–R40 000 per year', 'R201–R300 per year', 'R3 001–R4 000 per year', 'R301–R500 per year', 'R40 001–R80 000 per year', 'R501–R1 000 per year', 'R8 001–R12 000 per year']] = Field(default=None, json_schema_extra={'carried_by': 'guardian'})
    guards_grandchildren: bool = Field(default=None, json_schema_extra={'carried_by': 'guardian'})
    farm_market_orientation: Literal['market', 'subsistence'] = Field(default=None, json_schema_extra={'carried_by': 'farmer'})
    farm_products: Optional[Literal['Farming of animals', 'Growing of crops', 'Growing of crops combined with farming of animals(mixed farming)']] = Field(default=None, json_schema_extra={'carried_by': 'farmer'})

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
        **{k: HEADER[k] for k in ("version", "groups")},
        "fields": export_fields(LibraryPersona),
        "attitude_row": _row_section(AttitudeRow, "topics", TOPICS, "every_topic_once"),
        "circumstance_row": _row_section(CircumstanceRow, "fields", CIRCUMSTANCES, "every_field_once"),
        "derived_facts": DERIVED_FACTS,
    }
