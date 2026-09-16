"""The model catalogue: field types from the classes, survey notes from disk.

Two halves make one reviewable file per stored thing (app/data/model/<name>.json):

    app/models/<module>.py                the class — field names, Python types, methods
    app/data/model/catalogue/<name>.json  the data — allowed answers, and the notes saying
                                          which survey a field came from, which question
                                          codes, who writes it, how it reaches a prompt

The classes read no files (see tests/test_layers.py), so loading the catalogue happens
here. This module is the only place that merges the two, and it is what
scripts/export_data_models.py writes from.

A model with no catalogue exports exactly as its class defines it.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional

from ..models import accounts, caches, panel, persona, reference, simulation, uploads
from ..models.base import export_any

#: Every exported file is laid out the same way, checked across all 48: `version`, then
#: the class's own keys, then the catalogue's prose, then the field table, then trailers.
#: Rebuilding in this order is what keeps a merged file byte-identical to the old one.
CLASS_FIRST = ("version", "kind", "table")
FIELD_KEYS = ("fields", "tables", "values")
TRAILING = ("together", "room_income_provenance", "groups",
            "attitude_row", "circumstance_row", "derived_facts")

#: Keys in a catalogue that describe the catalogue itself, not the model.
NOT_MODEL_KEYS = ("model", "_file_note")

CATALOGUE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "data", "model", "catalogue")

_MODULES = (uploads, accounts, simulation, reference, caches)

#: Model name -> the class-side export (types only, no notes).
_CLASS_FORMS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "persona": persona.export,
    "answer": panel.export_answer,
    "room_seat": panel.export_room_seat,
    **{name: (lambda c=cls: export_any(c))
       for module in _MODULES for name, cls in module.MODELS.items()},
}


def catalogue(name: str) -> Optional[Dict[str, Any]]:
    """The catalogue for a model, or None when it has none."""
    path = os.path.join(CATALOGUE_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _merge_fields(types: Dict[str, Any], notes: Dict[str, Any]) -> Dict[str, Any]:
    """Class field types with catalogue notes laid over them, nesting included.

    A field can hold a whole field table of its own: an object field's `fields`, a list
    field's `items.fields`, or a free-key map's `values.fields`. Those inner fields have
    notes too. Merging only the top level would let a catalogue's inner `fields` dict
    replace the class's inner table outright, which silently empties it; missing the
    `values` case dropped a note from pitch_parts entirely.

    The class carries `carried_by` because its own validation reads it, but the catalogue
    is what the exported order comes from — so the catalogue's copy of a key wins, and
    keeps its position.
    """
    out: Dict[str, Any] = {}
    for field, spec in types.items():
        if not isinstance(spec, dict):
            out[field] = spec
            continue
        note = dict(notes.get(field) or {})
        inner_notes = note.pop("fields", None)
        holder_notes = {h: note.pop(h, None) for h in ("items", "values")}
        merged = {**{k: v for k, v in spec.items() if k not in note}, **note}
        if isinstance(spec.get("fields"), dict):
            merged["fields"] = _merge_fields(spec["fields"], inner_notes or {})
        for holder, sub_notes in holder_notes.items():
            sub = spec.get(holder)
            if isinstance(sub, dict) and isinstance(sub.get("fields"), dict):
                merged[holder] = {**sub,
                                  "fields": _merge_fields(sub["fields"],
                                                          (sub_notes or {}).get("fields") or {})}
        out[field] = merged
    return out


def exported(name: str) -> Dict[str, Any]:
    """One model's full reviewable form: its class types with its catalogue merged in.

    Laid out the way every exported file already is (checked across all 48): `version`
    and the class's own leading keys, then the catalogue's prose, then everything else
    the class defines, in the class's own order. Rebuilding this way is what keeps a
    merged file byte-identical to the one it replaces.
    """
    doc = _CLASS_FORMS[name]()
    side = catalogue(name)
    if not side:
        return doc

    # A SQLite model exports `tables` and a map model exports `values`, neither of
    # which has a field table at all.
    fields = _merge_fields(doc.get("fields") or {}, side.get("fields") or {})

    prose = {k: v for k, v in side.items()
             if k not in NOT_MODEL_KEYS and k not in FIELD_KEYS}

    out: Dict[str, Any] = {}
    for key in CLASS_FIRST:
        if key in doc:
            out[key] = doc[key]
    for key, value in prose.items():
        out.setdefault(key, value)
    for key, value in doc.items():
        if key in out:
            continue
        out[key] = fields if key == "fields" else value
    return out


#: Model name -> function returning its exported JSON form. The shape
#: scripts/export_data_models.py and tests/test_model_classes.py expect.
EXPORTS: Dict[str, Callable[[], Dict[str, Any]]] = {
    name: (lambda n=name: exported(n)) for name in _CLASS_FORMS
}
