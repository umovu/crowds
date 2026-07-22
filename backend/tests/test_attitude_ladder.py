"""Guard the attitude-matching backoff ladder — LLM off, no network.

The ladder in attitude_fuser was chosen by held-out evaluation
(backend/scripts/eval_attitude_match.py, 5-fold), scored on *subgroup
distribution fidelity*: total variation distance between the stance
distribution a ladder ASSIGNS to a demographic subgroup and the distribution
that subgroup really holds. Lower is better.

Why not per-person accuracy: assigning every persona the modal stance maximises
accuracy (49.2% vs ~42%) while giving the entire library one identical opinion.
Accuracy is actively misleading here; TVD is the objective. These tests exist so
a future ladder edit cannot quietly regress that, the way adding race as a join
key silently broke GHS education skeletons until it was measured.

Thresholds are set with headroom above the values measured when the ladder was
adopted, so normal drift doesn't flake but a real regression fails:

    shipping ladder   overall TVD 2.63   race-subgroup TVD 2.06   modal baseline 50.8

Skipped entirely when the licensed Afrobarometer microdata isn't present.
"""

import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))

# Ceilings, not targets. Set ~40% above measured so ordinary variation passes.
MAX_OVERALL_TVD = 4.0
MAX_RACE_TVD = 3.5
# Every race group must stay usable. The 24% minority groups are the whole point
# of matching on race; an overall win that comes from the 76% majority is not a win.
MAX_PER_RACE_TVD = 12.0


def _load(name):
    sys.path.insert(0, SCRIPTS)
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def evaluated():
    """Score the SHIPPING ladder — read from attitude_fuser, not copied here, so
    the test follows the ladder rather than a stale duplicate of it."""
    ada = _load("attitude_donor_adapter")
    if not os.path.exists(ada._AFROBAROMETER_PATH):
        pytest.skip("Afrobarometer microdata not present (licensed, gitignored)")
    fuser = _load("attitude_fuser")
    ev = _load("eval_attitude_match")
    donors = ada.load_afrobarometer(ada._AFROBAROMETER_PATH)
    return ev, donors, ev.evaluate(donors, fuser._BACKOFF_LADDER, 5, 0)


def test_beats_the_random_baseline(evaluated):
    """A ladder that can't beat a weighted random draw isn't earning its keep."""
    ev, donors, score = evaluated
    random_baseline = ev.evaluate_baseline(donors, "random", 5, 0)
    assert score.tvd() < random_baseline.tvd(), (
        f"ladder TVD {score.tvd():.2f} is no better than random {random_baseline.tvd():.2f}"
    )


def test_modal_baseline_is_terrible_on_the_objective(evaluated):
    """Pins WHY accuracy is not the objective: the modal baseline wins on accuracy
    and is catastrophic on distribution. If this ever passes narrowly, the metric
    has stopped measuring what we think it measures."""
    ev, donors, score = evaluated
    modal = ev.evaluate_baseline(donors, "modal", 5, 0)
    assert modal.acc > score.acc, "modal baseline should win on per-person accuracy"
    assert modal.tvd() > 10 * score.tvd(), (
        f"modal TVD {modal.tvd():.1f} should dwarf the ladder's {score.tvd():.2f}"
    )


def test_overall_and_race_fidelity(evaluated):
    _, _, score = evaluated
    assert score.tvd() <= MAX_OVERALL_TVD, f"overall TVD regressed to {score.tvd():.2f}"
    assert score.tvd("race") <= MAX_RACE_TVD, f"race TVD regressed to {score.tvd('race'):.2f}"


def test_no_race_group_is_abandoned(evaluated):
    """The failure mode this catches: a change that improves the average by serving
    the 76% African/Black majority better while degrading everyone else."""
    from collections import Counter

    _, _, score = evaluated
    worst = {}
    for key, truth in score.true_dist.items():
        grouping, group, _dim = key
        if grouping != "race" or group in ("None", "nan"):
            continue
        n = sum(truth.values())
        if n < 20:
            continue
        pred = score.pred_dist.get(key, Counter())
        m = sum(pred.values()) or 1
        tvd = 0.5 * sum(abs(truth[s] / n - pred[s] / m) for s in set(truth) | set(pred)) * 100
        acc, w = worst.get(group, (0.0, 0.0))
        worst[group] = (acc + tvd * n, w + n)

    for group, (acc, w) in worst.items():
        value = acc / w
        assert value <= MAX_PER_RACE_TVD, f"race group '{group}' TVD regressed to {value:.1f}"


def test_every_skeleton_source_supplies_the_join_keys():
    """race is a join key. A skeleton source that omits it matches only the 2 donors
    with unknown race — which is exactly how GHS education skeletons broke: 39 of 40
    drew from the same two respondents, with zero exact matches and no test failing.
    """
    ada = _load("attitude_donor_adapter")
    fuser = _load("attitude_fuser")
    ps = _load("persona_sampler")
    if not os.path.exists(ps._DEFAULT_DTA):
        pytest.skip("QLFS microdata not present (licensed, gitignored)")

    sources = {
        "civic": lambda: ps.sample_skeletons(20, seed=1),
        "teachers": lambda: ps.sample_teacher_skeletons(5, seed=1),
        "communal_farmers": lambda: ps.sample_communal_farmer_skeletons(5, seed=1),
        "smallholder_farmers": lambda: ps.sample_smallholder_owner_skeletons(5, seed=1),
        "professionals": lambda: ps.sample_professional_skeletons(5, seed=1),
    }
    try:
        ghs = _load("ghs_adapter")
        if os.path.exists(ghs._PERSON_DTA):
            sources["education_ghs"] = lambda: ghs.sample_education_skeletons(
                n_learners=5, n_guardians=5, seed=1)
    except Exception:  # noqa: BLE001 — GHS is optional locally
        pass

    # KNOWN PRE-EXISTING GAP, deliberately not hidden: some GHS education skeletons
    # carry employment_status=None — 15-17 year-old learners sit outside the labour-force
    # universe the field describes. It predates race becoming a join key and needs a data
    # decision (is a schoolchild "Other not economically active"?), not a test tweak. Race
    # is asserted strictly everywhere; this key is asserted strictly everywhere else.
    known_gaps = {("education_ghs", "employment_status")}
    gaps_seen = []

    for name, make in sources.items():
        skeletons = make()
        view_keys = set(fuser._skeleton_join_view(skeletons[0]))
        assert set(ada.JOIN_KEYS) <= view_keys, (
            f"{name}: join view is missing {set(ada.JOIN_KEYS) - view_keys}")
        for key in ada.JOIN_KEYS:
            filled = sum(1 for s in skeletons if fuser._skeleton_join_view(s).get(key))
            if filled == len(skeletons):
                continue
            if (name, key) in known_gaps:
                gaps_seen.append(f"{name}.{key} {filled}/{len(skeletons)}")
                continue
            raise AssertionError(
                f"{name}: only {filled}/{len(skeletons)} skeletons carry join key '{key}'")

    # Fail if a known gap silently disappears too — either it was fixed (update this
    # test) or the source stopped being exercised (worse).
    assert gaps_seen, (
        "expected the known GHS employment_status gap; it is absent — was it fixed, "
        "or did the GHS source stop being tested?")
