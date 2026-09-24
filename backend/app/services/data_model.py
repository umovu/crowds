"""Check what the app stores against its data models.

Models moving to Python classes live in app/models (Pydantic) and are the source of
truth there; their JSON in app/data/model is exported from the classes. Personas,
room seats and panel answers are checked through the classes. Every other stored
thing is still described by its JSON file in app/data/model/ and checked here.

Every check returns a list of plain problem sentences; an empty list means the record
fits. LLM-free and free of app imports, so build scripts can load it by file path and
the sim subprocess never pays for it.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "model")
_cache: Dict[str, Dict[str, Any]] = {}

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "list": list, "object": dict}


def load(name: str) -> Dict[str, Any]:
    """A model by name: load("persona") reads app/data/model/persona.json."""
    name = name[:-5] if name.endswith(".json") else name
    if name not in _cache:
        with open(os.path.join(MODEL_DIR, name + ".json"), encoding="utf-8") as fh:
            _cache[name] = json.load(fh)
    return _cache[name]


def _check_value(label: str, value: Any, spec: Dict[str, Any], problems: List[str]) -> None:
    if value is None:
        if not spec.get("nullable"):
            problems.append(f"{label} is empty but must have a value")
        return
    kind = spec.get("type", "any")
    if kind == "any":
        return
    if kind.startswith("model:"):
        problems.extend(model_problems(kind[len("model:"):], value, label))
        return
    if kind == "answer_row":
        problems.extend(answer_problems(value) if isinstance(value, dict)
                        else [f"{label} should be an answer row"])
        return
    if kind == "round_result":
        problems.extend(_object_problems(label, value, load("answer")["round_result"]["fields"]))
        return
    expected = _TYPES[kind]
    # bool is an int in Python; a True where a number belongs is a real mistake.
    if (isinstance(value, bool) and kind in ("integer", "number")) or not isinstance(value, expected):
        problems.append(f"{label} should be {kind}, got {type(value).__name__}")
        return
    if "allowed" in spec and value not in spec["allowed"]:
        problems.append(f"{label} has an answer not in the model: {value!r}")
    if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
        problems.append(f"{label} does not look right: {value!r}")
    if "min" in spec and value < spec["min"]:
        problems.append(f"{label} is below {spec['min']}: {value!r}")
    if "max" in spec and value > spec["max"]:
        problems.append(f"{label} is above {spec['max']}: {value!r}")
    if kind == "string":
        if len(value) < spec.get("min_length", 0):
            problems.append(f"{label} is too short")
        if "max_length" in spec and len(value) > spec["max_length"]:
            problems.append(f"{label} is longer than {spec['max_length']} characters ({len(value)})")
    if kind == "list":
        if len(value) < spec.get("min_items", 0):
            problems.append(f"{label} needs at least {spec['min_items']} item(s)")
        if "max_items" in spec and len(value) > spec["max_items"]:
            problems.append(f"{label} has more than {spec['max_items']} items ({len(value)})")
        items = spec.get("items")
        if items:
            for i, item in enumerate(value):
                _check_value(f"{label}[{i}]", item, items, problems)
    if kind == "object":
        if "fields" in spec:
            problems.extend(_object_problems(label, value, spec["fields"], spec.get("together", ())))
        if "values" in spec:
            for key, item in value.items():
                _check_value(f"{label}[{key!r}]", item, spec["values"], problems)


def _object_problems(label: str, obj: Any, fields: Dict[str, Any],
                     together: Iterable[List[str]] = ()) -> List[str]:
    if not isinstance(obj, dict):
        return [f"{label} should be an object"]
    problems = [f"{label}: key {k!r} is not in the model" for k in obj if k not in fields]
    for name, spec in fields.items():
        if name not in obj:
            if spec.get("when") == "always":
                problems.append(f"{label}: missing {name!r}")
            continue
        _check_value(f"{label}: {name}", obj[name], spec, problems)
    for group in together:
        present = [k for k in group if k in obj]
        if present and len(present) != len(group):
            missing = [k for k in group if k not in obj]
            problems.append(f"{label}: {missing} must be stored together with {present}")
    return problems


# ── one model file per stored thing ─────────────────────────────────────────

def model_problems(name: str, obj: Any, label: Optional[str] = None) -> List[str]:
    """Everything about one stored object that does not fit its class in app/models
    (REGISTRY[name]; the reviewable form is app/data/model/<name>.json)."""
    m = _classes()
    return m.problems_of(m.REGISTRY[name], obj, label or name)


def _classes():
    """The Python data models (app/models). Imported on first use so this module stays
    loadable by file path, and the sim subprocess only pays for them when it checks."""
    from app import models
    return models


def round_result_problems(result: Any, label: str = "round result") -> List[str]:
    """A batch interview result (panel round or a sim's impact_interviews.json)."""
    m = _classes()
    return m.problems_of(m.RoundResult, result, label)


def action_line_problems(line: Any) -> List[str]:
    """One line of a sim's actions.jsonl: an agent action, or a round/simulation marker."""
    if isinstance(line, dict) and "event_type" in line:
        return model_problems("sim_log_marker", line, f"marker {line.get('event_type')}")
    label = f"action round {line.get('round_num')} agent {line.get('agent_id')}" if isinstance(line, dict) else "action"
    return model_problems("sim_action", line, label)


def sqlite_problems(name: str, db_path: str) -> List[str]:
    """Tables and columns of a saved SQLite file against a "sqlite" model."""
    import sqlite3
    tables = _classes().REGISTRY[name].TABLES
    out: List[str] = []
    con = sqlite3.connect(db_path)
    try:
        found = {t for (t,) in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'")}
        for table in sorted(found - set(tables)):
            out.append(f"{name}: table {table!r} is not in the model")
        for table, columns in tables.items():
            if table not in found:
                out.append(f"{name}: missing table {table!r}")
                continue
            actual = [row[1] for row in con.execute(f"pragma table_info({table})")]
            out += [f"{name}.{table}: column {c!r} is not in the model" for c in actual if c not in columns]
            out += [f"{name}.{table}: missing column {c!r}" for c in columns if c not in actual]
    finally:
        con.close()
    return out


def warn_if_off_model(logger: Any, what: str, name: str, obj: Any, check=None) -> List[str]:
    """Log (never raise) when something about to be saved no longer fits its model.

    `check` replaces the plain model check for things with cross-field rules. A
    user's run is never lost to a model warning; the log says what drifted.
    """
    try:
        problems = check(obj) if check else model_problems(name, obj)
    except Exception as e:  # noqa: BLE001 — the check is a guard, never a gate
        problems = [f"could not check: {e}"]
    if problems:
        logger.warning("%s does not match its data model (%s): %d problem(s). First: %s",
                       what, name, len(problems), "; ".join(problems[:3]))
    return problems


def row_problems(name: str, row: Any, label: Optional[str] = None) -> List[str]:
    """A row, or the part of one, that code sends to a database table (a "table" model).

    Every column must exist and every value must fit. Columns left out are the
    database's business (defaults, triggers), so a partial update is fine.
    """
    m = _classes()
    cls = m.REGISTRY[name]
    return m.partial_problems(cls, row, label or cls.HEADER.get("table", name))


def column_problems(name: str, columns: Iterable[str], label: Optional[str] = None) -> List[str]:
    """Columns code selects or filters on that the table does not have."""
    cls = _classes().REGISTRY[name]
    label = label or cls.HEADER.get("table", name)
    known = {info.alias or field for field, info in cls.model_fields.items()}
    return [f"{label}: column {c!r} does not exist" for c in columns if c not in known]


_DIGIT = re.compile(r"\d")


def mechanism_card_problems(card: Any, file_name: Optional[str] = None) -> List[str]:
    """A research card: the model, plus the rules that span fields.

    Text the prompt shows carries no numbers (cards give reasoning, never figures),
    segment tags name real persona types, and every "who it's for" rule (the card's
    applies_when and each claim's needs) names facts and answers a persona can have.
    """
    label = f"card {card.get('id') if isinstance(card, dict) else None or file_name}"
    out = model_problems("mechanism_card", card, label)
    if not isinstance(card, dict):
        return out
    if file_name and card.get("id") and file_name != f"{card['id']}.json":
        out.append(f"{label}: file should be named {card['id']}.json, not {file_name}")
    archetypes = set(load("persona")["fields"]["actor_archetype"]["allowed"])
    out += [f"{label}: segment tag {t!r} is not a persona type"
            for t in card.get("segment_tags") or [] if t not in archetypes]
    out += rule_problems(label, card.get("applies_when"))
    if card.get("borrowed_from"):
        # Borrowed reasoning only reaches people who closely match the speakers.
        clauses = card.get("applies_when") or []
        if not clauses:
            out.append(f"{label}: a borrowed card needs an applies_when gate")
        out += [f"{label}: borrowed card gate clause {j} names fewer than two facts"
                for j, clause in enumerate(clauses)
                if isinstance(clause, dict) and len(clause) < 2]
    for i, claim in enumerate(card.get("claims") or []):
        if not isinstance(claim, dict):
            continue
        where = f"{label} claims[{i}]"
        words = [claim.get("text"), *(claim.get("objections") or []),
                 *(claim.get("vocabulary") or []), *(claim.get("evaluative_rules") or [])]
        out += [f"{where}: number in claim: {x!r}"
                for x in words if isinstance(x, str) and _DIGIT.search(x)]
        out += rule_problems(where, claim.get("needs"))
    return out


def room_seat_problems(seat: Any, check_persona: bool = True) -> List[str]:
    """One seat in a panel or sim room: the fields the room adds, plus the person.

    A library seat is checked against the persona model (with its library id as id);
    anyone else against the custom agent model. `check_persona=False` checks only the
    room's own fields, for saved rooms built from an older library.
    """
    if not isinstance(seat, dict):
        return ["seat should be an object"]
    m = _classes()
    runtime = m.RoomSeat.model_fields
    label = f"seat {seat.get('id')}"
    own = {k: v for k, v in seat.items() if k in runtime}
    out = m.problems_of(m.RoomSeat, own, label)
    if not check_persona:
        return out
    person = {k: v for k, v in seat.items() if k not in runtime}
    # A grant detected at room build overwrites the persona's own income provenance.
    if seat.get("income_provenance") in m.RoomSeat.HEADER.get("room_income_provenance", []):
        person.pop("income_provenance", None)
    if seat.get("source_entity_type") == "library_persona":
        person["id"] = seat.get("library_id")
        out += persona_problems(person)
    else:
        person["id"] = seat.get("id")
        out += model_problems("custom_agent", person, label)
    return out


# ── personas ────────────────────────────────────────────────────────────────

def persona_problems(persona: Dict[str, Any]) -> List[str]:
    """Everything about one library persona that does not fit app.models.LibraryPersona."""
    m = _classes()
    who = str(persona.get("name") or persona.get("id") or "persona") if isinstance(persona, dict) else "persona"
    return m.problems_of(m.LibraryPersona, persona, who)


def library_problems(personas: Iterable[Dict[str, Any]]) -> List[str]:
    problems: List[str] = []
    ids: Dict[Any, int] = {}
    for persona in personas:
        problems += persona_problems(persona)
        ids[persona.get("id")] = ids.get(persona.get("id"), 0) + 1
    problems += [f"id {i!r} is used by {n} personas" for i, n in ids.items() if n > 1]
    return problems


def retired_fields(persona: Dict[str, Any]) -> List[str]:
    fields = load("persona")["fields"]
    return [k for k in persona if fields.get(k, {}).get("layer") == "retired"]


# ── rules that name persona facts (card applies_when, objection grounds) ────

def fact_answers(field: str) -> Optional[List[str]]:
    """The answers a rule may name for a fact, as the strings rules compare against.

    None when the model has no such fact. An empty list when the fact is open-ended
    (a count, say), so only the field name can be checked.
    """
    schema = load("persona")
    if field in schema["attitude_row"]["topics"]:
        return list(schema["attitude_row"]["topics"][field]["stances"])
    if field in schema["circumstance_row"]["fields"]:
        return list(schema["circumstance_row"]["fields"][field]["values"])
    if field in schema["derived_facts"]:
        return list(schema["derived_facts"][field]["values"])
    spec = schema["fields"].get(field)
    if spec is None or spec["type"] in ("attitude_rows", "circumstance_rows"):
        return None
    if spec["type"] == "boolean":
        return ["True", "False"]
    return [str(v) for v in spec.get("allowed", [])]


def rule_problems(where: str, clauses: Iterable[Dict[str, List[Any]]]) -> List[str]:
    """A rule clause that names a fact or answer no persona can have matches nobody, silently."""
    problems: List[str] = []
    for clause in clauses or []:
        for field, allowed in clause.items():
            answers = fact_answers(field)
            if answers is None:
                problems.append(f"{where}: names {field!r}, which no persona carries")
                continue
            if answers:
                problems += [f"{where}: {field} = {value!r} is not an answer any persona can have"
                             for value in allowed if str(value) not in answers]
    return problems


# ── panel answers ───────────────────────────────────────────────────────────

def answer_problems(row: Dict[str, Any]) -> List[str]:
    """Everything about one answer row that does not fit app.models.AnswerRow."""
    m = _classes()
    who = f"agent {row.get('agent_id')}" if isinstance(row, dict) else "answer"
    return m.problems_of(m.AnswerRow, row, who)


def round_problems(round_data: Dict[str, Any]) -> List[str]:
    """A saved round file: the envelope, the result, and every answer row in it."""
    m = _classes()
    label = f"round {round_data.get('round')}" if isinstance(round_data, dict) else "round"
    return m.problems_of(m.RoundFile, round_data, label)
