"""Simulation files on disk: state, config, profiles.

Everything a simulation persists lives in one directory per run, under
DATA_ROOT/uploads/simulations/<simulation_id>/:

    state.json                   what the run is doing now
    simulation_config.json       the generated config the subprocess reads
    agentsociety_profiles.json   the cast

Reads answer with `None` (or []) when a file is absent, rather than raising: a
half-prepared run is a normal state, not an error. What those absences *mean* —
"ready", "running", "not prepared yet" — is the simulation service's call, not this
module's.

The directory is the same one Config.OASIS_SIMULATION_DATA_DIR names, so saved runs
land on the mounted volume in production instead of the container filesystem, which
is wiped on every redeploy.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.repo.simulation")

SIMULATION_DATA_DIR = Config.OASIS_SIMULATION_DATA_DIR

STATE_FILE = "state.json"
CONFIG_FILE = "simulation_config.json"
PROFILES_FILE = "agentsociety_profiles.json"


#: Every function takes `root` so the caller decides where runs live — the manager
#: passes its own SIMULATION_DATA_DIR, which tests redirect at a temp directory. A
#: module-level snapshot would quietly ignore that and write to the real data dir.
def _root(root: Optional[str] = None) -> str:
    return root or SIMULATION_DATA_DIR


def sim_dir(simulation_id: str, root: Optional[str] = None) -> str:
    """The run's directory, created if it is not there yet.

    Only call this when about to WRITE. Reads must not bring a directory into
    existence, or an id that was never saved starts showing up in list_ids().
    """
    path = os.path.join(_root(root), simulation_id)
    os.makedirs(path, exist_ok=True)
    return path


def _read_json(simulation_id: str, filename: str, root: Optional[str] = None) -> Optional[Any]:
    path = os.path.join(_root(root), simulation_id, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read %s for %s: %s", filename, simulation_id, e)
        return None


def read_state(simulation_id: str, root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The stored state for a run, or None when it has never been saved."""
    data = _read_json(simulation_id, STATE_FILE, root)
    return data if isinstance(data, dict) else None


def write_state(simulation_id: str, data: Dict[str, Any], root: Optional[str] = None) -> None:
    """Save a run's state. Raises: losing this silently would strand the run."""
    path = os.path.join(sim_dir(simulation_id, root), STATE_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def read_config(simulation_id: str, root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The generated config, or None when the run has not been prepared."""
    data = _read_json(simulation_id, CONFIG_FILE, root)
    return data if isinstance(data, dict) else None


def read_profiles(simulation_id: str, root: Optional[str] = None) -> List[Dict[str, Any]]:
    """The run's cast, or [] when it has not been written yet."""
    data = _read_json(simulation_id, PROFILES_FILE, root)
    return data if isinstance(data, list) else []


def list_ids(root: Optional[str] = None) -> List[str]:
    """Every saved run id. Hidden entries and stray files are skipped."""
    base = _root(root)
    if not os.path.exists(base):
        return []
    out = []
    for name in os.listdir(base):
        if name.startswith("."):
            continue
        if not os.path.isdir(os.path.join(base, name)):
            continue
        out.append(name)
    return out


# ── reads that also report on the file itself ───────────────────────────────────
ENRICHMENT_FILE = "enrichment.json"
#: The subprocess appends one JSON object per agent action here, as it runs.
ACTIONS_FILE = os.path.join("opinion_space", "actions.jsonl")


def path(simulation_id: str, *parts: str, root: Optional[str] = None) -> str:
    """A path inside the run's directory, WITHOUT creating anything.

    The read-side counterpart to `sim_dir`. Use this whenever the answer is allowed to
    be "there is nothing there" — `sim_dir` would bring the directory into existence
    and the id would then show up in `list_ids()`.
    """
    return os.path.join(_root(root), simulation_id, *parts)


def exists(simulation_id: str, root: Optional[str] = None) -> bool:
    """Whether this run has a directory at all."""
    return os.path.isdir(path(simulation_id, root=root))


@dataclass(frozen=True)
class Snapshot:
    """A file's content plus what the UI needs to know about the file itself.

    The live progress screens poll while a run is still being prepared, so "the file
    is not there yet" and "the file is there but unreadable" are both normal, and both
    answer with `data is None`. `modified_at` lets the screen show staleness.
    """
    data: Optional[Any] = None
    present: bool = False
    modified_at: Optional[str] = None


def snapshot(simulation_id: str, filename: str, root: Optional[str] = None) -> Snapshot:
    """Read one of the run's JSON files and stat it, in one pass."""
    target = path(simulation_id, filename, root=root)
    if not os.path.exists(target):
        return Snapshot()
    modified_at = None
    try:
        modified_at = datetime.fromtimestamp(os.stat(target).st_mtime).isoformat()
    except OSError:  # noqa: BLE001 - a stat failure must not hide the content
        pass
    try:
        with open(target, "r", encoding="utf-8") as fh:
            return Snapshot(data=json.load(fh), present=True, modified_at=modified_at)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read %s for %s: %s", filename, simulation_id, e)
        return Snapshot(present=True, modified_at=modified_at)


def read_enrichment(simulation_id: str, root: Optional[str] = None) -> Dict[str, Any]:
    """Deep-research findings per archetype, or {} when the run has none."""
    data = _read_json(simulation_id, ENRICHMENT_FILE, root)
    return data if isinstance(data, dict) else {}


def action_totals(simulation_id: str, root: Optional[str] = None) -> Dict[str, float]:
    """Sum the tokens and cost the subprocess recorded for each action.

    Pure accumulation of stored numbers: what they cost in rand, and which prices were
    used, is a rule and belongs in a service. A malformed line is skipped rather than
    failing the total, because this file is appended to by a live run and the last line
    can be half-written.
    """
    target = path(simulation_id, ACTIONS_FILE, root=root)
    totals = {"prompt_tokens": 0.0, "completion_tokens": 0.0, "cost_usd": 0.0}
    if not os.path.exists(target):
        return totals
    try:
        with open(target, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    action = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                totals["prompt_tokens"] += action.get("prompt_tokens", 0) or 0
                totals["completion_tokens"] += action.get("completion_tokens", 0) or 0
                totals["cost_usd"] += action.get("estimated_cost_usd", 0) or 0
    except OSError as e:
        logger.warning("Could not read actions for %s: %s", simulation_id, e)
    return totals
