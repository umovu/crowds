"""
PersonaCache — on-disk cache for generated agent personas.

Caches the output of `AgentProfileGenerator._generate_profile_with_llm` keyed
by a deterministic hash of (model, entity inputs, enrichment context). Re-runs
on the same project / topic / entity reuse the cached persona, skipping the
expensive Plus-model LLM call (~5-10k tokens per agent).

The cache is a directory of JSON files (no extra deps, survives restarts).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("fub.persona_cache")

# One shared cache dir for the whole backend
_CACHE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "uploads", "persona_cache"
)


def _ensure_dir() -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return _CACHE_DIR


def _normalize(obj: Any) -> Any:
    """Make dicts deterministically hashable by sorting keys recursively."""
    if isinstance(obj, dict):
        return {k: _normalize(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    return obj


def make_key(
    *,
    model_name: str,
    entity_name: str,
    entity_type: str,
    entity_summary: str,
    entity_attributes: Optional[Dict[str, Any]],
    context: str,
    enrichment_snippet: str = "",
) -> str:
    """Build a stable cache key for one persona generation call.

    Two-level scheme:
      * **Exact** key (same project, same entity) → already preferred above.
      * **Archetype** key (any project on the same topic / archetype combo) →
        used as a fallback so different projects with similar archetypes can
        share personas. Caller checks exact first, then archetype.

    This function returns the **exact** key. Use ``make_archetype_key`` for
    the broader cross-project fallback.
    """
    payload = {
        "v": 3,                                 # bump if prompt template changes
        "kind": "exact",
        "model": (model_name or "").strip(),
        "name": (entity_name or "").strip(),
        "type": (entity_type or "").strip(),
        "summary": (entity_summary or "").strip(),
        "attrs": _normalize(entity_attributes or {}),
        "context": (context or "").strip(),
        "enrich": (enrichment_snippet or "").strip(),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_archetype_key(
    *,
    model_name: str,
    entity_type: str,
    enrichment_snippet: str = "",
) -> str:
    """Build a broader archetype-level key — same archetype + same enrichment
    data ⇒ same key, regardless of project or specific entity name.

    Allows cross-project reuse: a 'taxi_operator' persona generated for one
    SANDF/Cape Flats project can be reused by another project on the same
    topic. The enrichment_snippet is the topic proxy (it carries the live
    web-research data for this archetype, which is topic-specific).
    """
    payload = {
        "v": 3,
        "kind": "archetype",
        "model": (model_name or "").strip(),
        "type": (entity_type or "").strip().lower(),
        "enrich": (enrichment_snippet or "").strip(),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def get(key: str) -> Optional[Dict[str, Any]]:
    """Return cached profile dict, or None if absent / unreadable."""
    path = os.path.join(_ensure_dir(), f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Stored as {"profile": {...}, "meta": {...}}; return only the profile
        if isinstance(data, dict) and "profile" in data:
            logger.info(f"PersonaCache HIT key={key[:12]}")
            return data["profile"]
        # Backwards-compat: bare dict
        if isinstance(data, dict):
            logger.info(f"PersonaCache HIT (legacy) key={key[:12]}")
            return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"PersonaCache read failed for {key[:12]}: {e}")
    return None


def _render_markdown_card(profile: Dict[str, Any], meta: Dict[str, Any]) -> str:
    """Build a human-readable .md card for a persona. View only — never parsed
    back. The JSON file remains the source of truth."""
    name = profile.get("name") or meta.get("entity") or "Unknown"
    archetype = profile.get("actor_archetype") or meta.get("type") or "—"
    age = profile.get("age", "—")
    gender = profile.get("gender", "—")
    occupation = profile.get("occupation", "—")
    province = profile.get("province", "—")
    persona = (profile.get("persona") or "").strip()
    bg = (profile.get("background_story") or "").strip()
    voice = (profile.get("voice_guide") or "").strip()
    group = profile.get("group_affiliation") or "—"
    beliefs = profile.get("beliefs") or []
    attitudes = profile.get("attitudes") or []
    emotions = profile.get("emotions") or {}
    needs = profile.get("needs") or {}

    lines = []
    lines.append(f"# {name}")
    lines.append("")
    lines.append(f"**Archetype:** `{archetype}` &nbsp;•&nbsp; **Age:** {age} &nbsp;•&nbsp; **Gender:** {gender}")
    lines.append(f"**Occupation:** {occupation} &nbsp;•&nbsp; **Province:** {province} &nbsp;•&nbsp; **Group:** {group}")
    lines.append("")
    if persona:
        lines.append("## Persona")
        lines.append(persona)
        lines.append("")
    if bg:
        lines.append("## Background")
        lines.append(bg)
        lines.append("")
    if voice:
        lines.append("## Voice")
        lines.append(f"_{voice}_")
        lines.append("")
    if beliefs:
        lines.append("## Beliefs")
        for b in beliefs:
            lines.append(f"- {b}")
        lines.append("")
    if attitudes:
        lines.append("## Attitudes")
        for a in attitudes:
            if isinstance(a, dict):
                topic = a.get("topic", "?"); rating = a.get("rating", "?"); desc = a.get("description", "")
                lines.append(f"- **{topic}** ({rating}/10) — {desc}")
            else:
                lines.append(f"- {a}")
        lines.append("")
    if emotions:
        em_pairs = ", ".join(f"{k} {v}" for k, v in emotions.items())
        lines.append(f"## Emotions")
        lines.append(em_pairs)
        lines.append("")
    if needs:
        top_needs = sorted(needs.items(), key=lambda kv: -float(kv[1] or 0))[:5]
        lines.append("## Top needs")
        for k, v in top_needs:
            lines.append(f"- {k}: {v}")
        lines.append("")
    # Footer
    if meta:
        lines.append("---")
        lines.append("<sub>")
        bits = [f"cache level: `{meta.get('level', 'exact')}`"]
        if meta.get("entity"): bits.append(f"source entity: `{meta['entity']}`")
        if meta.get("fixed_json"): bits.append("(json auto-repaired)")
        lines.append(" • ".join(bits))
        lines.append("</sub>")
    return "\n".join(lines) + "\n"


def put(key: str, profile: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> None:
    """Persist a generated profile under this key.

    Writes two files:
      * ``<key>.json`` — source of truth, read by the cache layer
      * ``<key>.md``   — human-readable card, view only (never parsed back)
    """
    if not isinstance(profile, dict):
        return
    meta = meta or {}
    cache_dir = _ensure_dir()
    path = os.path.join(cache_dir, f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"profile": profile, "meta": meta},
                f, ensure_ascii=False, indent=2,
            )
        logger.info(f"PersonaCache MISS → stored key={key[:12]}")
    except OSError as e:
        logger.warning(f"PersonaCache write failed for {key[:12]}: {e}")
        return  # don't try the .md if JSON failed
    # Companion human-readable card. Best-effort: failures here never affect
    # the cache (the JSON is the source of truth).
    md_path = os.path.join(cache_dir, f"{key}.md")
    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(_render_markdown_card(profile, meta))
    except Exception as e:
        logger.debug(f"PersonaCache .md write failed for {key[:12]}: {e}")


def stats() -> Dict[str, Any]:
    """Return basic cache stats — entry count and total size on disk."""
    d = _ensure_dir()
    files = [f for f in os.listdir(d) if f.endswith(".json")]
    total_bytes = sum(os.path.getsize(os.path.join(d, f)) for f in files)
    return {"entries": len(files), "bytes": total_bytes}
