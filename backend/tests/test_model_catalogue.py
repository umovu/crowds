"""The model catalogue: class types and survey notes stay in step. LLM-off.

A stored thing is described in two halves — the types in app/models/<module>.py, the
survey notes in app/data/model/notes/<name>.json. These tests keep the halves honest:
a notes file must describe a real model, and the one key that exists in both places
(`carried_by`, which the class's own validation reads) must say the same thing in each.
"""

import glob
import json
import os

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
NOTES_DIR = os.path.join(BACKEND, "app", "data", "model", "notes")


def _notes_files():
    return sorted(glob.glob(os.path.join(NOTES_DIR, "*.json")))


def test_every_notes_file_describes_a_real_model():
    from app.repositories.model_catalogue_repository import EXPORTS
    for path in _notes_files():
        name = os.path.basename(path)[:-5]
        assert name in EXPORTS, f"{name}.json has notes but no model class"


def test_notes_only_describe_fields_the_class_has():
    from app.repositories.model_catalogue_repository import EXPORTS, notes
    for path in _notes_files():
        name = os.path.basename(path)[:-5]
        fields = set(EXPORTS[name]().get("fields") or {})
        described = set((notes(name).get("fields") or {}))
        assert described <= fields, f"{name}.json notes unknown field(s): {sorted(described - fields)}"


def test_carried_by_agrees_between_the_class_and_its_notes():
    """The class keeps `carried_by` because LibraryPersona validates against it, and the
    notes file keeps it because that is what the exported file is ordered by. Two copies
    of one fact drift unless something checks them."""
    from app.models import REGISTRY
    from app.repositories.model_catalogue_repository import notes
    for path in _notes_files():
        name = os.path.basename(path)[:-5]
        cls = REGISTRY.get(name)
        if cls is None or not hasattr(cls, "model_fields"):
            continue
        field_notes = notes(name).get("fields") or {}
        for field, info in cls.model_fields.items():
            on_class = (info.json_schema_extra or {}).get("carried_by")
            if on_class is None:
                continue
            in_notes = field_notes.get(field, {}).get("carried_by")
            assert on_class == in_notes, (
                f"{name}.{field}: class says carried_by={on_class!r}, "
                f"notes say {in_notes!r}")


def test_the_notes_are_prose_not_rules():
    """Anything the app *enforces* belongs with the types in the class. The notes file
    carries provenance and prompt wording only, so a missing notes file can never
    silently loosen validation."""
    allowed = {"layer", "carried_by", "source", "note", "known_issue", "free_text",
               "prompt", "optional", "replaced_by"}
    for path in _notes_files():
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for field, spec in (doc.get("fields") or {}).items():
            unknown = set(spec) - allowed
            assert not unknown, f"{os.path.basename(path)}:{field} has {sorted(unknown)}"
