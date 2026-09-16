"""The model catalogue: field types from the classes, survey notes from disk.

Two halves make one reviewable file per stored thing (app/data/model/<name>.json):

    app/models/<module>.py          the types — what a field is, and its allowed answers
    app/data/model/notes/<name>.json  the notes — which survey it came from, which question
                                      codes, who wrote it, how it reaches a prompt

The classes stay data-only (see tests/test_layers.py), so reading the notes happens
here. This module is the only place that merges the two, and it is what
scripts/export_data_models.py writes from.

A model with no notes file exports exactly as its class defines it.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional

from ..models import accounts, caches, panel, persona, reference, simulation, uploads
from ..models.base import export_any

#: Top-level keys in the order the exported file has always carried them. Some live on
#: the class (version, groups), some in the notes file (about, rules, sources, layers).
HEADER_ORDER = ("version", "about", "rules", "sources", "layers", "groups")

NOTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "data", "model", "notes")

_MODULES = (uploads, accounts, simulation, reference, caches)

#: Model name -> the class-side export (types only, no notes).
_CLASS_FORMS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "persona": persona.export,
    "answer": panel.export_answer,
    "room_seat": panel.export_room_seat,
    **{name: (lambda c=cls: export_any(c))
       for module in _MODULES for name, cls in module.MODELS.items()},
}


def notes(name: str) -> Optional[Dict[str, Any]]:
    """The notes file for a model, or None when it has none."""
    path = os.path.join(NOTES_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def exported(name: str) -> Dict[str, Any]:
    """One model's full reviewable form: its class types with its notes merged in."""
    doc = _CLASS_FORMS[name]()
    side = notes(name)
    if not side:
        return doc

    field_notes = side.get("fields") or {}
    # The class carries `carried_by` because its own validation reads it, but the notes
    # file is what the exported order comes from — so take the notes' copy, not the
    # class's, or every field's keys would come out in a different order than before.
    fields = {f: {**{k: v for k, v in spec.items() if k not in field_notes.get(f, {})},
                  **field_notes.get(f, {})}
              for f, spec in doc["fields"].items()}

    out: Dict[str, Any] = {}
    for key in HEADER_ORDER:
        if key in side:
            out[key] = side[key]
        elif key in doc:
            out[key] = doc[key]
    out["fields"] = fields
    for key, value in doc.items():
        if key != "fields" and key not in out:
            out[key] = value
    return out


#: Model name -> function returning its exported JSON form. The shape
#: scripts/export_data_models.py and tests/test_model_classes.py expect.
EXPORTS: Dict[str, Callable[[], Dict[str, Any]]] = {
    name: (lambda n=name: exported(n)) for name in _CLASS_FORMS
}
