"""Names fit the persona's recorded race; language and province only choose within it.

LLM-off. Loads the script by path.
"""

import importlib.util
import json
import os
import random

import pytest

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
LIBRARY = os.path.join(HERE, "..", "app", "data", "persona_library", "personas.json")

_spec = importlib.util.spec_from_file_location("sa_names_under_test", os.path.join(SCRIPTS, "sa_names.py"))
sn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sn)


def _names(n=60, **kw):
    used, rng = set(), random.Random(3)
    return [sn.pick_unique_name(used, rng=rng, **kw) for _ in range(n)]


def test_black_western_cape_resident_gets_a_xhosa_name_not_an_afrikaans_one():
    # Was "Morné Pietersen": province alone picked the Afrikaans / Cape banks.
    for nm in _names(race="African/Black", province="Western Cape", gender="Male"):
        assert nm.split(" ", 1)[1] in sn._BANKS["xhosa"]["sur"], nm


def test_every_race_gets_names_that_fit_it():
    for race in sn._RACE_GROUPS:
        for prov in ("Gauteng", "Western Cape", "KwaZulu-Natal", "Limpopo", None):
            for lang in (None, "Afrikaans", "English", "IsiZulu"):
                for nm in _names(12, race=race, province=prov, home_language=lang):
                    assert sn.name_fits(nm, race), (race, prov, lang, nm)


def test_home_language_chooses_within_the_race():
    assert all(nm.split(" ", 1)[1] in sn._BANKS["afrikaans"]["sur"]
               for nm in _names(race="White", home_language="Afrikaans"))
    assert all(nm.split(" ", 1)[1] in sn._BANKS["english"]["sur"]
               for nm in _names(race="White", home_language="English"))


def test_indian_names_do_not_mix_hindu_and_muslim_parts():
    assert not sn.name_fits("Yusuf Naidoo", "Indian/Asian")
    assert sn.name_fits("Yusuf Moosa", "Indian/Asian")


def test_the_mismatches_that_prompted_this_are_caught():
    assert not sn.name_fits("Morné Pietersen", "African/Black")
    assert not sn.name_fits("Thandeka Shabangu", "White")
    assert sn.name_fits("Morné Pietersen", "Coloured")


def test_unknown_race_is_not_judged():
    assert sn.name_fits("Morné Pietersen", None)
    assert sn.name_fits("Someone Unlisted", "African/Black")


@pytest.mark.skipif(not os.path.exists(LIBRARY), reason="persona library is local-only")
def test_the_library_has_no_race_mismatched_names():
    with open(LIBRARY, encoding="utf-8") as fh:
        personas = json.load(fh)["personas"]
    bad = [(p["name"], p.get("race")) for p in personas if not sn.name_fits(p["name"], p.get("race"))]
    assert not bad, bad
