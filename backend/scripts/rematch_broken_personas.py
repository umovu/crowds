"""Re-match only the library personas whose matched survey facts disagree with their own.

No model calls. Identity (name, age, income, household, story) is never touched.

A persona is broken when:
  * its Afrobarometer respondent lives in the other kind of area (urban vs rural);
  * it is a household-survey (GHS) persona whose own phone or smartphone answer
    disagrees with the respondent's phone facts;
  * its stored circumstances are not the recorded respondent's answers (post-build
    passes left the two out of step);
  * it is 75 or older and matched to someone under 75.

Broken personas are re-matched on the usual backoff ladder, with these changes:
  * age 60+ is split into 60-74 and 75+;
  * the respondent should live in the same kind of area and, for a traced GHS persona,
    agree on phone and smartphone. Phone gives way first, then area, rather than use a
    respondent more than 15 years older or younger, or match on race alone;
  * before a rung that drops age is used, respondents within 10 years are tried first.
    Where age still has to go, the respondents nearest in age are used.
Everyone else is left exactly as they are; traced GHS personas also record their GHS rows.

Dry run by default. --apply backs up the library, writes it, and writes a change log to
scripts/out/rematch_broken/ (changes.md, changes.json).
"""
import argparse
import collections
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pyreadstat  # noqa: E402
import attitude_donor_adapter as ada  # noqa: E402
import attitude_fuser as af  # noqa: E402

SEED = 0
AGE_WINDOW = 10
AGE_SLACK = 5
MAX_AGE_GAP = 15
PHONE = ("owns_phone", "phone_internet", "phone_use")
ALLOWED = {"attitudes", "beliefs", "attitude_match_quality", "circumstances", "survey_respondent", "ghs_person_rows"}
GHS_FINGERPRINT = ("age", "gender", "province", "education", "race", "geotype", "home_language",
                   "monthly_household_income_rand", "internet_at_home", "computer_in_home",
                   "receives_grant", "medical_aid")
ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "app/data/persona_library/personas.json"
OUT = ROOT / "scripts/out/rematch_broken"


# ── small facts ────────────────────────────────────────────────────────────

def area(person):
    return None if not person.get("geotype") else ("Urban" if person["geotype"] == "Urban" else "Rural")


def band2(age):
    band = ada.age_to_band(int(age))
    return "75+" if age >= 75 else ("60-74" if band == "60+" else band)


def facts(person):
    return {r["field"]: r["value"] for r in person.get("circumstances") or []}


def stances(person):
    return {r["topic"]: r["stance"] for r in person.get("attitudes") or []}


def is_ghs(person):
    return (person.get("internet_at_home") is not None or person.get("ghs_role")
            or person.get("income_provenance") == "ghs_2025_reported" or "household_farms" in person)


# ── survey links ───────────────────────────────────────────────────────────

def donors_with_age():
    """Afrobarometer donors, each with its real age and the 60-74 / 75+ age band."""
    df, _ = pyreadstat.read_sav(ada._AFROBAROMETER_PATH, usecols=["RESPNO", "Q1"])
    ages = {str(r.RESPNO): int(r.Q1) for r in df.itertuples() if r.Q1 == r.Q1}
    out = []
    for d in ada.load_donors():
        age = ages.get(d["respondent"])
        out.append(dict(d, _age=age, age_band=band2(age) if age is not None else d["age_band"]))
    return out


def trace_ghs(people):
    """GHS rows and phone answers per persona, found by its surveyed facts. A persona whose
    matching rows disagree on phones is left out."""
    import ghs_adapter as ga
    df, labels = ga._load()
    index = collections.defaultdict(list)
    for i, row in df.iterrows():
        try:
            index[tuple(ga._base_skeleton(row, labels).get(k) for k in GHS_FINGERPRINT)].append(i)
        except Exception:
            continue
    traced = {}
    for p in people:
        rows = index.get(tuple(p.get(k) for k in GHS_FINGERPRINT), [])
        answers = {(df.at[r, "Itp_cell"], df.at[r, "Itp_cell_sphone"]) for r in rows}
        if len(answers) != 1:
            continue
        cell, smart = answers.pop()
        if cell not in (1.0, 2.0):
            continue
        traced[p["id"]] = {"own": bool(cell == 1.0), "smart": bool(cell == 1.0 and smart == 1.0),
                           "rows": sorted(f"{df.at[r, 'uqnr']}:{int(df.at[r, 'personnr'])}" for r in rows)}
    return traced


def agrees_on_phone(gh, donor):
    c = donor.get("circumstances") or {}
    if c.get("owns_phone") is None or gh["own"] != (c.get("owns_phone") == "own"):
        return False
    return gh["smart"] == (c.get("phone_internet") == "yes")


def phone_contradictions(person, gh):
    f, out = facts(person), []
    if "owns_phone" in f and gh["own"] != (f["owns_phone"] == "own"):
        out.append("phone ownership")
    if "owns_phone" in f and gh["smart"] != (f.get("phone_internet") == "yes"):
        out.append("smartphone vs phone online")
    if gh["smart"] and f.get("internet_use") == "never":
        out.append("smartphone but never online")
    return out


def broken_reasons(person, donor, gh=None):
    if donor is None:
        return ["survey person not found"]
    why = []
    if area(person) and donor.get("geotype") != area(person):
        why.append("wrong area")
    if gh and phone_contradictions(person, gh):
        why.append("phone contradiction")
    # Only the Afrobarometer rows came from this persona's matched respondent. GHS
    # rows (metro, dwelling) are drawn from a demographic pool, so the respondent
    # has no answer to check them against — see scripts/add_ghs_geography.py.
    stored = [r for r in person.get("circumstances") or []
              if r.get("source") == "afrobarometer_r9_sa"
              and r.get("match_quality") != "population_draw"]
    if any((donor.get("circumstances") or {}).get(r["field"]) != r["value"] for r in stored):
        why.append("facts not from recorded survey person")
    if (person.get("age") or 0) >= 75 and (donor.get("_age") or 0) < 75:
        why.append("75+ matched to someone younger")
    return why


# ── matching ───────────────────────────────────────────────────────────────

def steps():
    """(keys, age window, quality label), in the order tried."""
    out = []
    for rung, keys in enumerate(af._BACKOFF_LADDER):
        if "age_band" not in keys:
            out.append((keys, AGE_WINDOW, af._QUALITY_LABELS[rung]))
        out.append((keys, None, af._QUALITY_LABELS[rung]))
    return out


def closest_in_age(cands, age, slack=AGE_SLACK):
    """Where age is no longer a match key, keep the respondents nearest in age (within
    `slack` years of the nearest one) instead of drawing from every age."""
    aged = [d for d in cands if d.get("_age") is not None]
    if not aged:
        return cands
    nearest = min(abs(d["_age"] - age) for d in aged)
    return [d for d in aged if abs(d["_age"] - age) <= nearest + slack]


# Rungs the area and phone rules may push a persona down to. Below these a persona would be
# matched on race alone, which the library does not allow; there the rules give way instead.
_CONSTRAINED_LABELS = {"exact", "age_backoff", "education_backoff", "province_backoff", "status_race"}


def rematch(person, pool, gh=None):
    """Three passes, each on the ladder: same area and agreeing phones; same area only;
    neither. In the first two a respondent more than MAX_AGE_GAP years away is not used, so
    area and phone never cost a big age gap; the last pass takes the nearest ages."""
    view = af._skeleton_join_view(person)
    if person.get("age") is not None:
        view["age_band"] = band2(person["age"])
    age = person.get("age")
    passes = [("area", "phone"), ("area",), ()]
    for rules in passes:
        for keys, window, label in steps():
            if rules and label not in _CONSTRAINED_LABELS:
                continue
            cands = af._matching_donors(view, pool, keys)
            if window is not None and age is not None:
                cands = [d for d in cands if d.get("_age") is not None and abs(d["_age"] - age) <= window]
            if "area" in rules and area(person):
                cands = [d for d in cands if d.get("geotype") == area(person)]
            if "phone" in rules and gh is not None:
                cands = [d for d in cands if agrees_on_phone(gh, d)]
            if rules and age is not None:
                cands = [d for d in cands if d.get("_age") is not None and abs(d["_age"] - age) <= MAX_AGE_GAP]
            if cands and window is None and "age_band" not in keys and age is not None:
                cands = closest_in_age(cands, age)
            if cands:
                return af._seeded_weighted_pick(cands, person, SEED), label
    donor, label = af._match_with_backoff(person, pool, SEED)
    return donor, label


class PoolStats:
    def __init__(self, pool):
        self.modal = af._population_modal_stances(pool)
        self.modal_circ = af._population_modal_circumstances(pool)
        self.dist_att = af._population_distributions(pool, "attitudes", ada.ATTITUDE_VOCAB)
        self.dist_circ = af._population_distributions(pool, "circumstances", ada.CIRCUMSTANCE_VOCAB)


def apply_donor(person, donor, quality, source, stats):
    """The same fill the fuser does, except a phone fact is never guessed."""
    full = dict(donor["attitudes"])
    per_dim = {dim: quality for dim in full}
    for dim in ada.ATTITUDE_VOCAB:
        if dim not in full:
            full[dim] = af._population_draw(stats.dist_att, dim, person, SEED) or stats.modal[dim]
            per_dim[dim] = "population_draw"
    rows, fresh = af._attitudes_to_fields(full, source, per_dim, donor.get("attitude_answers") or {})
    generated = {s for ph in af._BELIEF_PHRASING.values() for s in ph.values()} | set(af._RETIRED_PHRASING)
    kept_prose = [b for b in (person.get("beliefs") or []) if b not in generated]
    circ_rows = []
    for field in ada.CIRCUMSTANCE_VOCAB:
        value, field_quality = (donor.get("circumstances") or {}).get(field), quality
        if value is None:
            if field in PHONE:
                continue
            value = af._population_draw(stats.dist_circ, field, person, SEED) or stats.modal_circ.get(field)
            field_quality = "population_draw"
        if value is not None:
            circ_rows.append({"field": field, "value": value, "source": source, "match_quality": field_quality})
    person["attitudes"] = rows
    person["beliefs"] = fresh + kept_prose
    person["attitude_match_quality"] = quality
    person["circumstances"] = circ_rows
    person["survey_respondent"] = donor["respondent"]


def run(library, donors, traced):
    """(new library, change entries). Deterministic for (library, donors, traced)."""
    by_resp = {d["respondent"]: d for d in donors}
    new = copy.deepcopy(library)
    pools, changes = {}, []
    for person in new["personas"]:
        gh = traced.get(person["id"])
        if gh:
            person["ghs_person_rows"] = gh["rows"]
        old_donor = by_resp.get(person.get("survey_respondent") or "")
        why = broken_reasons(person, old_donor, gh)
        if not why:
            continue
        role = person.get("actor_archetype")
        key = role if role in ("learner", "educator") else None
        if key not in pools:
            pool, suffix = ada.donor_pool_for_role(key, donors)
            pools[key] = (pool, f"afrobarometer_r9_sa:{suffix}" if suffix else "afrobarometer_r9_sa", PoolStats(pool))
        pool, source, stats = pools[key]
        before = copy.deepcopy(person)
        donor, quality = rematch(person, pool, gh)
        apply_donor(person, donor, quality, source, stats)
        changes.append({"before": before, "after": person, "why": why,
                        "old_donor": old_donor, "new_donor": donor})
    for old, cur in zip(library["personas"], new["personas"]):
        moved = {k for k in set(old) | set(cur) if old.get(k) != cur.get(k)}
        assert moved <= ALLOWED, f"{old['name']}: unexpected change to {sorted(moved - ALLOWED)}"
    return new, changes


# ── change log ─────────────────────────────────────────────────────────────

def _shares(people, getter):
    """Share of the personas that carry each fact or view, per answer. A fact a persona does
    not carry (phone facts on an untraceable persona) is left out rather than counted as a no."""
    counts, carriers = collections.Counter(), collections.Counter()
    for p in people:
        for k, v in getter(p).items():
            counts[(k, v)] += 1
            carriers[k] += 1
    return {kv: n / carriers[kv[0]] * 100 for kv, n in counts.items()}


def change_log(library, new, changes, traced, donors):
    by_resp = {d["respondent"]: d for d in donors}
    old_people, new_people = library["personas"], new["personas"]

    def health(people, lookup):
        c = collections.Counter()
        for p in people:
            why = broken_reasons(p, by_resp.get(p.get("survey_respondent") or ""), traced.get(p["id"]))
            c["wrong area"] += "wrong area" in why
            c["phone contradiction"] += "phone contradiction" in why
            c["facts not from recorded survey person"] += "facts not from recorded survey person" in why
            c["75+ matched to someone younger"] += "75+ matched to someone younger" in why
            d = by_resp.get(p.get("survey_respondent") or "")
            c["age gap over 15 years"] += bool(d and d.get("_age") is not None and abs(d["_age"] - p["age"]) > 15)
        levels = collections.Counter(p.get("attitude_match_quality") for p in people)
        c["exact matches"] = levels.get("exact", 0)
        c["weak matches (province level or below)"] = sum(v for k, v in levels.items()
                                                          if k not in ("exact", "age_backoff", "education_backoff"))
        c["never online (%)"] = round(sum(facts(p).get("internet_use") == "never" for p in people) / len(people) * 100, 1)
        return c

    h_old, h_new = health(old_people, by_resp), health(new_people, by_resp)
    why_counts = collections.Counter(w for c in changes for w in c["why"])

    fact_old, fact_new = _shares(old_people, facts), _shares(new_people, facts)
    view_old, view_new = _shares(old_people, stances), _shares(new_people, stances)
    shifts = []
    for kind, a, b in (("fact", fact_old, fact_new), ("view", view_old, view_new)):
        for kv in set(a) | set(b):
            shifts.append((abs(b.get(kv, 0) - a.get(kv, 0)), kind, kv, a.get(kv, 0), b.get(kv, 0)))
    shifts.sort(reverse=True)

    groups = collections.defaultdict(lambda: {"n": 0, "changed": 0})
    changed_ids = {c["after"]["id"] for c in changes}
    for p in old_people:
        g = groups[p.get("actor_archetype")]
        g["n"] += 1
        g["changed"] += p["id"] in changed_ids
    group_rows = []
    for g, v in sorted(groups.items(), key=lambda kv: -kv[1]["changed"]):
        members_old = [p for p in old_people if p.get("actor_archetype") == g]
        members_new = [p for p in new_people if p.get("actor_archetype") == g]
        pct = lambda ppl, test: round(sum(test(p) for p in ppl) / len(ppl) * 100)
        group_rows.append((g, v["n"], v["changed"],
                           pct(members_old, lambda p: facts(p).get("internet_use") == "never"),
                           pct(members_new, lambda p: facts(p).get("internet_use") == "never"),
                           pct(members_old, lambda p: facts(p).get("lived_poverty") in ("moderate", "high")),
                           pct(members_new, lambda p: facts(p).get("lived_poverty") in ("moderate", "high")),
                           pct(members_old, lambda p: stances(p).get("health_service_satisfaction") == "dissatisfied"),
                           pct(members_new, lambda p: stances(p).get("health_service_satisfaction") == "dissatisfied")))

    import texture_generator as tg
    entries, stale = [], []
    for c in changes:
        b, a = c["before"], c["after"]
        fb, fa, sb, sa = facts(b), facts(a), stances(b), stances(a)
        fact_changes = {f: [fb.get(f), fa.get(f)] for f in set(fb) | set(fa) if fb.get(f) != fa.get(f)}
        view_changes = {t: [sb.get(t), sa.get(t)] for t in set(sb) | set(sa) if sb.get(t) != sa.get(t)}
        story = b.get("background_story") or ""
        story_hits = sorted(f for f in fb if fb[f] != fa.get(f)
                            and tg._CIRCUMSTANCE_GLOSS.get(f, {}).get(fb[f], "\0") in story)
        if story_hits:
            stale.append((b["name"], story_hits))
        od, nd = c["old_donor"] or {}, c["new_donor"]
        entries.append({
            "id": b["id"], "name": b["name"], "group": b.get("actor_archetype"), "age": b.get("age"),
            "area": b.get("geotype"), "province": b.get("province"), "why": c["why"],
            "survey_person_before": {"id": b.get("survey_respondent"), "age": od.get("_age"), "area": od.get("geotype")},
            "survey_person_after": {"id": a.get("survey_respondent"), "age": nd.get("_age"), "area": nd.get("geotype")},
            "match_level": [b.get("attitude_match_quality"), a.get("attitude_match_quality")],
            "facts_changed": fact_changes, "views_changed": view_changes, "story_states_old_fact": story_hits,
        })

    label = lambda kv: f"{kv[0]} = {kv[1]}"
    md = ["# Persona library re-match: what changed", "",
          f"Re-matched **{len(changes)} of {len(old_people)}** personas. Everyone else is unchanged. "
          "Names, ages, incomes, households and stories were not touched. No model calls.", "",
          "## Before and after (whole library)", "", "| | Before | After |", "|---|---|---|"]
    md += [f"| {k} | {h_old[k]} | {h_new[k]} |" for k in h_old]
    md += ["", "## Why personas were re-matched", "", "| Reason | Personas |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in why_counts.most_common()]
    md += ["", "## Biggest library-wide shifts (share of personas carrying that fact or view, percentage points)", "",
           "| Kind | Answer | Before | After | Change |", "|---|---|---|---|---|"]
    md += [f"| {kind} | {label(kv)} | {a:.0f}% | {b:.0f}% | {b - a:+.0f} |" for _, kind, kv, a, b in shifts[:20]]
    md += ["", "## By group", "",
           "| Group | Personas | Re-matched | Never online | Often short of money | Unhappy with clinics |",
           "|---|---|---|---|---|---|"]
    md += [f"| {g} | {n} | {ch} | {a}% → {b}% | {c}% → {d}% | {e}% → {f}% |"
           for g, n, ch, a, b, c, d, e, f in group_rows if ch]
    md += ["", f"## Stories that now state an old fact ({len(stale)})", "",
           "These background stories were written from the old facts. They need fact prompts on, or a rewrite.", ""]
    md += [f"- {n}: {', '.join(h)}" for n, h in stale]
    md += ["", "## Every re-matched persona", "",
           "| Persona | Group | Area | Why | Survey person before → after | Facts changed | Views changed |",
           "|---|---|---|---|---|---|---|"]
    for e in sorted(entries, key=lambda e: e["name"]):
        sp_b, sp_a = e["survey_person_before"], e["survey_person_after"]
        fc = "; ".join(f"{k}: {v[0]}→{v[1]}" for k, v in sorted(e["facts_changed"].items())) or "none"
        vc = len(e["views_changed"])
        md.append(f"| {e['name']} ({e['age']}) | {e['group']} | {e['area']} {e['province']} | {', '.join(e['why'])} | "
                  f"{sp_b['age']} {sp_b['area']} → {sp_a['age']} {sp_a['area']} | {fc} | {vc} |")
    report = {"rematched": len(changes), "personas": len(old_people), "before": dict(h_old), "after": dict(h_new),
              "why": dict(why_counts), "stories_with_old_facts": len(stale), "personas_changed": entries}
    return "\n".join(md) + "\n", report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    raw = LIBRARY.read_bytes()
    library = json.loads(raw)
    donors = donors_with_age()
    traced = trace_ghs([p for p in library["personas"] if is_ghs(p)])
    new, changes = run(library, donors, traced)
    md, report = change_log(library, new, changes, traced, donors)
    print(json.dumps({k: report[k] for k in ("personas", "rematched", "why", "before", "after", "stories_with_old_facts")},
                     ensure_ascii=False, indent=2))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "changes.md").write_text(md, encoding="utf-8")
    (OUT / "changes.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.apply:
        backup = LIBRARY.with_name("personas.backup-pre-rematch-broken.json")
        if backup.exists():
            raise SystemExit(f"{backup.name} already exists; refusing to overwrite it")
        backup.write_bytes(raw)
        LIBRARY.write_bytes((json.dumps(new, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"applied; backup at {backup.name}")


if __name__ == "__main__":
    main()
