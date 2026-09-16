"""The model catalogue: classes, catalogues and generated types stay in step. LLM-off.

A stored thing is described in two halves:

    app/models/<module>.py                 the class — names, Python types, methods
    app/data/model/catalogue/<name>.json   the data — allowed answers, tables, and the
                                           notes saying where each field came from

Python needs the answer lists as types at import, so they are generated into
app/models/_<module>_types.py from the catalogue. These tests keep the three honest:
a catalogue must describe a real model and real fields, it may hold prose only, the
generated types must not have drifted, and the one fact stored in two places
(`carried_by`) must agree.
"""

import glob
import json
import os
import subprocess
import sys

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CAT_DIR = os.path.join(BACKEND, "app", "data", "model", "catalogue")


def _catalogues():
    return sorted(glob.glob(os.path.join(CAT_DIR, "*.json")))


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_every_catalogue_describes_a_real_model():
    from app.repositories.model_catalogue_repository import EXPORTS
    for path in _catalogues():
        name = os.path.basename(path)[:-5]
        assert name in EXPORTS, f"{name}.json has a catalogue but no model class"


def test_catalogues_only_describe_fields_the_class_has():
    from app.repositories.model_catalogue_repository import EXPORTS, catalogue
    for path in _catalogues():
        name = os.path.basename(path)[:-5]
        fields = set(EXPORTS[name]().get("fields") or {})
        described = set(catalogue(name).get("fields") or {})
        assert described <= fields, \
            f"{name}.json describes unknown field(s): {sorted(described - fields)}"


def test_a_catalogue_holds_prose_not_rules():
    """Anything the app enforces belongs with the class. A catalogue carries provenance
    and prompt wording only, so a missing catalogue can never loosen validation."""
    # `fields`, `items` and `values` are not rules: they hold the notes for a nested
    # field table (an object's fields, a list's items, a free-key map's values).
    allowed = {"layer", "carried_by", "source", "note", "known_issue", "free_text",
               "prompt", "optional", "replaced_by", "legacy", "fields", "items", "values"}
    for path in _catalogues():
        for field, spec in (_load(path).get("fields") or {}).items():
            unknown = set(spec) - allowed
            assert not unknown, f"{os.path.basename(path)}:{field} has {sorted(unknown)}"


def test_carried_by_agrees_between_the_class_and_its_catalogue():
    """The class keeps `carried_by` because LibraryPersona validates against it; the
    catalogue keeps it because that is what the exported file is ordered by. Two copies
    of one fact drift unless something checks them."""
    from app.models import REGISTRY
    from app.repositories.model_catalogue_repository import catalogue
    for path in _catalogues():
        name = os.path.basename(path)[:-5]
        cls = REGISTRY.get(name)
        if cls is None or not hasattr(cls, "model_fields"):
            continue
        notes = catalogue(name).get("fields") or {}
        for field, info in cls.model_fields.items():
            on_class = (info.json_schema_extra or {}).get("carried_by")
            if on_class is None:
                continue
            assert on_class == notes.get(field, {}).get("carried_by"), (
                f"{name}.{field}: class says carried_by={on_class!r}, "
                f"catalogue says {notes.get(field, {}).get('carried_by')!r}")


def test_required_fields_and_the_when_tag_agree():
    """`when: always` in the exported file and a required field on the class are the same
    fact. They are written in different places, so they are checked against each other."""
    from app.models import REGISTRY
    from app.repositories.model_catalogue_repository import EXPORTS
    for name, cls in REGISTRY.items():
        if not hasattr(cls, "model_fields"):
            continue
        for field, spec in (EXPORTS[name]().get("fields") or {}).items():
            info = cls.model_fields.get(field)
            if info is None or not isinstance(spec, dict) or "when" not in spec:
                continue
            assert (spec["when"] == "always") == info.is_required(), (
                f"{name}.{field}: when={spec['when']!r} but "
                f"required={info.is_required()}")


def test_the_generated_types_are_not_stale():
    """The answer lists are generated from the catalogues. A hand edit to either side
    that forgets the other fails here, the same way the exported JSON is guarded."""
    result = subprocess.run(
        [sys.executable, os.path.join("scripts", "generate_model_types.py"), "--check"],
        cwd=BACKEND, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
