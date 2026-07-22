"""Scorer for invisible_numbers_pilot.py — deterministic, LLM-off by design.
Spec: docs/INVISIBLE_NUMBERS_PILOT.md.

HEADLINE metric (the claim under test): post-strip balanced accuracy of the
frozen marker classifier — digit-stripped text only, same instrument for every
condition. Primary variant is ECHO-ROBUST: response 4-grams overlapping the
persona's own injected econ block are masked before classification, so tier
separation that survives masking cannot be prompt echo.

Gated contrasts (frozen in spec):
  1. C vs chance — cluster permutation p < 0.05 on echo-robust balanced accuracy.
  2. C vs A     — persona-cluster bootstrap 95% CI on (C - A), lower bound >= 0.

Usage:
  D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/score_invisible_numbers.py [output_json]
"""

import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from situation_compiler import (  # noqa: E402
    CLASSIFIER_MARKERS, CLASSIFIER_MARKERS_V2, normalize,
)
from score_prompt_shape import (  # noqa: E402  (module is import-safe)
    VOICE_MARKERS, ANNUALIZE, UNLICENSED, RAND_FIG,
    first_sentence, classify_opener, entropy, card_markers,
)

OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "invisible_numbers_pilot_output.json"
LEXICON_VERSION = sys.argv[2] if len(sys.argv) > 2 else "v1"
ACTIVE_MARKERS = {"v1": CLASSIFIER_MARKERS, "v2": CLASSIFIER_MARKERS_V2}[LEXICON_VERSION]

TIERS = ("tight", "moderate", "loose")
SEED = 241946
N_PERM = 10000
N_BOOT = 10000
ECHO_N = 4

# Number-leak whitelist (spec): pitch figure + its legitimate arithmetic out
# to 3 years. Own income/fee figures count as leaks under the new rule.
LEAK_WHITELIST = {50} | {50 * k for k in range(2, 37)}


# ---------------------------------------------------------------------------
# Classifier (frozen markers; abstain on tie or zero hits)
# ---------------------------------------------------------------------------

def _marker_pattern(marker):
    nm = normalize(marker)
    return re.compile(r"\b" + r"\s+".join(re.escape(w) for w in nm.split()) + r"\b")


_MARKER_PATTERNS = {
    tier: [(m, _marker_pattern(m)) for m in markers]
    for tier, markers in ACTIVE_MARKERS.items()
}


def classify_tier(text_norm):
    scores = {}
    for tier, pats in _MARKER_PATTERNS.items():
        scores[tier] = sum(len(pat.findall(text_norm)) for _, pat in pats)
    best = max(scores.values())
    if best == 0:
        return None
    winners = [t for t, s in scores.items() if s == best]
    return winners[0] if len(winners) == 1 else None


# ---------------------------------------------------------------------------
# Echo masking + paraphrase-leak containment
# ---------------------------------------------------------------------------

def _ngrams(words, n):
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def mask_echo(text_norm, block_norm, n=ECHO_N):
    """Drop every word participating in a text n-gram that also appears in the
    injected block. Conservative: can only remove signal, never add it."""
    tw = text_norm.split()
    if len(tw) < n:
        return text_norm
    bg = _ngrams(block_norm.split(), n)
    masked = [False] * len(tw)
    for i in range(len(tw) - n + 1):
        if tuple(tw[i:i + n]) in bg:
            for j in range(i, i + n):
                masked[j] = True
    return " ".join(w for w, m in zip(tw, masked) if not m)


def containment(text_norm, block_norm, n=ECHO_N):
    tg = _ngrams(text_norm.split(), n)
    if not tg:
        return 0.0
    bg = _ngrams(block_norm.split(), n)
    return len(tg & bg) / len(tg)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def balanced_accuracy(pairs):
    recalls = []
    for t in TIERS:
        tot = sum(1 for tr, _ in pairs if tr == t)
        cor = sum(1 for tr, pr in pairs if tr == t and pr == t)
        recalls.append(cor / tot if tot else 0.0)
    return sum(recalls) / len(recalls), recalls


def permutation_p(persona_tiers, preds_by_persona, rng, n_perm=N_PERM):
    """Cluster permutation: permute persona->tier as whole clusters; the
    per-response predictions stay fixed. p with +1 correction."""
    names = sorted(preds_by_persona)
    true = [persona_tiers[n] for n in names]
    obs_pairs = [(persona_tiers[n], p) for n in names for p in preds_by_persona[n]]
    obs, _ = balanced_accuracy(obs_pairs)
    ge = 0
    for _ in range(n_perm):
        perm = true[:]
        rng.shuffle(perm)
        pairs = [(perm[i], p) for i, n in enumerate(names) for p in preds_by_persona[n]]
        if balanced_accuracy(pairs)[0] >= obs:
            ge += 1
    return obs, (ge + 1) / (n_perm + 1)


def bootstrap_diff(tiers_x, preds_x, tiers_y, preds_y, rng, n_boot=N_BOOT):
    """Persona-cluster bootstrap 95% CI on BA(X) - BA(Y)."""
    names = sorted(set(preds_x) & set(preds_y))
    diffs = []
    for _ in range(n_boot):
        sample = [rng.choice(names) for _ in names]
        px = [(tiers_x[n], p) for n in sample for p in preds_x[n]]
        py = [(tiers_y[n], p) for n in sample for p in preds_y[n]]
        diffs.append(balanced_accuracy(px)[0] - balanced_accuracy(py)[0])
    diffs.sort()
    return diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot)]


# ---------------------------------------------------------------------------
# Side metrics
# ---------------------------------------------------------------------------

OBJECTION_CLASSES = [
    ("price", r"cost|price|afford|expensive|rand|money|fee|budget|pay"),
    ("proof", r"proof|prove|result|marks|grades|outcome|evidence|work"),
    ("trust", r"trust|scam|hidden|promise|guarantee|payout"),
    ("access", r"data|phone|internet|device|offline|screen|computer|airtime"),
    ("philosophy", r"intrinsic|discipline|motivat|reward|gamif"),
]


def bucket_objection(text):
    t = (text or "").lower()
    for label, pat in OBJECTION_CLASSES:
        if re.search(pat, t):
            return label
    return "other"


def parse_economic(text):
    m = re.search(r"^ECONOMIC:\s*(\{.*\})", text, re.M)
    if not m:
        return None
    try:
        return json.loads(m.group(1).splitlines()[0])
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    with open(OUTPUT, encoding="utf-8") as f:
        data = json.load(f)

    cards_dir = Path("D:/Fub-agentsociety/backend/app/data/mechanism_cards")
    cards = {}
    for fp in cards_dir.glob("*.json"):
        c = json.loads(fp.read_text(encoding="utf-8"))
        if c.get("id"):
            cards[c["id"]] = card_markers(c)

    rng = random.Random(SEED)

    conditions = data.get("conditions") or sorted({r["condition"] for r in data["runs"]})
    per = {c: {"valid": [], "errors": 0} for c in conditions}
    for r in data["runs"]:
        if r["response"].startswith("__ERROR__"):
            per[r["condition"]]["errors"] += 1
        else:
            per[r["condition"]]["valid"].append(r)

    print("model=%s  repeats=%s  seed=%s  lexicon=%s" % (
        data["model"], data["n_repeats"], SEED, LEXICON_VERSION))
    print("output: %s" % OUTPUT)
    for c in conditions:
        print("  %-14s valid=%d errors=%d" % (c, len(per[c]["valid"]), per[c]["errors"]))

    agg = {}
    for c in conditions:
        a = {
            "n": 0, "collapse": 0, "openers": Counter(), "voice_hit": 0,
            "unlicensed": 0, "stance_ok": 0, "econ_ok": 0, "leak": 0,
            "card_hit": 0, "card_n": 0, "contain": [],
            "abstain_raw": 0, "abstain_echo": 0,
            "pairs_raw": [], "pairs_echo": [],
            "preds_raw": defaultdict(list), "preds_echo": defaultdict(list),
            "tiers": {}, "impulse": defaultdict(list),
            "objections": defaultdict(Counter),
        }
        for r in per[c]["valid"]:
            a["n"] += 1
            text = r["response"]
            prose = re.split(r"\nSTANCE:", text)[0]
            tnorm = normalize(prose)
            bnorm = normalize(r.get("econ_block") or "")
            true_tier = r["budget_tier"]
            a["tiers"][r["name"]] = true_tier

            pred_raw = classify_tier(tnorm)
            masked = mask_echo(tnorm, bnorm)
            pred_echo = classify_tier(masked) if masked else None
            a["pairs_raw"].append((true_tier, pred_raw))
            a["pairs_echo"].append((true_tier, pred_echo))
            a["preds_raw"][r["name"]].append(pred_raw)
            a["preds_echo"][r["name"]].append(pred_echo)
            a["abstain_raw"] += pred_raw is None
            a["abstain_echo"] += pred_echo is None
            a["contain"].append(containment(tnorm, bnorm))

            sent1 = first_sentence(prose)
            if ANNUALIZE.search(sent1):
                a["collapse"] += 1
            a["openers"][classify_opener(sent1)] += 1
            if any(m in prose.lower() for m in VOICE_MARKERS.get(r["name"], [])):
                a["voice_hit"] += 1
            if UNLICENSED.search(prose):
                a["unlicensed"] += 1
            if re.search(r"^STANCE:\s*(supportive|neutral|concerned|oppose)", text, re.I | re.M):
                a["stance_ok"] += 1
            econ = parse_economic(text)
            if econ is not None:
                a["econ_ok"] += 1
                imp = econ.get("impulse")
                if isinstance(imp, (int, float)):
                    a["impulse"][true_tier].append(float(imp))
                a["objections"][true_tier][bucket_objection(econ.get("primary_objection"))] += 1

            for fig in RAND_FIG.findall(prose):
                val = int(re.sub(r"[^\d]", "", fig) or 0)
                if val and val not in LEAK_WHITELIST:
                    a["leak"] += 1
                    break

            if r.get("cards_bound"):
                a["card_n"] += 1
                kws = set()
                for cid in r["cards_bound"]:
                    kws |= cards.get(cid, set())
                if any(k in prose.lower() for k in kws):
                    a["card_hit"] += 1

        agg[c] = a

    # ---- HEADLINE ---------------------------------------------------------
    print("\n== HEADLINE: post-strip tier classification (same instrument, all conditions) ==")
    print(f"{'condition':<14} {'BA(raw)':>8} {'BA(echo)':>9} {'abst raw':>9} {'abst echo':>10} {'p(raw)':>8} {'p(echo)':>8}")
    print("-" * 74)
    pvals = {}
    for c in conditions:
        a = agg[c]
        ba_raw, _ = balanced_accuracy(a["pairs_raw"])
        ba_echo, recalls_echo = balanced_accuracy(a["pairs_echo"])
        obs_r, p_r = permutation_p(a["tiers"], a["preds_raw"], rng)
        obs_e, p_e = permutation_p(a["tiers"], a["preds_echo"], rng)
        pvals[c] = (p_r, p_e)
        print(f"{c:<14} {ba_raw:>8.2f} {ba_echo:>9.2f} "
              f"{a['abstain_raw']:>9d} {a['abstain_echo']:>10d} {p_r:>8.4f} {p_e:>8.4f}")
        print(f"{'':<14} echo recalls: " + "  ".join(
            f"{t}={r:.2f}" for t, r in zip(TIERS, recalls_echo)))

    # ---- Gated contrasts --------------------------------------------------
    # Condition names differ across condition sets (run1: B/C, run2: B2/C2).
    c_name = "C2_full_v2" if "C2_full_v2" in agg else "C_full"
    b_name = "B2_block_v2" if "B2_block_v2" in agg else "B_block_only"
    print("\n== GATED CONTRASTS (echo-robust) ==")
    c, a = agg[c_name], agg["A_control"]
    _, p_c = pvals[c_name]
    lo, hi = bootstrap_diff(c["tiers"], c["preds_echo"], a["tiers"], a["preds_echo"], rng)
    print(f"1. {c_name} vs chance: p(echo)={p_c:.4f}  -> {'PASS' if p_c < 0.05 else 'FAIL'} (need < 0.05)")
    print(f"2. {c_name} vs A: 95% CI [{lo:+.2f}, {hi:+.2f}]  -> "
          f"{'PASS' if lo >= 0 else 'FAIL'} (need lower bound >= 0)")
    print("   chance level for balanced accuracy over 3 tiers = 0.33")

    print("\n== SECONDARY (ungated) ==")
    for x in (b_name, "D_rule_only"):
        lo, hi = bootstrap_diff(agg[x]["tiers"], agg[x]["preds_echo"],
                                a["tiers"], a["preds_echo"], rng)
        print(f"{x} vs A: 95% CI [{lo:+.2f}, {hi:+.2f}]")

    # ---- Leak + containment ----------------------------------------------
    print("\n== PROMPT-ECHO + NUMBER-LEAK ==")
    print(f"{'condition':<14} {'containment':>12} {'number_leak':>12}")
    for c in conditions:
        a2 = agg[c]
        mean_cont = sum(a2["contain"]) / len(a2["contain"]) if a2["contain"] else 0.0
        print(f"{c:<14} {mean_cont:>12.2f} {a2['leak'] / (a2['n'] or 1) * 100:>11.0f}%")

    # ---- Carried-over metrics --------------------------------------------
    print("\n== CARRIED-OVER METRICS ==")
    header = f"{'metric':<22}" + "".join(f"{c:>16}" for c in conditions)
    print(header)
    print("-" * len(header))

    def row(label, fn, denom="n"):
        cells = []
        for c in conditions:
            a2 = agg[c]
            d = a2[denom] or 1
            cells.append(f"{fn(a2) / d * 100:>15.0f}%")
        print(f"{label:<22}" + "".join(cells))

    row("template_collapse", lambda a2: a2["collapse"])
    row("voice_fidelity", lambda a2: a2["voice_hit"])
    row("unlicensed_texture", lambda a2: a2["unlicensed"])
    row("stance_line_ok", lambda a2: a2["stance_ok"])
    row("economic_json_ok", lambda a2: a2["econ_ok"])
    row("card_surfacing", lambda a2: a2["card_hit"], denom="card_n")
    print(f"{'opener_entropy(bits)':<22}" + "".join(
        f"{entropy(agg[c]['openers']):>16.2f}" for c in conditions))

    # ---- Economics retained ----------------------------------------------
    print("\n== ECONOMICS RETAINED (ECONOMIC json by true tier) ==")
    for c in conditions:
        a2 = agg[c]
        print(f"{c}:")
        for t in TIERS:
            imps = a2["impulse"].get(t, [])
            mean_i = sum(imps) / len(imps) if imps else float("nan")
            objs = dict(a2["objections"].get(t, {}))
            print(f"  {t:<9} impulse_mean={mean_i:>5.2f} (n={len(imps)})  objections={objs}")


if __name__ == "__main__":
    main()
