"""Deterministic scorer for prompt_shape_pilot.py output. LLM-off by design.

Metrics per condition (A_production / B_free_grounded / C_free_nocards):
  template_collapse  share of responses whose FIRST sentence does the
                     annualize-and-compare move (R.. a month is R.. a year family)
  opener_diversity   entropy over first-sentence concern classes
                     (price / proof / data-device / trust / other)
  card_surfacing     share of responses containing >=1 marker of a card actually
                     bound to that persona (vocabulary or mechanism keywords)
  voice_fidelity     share containing >=1 persona-DISTINCTIVE referent
                     (generic-SA markers like load-shedding deliberately excluded)
  unlicensed_texture share mentioning load-shedding / water outages (no survey
                     field licenses these — should be ~0 under the B guardrail)
  discipline         STANCE line present; ECONOMIC json parses; no invented rand
                     amount (any R-figure not in {pitch, income, fees band})

Run:
  D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/score_prompt_shape.py
"""

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
OUTPUT = HERE / "prompt_shape_pilot_output.json"

# Persona-distinctive referents (from each profile's own record/voice guide —
# generic SA texture like load-shedding/taxis deliberately NOT counted).
VOICE_MARKERS = {
    "Nomfundo Mthembu": ["gogo", "grandmother", "pietermaritzburg", "matric", "tap"],
    "Siphosethu Mhlontlo": ["eastern cape", "mom", "mother"],
    "Thulani Mkhize": ["my children", "my kids"],
    "Lukhanyo Mthini": ["child support grant", "phone"],
    "Jaco Botes": ["private security", "my son", "my teenager", "marks"],
    "Slindile Cele": ["r1,500", "r1500", "token", "check their books", "taxi fare"],
    "Kelebogile Tlhape": ["tvet", "college", "laptop", "registration"],
    "Nolwandle Makhaphela": ["ngangelizwe", "grandson", "smartphone", "pension"],
    "Themba Mpondo": ["check his books", "my child", "my teenager"],
    "Sibusiso Nkosi": ["aunt", "five people", "phone"],
    "Thandiwe Mkhize": ["three", "my children"],
    "Palesa Molefe": ["matric", "mother's phone", "my mother"],
}

OPENER_CLASSES = [
    ("price", r"R\s?\d+|rand|afford|cost|cheap|expensive|fees|budget|income|money"),
    ("proof", r"proof|prove|results|marks|grades|improve|evidence|guarantee|work(s|ing)?\b"),
    ("data-device", r"data|airtime|phone|computer|laptop|screen|bundle|internet|device"),
    ("trust", r"trust|scam|promise|hidden|honest|believe|skeptic"),
]

ANNUALIZE = re.compile(r"R\s?\d+\s*(a|per)\s*month.{0,60}R\s?\d+\s*(a|per)\s*year", re.I)
UNLICENSED = re.compile(r"load[- ]?shedding|taps? run dry|water (outage|cuts?)", re.I)
RAND_FIG = re.compile(r"R\s?(\d[\d,\s]*)")

# Figures that are legitimately available to every persona (pitch + arithmetic on it)
GLOBAL_OK = {50, 600}


def first_sentence(text):
    text = text.strip()
    m = re.split(r"(?<=[.!?])\s", text, maxsplit=1)
    return m[0] if m else text


def classify_opener(sent):
    for label, pat in OPENER_CLASSES:
        if re.search(pat, sent, re.I):
            return label
    return "other"


def entropy(counter):
    total = sum(counter.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counter.values() if c)


def card_markers(card):
    """Cheap keyword markers per card: vocabulary + salient mechanism nouns."""
    kws = set(w.lower() for w in (card.get("vocabulary") or []))
    for m in card.get("mechanisms") or []:
        for w in re.findall(r"[a-z\-]{6,}", m.lower()):
            kws.add(w)
    return kws


def allowed_figures(profile_income, fees_band):
    ok = set(GLOBAL_OK)
    if profile_income:
        ok.add(int(profile_income))
    for n in re.findall(r"\d[\d\s,]*", fees_band or ""):
        ok.add(int(re.sub(r"[^\d]", "", n)))
    return ok


def main():
    with open(OUTPUT, encoding="utf-8") as f:
        data = json.load(f)

    cards_dir = Path("D:/Fub-agentsociety/backend/app/data/mechanism_cards")
    cards = {}
    for fp in cards_dir.glob("*.json"):
        c = json.loads(fp.read_text(encoding="utf-8"))
        if c.get("id"):
            cards[c["id"]] = card_markers(c)

    profiles = {p["name"]: p for p in json.loads(
        (Path(data["panel_source"]) / "agentsociety_profiles.json").read_text(encoding="utf-8"))}

    agg = defaultdict(lambda: {
        "n": 0, "collapse": 0, "openers": Counter(), "card_hit": 0, "card_n": 0,
        "voice_hit": 0, "unlicensed": 0, "stance_ok": 0, "econ_ok": 0, "invented": 0,
    })

    for run in data["runs"]:
        text = run["response"]
        if text.startswith("__ERROR__"):
            continue
        cond = run["condition"]
        a = agg[cond]
        a["n"] += 1

        prose = re.split(r"\nSTANCE:", text)[0]
        sent1 = first_sentence(prose)
        if ANNUALIZE.search(sent1):
            a["collapse"] += 1
        a["openers"][classify_opener(sent1)] += 1

        if run["cards_bound"]:
            a["card_n"] += 1
            kws = set()
            for cid in run["cards_bound"]:
                kws |= cards.get(cid, set())
            if any(k in prose.lower() for k in kws):
                a["card_hit"] += 1

        markers = VOICE_MARKERS.get(run["name"], [])
        if any(m in prose.lower() for m in markers):
            a["voice_hit"] += 1

        if UNLICENSED.search(prose):
            a["unlicensed"] += 1

        if re.search(r"^STANCE:\s*(supportive|neutral|concerned|oppose)", text, re.I | re.M):
            a["stance_ok"] += 1
        m = re.search(r"^ECONOMIC:\s*(\{.*\})", text, re.M | re.S)
        if m:
            try:
                json.loads(m.group(1).splitlines()[0])
                a["econ_ok"] += 1
            except json.JSONDecodeError:
                pass

        prof = profiles.get(run["name"], {})
        ok = allowed_figures(prof.get("monthly_household_income_rand"), prof.get("fees_band"))
        for fig in RAND_FIG.findall(prose):
            val = int(re.sub(r"[^\d]", "", fig) or 0)
            if val and val not in ok:
                a["invented"] += 1
                break

    print(f"model={data['model']}  repeats={data['n_repeats']}\n")
    header = f"{'metric':<22}" + "".join(f"{c:>18}" for c in sorted(agg))
    print(header)
    print("-" * len(header))

    def row(label, fn, denom="n"):
        cells = []
        for c in sorted(agg):
            a = agg[c]
            d = a[denom] or 1
            cells.append(f"{fn(a) / d * 100:>17.0f}%")
        print(f"{label:<22}" + "".join(cells))

    row("template_collapse", lambda a: a["collapse"])
    row("card_surfacing", lambda a: a["card_hit"], denom="card_n")
    row("voice_fidelity", lambda a: a["voice_hit"])
    row("unlicensed_texture", lambda a: a["unlicensed"])
    row("stance_line_ok", lambda a: a["stance_ok"])
    row("economic_json_ok", lambda a: a["econ_ok"])
    row("invented_figures", lambda a: a["invented"])
    print(f"{'opener_entropy(bits)':<22}" + "".join(
        f"{entropy(agg[c]['openers']):>18.2f}" for c in sorted(agg)))
    for c in sorted(agg):
        print(f"\n{c} openers: {dict(agg[c]['openers'])}")


if __name__ == "__main__":
    main()
