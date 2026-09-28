"""sa_names — curated South African name pool + unique-name assignment.

WHY THIS EXISTS
Survey microdata (QLFS bodies, Afrobarometer attitudes) is anonymized — it
carries NO names. Names were previously invented by the LLM in texture_generator,
one persona at a time with no awareness of names already used. Asked in isolation
for "a realistic SA name" hundreds of times, the model mode-collapsed onto a few
prototypes (≈55 library personas ended up named "Thabo Mokoena"). Duplicate names
then break a sim: the feed shows "[Thabo Mokoena] said …" for several different
people, and name-keyed UI merges them.

This module takes names OFF the LLM: a deterministic, inspectable pool of common
SA first names + surnames, grouped by language family, assigned uniquely against a
running `used` set. No model involved — pure data, assertable with the LLM off.

Linguistic grouping is broad and plausibility-first, not ethnographic; SA names
cross groups in real life. Race sets which banks are possible; home language picks
among them when known; province is the fallback; otherwise a broad urban mix is used.
"""

from __future__ import annotations

import random as _random
from typing import Dict, List, Optional, Set

# ── Name banks by broad language family ─────────────────────────────────────
# Each bank: first names by gender + surnames. Sized so first×surname yields
# hundreds of unique combos per group — far more than any single cast (≤24) or
# the whole library (≈269) needs.
_BANKS: Dict[str, Dict] = {
    "nguni": {  # isiZulu / siSwati / isiNdebele
        "female": ["Nomvula", "Thandeka", "Nosipho", "Zanele", "Nokuthula",
                   "Sibongile", "Lindiwe", "Busisiwe", "Phumzile", "Nonhlanhla",
                   "Thembeka", "Zinhle", "Ayanda", "Nokwanda", "Sindisiwe",
                   "Bongiwe", "Khanyisile", "Slindile", "Noluthando", "Zodwa"],
        "male": ["Sipho", "Mandla", "Bheki", "Sibusiso", "Nkosinathi",
                 "Bonginkosi", "Themba", "Musa", "Sandile", "Lwazi",
                 "Mxolisi", "Vusi", "Sifiso", "Andile", "Mlungisi",
                 "Zweli", "Mthunzi", "Khulani", "Senzo", "Njabulo"],
        "sur": ["Nene", "Dlamini", "Khumalo", "Ndlovu", "Zulu", "Mthembu",
                "Ngcobo", "Cele", "Mhlongo", "Buthelezi", "Shabangu", "Gumede",
                "Sithole", "Mkhize", "Zungu", "Hadebe", "Nxumalo", "Mchunu",
                "Xaba", "Mabaso", "Ntuli", "Zwane"],
    },
    "xhosa": {  # isiXhosa: Eastern Cape, and most Black Western Cape families
        "female": ["Nomsa", "Siphokazi", "Ntombizodwa", "Nwabisa", "Lulama",
                   "Yonela", "Asanda", "Zukiswa", "Nomonde", "Babalwa",
                   "Ziyanda", "Unathi", "Nolitha", "Akhona", "Anathi"],
        "male": ["Luvuyo", "Lwando", "Siyabonga", "Xolani", "Mzwandile",
                 "Luthando", "Thando", "Sizwe", "Lunga", "Siphiwo",
                 "Bongani", "Mncedisi", "Aphiwe", "Yamkela", "Lindani"],
        "sur": ["Mgidi", "Makhaya", "Ngcukana", "Mqhayi", "Jongile", "Ntshebe",
                "Nkwinti", "Gxasheka", "Nqoko", "Mabandla", "Qamata", "Tshawe",
                "Ndamase", "Tyali", "Dyantyi", "Bokwe", "Ntlabati", "Nombembe"],
    },
    "sotho_tswana": {  # Sesotho / Setswana / Sepedi
        "female": ["Lerato", "Palesa", "Refilwe", "Dineo", "Boitumelo",
                   "Tshepang", "Mpho", "Keabetswe", "Naledi", "Lebogang",
                   "Tshegofatso", "Kgomotso", "Masego", "Thato", "Karabo",
                   "Bontle", "Nthabiseng", "Realeboga", "Mamello", "Dimakatso"],
        "male": ["Thabo", "Tshepo", "Kagiso", "Katlego", "Tebogo", "Bokang",
                 "Lehlohonolo", "Oratile", "Kabelo", "Neo", "Lesedi",
                 "Itumeleng", "Rorisang", "Tumelo", "Kgosi", "Lefa",
                 "Tshiamo", "Reabetswe", "Otsile", "Phenyo"],
        "sur": ["Mokoena", "Molefe", "Modise", "Moloi", "Phiri", "Maleka",
                "Tau", "Mosia", "Motaung", "Radebe", "Mofokeng", "Tshabalala",
                "Khoza", "Sekhukhune", "Mahlangu", "Pheko", "Letlhake",
                "Nkoane", "Mabote", "Seabi", "Moeketsi", "Rampa"],
    },
    "tsonga_venda": {  # Xitsonga / Tshivenda
        "female": ["Rhandzu", "Nyeleti", "Tsakani", "Mukondi", "Rofhiwa",
                   "Ndivhuwo", "Khathutshelo", "Vhutshilo", "Mulalo", "Tshilidzi",
                   "Rendani", "Lufuno", "Hlamalani", "Mishengu", "Vongani"],
        "male": ["Hlamulo", "Rhulani", "Tinyiko", "Tshianeo", "Mukhethwa",
                 "Thabelo", "Rabelani", "Takalani", "Hangwani", "Mpho",
                 "Khensani", "Risenga", "Mhlava", "Fhatuwani", "Murunwa"],
        "sur": ["Baloyi", "Mathebula", "Chauke", "Maluleke", "Nkuna",
                "Ngobeni", "Shirinda", "Mthombeni", "Mulaudzi", "Mudau",
                "Tshivhase", "Nemukula", "Netshitenzhe", "Mabunda", "Hlungwani",
                "Mabasa", "Ramavhoya", "Munyai"],
    },
    "afrikaans": {
        "female": ["Anel", "Marike", "Elmarie", "Lize", "Annelize", "Marlene",
                   "Suné", "Riana", "Carike", "Ronel", "Elsabe", "Mariska",
                   "Lindi", "Hesti", "Nadia", "Carin", "Marizanne", "Annerie"],
        "male": ["Wynand", "Pieter", "Johan", "Riaan", "Schalk", "Hendrik",
                 "Kobus", "Gerhard", "Dewald", "Stefan", "Werner", "Andries",
                 "Francois", "Ruan", "Morné", "Tiaan", "Bernard", "Christo"],
        "sur": ["Van der Merwe", "Botha", "Pretorius", "Venter", "Coetzee",
                "Steyn", "Fourie", "Nel", "Kruger", "Du Plessis", "Van Wyk",
                "Joubert", "Swanepoel", "Le Roux", "Bezuidenhout", "Vermeulen",
                "Schoeman", "Erasmus", "Lombard", "Oosthuizen"],
    },
    "cape": {  # English / Afrikaans first names + Cape surnames, common in Coloured families
        "female": ["Megan", "Kayla", "Chloe", "Jessica", "Amber", "Robyn",
                   "Nicole", "Shannon", "Candice", "Tamryn", "Bianca", "Caitlin",
                   "Erin", "Leigh", "Paige", "Jade", "Tegan", "Roxanne"],
        "male": ["Wayne", "Brandon", "Liam", "Dylan", "Kyle", "Brett", "Craig",
                 "Shaun", "Ryan", "Travis", "Grant", "Clinton", "Trevor",
                 "Bradley", "Devon", "Lance", "Garth", "Ashley"],
        "sur": ["Petersen", "Adams", "Williams", "Daniels", "Jacobs",
                "Hendricks", "September", "Davids", "Isaacs", "Booysen",
                "Arendse", "Fortuin", "Cupido", "Pietersen", "Solomons",
                "Abrahams", "Cloete", "Goliath", "Plaatjies", "Fredericks"],
    },
    "english": {  # English-speaking white families
        "female": ["Sarah", "Emma", "Claire", "Kate", "Lauren", "Michelle",
                   "Samantha", "Rebecca", "Hannah", "Lisa", "Karen", "Jenna",
                   "Gemma", "Kirsten", "Alison", "Natalie"],
        "male": ["James", "Michael", "David", "Andrew", "Graham", "Gareth",
                 "Justin", "Matthew", "Richard", "Stuart", "Ross", "Sean",
                 "Nicholas", "Simon", "Duncan", "Warren"],
        "sur": ["Smith", "Taylor", "Brown", "Wilson", "Stewart", "Campbell",
                "Robertson", "Thompson", "Harris", "Clarke", "Edwards", "Walker",
                "Murray", "Wright", "Mitchell", "Bennett", "Hughes", "Fraser",
                "Palmer", "Watson"],
    },
    "indian_hindu": {  # Tamil / Hindi-speaking-heritage families, mostly KZN and Gauteng
        "female": ["Priya", "Kavitha", "Anusha", "Shamila", "Nisha", "Sharmila",
                   "Thanusha", "Kamini", "Rekha", "Sunitha", "Yashika", "Pooja"],
        "male": ["Rajesh", "Pravin", "Sanjay", "Vikash", "Suren", "Dinesh",
                 "Ashwin", "Rakesh", "Nitesh", "Kumaran", "Prenesh", "Yashveer"],
        "sur": ["Naidoo", "Pillay", "Govender", "Moodley", "Reddy", "Chetty",
                "Singh", "Maharaj", "Naicker", "Padayachee", "Ramlall", "Munsamy",
                "Perumal", "Rampersad", "Sookdeo"],
    },
    "indian_muslim": {
        "female": ["Fathima", "Ayesha", "Zainab", "Nadira", "Rukshana", "Shereen",
                   "Naseema", "Yasmin", "Raeesa", "Tasneem"],
        "male": ["Yusuf", "Imraan", "Faizal", "Ridwaan", "Ebrahim", "Zaheer",
                 "Riaz", "Shaheed", "Nazeer", "Irfaan"],
        "sur": ["Moosa", "Patel", "Khan", "Essop", "Mahomed", "Jeewa", "Dawood",
                "Bhamjee", "Cassim", "Suleman"],
    },
}

# Home language → bank.
_LANG_GROUP = {
    "IsiZulu": "nguni", "IsiXhosa": "xhosa", "IsiNdebele": "nguni", "SiSwati": "nguni",
    "Sesotho": "sotho_tswana", "Setswana": "sotho_tswana", "Sepedi": "sotho_tswana",
    "Xitsonga": "tsonga_venda", "Tshivenda": "tsonga_venda",
    "Afrikaans": "afrikaans", "English": "english",
}

# Race → the banks a name may come from. Home language and province only choose
# among these: a Black Western Cape resident with no recorded language was being
# named "Morné Pietersen", a White Gauteng resident "Thandeka Shabangu".
_RACE_GROUPS = {
    "African/Black": ["nguni", "xhosa", "sotho_tswana", "tsonga_venda"],
    "White": ["afrikaans", "english"],
    "Coloured": ["cape", "afrikaans"],
    "Indian/Asian": ["indian_hindu", "indian_muslim"],
}

# Province → likely bank(s), used only when home language is unknown. Mixed
# provinces draw from several banks so an unknown-language persona still gets a
# plausible, varied name.
_PROVINCE_GROUPS = {
    "KwaZulu-Natal": ["nguni"],
    "Eastern Cape": ["xhosa"],
    "Mpumalanga": ["nguni", "sotho_tswana"],
    "Gauteng": ["nguni", "sotho_tswana"],
    "Free State": ["sotho_tswana"],
    "North West": ["sotho_tswana"],
    "Limpopo": ["sotho_tswana", "tsonga_venda"],
    "Northern Cape": ["sotho_tswana", "afrikaans", "cape"],
    "Western Cape": ["afrikaans", "cape", "english", "xhosa"],
}

_DEFAULT_GROUPS = ["nguni", "sotho_tswana"]  # broad urban-majority fallback


def _gender_key(gender: Optional[str]) -> Optional[str]:
    g = (str(gender) if gender is not None else "").strip().lower()
    if g.startswith("f"):
        return "female"
    if g.startswith("m"):
        return "male"
    return None


def _groups_for(home_language: Optional[str], province: Optional[str],
                race: Optional[str] = None) -> List[str]:
    allowed = _RACE_GROUPS.get(race or "")
    if not allowed:
        allowed = list(_BANKS)
        default = _DEFAULT_GROUPS
    else:
        default = [g for g in _DEFAULT_GROUPS if g in allowed] or allowed
    lang = _LANG_GROUP.get(home_language or "")
    if lang in allowed:
        return [lang]
    near = [g for g in _PROVINCE_GROUPS.get(province or "", []) if g in allowed]
    return near or list(default)


def name_fits(name: str, race: Optional[str]) -> bool:
    """True when the first name and surname could both come from a bank this race
    draws on. Unknown race, or a surname the pool never issued, is not judged."""
    allowed = _RACE_GROUPS.get(race or "")
    first, _, sur = (name or "").partition(" ")
    if not allowed or not any(sur in b["sur"] for b in _BANKS.values()):
        return True
    firsts = lambda g: _BANKS[g]["female"] + _BANKS[g]["male"]  # noqa: E731
    if race == "Indian/Asian":  # Hindu and Muslim names do not mix within one person
        return any(first in firsts(g) and sur in _BANKS[g]["sur"] for g in allowed)
    return (any(first in firsts(g) for g in allowed)
            and any(sur in _BANKS[g]["sur"] for g in allowed))


def _candidate_lists(groups: List[str], gkey: Optional[str]):
    firsts: List[str] = []
    surs: List[str] = []
    for g in groups:
        bank = _BANKS[g]
        if gkey:
            firsts += bank["female" if gkey == "female" else "male"]
        else:
            firsts += bank["female"] + bank["male"]
        surs += bank["sur"]
    # Preserve order, drop dups (when several banks are unioned).
    firsts = list(dict.fromkeys(firsts))
    surs = list(dict.fromkeys(surs))
    return firsts, surs


def pick_unique_name(
    used: Set[str],
    *,
    gender: Optional[str] = None,
    home_language: Optional[str] = None,
    province: Optional[str] = None,
    race: Optional[str] = None,
    rng: Optional[_random.Random] = None,
) -> str:
    """Return a 'First Surname' not already in `used`, plausible for the persona.

    `used` is a set of lowercased full names; the chosen name is added to it.
    Deterministic when a seeded `rng` is supplied. LLM-free.
    """
    r = rng or _random
    gkey = _gender_key(gender)
    groups = _groups_for(home_language, province, race)
    firsts, surs = _candidate_lists(groups, gkey)
    if not firsts or not surs:  # paranoia: never happens with banks above
        firsts, surs = ["Lerato", "Thabo"], ["Mokoena", "Nene"]

    # Fast path: random combos, first name and surname from the same bank so a
    # union of banks never yields a "Yusuf Naidoo".
    for _ in range(300):
        f, s = _candidate_lists([r.choice(groups)], gkey)
        nm = f"{r.choice(f)} {r.choice(s)}"
        if nm.lower() not in used:
            used.add(nm.lower())
            return nm

    # Exhaustive sweep of this group's combos (handles a near-saturated pool).
    combos = [f"{f} {s}" for g in groups
              for f in _candidate_lists([g], gkey)[0] for s in _BANKS[g]["sur"]]
    r.shuffle(combos)
    for nm in combos:
        if nm.lower() not in used:
            used.add(nm.lower())
            return nm

    # Last resort: double-barrel surname so we can always return something unique.
    base_first = r.choice(firsts)
    for s1 in surs:
        for s2 in surs:
            if s1 == s2:
                continue
            nm = f"{base_first} {s1}-{s2}"
            if nm.lower() not in used:
                used.add(nm.lower())
                return nm
    # Truly exhausted (astronomically unlikely): fall back to a counter suffix.
    i = 2
    while True:
        nm = f"{base_first} {surs[0]} {i}"
        if nm.lower() not in used:
            used.add(nm.lower())
            return nm
        i += 1
