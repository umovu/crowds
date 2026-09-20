"""grounded_segment_probe — the beachhead question with the REAL people in the state.

The first pass sent only the pitch and asked Jev to choose between twenty
hand-written labels. That is the model reasoning from its own world knowledge:
a guess dressed as an answer. Here the state carries a measured profile of each
segment, computed from the library, so the question becomes a comparison
between the pitch and real people rather than between the pitch and a label.
"""
import json
import os
import statistics
import sys
from collections import Counter

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)
for line in open(os.path.join(BACKEND, "..", ".env"), encoding="utf-8"):
    line = line.strip()
    if line.startswith("TYPESAFE_") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)


def segment_facts():
    """A measured profile per 'who' segment, straight off the library."""
    from app.services.panel_service import SEGMENTS, get_library

    personas = get_library().all()
    out = {}
    for seg_id, seg in SEGMENTS.items():
        if seg.get("kind") != "who" or seg_id == "everyone":
            continue
        pred = seg["predicate"]
        members = personas if pred is None else [p for p in personas if pred(p)]
        if not members:
            continue

        def mode(key):
            vals = [p.get(key) for p in members if p.get(key)]
            return Counter(vals).most_common(1)[0][0] if vals else None

        incomes = [p["monthly_household_income_rand"] for p in members
                   if isinstance(p.get("monthly_household_income_rand"), (int, float))
                   and p["monthly_household_income_rand"] > 0]
        ages = [p["age"] for p in members if isinstance(p.get("age"), (int, float))]
        out[seg_id] = {
            "who": seg["description"],
            "people_in_library": len(members),
            "median_age": int(statistics.median(ages)) if ages else None,
            "median_household_income_rand_per_month":
                int(statistics.median(incomes)) if incomes else None,
            "most_common_employment": mode("employment_status"),
            "most_common_area": mode("geotype"),
            "share_receiving_a_grant":
                round(sum(1 for p in members if p.get("receives_grant")) / len(members), 2),
            "share_with_internet_at_home":
                round(sum(1 for p in members if p.get("internet_at_home")) / len(members), 2),
            "share_with_medical_aid":
                round(sum(1 for p in members if p.get("medical_aid")) / len(members), 2),
        }
    return out


def ask(pitch, facts, grounded=True):
    from app.utils import typesafe_client as ts

    if grounded:
        state = {"pitch": pitch, "candidate_groups": facts}
        instructions = (
            "`pitch` describes an offer. `candidate_groups` describes real measured "
            "groups of South Africans. Which group is the best FIRST customer — the "
            "one whose measured situation means they feel this problem most sharply "
            "and could actually take it up?")
        options = {k: None for k in facts}
    else:
        state = pitch
        instructions = ("Which single group of South Africans is the best FIRST customer "
                        "for this — the group that feels the problem most sharply and "
                        "would take it up earliest?")
        options = {k: v["who"] for k, v in facts.items()}

    answers = ts.ask(state, {"beachhead": ts.choice_question(instructions, options)})
    return (answers or {}).get("beachhead") or {}


def show(label, answer):
    ranked = sorted((answer.get("probabilities") or {}).items(), key=lambda kv: -kv[1])[:4]
    print(f"  {label:26} conf {answer.get('confidence', 0):.2f}   "
          + ", ".join(f"{k} {v:.0%}" for k, v in ranked))


def main():
    facts = segment_facts()
    print(f"state carries {len(facts)} measured groups\n")
    print("one group, as sent:")
    k = "informal_traders"
    print("  " + json.dumps({k: facts[k]}, indent=2).replace("\n", "\n  ")[:600])

    sessions = os.path.join(BACKEND, "uploads", "panel_sessions")
    pitches = {}
    for d in os.listdir(sessions):
        f = os.path.join(sessions, d, "panel_session.json")
        if not os.path.exists(f):
            continue
        try:
            p = (json.load(open(f, encoding="utf-8")).get("pitch") or "").strip()
        except Exception:
            continue
        if len(p) > 180:
            pitches.setdefault(p[:50], p)

    print()
    for p in list(pitches.values())[:4]:
        print(f"\nPITCH: {p[:110]}...")
        show("pitch only (guessing)", ask(p, facts, grounded=False))
        show("with real group data", ask(p, facts, grounded=True))


if __name__ == "__main__":
    main()
