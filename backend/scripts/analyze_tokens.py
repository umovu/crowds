"""
Simulation Token Analyzer

Reads an actions.jsonl file and computes:
- Total prompt / completion tokens consumed
- Estimated cost (based on the model that was used)
- Projected cost on other models (e.g., Groq -> DeepSeek)

Usage:
    uv run python scripts/analyze_tokens.py uploads/simulations/<sim_id>/opinion_space/actions.jsonl

Or analyze the most recent simulation:
    uv run python scripts/analyze_tokens.py --latest
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, ".."))
sys.path.insert(0, _backend_dir)

from app.utils.token_counter import _DEFAULT_PRICING


def analyze_actions_file(actions_path: str) -> Dict:
    """Parse actions.jsonl and aggregate token stats."""
    total_prompt = 0
    total_completion = 0
    total_cost = 0.0
    actions_with_tokens = 0
    actions_without_tokens = 0
    rounds = set()
    agents = set()

    with open(actions_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Skip event markers
            if "event_type" in data:
                if data["event_type"] == "simulation_end":
                    # Prefer actual totals if present
                    pass
                continue

            # Skip system/agent-less entries
            agent_id = data.get("agent_id")
            if agent_id is not None:
                agents.add(agent_id)
                rounds.add(data.get("round_num", 0))

            pt = data.get("prompt_tokens", 0)
            ct = data.get("completion_tokens", 0)
            ec = data.get("estimated_cost_usd", 0.0)

            if pt or ct:
                actions_with_tokens += 1
                total_prompt += pt
                total_completion += ct
                total_cost += ec
            else:
                actions_without_tokens += 1

    return {
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_prompt + total_completion,
        "estimated_cost_usd": total_cost,
        "actions_with_tokens": actions_with_tokens,
        "actions_without_tokens": actions_without_tokens,
        "unique_agents": len(agents),
        "unique_rounds": len(rounds),
        "total_actions": actions_with_tokens + actions_without_tokens,
    }


def project_cost(prompt_tokens: int, completion_tokens: int, model: str) -> Tuple[float, Dict]:
    """Project cost for a given model."""
    clean = model.lower()
    for prefix in ("groq/", "ollama/", "openai/"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]

    price = _DEFAULT_PRICING.get(clean, (0.0, 0.0))
    prompt_price, completion_price = price

    cost = (prompt_tokens / 1_000_000) * prompt_price + (completion_tokens / 1_000_000) * completion_price
    return round(cost, 6), {
        "model": model,
        "prompt_price_per_1m": prompt_price,
        "completion_price_per_1m": completion_price,
    }


def print_report(stats: Dict, source_model: str = "unknown"):
    """Pretty-print analysis report."""
    print("=" * 60)
    print("SIMULATION TOKEN ANALYSIS")
    print("=" * 60)
    print()
    print(f"Actions with token data : {stats['actions_with_tokens']}")
    print(f"Actions without tokens  : {stats['actions_without_tokens']}")
    print(f"Unique agents           : {stats['unique_agents']}")
    print(f"Rounds                  : {stats['unique_rounds']}")
    print()
    print(f"Prompt tokens           : {stats['total_prompt_tokens']:,}")
    print(f"Completion tokens       : {stats['total_completion_tokens']:,}")
    print(f"Total tokens            : {stats['total_tokens']:,}")
    print()

    if stats['actions_with_tokens'] == 0:
        print("⚠️  No token data found. This simulation was run before")
        print("   the token counter was added, or the model did not")
        print("   return usage statistics.")
        print()
        print("   To measure tokens, run a NEW simulation with the")
        print("   updated code and a model that supports usage stats")
        print("   (Groq, OpenAI, or DeepSeek with usage reporting).")
        return

    print(f"Estimated cost (recorded): ${stats['estimated_cost_usd']:.6f}")
    print()
    print("-" * 60)
    print("COST PROJECTIONS — same workload on other models")
    print("-" * 60)
    print()

    pt = stats['total_prompt_tokens']
    ct = stats['total_completion_tokens']

    models_to_compare = [
        "deepseek-v4-flash",
        "deepseek-chat",
        "deepseek-reasoner",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gpt-4o",
        "gpt-4o-mini",
    ]

    for model in models_to_compare:
        cost, info = project_cost(pt, ct, model)
        marker = "  ← CURRENT" if model.lower() in source_model.lower() else ""
        print(f"  {model:30s}  ${cost:>10.6f}{marker}")

    print()
    print("-" * 60)
    print("BUDGET PROJECTIONS — how many simulations per $20")
    print("-" * 60)
    print()
    for model in ["deepseek-v4-flash", "deepseek-chat", "llama-3.3-70b-versatile"]:
        cost, _ = project_cost(pt, ct, model)
        per_20 = int(20 / cost) if cost > 0 else "∞"
        print(f"  {model:30s}  ~{per_20} sims / $20")
    print()


def find_latest_simulation() -> str:
    """Find the most recently modified simulation directory."""
    sims_dir = Path(_backend_dir) / "uploads" / "simulations"
    if not sims_dir.exists():
        raise FileNotFoundError(f"Simulations directory not found: {sims_dir}")

    sim_dirs = [d for d in sims_dir.iterdir() if d.is_dir()]
    if not sim_dirs:
        raise FileNotFoundError("No simulation directories found")

    latest = max(sim_dirs, key=lambda d: d.stat().st_mtime)
    actions_file = latest / "opinion_space" / "actions.jsonl"
    if not actions_file.exists():
        raise FileNotFoundError(f"No actions.jsonl found in {latest}")

    return str(actions_file)


def main():
    parser = argparse.ArgumentParser(description="Analyze simulation token usage")
    parser.add_argument("file", nargs="?", help="Path to actions.jsonl")
    parser.add_argument("--latest", action="store_true", help="Use the most recent simulation")
    parser.add_argument("--model", default="unknown", help="Source model name (for labeling)")
    args = parser.parse_args()

    if args.latest:
        actions_path = find_latest_simulation()
        print(f"Using latest simulation: {actions_path}\n")
    elif args.file:
        actions_path = args.file
    else:
        print("Usage: python analyze_tokens.py <actions.jsonl>  OR  --latest")
        sys.exit(1)

    if not os.path.exists(actions_path):
        print(f"File not found: {actions_path}")
        sys.exit(1)

    stats = analyze_actions_file(actions_path)
    print_report(stats, source_model=args.model)


if __name__ == "__main__":
    main()
