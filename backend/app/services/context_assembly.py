import hashlib
import json
from typing import Any, Dict, List, Optional


def assemble_prompt_sections(
    persona_facts: str,
    starting_outlook: str,
    research_block: str,
    current_context: Optional[str],
    scenario: str,
    instructions: str,
) -> Dict[str, Any]:
    sections = {
        "fixed_persona_facts": persona_facts or "",
        "starting_outlook": starting_outlook or "",
        "research_patterns": research_block or "",
        "dated_current_conditions": current_context or "",
        "scenario_assumptions": scenario or "",
        "response_instructions": instructions or "",
    }
    ordered = "\n\n".join(f"## {k.upper()}\n{v}" for k, v in sections.items() if v)
    hashes = {k: hashlib.sha256(v.encode("utf-8")).hexdigest()[:16] for k, v in sections.items()}
    return {"text": ordered, "sections": sections, "hashes": hashes, "snapshot_id": hashlib.sha256((current_context or "").encode()).hexdigest()[:12]}


def historical_mode() -> bool:
    import os
    return os.environ.get("HISTORICAL_BACKTEST", "").strip().lower() in ("1", "true", "yes", "on")
