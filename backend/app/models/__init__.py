"""The app's data models as Python classes (Pydantic).

The classes here are the source of truth for everything the app stores. The JSON
files in app/data/model are exported from them by scripts/export_data_models.py, for
review and for loaders that must stay light; tests fail when one is stale.

    persona      library personas and their measured rows
    panel        answers, rounds, room seats
    uploads      panel sessions, custom agents, projects, research cards, reports, posters, papers
    accounts     Supabase tables: subscriptions, profiles, waitlist, access, operator context, run events
    simulation   sim state, config, run state, IPC files, action log, databases, reports
    reference    grants, world facts, event rules, B2B frames, word lists
    caches       SA context cache, judge log, legacy persona cache, API payloads

`project` and `task` are the older dataclass models. Their `*Manager` classes still
carry their own storage code; those move to app/repositories/ in a later pass.
"""

from . import accounts, caches, panel, persona, reference, simulation, uploads
from .base import (DataModel, DataModelError, SqliteModel, check, export_any, is_map_model,
                   partial_problems, problems_of, strict_mode)
from .panel import AnswerRow, RoomSeat, RoundFile, RoundResult
from .persona import AttitudeRow, CircumstanceRow, LibraryPersona

_MODULES = (uploads, accounts, simulation, reference, caches)

#: Model name (app/data/model/<name>.json) -> class. `answer` is three classes in one
#: file (AnswerRow, RoundResult, RoundFile) and is checked through them directly.
REGISTRY = {
    "persona": LibraryPersona,
    "room_seat": RoomSeat,
    **{name: cls for module in _MODULES for name, cls in module.MODELS.items()},
}

#: Model name -> function returning its exported JSON form.
EXPORTS = {
    "persona": persona.export,
    "answer": panel.export_answer,
    "room_seat": panel.export_room_seat,
    **{name: (lambda c=cls: export_any(c)) for module in _MODULES for name, cls in module.MODELS.items()},
}

__all__ = [
    "DataModel", "DataModelError", "SqliteModel", "check", "export_any", "is_map_model",
    "partial_problems", "problems_of", "strict_mode", "REGISTRY", "EXPORTS",
    "AnswerRow", "RoomSeat", "RoundFile", "RoundResult",
    "AttitudeRow", "CircumstanceRow", "LibraryPersona",
]
