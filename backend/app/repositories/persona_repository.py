"""Where the persona library is read from.

The library is the offline-built set of representative, survey-grounded SA persona
identities (see scripts/build_library.py). This module only moves the bytes:

  * locally, the in-repo JSON at app/data/persona_library/personas.json (gitignored)
  * on a host, a file on the persistent volume, seeded from a private Supabase
    Storage bucket — set PERSONA_LIBRARY_PATH=/data/persona_library/personas.json

It is never shipped in git. Nothing here scores, filters or checks a persona: those
are rules, and they live in services/persona_library.py.

Env: PERSONA_LIBRARY_PATH, PERSONA_LIBRARY_BUCKET, PERSONA_LIBRARY_OBJECT
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

from ..utils.logger import get_logger
from . import supabase

logger = get_logger("fub.repo.persona")

#: The in-repo path, used when PERSONA_LIBRARY_PATH is unset.
IMAGE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "persona_library", "personas.json",
)


def library_path() -> str:
    return os.environ.get("PERSONA_LIBRARY_PATH") or IMAGE_PATH


def seed_from_storage(dest_path: str) -> bool:
    """Download the library from Supabase Storage to `dest_path`.

    Lets the persistent volume be seeded without the file ever being in git. A no-op
    (False) unless the storage env vars are set, and a failed download leaves any
    existing file untouched — a stale library still serves rooms, an empty one does not.
    """
    bucket = os.environ.get("PERSONA_LIBRARY_BUCKET", "")
    obj = os.environ.get("PERSONA_LIBRARY_OBJECT", "personas.json")
    if not (supabase.enabled() and bucket):
        return False
    try:
        content = supabase.download(bucket, obj)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as fh:
            fh.write(content)
        logger.info("Seeded persona library from Supabase Storage (%d bytes) -> %s",
                    len(content), dest_path)
        return True
    except Exception as e:  # noqa: BLE001 - a failed seed must not stop the app
        logger.error("Could not seed persona library from storage: %s", e)
        return False


def read(path: str) -> List[Dict]:
    """The personas in a library file, or [] when it is missing or unreadable."""
    if not os.path.exists(path):
        logger.warning(
            "Persona library not found at %s; the library is empty. Seed Supabase "
            "Storage or run scripts/build_library.py to populate it.", path)
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to read persona library: %s", e)
        return []
    return data.get("personas", []) if isinstance(data, dict) else list(data)
