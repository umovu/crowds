"""Finding saved reports on disk.

A report is a directory under DATA_ROOT/uploads/reports/<report_id>/ with a meta.json
naming the simulation it was written for. This module answers "which report belongs to
this run", which is the only report lookup the simulation screens need.

Report *content* — assembling sections, cleaning drift, rewriting heading levels — is
`report_agent.ReportManager`'s job and stays there. This is storage only.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.repo.report")

META_FILE = "meta.json"


def reports_dir() -> str:
    """The directory holding every saved report. Not created here: this module reads."""
    return os.path.join(Config.UPLOAD_FOLDER, "reports")


def _meta(report_folder: str) -> Optional[Dict]:
    """One report's meta.json, or None when it is missing or unreadable."""
    path = os.path.join(reports_dir(), report_folder, META_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def for_simulation(simulation_id: str) -> List[Dict]:
    """Every report written for this run, newest first.

    Newest is decided by the stored `created_at` string, which sorts correctly because
    it is ISO-8601. An unreadable report is skipped rather than failing the lookup: a
    half-written report must not hide the good ones.
    """
    base = reports_dir()
    if not os.path.exists(base):
        return []

    found = []
    try:
        for folder in os.listdir(base):
            if not os.path.isdir(os.path.join(base, folder)):
                continue
            meta = _meta(folder)
            if meta and meta.get("simulation_id") == simulation_id:
                found.append({
                    "report_id": meta.get("report_id"),
                    "created_at": meta.get("created_at", ""),
                    "status": meta.get("status", ""),
                })
    except OSError as e:
        logger.warning("Failed to scan reports for simulation %s: %s", simulation_id, e)
        return []

    found.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return found


def latest_id_for_simulation(simulation_id: str) -> Optional[str]:
    """The newest report id for this run, or None when it has never been reported on."""
    found = for_simulation(simulation_id)
    return found[0].get("report_id") if found else None
