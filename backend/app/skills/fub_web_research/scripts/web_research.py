"""
Web Research Skill — Agentsociety2-compatible subprocess script.

Calls Fub's Flask API endpoint to trigger deep web research (Firecrawl + Jina + LLM).
"""

import json
import sys
import os
import urllib.request
import urllib.parse


def run_web_research(args_json: str) -> dict:
    """
    Perform web research by calling Fub's API.

    Args from --args-json:
        - query: Research question
        - agent_context: Optional dict with custom agent context to shape research

    Returns:
        Dict with research results
    """
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON args: {e}"}

    query = args.get("query", "")
    agent_context = args.get("agent_context", {})
    if not query:
        return {"success": False, "error": "Query is required"}

    # Call Fub's own web research API
    api_url = os.environ.get("FUB_API_URL", "http://localhost:5001")
    url = f"{api_url}/api/research/web"

    data = json.dumps({"query": query, "agent_context": agent_context}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    args_json = None
    for i, arg in enumerate(sys.argv):
        if arg == "--args-json" and i + 1 < len(sys.argv):
            args_json = sys.argv[i + 1]
            break

    if not args_json:
        result = {"success": False, "error": "No --args-json provided"}
    else:
        result = run_web_research(args_json)

    print(json.dumps(result))