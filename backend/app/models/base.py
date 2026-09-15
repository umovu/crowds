"""Shared machinery for the app's data models (Pydantic classes).

Each stored thing has a class in this package, and the class is the source of truth:
field types say what is allowed, and `json_schema_extra` carries what a type cannot
(where a field came from, who writes and reads it, prompt wording). The files in
app/data/model/*.json are exported from these classes (scripts/export_data_models.py)
so a person can review a model without reading code, and the LLM-free loaders can
read it; a test fails when an exported file is stale.

Checking comes in two strengths:
  problems_of(cls, data)  every problem as a plain sentence; never raises
  check(cls, data, what)  at the door where data is created: raises DataModelError
                          when DATA_MODEL_STRICT is on (tests, local dev), logs a
                          warning otherwise, so a live run is never lost to old data
"""

from __future__ import annotations

import os
import types
import typing
from typing import Any, ClassVar, Dict, Iterable, List, Literal, Optional, Type

from pydantic import BaseModel, ConfigDict, RootModel, ValidationError, ValidationInfo, model_validator
from pydantic.fields import FieldInfo

NoneType = type(None)


class DataModelError(ValueError):
    """Raised by `check` in strict mode. `problems` holds every sentence."""

    def __init__(self, what: str, problems: List[str]):
        super().__init__(f"{what} does not match its data model: " + "; ".join(problems[:5]))
        self.problems = problems


class DataModel(BaseModel):
    """Base for every stored thing: unknown keys fail, and no silent type coercion
    ("5" is not 5, 1 is not True)."""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    #: File name in app/data/model when exported on its own ("" = only inside another model).
    MODEL_NAME: ClassVar[str] = ""
    #: Type name written in exported JSON when this class is used inside another model.
    EXPORT_TYPE: ClassVar[str] = ""
    #: Top-level keys of the exported file other than fields/together (about, stored_in, rules...).
    HEADER: ClassVar[Dict[str, Any]] = {}
    #: Groups of keys stored together or not at all.
    TOGETHER: ClassVar[List[List[str]]] = []

    @classmethod
    def cross_field_problems(cls, data: Dict[str, Any], label: str) -> List[str]:
        """Rules that span fields, run on the raw dict. Subclasses extend this."""
        return together_problems(label, data, cls.TOGETHER)

    @model_validator(mode="after")
    def _cross_fields(self, info: ValidationInfo):
        if info.context and info.context.get("fields_only"):
            return self
        cls = type(self)
        problems = cls.cross_field_problems(self.model_dump(by_alias=True, exclude_unset=True), cls.__name__)
        if problems:
            raise ValueError("; ".join(problems))
        return self


class SqliteModel:
    """A SQLite file: its tables and their columns. Not Pydantic — rows are written by
    SQL, so the model is the table layout a saved file must have."""

    MODEL_NAME: ClassVar[str] = ""
    HEADER: ClassVar[Dict[str, Any]] = {}
    TABLES: ClassVar[Dict[str, List[str]]] = {}


def is_map_model(cls: Any) -> bool:
    """A map with free keys (an archetype, a user id) and one shape of value."""
    return isinstance(cls, type) and issubclass(cls, RootModel)


# ── checking ─────────────────────────────────────────────────────────────────

def together_problems(label: str, data: Dict[str, Any], groups: Iterable[List[str]]) -> List[str]:
    out = []
    for group in groups or ():
        present = [k for k in group if k in data]
        if present and len(present) != len(group):
            missing = [k for k in group if k not in data]
            out.append(f"{label}: {missing} must be stored together with {present}")
    return out


_TYPE_WORDS = {
    "string_type": "string", "int_type": "integer", "float_type": "number",
    "bool_type": "boolean", "list_type": "list", "dict_type": "object",
    "model_type": "object", "model_attributes_type": "object",
}


def sentence(label: str, err: Dict[str, Any]) -> str:
    """One Pydantic error as a plain sentence, in the wording the checks always used."""
    loc = list(err.get("loc", ()))
    kind = err.get("type", "")
    ctx = err.get("ctx") or {}
    value = err.get("input")
    path = ".".join(str(p) for p in loc)
    where = f"{label}: {path}" if path else label
    parent = ".".join(str(p) for p in loc[:-1])
    parent = f"{parent}: " if parent else ""
    if kind == "extra_forbidden":
        return f"{label}: {parent}key {loc[-1]!r} is not in the model"
    if kind == "missing":
        return f"{label}: {parent}missing {loc[-1]!r}"
    if kind == "literal_error":
        return f"{where} has an answer not in the model: {value!r}"
    if kind == "string_pattern_mismatch":
        return f"{where} does not look right: {value!r}"
    if kind in ("greater_than_equal", "greater_than"):
        return f"{where} is below {ctx.get('ge', ctx.get('gt'))}: {value!r}"
    if kind in ("less_than_equal", "less_than"):
        return f"{where} is above {ctx.get('le', ctx.get('lt'))}: {value!r}"
    if kind == "string_too_short":
        return f"{where} is too short"
    if kind == "string_too_long":
        size = len(value) if isinstance(value, str) else "?"
        return f"{where} is longer than {ctx.get('max_length')} characters ({size})"
    if kind == "too_short":
        return f"{where} needs at least {ctx.get('min_length')} item(s)"
    if kind == "too_long":
        return f"{where} has more than {ctx.get('max_length')} items ({ctx.get('actual_length')})"
    if kind == "value_error":
        return f"{where}: {str(err.get('msg', '')).removeprefix('Value error, ')}"
    if kind in _TYPE_WORDS:
        return f"{where} should be {_TYPE_WORDS[kind]}, got {type(value).__name__}"
    return f"{where}: {err.get('msg')}"


def problems_of(cls: Type[DataModel], data: Any, label: Optional[str] = None) -> List[str]:
    """Everything about `data` that does not fit `cls`, as sentences. Never raises."""
    label = label or cls.__name__
    if not isinstance(data, dict):
        return [f"{label} should be an object"]
    out: List[str] = []
    try:
        cls.model_validate(data, context={"fields_only": True})
    except ValidationError as e:
        out += [sentence(label, _unroot(err)) for err in e.errors()]
    cross = getattr(cls, "cross_field_problems", None)
    if cross is not None:
        try:
            out += cross(data, label)
        except Exception as e:  # noqa: BLE001 — malformed input must still produce a report
            out.append(f"{label}: could not check rules across fields: {e}")
    return out


def _unroot(err: Dict[str, Any]) -> Dict[str, Any]:
    """A map model reports its keys under a leading 'root'; drop it."""
    loc = tuple(err.get("loc", ()))
    if loc[:1] == ("root",):
        err = {**err, "loc": loc[1:]}
    return err


def partial_problems(cls: Type[DataModel], row: Any, label: str) -> List[str]:
    """Part of a record (a database update): what is there must fit; what is left out
    is not reported."""
    if not isinstance(row, dict):
        return [f"{label}: row should be an object"]
    try:
        cls.model_validate(row, context={"fields_only": True})
    except ValidationError as e:
        return [sentence(label, err) for err in e.errors() if err.get("type") != "missing"]
    return []


def strict_mode() -> bool:
    return os.environ.get("DATA_MODEL_STRICT", "").strip().lower() in ("1", "true", "yes", "on")


def check(cls: Type[DataModel], data: Any, what: str, logger: Any = None,
          problems: Optional[List[str]] = None) -> List[str]:
    """Check data where it is created. Strict mode raises; otherwise logs and returns."""
    problems = problems_of(cls, data, what) if problems is None else problems
    if problems:
        if strict_mode():
            raise DataModelError(what, problems)
        if logger is not None:
            logger.warning("%s does not match its data model (%s): %d problem(s). First: %s",
                           what, cls.MODEL_NAME or cls.__name__, len(problems), "; ".join(problems[:3]))
    return problems


# ── export to the reviewable JSON form ──────────────────────────────────────

def export_model(cls: Type[DataModel]) -> Dict[str, Any]:
    out = dict(cls.HEADER)
    out["fields"] = export_fields(cls)
    if cls.TOGETHER:
        out["together"] = [list(g) for g in cls.TOGETHER]
    return out


def export_any(cls: Any) -> Dict[str, Any]:
    """The reviewable JSON form of any model class in this package."""
    if isinstance(cls, type) and issubclass(cls, SqliteModel):
        return {**cls.HEADER, "tables": {t: list(c) for t, c in cls.TABLES.items()}}
    if is_map_model(cls):
        return {**cls.HEADER, "values": type_spec(cls.model_fields["root"].annotation)["values"]}
    return export_model(cls)


def export_fields(cls: Type[DataModel]) -> Dict[str, Any]:
    return {info.alias or name: field_spec(info) for name, info in cls.model_fields.items()}


def field_spec(info: FieldInfo) -> Dict[str, Any]:
    extra = dict(info.json_schema_extra or {})
    spec = type_spec(info.annotation, info.metadata)
    if "type" in extra:
        # A type name the annotation cannot carry (attitude_rows, model:name...).
        spec = {"type": extra.pop("type"), **({"nullable": True} if spec.get("nullable") else {})}
    spec.update(extra)
    return spec


def _constraints(metadata: Iterable[Any]) -> List[Any]:
    out = []
    for m in metadata or ():
        if isinstance(m, FieldInfo):
            out += _constraints(m.metadata)
        else:
            out.append(m)
    return out


def type_spec(annotation: Any, metadata: Iterable[Any] = ()) -> Dict[str, Any]:
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return type_spec(args[0], list(metadata or ()) + list(args[1:]))
    if origin in (typing.Union, types.UnionType):
        real = [a for a in args if a is not NoneType]
        spec = type_spec(real[0], metadata)
        if len(real) < len(args):
            spec["nullable"] = True
        return spec

    if origin is Literal:
        values = list(args)
        kind = {bool: "boolean", str: "string", int: "integer", float: "number"}[type(values[0])]
        spec: Dict[str, Any] = {"type": kind, "allowed": values}
    elif annotation is Any:
        spec = {"type": "any"}
    elif annotation is bool:
        spec = {"type": "boolean"}
    elif annotation is str:
        spec = {"type": "string"}
    elif annotation is int:
        spec = {"type": "integer"}
    elif annotation is float:
        spec = {"type": "number"}
    elif annotation is list or origin is list:
        spec = {"type": "list"}
        if args and args[0] is not Any:
            spec["items"] = type_spec(args[0])
    elif annotation is dict or origin is dict:
        spec = {"type": "object"}
        if args and args[1] is not Any:
            spec["values"] = type_spec(args[1])
    elif isinstance(annotation, type) and issubclass(annotation, DataModel):
        if annotation.EXPORT_TYPE:
            spec = {"type": annotation.EXPORT_TYPE}
        elif annotation.MODEL_NAME:
            spec = {"type": f"model:{annotation.MODEL_NAME}"}
        else:
            spec = {"type": "object", "fields": export_fields(annotation)}
            if annotation.TOGETHER:
                spec["together"] = [list(g) for g in annotation.TOGETHER]
    else:
        raise TypeError(f"no export rule for annotation {annotation!r}")

    kind = spec["type"]
    for m in _constraints(metadata):
        if getattr(m, "ge", None) is not None:
            spec["min"] = m.ge
        if getattr(m, "le", None) is not None:
            spec["max"] = m.le
        if getattr(m, "pattern", None) is not None:
            spec["pattern"] = m.pattern
        if getattr(m, "min_length", None) is not None:
            spec["min_length" if kind == "string" else "min_items"] = m.min_length
        if getattr(m, "max_length", None) is not None:
            spec["max_length" if kind == "string" else "max_items"] = m.max_length
    return spec
