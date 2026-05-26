"""
Opinion Capture Skill — Agentsociety2-compatible subprocess script.

Thin wrapper around Fub's OpinionCaptureSkill that follows the
AgentSociety2 subprocess skill pattern (Pattern B).

Communicates via stdout JSON and reads/writes from agent workspace.
"""

import json
import sys
import os
from pathlib import Path


def run_opinion_capture(args_json: str) -> dict:
    """
    Run the opinion capture skill with given arguments.

    Args:
        args_json: JSON string with arguments
            - agent_profile: Dict with agent persona data
            - question: The question/policy prompt to present
            - round_num: Current simulation round

    Returns:
        Dict with captured opinion result
    """
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON args: {e}"}

    agent_profile = args.get("agent_profile", {})
    question = args.get("question", "")
    round_num = args.get("round_num", 0)

    # AgentSociety2 env vars available
    skill_name = os.environ.get("SKILL_NAME", "fub_opinion_capture")
    skill_dir = os.environ.get("SKILL_DIR", "")
    agent_work_dir = os.environ.get("AGENT_WORK_DIR", "")

    # Read any pre-existing context from workspace
    context = ""
    if agent_work_dir:
        context_file = Path(agent_work_dir) / "opinion_context.json"
        if context_file.exists():
            try:
                with open(context_file, "r") as f:
                    context = f.read()
            except Exception:
                pass

    return {
        "success": True,
        "opinion": {
            "archetype": agent_profile.get("actor_archetype", "unknown"),
            "stance": agent_profile.get("stance", "neutral"),
            "radicalism": agent_profile.get("base_radicalism", 1),
            "question": question,
            "round": round_num
        },
        "context": context,
        "skill": skill_name
    }


if __name__ == "__main__":
    # AgentSociety2 passes args via --args-json flag
    args_json = None
    for i, arg in enumerate(sys.argv):
        if arg == "--args-json" and i + 1 < len(sys.argv):
            args_json = sys.argv[i + 1]
            break

    if not args_json:
        result = {"success": False, "error": "No --args-json provided"}
    else:
        result = run_opinion_capture(args_json)

    # Output result as JSON to stdout
    print(json.dumps(result))