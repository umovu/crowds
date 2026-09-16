"""Projects on disk: metadata, uploaded files, extracted text.

One directory per project, under Config.UPLOAD_FOLDER/projects/<project_id>/:

    project.json        the Project model, as saved
    files/              the documents the user uploaded
    extracted_text.txt  the text pulled out of those documents

Project state is kept server-side so the frontend never has to carry large data
between requests.

Reads answer with None (or []) when something is absent — a project part-way through
setup is a normal state, not an error. `Project`, `ProjectStatus` and the drift check
stay in app/models/project.py: this module only moves bytes.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..config import Config
from ..models.project import Project, ProjectStatus, warn_if_off_model
from ..utils.logger import get_logger

logger = get_logger("fub.repo.project")

PROJECTS_DIR = os.path.join(Config.UPLOAD_FOLDER, "projects")

META_FILE = "project.json"
FILES_DIR = "files"
TEXT_FILE = "extracted_text.txt"


def set_root(path: str) -> None:
    """Point every function at a different projects directory.

    Tests redirect this at a temp folder. A module-level snapshot with no way to
    change it would silently keep writing to the real uploads directory — which is
    exactly how the simulation repository first went wrong.
    """
    global PROJECTS_DIR
    PROJECTS_DIR = path


# ── where things live ───────────────────────────────────────────────────────
def _ensure_root() -> None:
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def project_dir(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, project_id)


def _meta_path(project_id: str) -> str:
    return os.path.join(project_dir(project_id), META_FILE)


def files_dir(project_id: str) -> str:
    return os.path.join(project_dir(project_id), FILES_DIR)


def _text_path(project_id: str) -> str:
    return os.path.join(project_dir(project_id), TEXT_FILE)


# ── the project itself ──────────────────────────────────────────────────────
def create(name: str = "Unnamed Project") -> Project:
    """Make a new project, with its directories, and save it."""
    _ensure_root()
    project_id = f"proj_{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()
    project = Project(project_id=project_id, name=name, status=ProjectStatus.CREATED,
                      created_at=now, updated_at=now)
    os.makedirs(project_dir(project_id), exist_ok=True)
    os.makedirs(files_dir(project_id), exist_ok=True)
    save(project)
    return project


def save(project: Project) -> None:
    """Write a project's metadata. Raises: losing this strands the user's work."""
    project.updated_at = datetime.now().isoformat()
    data = project.to_dict()
    warn_if_off_model(data)
    os.makedirs(project_dir(project.project_id), exist_ok=True)
    with open(_meta_path(project.project_id), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def get(project_id: str) -> Optional[Project]:
    """One project, or None when there is no such project."""
    path = _meta_path(project_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read project %s: %s", project_id, e)
        return None
    return Project.from_dict(data)


def list_projects(limit: int = 50) -> List[Project]:
    """Every project, newest first."""
    _ensure_root()
    projects = [p for p in (get(pid) for pid in os.listdir(PROJECTS_DIR)) if p]
    projects.sort(key=lambda p: p.created_at, reverse=True)
    return projects[:limit]


def delete(project_id: str) -> bool:
    """Remove a project and everything under it. False when it was not there."""
    path = project_dir(project_id)
    if not os.path.exists(path):
        return False
    shutil.rmtree(path)
    return True


# ── uploaded files and extracted text ───────────────────────────────────────
def save_upload(project_id: str, write: Callable[[str], None],
                original_filename: str) -> Dict[str, Any]:
    """Store one uploaded document and describe what was stored.

    `write` is handed the destination path and does the writing — that keeps the web
    framework's upload object in the controller, so this module stays free of it.
    """
    target_dir = files_dir(project_id)
    os.makedirs(target_dir, exist_ok=True)
    ext = os.path.splitext(original_filename)[1].lower()
    saved_filename = f"{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(target_dir, saved_filename)
    write(path)
    return {
        "original_filename": original_filename,
        "saved_filename": saved_filename,
        "path": path,
        "size": os.path.getsize(path),
    }


def save_extracted_text(project_id: str, text: str) -> None:
    os.makedirs(project_dir(project_id), exist_ok=True)
    with open(_text_path(project_id), "w", encoding="utf-8") as fh:
        fh.write(text)


def get_extracted_text(project_id: str) -> Optional[str]:
    path = _text_path(project_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def uploaded_files(project_id: str) -> List[str]:
    """Paths of the documents uploaded to a project."""
    target_dir = files_dir(project_id)
    if not os.path.exists(target_dir):
        return []
    return [os.path.join(target_dir, name) for name in os.listdir(target_dir)
            if os.path.isfile(os.path.join(target_dir, name))]
