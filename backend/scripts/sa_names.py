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
cross groups in real life. Home language drives the choice when known; province is
the fallback; otherwise a broad urban mix is used.
"""

from __future__ import annotations

import random as _random
from typing import Dict, List, Optional, Set

# ── Name banks by broad language family ─────────────────────────────────────
# Each bank: first names by gender + surnames. Sized so first×surname yields
# hundreds of unique combos per group — far more than any single cast (≤24) or
# the whole library (≈269) needs.
_BANKS: Dict[str, Dict] = {
    "nguni": {  # isiZulu / isiXhosa / siSwati / isiNdebele
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
    "english": {  # English / Cape creole surnames common in WC
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
}

# Home language → bank.
_LANG_GROUP = {
    "IsiZulu": "nguni", "IsiXhosa": "nguni", "IsiNdebele": "nguni", "SiSwati": "nguni",
    "Sesotho": "sotho_tswana", "Setswana": "sotho_tswana", "Sepedi": "sotho_tswana",
    "Xitsonga": "tsonga_venda", "Tshivenda": "tsonga_venda",
    "Afrikaans": "afrikaans", "English": "english",
}

# Province → likely bank(s), used only when home language is unknown. Mixed
# provinces draw from several banks so an unknown-language persona still gets a
# plausible, varied name.
_PROVINCE_GROUPS = {
    "KwaZulu-Natal": ["nguni"],
    "Eastern Cape": ["nguni"],
    "Mpumalanga": ["nguni", "sotho_tswana"],
    "Gauteng": ["nguni", "sotho_tswana"],
    "Free State": ["sotho_tswana"],
    "North West": ["sotho_tswana"],
    "Limpopo": ["sotho_tswana", "tsonga_venda"],
    "Northern Cape": ["sotho_tswana", "afrikaans"],
    "Western Cape": ["afrikaans", "english"],
}

_DEFAULT_GROUPS = ["nguni", "sotho_tswana"]  # broad urban-majority fallback


def _gender_key(gender: Optional[str]) -> Optional[str]:
    g = (str(gender) if gender is not None else "").strip().lower()
    if g.startswith("f"):
        return "female"
    if g.startswith("m"):
        return "male"
    return None


def _groups_for(home_language: Optional[str], province: Optional[str]) -> List[str]:
    if home_language and home_language in _LANG_GROUP:
        return [_LANG_GROUP[home_language]]
    if province and province in _PROVINCE_GROUPS:
        return list(_PROVINCE_GROUPS[province])
    return list(_DEFAULT_GROUPS)


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
    rng: Optional[_random.Random] = None,
) -> str:
    """Return a 'First Surname' not already in `used`, plausible for the persona.

    `used` is a set of lowercased full names; the chosen name is added to it.
    Deterministic when a seeded `rng` is supplied. LLM-free.
    """
    r = rng or _random
    gkey = _gender_key(gender)
    firsts, surs = _candidate_lists(_groups_for(home_language, province), gkey)
    if not firsts or not surs:  # paranoia: never happens with banks above
        firsts, surs = ["Lerato", "Thabo"], ["Mokoena", "Nene"]

    # Fast path: random combos.
    for _ in range(300):
        nm = f"{r.choice(firsts)} {r.choice(surs)}"
        if nm.lower() not in used:
            used.add(nm.lower())
            return nm

    # Exhaustive sweep of this group's combos (handles a near-saturated pool).
    combos = [f"{f} {s}" for f in firsts for s in surs]
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
