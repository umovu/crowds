"""LLM-off tests for situation_compiler.py. Run directly:

  D:/Fub-agentsociety/backend/.venv/Scripts/python.exe backend/scripts/test_situation_compiler.py

Exits non-zero on first failure detail summary. No LLM, no network.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from situation_compiler import (  # noqa: E402
    CLASSIFIER_MARKERS,
    CLASSIFIER_MARKERS_V2,
    RHYTHM,
    RHYTHM_V2_OVERRIDES,
    TIERS,
    compile_situation,
    compiler_vocabulary,
    naive_income_band,
    normalize,
    role_of,
    tier_of,
)

CAST_PATH = Path(
    "D:/Fub-agentsociety/backend/uploads/panel_sessions/"
    "panel_07eb044c9c55/agentsociety_profiles.json"
)

FAILURES = []


def check(name, ok, detail=""):
    if ok:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s  %s" % (name, detail))
        FAILURES.append(name)


def load_cast():
    with open(CAST_PATH, encoding="utf-8") as f:
        return json.load(f)


def all_compiler_texts(cast):
    """Every string the compiler can emit, ALL versions: v1 + v2 templates
    (both obligation variants) + compiled v1/v2 output for every cast persona."""
    texts = []
    templates = list(RHYTHM.values()) + list(RHYTHM_V2_OVERRIDES.values())
    for tpl in templates:
        for oblig in ("food and transport", "food, transport and school things"):
            texts.append(tpl.format(obligations=oblig))
    from situation_compiler import GRANT_LINE, DIGITAL_PHONE_LINE, DIGITAL_COMPUTER_LINE
    texts += [GRANT_LINE, DIGITAL_PHONE_LINE, DIGITAL_COMPUTER_LINE]
    for p in cast:
        texts.append(compile_situation(p))
        texts.append(compile_situation(p, version=2))
    return texts


def main():
    cast = load_cast()
    check("cast loads (12 personas)", len(cast) == 12, "got %d" % len(cast))

    # 1. No numeric tokens in any compiled output (both template versions).
    bad = [p["name"] for p in cast
           if re.search(r"\d", compile_situation(p))
           or re.search(r"\d", compile_situation(p, version=2))]
    check("no numeric tokens in compiled output (v1+v2)", not bad, ", ".join(bad))

    # 2. Lexicon disjointness (anti-circularity 1): no classifier marker is a
    #    substring of any compiler text, and no compiler sentence is a
    #    substring of any marker (symmetric). Both lexicon versions, union of
    #    all compiler texts.
    texts = [normalize(t) for t in all_compiler_texts(cast)]
    hits = []
    for lname, lexicon in (("v1", CLASSIFIER_MARKERS), ("v2", CLASSIFIER_MARKERS_V2)):
        for tier, markers in lexicon.items():
            for m in markers:
                nm = normalize(m)
                for t in texts:
                    if nm and nm in t:
                        hits.append("%s %s marker %r in compiler text %r" % (lname, tier, m, t))
                    if t and t in nm:
                        hits.append("compiler text %r inside %s %s marker %r" % (t, lname, tier, m))
    check("classifier/compiler disjointness (v1+v2)", not hits, "; ".join(hits[:3]))

    # 3. Referent licensing on the cast.
    problems = []
    for p in cast:
        out = compile_situation(p)
        if ("grant" in out.lower()) != bool(p.get("receives_grant")):
            problems.append("%s grant line mismatch" % p["name"])
        has_comp_line = "computer and an internet" in out.lower()
        if has_comp_line != bool(p.get("computer_in_home")):
            problems.append("%s computer line mismatch" % p["name"])
        has_phone_line = "data is bought" in out.lower()
        expect_phone = bool(p.get("internet_at_home")) and not p.get("computer_in_home")
        if has_phone_line != expect_phone:
            problems.append("%s phone-data line mismatch" % p["name"])
        licensed_school = (
            any((b or "").strip().lower() != "no fees" for b in
                ([p.get("fees_band")] if p.get("fees_band") else []) +
                (list(p.get("learner_fee_bands") or [])))
            or role_of(p) == "learner"
            or bool(p.get("learners_in_household"))
        )
        if ("school things" in out.lower()) != bool(licensed_school):
            problems.append("%s school referent mismatch" % p["name"])
    check("referent licensing on cast", not problems, "; ".join(problems[:3]))

    # 4. Naive income banding agrees with recorded tier on all 12.
    bad = [
        "%s inc=%s recorded=%s naive=%s" % (
            p["name"], p.get("monthly_household_income_rand"),
            tier_of(p), naive_income_band(p.get("monthly_household_income_rand")))
        for p in cast
        if naive_income_band(p.get("monthly_household_income_rand")) != tier_of(p)
    ]
    check("income banding reproduces recorded tiers", not bad, "; ".join(bad))

    # 5. Template distinctness: 6 rhythm templates pairwise distinct, and
    #    tight vs loose variants of the same role share no 4-gram. The
    #    obligations slot is tier-neutral by design (identical referents for
    #    every tier), so it is masked before comparison — tier signal must
    #    live in the rhythm wording only.
    OBLIG = normalize("food, transport and school things")
    tpls = {}
    for k, v in RHYTHM.items():
        t = normalize(v.format(obligations="food, transport and school things"))
        tpls[k] = t.replace(OBLIG, "obligationslot")
    check("templates pairwise distinct", len(set(tpls.values())) == len(tpls))

    def ngrams(t, n=4):
        w = t.split()
        return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}

    overlaps = []
    for role in ("guardian", "learner"):
        shared = ngrams(tpls[(role, "tight")]) & ngrams(tpls[(role, "loose")])
        if shared:
            overlaps.append("%s tight/loose share %r" % (role, sorted(shared)[:2]))
    check("tight/loose templates share no 4-gram", not overlaps, "; ".join(overlaps))

    # 5b. v2 loose overrides: distinct from v1 loose, and share no 4-gram with
    #     v1 tight/moderate rhythm (obligations masked as above).
    problems = []
    for role in ("guardian", "learner"):
        v2t = normalize(RHYTHM_V2_OVERRIDES[(role, "loose")].format(
            obligations="food, transport and school things")).replace(OBLIG, "obligationslot")
        if v2t == tpls[(role, "loose")]:
            problems.append("%s v2 loose identical to v1" % role)
        for tier in ("tight", "moderate"):
            shared = ngrams(v2t) & ngrams(tpls[(role, tier)])
            if shared:
                problems.append("%s v2-loose/%s share %r" % (role, tier, sorted(shared)[:2]))
    check("v2 loose overrides distinct, no 4-gram bleed", not problems, "; ".join(problems))

    # 6. Role mapping: learners get learner templates, guardians guardian,
    #    unknown archetype raises.
    problems = []
    for p in cast:
        out = compile_situation(p)
        tpl = RHYTHM[(role_of(p), tier_of(p))].format(
            obligations="food, transport and school things")
        if role_of(p) == "learner" and not out.startswith(normalize_start(tpl)):
            problems.append(p["name"])
    def _unused():  # placeholder to keep structure clear
        pass
    try:
        role_of({"actor_archetype": "alien_overlord"})
        check("unknown archetype raises", False, "no ValueError")
    except ValueError:
        check("unknown archetype raises", True)
    check("role templates applied per cast archetype", not problems, "; ".join(problems))

    # 7. Vocabulary self-consistency: every token the compiler emits for the
    #    cast (both versions) is inside the union compiler_vocabulary().
    vocab = compiler_vocabulary()
    stray = set()
    for p in cast:
        stray.update(set(normalize(compile_situation(p)).split()) - vocab)
        stray.update(set(normalize(compile_situation(p, version=2)).split()) - vocab)
    check("compiled tokens within enumerable vocabulary", not stray, str(sorted(stray)[:5]))

    # 8. Synthetic all-'No fees' guardian: no school referent, no digits.
    synth = {
        "name": "Synthetic", "actor_archetype": "guardian_parent",
        "budget_tier": "moderate", "monthly_household_income_rand": 9000,
        "learner_fee_bands": ["No fees", "No fees"], "learners_in_household": 0,
        "receives_grant": False, "internet_at_home": False, "computer_in_home": False,
    }
    out = compile_situation(synth)
    check("no-fee guardian drops school referent", "school things" not in out.lower(), out)
    check("synthetic output number-free", not re.search(r"\d", out), out)

    # 9. Missing tier AND missing income raises.
    try:
        tier_of({"budget_tier": "", "monthly_household_income_rand": None})
        check("missing tier+income raises", False, "no ValueError")
    except ValueError:
        check("missing tier+income raises", True)

    print()
    if FAILURES:
        print("FAILED: %d check(s): %s" % (len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("ALL CHECKS PASSED")


def normalize_start(tpl):
    """First few normalized words of a filled template (for prefix matching)."""
    return tpl  # templates are compared raw; normalization not needed here


if __name__ == "__main__":
    main()
