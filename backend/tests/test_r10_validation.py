"""No application config, network, or LLM needed."""
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backtest_panel import spread


def test_wording_floor_retains_known_pairs_and_demotes_false_match():
    pytest.importorskip("pyreadstat")
    from build_r10_crosswalk import build, _R9, _R10
    if not _R9.exists() or not _R10.exists():
        pytest.skip("Local survey files not installed")
    rows = {r["r9"]: r for r in build()["mappings"]}
    assert not rows["Q85A"]["confident"]
    assert rows["Q85A"]["wording_overlap"] < rows["Q85A"]["wording_floor"]
    for a, b in [("Q37G", "Q37G"), ("Q38E", "Q38E"), ("Q78A", "Q67B"), ("Q47A", "Q48A")]:
        assert rows[a]["r10"] == b and rows[a]["confident"]


def test_spread_exact_flat_and_piled_room():
    truth = {"strongly_disagree": .1, "disagree": .2, "neither": .4,
             "agree": .2, "strongly_agree": .1}
    extremes = ["strongly_disagree", "strongly_agree"]
    exact = spread(Counter({k: v * 100 for k, v in truth.items()}), truth, extremes)
    flat = spread(Counter({k: 20 for k in truth}), truth, extremes)
    pile = spread(Counter(neither=100), truth, extremes)
    # Correct ranking by error is exact < flat < pile, not a universal ranking
    # independent of truth. Here the full, fixed truth makes it testable.
    assert exact["tvd_pp"] == 0
    assert exact["tvd_pp"] < flat["tvd_pp"] < pile["tvd_pp"]
    assert exact["pass"] and not flat["pass"] and not pile["pass"]
    assert pile["modal_excess_pp"] == pytest.approx(60)
    assert pile["tail_gap_pp"] == pytest.approx(-20)


def test_spread_rejects_empty_room_and_invalid_options():
    truth = {"low": .5, "high": .5}
    with pytest.raises(ValueError):
        spread(Counter(), truth, ["low", "high"])
    with pytest.raises(ValueError):
        spread(Counter(low=3), truth, ["low", "missing"])
    with pytest.raises(ValueError):
        spread(Counter(bogus=3), truth, ["low", "high"])


def test_weighted_variance_and_singleton_trap():
    pytest.importorskip("numpy")
    pytest.importorskip("pyreadstat")
    from check_r10_realism import explained_variance
    assert explained_variance([0, 2, 0, 2], [1, 1, 1, 1], ["a", "a", "b", "b"]) == pytest.approx(0)
    assert explained_variance([0, 0, 2, 2], [1, 1, 1, 1], ["a", "a", "b", "b"]) == pytest.approx(1)
    assert explained_variance([0, 2, 0, 2], [1, 1, 1, 1], ["a", "b", "c", "d"]) == pytest.approx(1)
    assert explained_variance([1, 1], [1, 2], ["a", "b"]) is None
    assert explained_variance([0, 2, 2], [3, 1, 1], ["a", "a", "b"]) == pytest.approx(.375)


def test_frozen_list_and_truth_free_questions():
    import hashlib
    import json
    pytest.importorskip("pyreadstat")
    from shortlist_r10_items import _IMPORTED
    root = Path(__file__).resolve().parents[1] / "scripts" / "out"
    lock = json.loads((root / "r10_item_lock.json").read_text(encoding="utf-8"))
    for name, digest in lock["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    items = json.loads((root / "r10_item_list.json").read_text(encoding="utf-8"))["items"]
    held = [i for i in items if i["bucket"] == "held_out"]
    assert len(held) == 12 and not {i["r9"] for i in held} & _IMPORTED
    assert sum(abs(i["urban_rural_gap_pp"]) >= 5-1e-9 for i in held) >= 3
    blind = json.loads((root / "r10_ask_scenarios.json").read_text(encoding="utf-8"))["items"]
    assert len(blind) == len(items)
    for ask_item, truth_item in zip(blind, items):
        assert set(ask_item) == {"id", "r9", "r10", "bucket", "framing", "answers", "extremes"}
        assert ask_item["answers"] == truth_item["answers"]
        assert ask_item["framing"] == truth_item["question"]


def test_employment_keys_use_survey_buckets_without_changing_personas():
    from attitude_donor_adapter import employment_to_canonical
    from attitude_fuser import _skeleton_join_view
    person = {"age": 30, "employment_status": "Discouraged job seeker"}
    assert _skeleton_join_view(person)["employment_status"] == "Other not economically active"
    assert person["employment_status"] == "Discouraged job seeker"
    assert employment_to_canonical(" Employed ") == "Employed"
    assert employment_to_canonical("Unemployed") == "Unemployed"
    assert employment_to_canonical("unexpected") is None
    assert employment_to_canonical(None) is None
