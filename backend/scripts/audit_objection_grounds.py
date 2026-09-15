"""audit_objection_grounds — does the objection card log walls the persona has no grounds for?

For every objection logged against a persona in the saved panels, does that persona's
own measured data entitle them to raise it? A persona who owns a car, lives in a metro
and has never gone without care has no grounds for "costs something just to reach it".

Reports both objection layers side by side:
  * mention — `objections.classify`, the raw keyword count the benchmark uses
  * reading — `objections.read`, mood-aware (what the product screens now use)

The grounds rules live in app/data/objection_vocab.json. They are hand-authored
proposals over fields the library carries and need a human sign-off, same as a
mechanism card. Everything here is deterministic and LLM-free.

Usage:
    python audit_objection_grounds.py [--sessions DIR] [--library PATH] [--verbose]
"""

from __future__ import annotations

import argparse
import collections
import glob
import importlib.util
import json
import os
from typing import Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_SESSIONS = os.path.join(_HERE, "..", "uploads", "panel_sessions")
_DEFAULT_LIBRARY = os.path.join(
    _HERE, "..", "app", "data", "persona_library", "personas.json")

# Load the classifier BY PATH — importing app.services pulls AgentSociety2 and
# dies without an API key. Same trick as classify_objections.py, same reason:
# this must run with no model and no key.
_spec = importlib.util.spec_from_file_location(
    "objections_audit",
    os.path.abspath(os.path.join(_HERE, "..", "app", "services", "objections.py")))
objections = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(objections)

# Re-exported so scripts that used this module's helpers keep working.
persona_facts = objections.persona_facts
has_grounds = objections.has_grounds


def load_library(path: str) -> Dict[str, Dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data if isinstance(data, list) else data.get("personas", data)
    index: Dict[str, Dict] = {}
    for p in rows:
        if p.get("id"):
            index[p["id"]] = p
        if p.get("name"):
            index.setdefault("name:" + p["name"], p)
    return index


def _table(title: str, grounded, ungrounded, untestable) -> None:
    print(title)
    header = f"{'objection':<38}{'grounded':>9}{'ungrounded':>12}{'untestable':>12}{'false %':>9}"
    print(header)
    print("-" * len(header))
    order = sorted(objections.OBJECTION_TYPES,
                   key=lambda t: -(grounded[t] + ungrounded[t] + untestable[t]))
    tot_g = tot_u = tot_n = 0
    for otype in order:
        g, u, n = grounded[otype], ungrounded[otype], untestable[otype]
        if not (g or u or n):
            continue
        tot_g, tot_u, tot_n = tot_g + g, tot_u + u, tot_n + n
        pct = f"{(100.0 * u / (g + u)):.0f}%" if (g + u) else "-"
        print(f"{objections.LABELS[otype]:<38}{g:>9}{u:>12}{n:>12}{pct:>9}")
    print("-" * len(header))
    overall = f"{(100.0 * tot_u / (tot_g + tot_u)):.0f}%" if (tot_g + tot_u) else "-"
    print(f"{'TOTAL':<38}{tot_g:>9}{tot_u:>12}{tot_n:>12}{overall:>9}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default=_DEFAULT_SESSIONS)
    ap.add_argument("--library", default=_DEFAULT_LIBRARY)
    ap.add_argument("--verbose", action="store_true",
                    help="print sample ungrounded mention-layer hits")
    args = ap.parse_args()

    index = load_library(args.library)
    total_responses = matched = 0
    layers = {name: (collections.Counter(), collections.Counter(), collections.Counter())
              for name in ("mention", "reading")}
    examples: Dict[str, List[str]] = collections.defaultdict(list)

    for path in sorted(glob.glob(os.path.join(args.sessions, "*", "rounds", "round_*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            continue
        for row in (payload.get("result") or {}).get("results") or []:
            total_responses += 1
            persona = (index.get(row.get("library_id") or "")
                       or index.get("name:" + (row.get("agent_name") or "")))
            if not persona:
                continue
            matched += 1
            text = row.get("response") or ""
            facts = persona_facts(persona)
            hits = {"mention": objections.classify(text),
                    "reading": objections.read(text)["walls"]}
            for layer, types in hits.items():
                grounded, ungrounded, untestable = layers[layer]
                for otype in types:
                    verdict = has_grounds(otype, facts)
                    if verdict is True:
                        grounded[otype] += 1
                    elif verdict is False:
                        ungrounded[otype] += 1
                        if layer == "mention" and len(examples[otype]) < 3:
                            examples[otype].append(
                                f"{persona.get('name')} ({persona.get('geotype')}): "
                                + " ".join(text.split())[:150])
                    else:
                        untestable[otype] += 1

    print(f"panel responses found : {total_responses}")
    print(f"matched to a persona  : {matched}")
    print()
    _table("MENTION layer (benchmark keyword count)", *layers["mention"])
    _table("READING layer (mood-aware, before grounds are applied)", *layers["reading"])

    if args.verbose:
        for otype in objections.OBJECTION_TYPES:
            if examples[otype]:
                print(f"-- ungrounded mention: {objections.LABELS[otype]}")
                for line in examples[otype]:
                    print("   " + line)


if __name__ == "__main__":
    main()
