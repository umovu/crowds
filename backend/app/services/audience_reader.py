"""audience_reader — who a founder says the product is for, as facts the library holds.

"City workers without medical aid" is one group of people: all three at once. The
group chips cannot say that; picking three of them seats anyone in ANY of the three.
This reads the audience part of the founder's own sentence into a short list of
facts the personas actually carry, and the room is then the people who match ALL of
them (same field twice reads as either: "renters or homeowners").

Keywords only, with the model off. A typed reader (Jev) was tried on the answer
sheet (tests/data/audience_cases.json, 2026-09-24) and made it worse: precision
fell from 100% to 88% because it inferred facts nobody wrote ("Soweto" read as
struggling, "retired" as out of work, a city name as "lives in a city"), and it
found nothing the keywords missed. A founder's audience must be what they said.

  * Only facts on the fixed list below.
  * Nothing is invented: a phrase that names
    something the library does not know well enough (income, informal work) comes
    back as `unmatched`, in plain words, never as a silent guess.
  * Only the sentences that describe people are read. "No medical aid needed" in a
    product description is a feature of the product, not a fact about its buyers.

Selection only: it chooses among real library people and never writes one.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..models.persona import fact_value

# id -> (plain label, persona field, answers that count, keywords). Keywords are
# matched as whole words/phrases, so "men" never fires inside "women".
OPTIONS: Dict[str, Dict[str, Any]] = {
    "city": {"label": "Lives in a city or town", "field": "geotype", "values": ["Urban"],
             "words": ["city", "cities", "urban", "towns", "township", "townships", "metro", "metros"]},  # not "town": Cape Town
    "rural": {"label": "Lives in a rural area", "field": "geotype", "values": ["Traditional", "Farms"],
              "words": ["rural", "village", "villages", "countryside"]},
    "working": {"label": "Has a job", "field": "employment_status", "values": ["Employed"],
                "words": ["workers", "working", "working people", "employed", "employees", "salaried", "wage earners",
                          "professionals", "working adults", "who work", "with a job", "with jobs"]},
    "out_of_work": {"label": "Out of work", "field": "employment_status",
                    "values": ["Unemployed", "Discouraged job seeker"],
                    "words": ["unemployed", "jobless", "job seekers", "work seekers", "out of work"]},
    "no_medical_aid": {"label": "No medical aid", "field": "medical_aid", "values": ["False"],
                       "words": ["no medical aid", "without medical aid", "don't have medical aid",
                                 "do not have medical aid", "uninsured", "out-of-pocket", "out of pocket",
                                 "pay cash for", "pay-as-you-go", "pay as you go"]},
    "has_medical_aid": {"label": "Has medical aid", "field": "medical_aid", "values": ["True"],
                        "words": ["with medical aid", "medical aid members", "on medical aid", "insured"]},
    "renters": {"label": "Rents their home", "field": "housing_tenure", "values": ["rent"],
                "words": ["renters", "tenants", "who rent", "renting"]},
    "homeowners": {"label": "Owns their home", "field": "housing_tenure", "values": ["own", "bond"],
                   "words": ["homeowners", "home owners", "own their home", "own their homes", "own a home"]},
    "bond": {"label": "Paying off a home loan", "field": "housing_tenure", "values": ["bond"],
             "words": ["home loan", "home loans", "bond holders", "a bond", "their bond"]},
    "car_owners": {"label": "Owns a car", "field": "owns_vehicle", "values": ["own"],
                   "words": ["car owners", "drivers", "own a car", "who drive", "motorists"]},
    "no_car": {"label": "No car", "field": "owns_vehicle", "values": ["none"],
               "words": ["without a car", "no car", "taxi users", "taxi commuters", "rely on taxis", "use taxis"]},
    "women": {"label": "Women", "field": "gender", "values": ["Female"],
              "words": ["women", "woman", "mothers", "moms", "mums", "female", "females", "ladies", "girls"]},
    "men": {"label": "Men", "field": "gender", "values": ["Male"],
            "words": ["men", "fathers", "dads", "male", "males"]},
    "young": {"label": "Aged 15-34", "field": "age_band", "values": ["15-24", "25-34"],
              "words": ["young people", "youth", "young adults", "younger", "millennials", "gen z", "students"]},
    "age_15_24": {"label": "Aged 15-24", "field": "age_band", "values": ["15-24"],
                  "words": ["teenagers", "teens", "school leavers"]},
    "age_25_34": {"label": "Aged 25-34", "field": "age_band", "values": ["25-34"], "words": []},
    "middle_aged": {"label": "Aged 35-59", "field": "age_band", "values": ["35-59"],
                    "words": ["middle-aged", "middle aged"]},
    "older": {"label": "Aged 60+", "field": "age_band", "values": ["60+"],
              "words": ["pensioners", "elderly", "older people", "retired", "retirees", "seniors", "over 60"]},
    "parents": {"label": "Raising children at school", "field": "ghs_role",
                "values": ["guardian_parent", "gogo_guardian"],
                "words": ["parents", "parent", "mothers", "fathers", "moms", "mums", "dads", "guardians", "with kids",
                          "with children", "families with children"]},
    "grandparents": {"label": "Grandparents raising children", "field": "ghs_role", "values": ["gogo_guardian"],
                     "words": ["grandparents", "gogos", "grannies"]},
    "learners": {"label": "High-school learners", "field": "ghs_role", "values": ["learner"],
                 "words": ["learners", "pupils", "high school students", "high-school students"]},
    "farmers": {"label": "Farmers", "field": "actor_archetype",
                "values": ["communal_farmer", "smallholder_emerging_farmer"],
                "words": ["farmers", "farmer", "smallholders", "smallholder farmers"]},
    "small_business": {"label": "Small business owners", "field": "actor_archetype",
                       "values": ["small_business_owner"],
                       "words": ["small business owners", "business owners", "sme owners", "small businesses"]},
    "comfortable": {"label": "Comfortable (rarely goes without)", "field": "lived_poverty",
                    "values": ["none", "low"],
                    "words": ["middle class", "middle-class", "middle income", "middle-income",
                              "comfortable", "affluent", "well-off", "higher income", "higher-income"]},
    "struggling": {"label": "Struggling (often goes without)", "field": "lived_poverty",
                   "values": ["moderate", "high"],
                   "words": ["low-income", "low income", "the poor", "poor households", "poor families", "poor people",
                             "poorer households", "poorer families", "struggling", "working poor"]},  # not "poor service"
    "tertiary": {"label": "Studied after school", "field": "education", "values": ["Tertiary"],
                 "words": ["graduates", "university educated", "university-educated", "tertiary", "degree holders"]},
}

# Province names and the big cities people write instead of them.
PROVINCES: Dict[str, List[str]] = {
    "Gauteng": ["gauteng", "johannesburg", "joburg", "jozi", "pretoria", "tshwane", "soweto", "ekurhuleni",
                "sandton", "midrand", "centurion", "alexandra"],
    "Western Cape": ["western cape", "cape town"],
    "KwaZulu-Natal": ["kwazulu-natal", "kwazulu natal", "kzn", "durban", "pietermaritzburg"],
    "Eastern Cape": ["eastern cape", "gqeberha", "port elizabeth", "east london"],
    "Limpopo": ["limpopo", "polokwane"],
    "Mpumalanga": ["mpumalanga", "mbombela", "nelspruit"],
    "North West": ["north west", "rustenburg", "mahikeng"],
    "Free State": ["free state", "bloemfontein"],
    "Northern Cape": ["northern cape", "kimberley"],
}

# Things founders say about their buyers that the library cannot match well
# enough to filter on. Reported back, never guessed at.
UNMATCHABLE: List[Dict[str, Any]] = [
    # Not bare "earn": "customers earn points" says nothing about income.
    {"words": ["earn between", "earning between", "earns between", "earn r", "earning r", "earns r",
               "earn less than", "earn more than", "earning less than", "earning more than",
               "income of", "income between", "incomes between", "salary of", "salaries of"],
     "say": "income: most people in the library have no income figure"},
    {"words": ["informal entrepreneurs", "informal traders", "informal sector", "informal workers",
               "hawkers", "street vendors", "spaza owners", "spaza shop owners"],  # not "sold at spaza shops"
     "say": "informal work: only known for some people"},
    {"words": ["grant recipients", "on a grant", "sassa", "social grant", "social grants"],
     "say": "grants: only known for some people (use the 'Living on a grant' group)"},
    {"words": ["zulu-speaking", "xhosa-speaking", "sotho-speaking", "afrikaans-speaking", "english-speaking",
               "home language", "isizulu", "isixhosa"],
     "say": "home language: not in the library"},
    {"words": ["christian", "muslim", "religious", "church"],
     "say": "religion: not in the library"},
]

# A sentence describes people when it names them. Only such sentences are read,
# so a product feature ("no medical aid needed") is not taken for a buyer.
_CUES = ["for", "aimed at", "targeting", "target market", "target", "segment", "customers", "customer",
         "clients", "users", "consumers", "individuals", "people", "households", "buyers", "audience",
         "who", "these", "they", "families"]

# Words that name people are cues on their own: "Grandparents raising grandchildren
# need help" describes buyers without any of the words above. Fact phrases that
# describe a product ("no medical aid needed") are deliberately not in this list.
_PEOPLE = ["renters", "tenants", "homeowners", "home owners", "drivers", "motorists", "commuters",
           "women", "mothers", "moms", "mums", "ladies", "men", "fathers", "dads", "pensioners",
           "elderly", "retirees", "seniors", "parents", "guardians", "grandparents", "gogos", "learners",
           "pupils", "students", "teenagers", "teens", "workers", "employees", "professionals",
           "graduates", "youth", "millennials", "unemployed", "job seekers", "farmers", "smallholders",
           "business owners"]

def _has(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


# "no medical aid needed", "without a car required": what the product does not
# ask of you, not who the buyer is. Removed before any fact is read.
_NOT_NEEDED = re.compile(r"\b(?:no|without)\s+[a-z -]{1,25}?\s+(?:needed|required|necessary)\b")


def audience_text(text: str) -> str:
    """The sentences of `text` that describe people, lower-cased and joined."""
    low = _NOT_NEEDED.sub(" ", (text or "").lower())
    sentences = re.split(r"(?<=[.!?])\s+|\n+", low)
    return " ".join(s for s in sentences if any(_has(s, c) for c in _CUES + _PEOPLE))


_BANDS = [("age_15_24", 15, 24), ("age_25_34", 25, 34), ("middle_aged", 35, 59), ("older", 60, 120)]
_RANGE_RES = [
    (re.compile(r"(?:aged|ages|between)\s+(\d{2})\s*(?:-|–|to|and)\s*(\d{2})"), lambda a, b: (a, b)),
    (re.compile(r"\b(\d{2})\s*(?:-|–|to)\s*(\d{2})[- ]year[- ]olds?"), lambda a, b: (a, b)),
    (re.compile(r"(?:over|older than|above)\s+(\d{2})\b"), lambda a: (int(a) + 1, 120)),
    (re.compile(r"(?:under|younger than|below)\s+(\d{2})\b"), lambda a: (15, int(a) - 1)),
]


def _age_facts(about: str) -> List[str]:
    """"aged 25-35" -> every age band that range touches."""
    out: List[str] = []
    for rx, span in _RANGE_RES:
        for m in rx.finditer(about):
            lo, hi = (int(x) for x in span(*m.groups()))
            out += [oid for oid, b_lo, b_hi in _BANDS if lo <= b_hi and hi >= b_lo and oid not in out]
    return out


def _narrowest(facts: List[str]) -> List[str]:
    """Within one field, a narrower pick beats a broader one that contains it:
    "homeowners paying off a bond" is bond holders, not every homeowner."""
    keep = []
    for f in facts:
        vals = set(OPTIONS[f]["values"])
        wider_than_another = any(g != f and OPTIONS[g]["field"] == OPTIONS[f]["field"]
                                 and set(OPTIONS[g]["values"]) < vals for g in facts)
        if not wider_than_another:
            keep.append(f)
    return keep


def _keyword_facts(about: str) -> List[str]:
    words = [oid for oid, o in OPTIONS.items() if any(_has(about, w) for w in o["words"])]
    # "young drivers", "young mothers": young describing people, not "young children".
    if "young" not in words and any(_has(about, "young " + p) for p in _PEOPLE):
        words.append("young")
    return words + [f for f in _age_facts(about) if f not in words]


def _keyword_provinces(about: str) -> List[str]:
    return [p for p, words in PROVINCES.items() if any(_has(about, w) for w in words)]


def _unmatched(about: str) -> List[str]:
    return [u["say"] for u in UNMATCHABLE if any(_has(about, w) for w in u["words"])]


def read(text: str) -> Dict[str, Any]:
    """The audience a founder's text names: fact ids, provinces, and what could not be matched."""
    about = audience_text(text)
    facts = _keyword_facts(about)
    # "Mothers" names a woman AND a parent, so both facts are kept on purpose.
    facts = _narrowest(facts)
    return {
        "facts": [f for f in OPTIONS if f in facts],  # stable order
        "provinces": _keyword_provinces(about),
        "unmatched": _unmatched(about),
    }


def rule(facts: List[str], provinces: Optional[List[str]] = None) -> Dict[str, set]:
    """Facts -> {field: allowed answers}. Same field twice is OR, different fields AND."""
    out: Dict[str, set] = {}
    for f in facts or []:
        o = OPTIONS.get(f)
        if o is None:
            raise ValueError(f"unknown audience fact '{f}' — one of {sorted(OPTIONS)}")
        out.setdefault(o["field"], set()).update(o["values"])
    if provinces:
        out["province"] = set(provinces)
    return out


def _age_band(age) -> Optional[str]:
    if not isinstance(age, int):
        return None
    return "15-24" if age < 25 else "25-34" if age < 35 else "35-59" if age < 60 else "60+"


def matches(persona: Dict[str, Any], wanted: Dict[str, set]) -> bool:
    """True when the persona has every wanted fact. A fact the persona lacks does not match."""
    for field, allowed in wanted.items():
        value = _age_band(fact_value(persona, "age")) if field == "age_band" else fact_value(persona, field)
        if value is None or str(value) not in allowed:
            return False
    return True


def labels(facts: List[str], provinces: Optional[List[str]] = None) -> List[str]:
    return [OPTIONS[f]["label"] for f in facts if f in OPTIONS] + list(provinces or [])


def count(facts: List[str], provinces: Optional[List[str]] = None) -> int:
    """How many library people are all of it — shown before the room is built."""
    from .persona_library import get_library
    wanted = rule(facts, provinces)
    return sum(1 for p in get_library().all() if matches(p, wanted))


def members(facts: List[str], provinces: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Library ids per fact (and per province, keyed "@Province"), so the page can
    recount on its own when the founder removes one: the room is their intersection."""
    from .persona_library import get_library
    people = get_library().all()
    out = {f: [p["id"] for p in people if matches(p, rule([f]))] for f in facts}
    for prov in provinces or []:
        out["@" + prov] = [p["id"] for p in people if matches(p, rule([], [prov]))]
    return out
