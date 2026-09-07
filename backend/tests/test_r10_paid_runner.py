"""Offline checks for the paid runner: mocked provider only, no real requests."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import backtest_panel as panel


def item():
    return {"r9":"Q1","r10":"Q1","bucket":"held_out","question":"Choose?",
            "answers":["Yes","No"],"extremes":["Yes","No"],
            "r10_columns":["Urban","Rural","Men","Women","Total"],
            "r10_rows":{"Yes":[60,40,55,45,50],"No":[40,60,45,55,50]},
            "subgroup_focus_answer":"Yes"}


def test_truth_null_is_not_zero_and_rounding_is_normalized():
    obj=item()
    assert panel.r10_distribution(obj)=={"Yes":.5,"No":.5}
    obj["r10_rows"]["No"][-1]=None
    assert panel.r10_distribution(obj) is None
    obj["r10_rows"]["No"][-1]=49.9
    assert sum(panel.r10_distribution(obj).values())==pytest.approx(1)
    obj["r10_rows"]["No"][-1]=40
    assert panel.r10_distribution(obj) is None


def test_weight_fit_and_missing_category_are_explicit():
    rows=[{"gender":"M"},{"gender":"M"},{"gender":"F"},{"gender":None}]
    weights,report=panel.rake_library(rows,{"gender":{"M":40,"F":59,"X":1}})
    assert weights[-1]==0
    assert sum(weights[:2])/sum(weights)==pytest.approx(40/99)
    assert report["excluded_target_percent"]=={"gender":{"X":1}}
    assert report["excluded_library_records"]==1


def test_subgroup_sign_size_and_small_group_guard():
    people={i:{"demographics":{"location":"Urban" if i<6 else "Rural"},"weight":1} for i in range(1,11)}
    rows=[{"slot":i,"answer":"Yes" if i<6 else "No"} for i in people]
    result=panel.r10_gap(rows,people,item(),"location",("Urban","Rural"),"Yes")
    assert result["predicted_pp"]==100
    assert result["real_pp"]==20
    assert result["absolute_error_pp"]==80
    assert result["sign_correct"]
    assert not panel.r10_gap(rows[:-1],people,item(),"location",("Urban","Rural"),"Yes")["available"]


def fixture(tmp_path,monkeypatch):
    scripts=tmp_path/"backend/scripts"
    out=scripts/"out"
    out.mkdir(parents=True)
    monkeypatch.setattr(panel,"_HERE",str(scripts))
    method={"runner_sha256":panel._sha(Path(panel.__file__).read_bytes()),"model":"test-model","base_url":"https://example.invalid/v1",
            "temperature":.7,"max_tokens":220,"timeout_seconds":1,"concurrency":2,"estimate_input_usd_per_million":1.32,
            "estimate_output_usd_per_million":3.96,"cost_ceiling_usd":10,"planned_requests":10,
            "limitations":["Test only"],"weighting":{}}
    truth=item()
    blind={"id":"Q1_Q1","r9":"Q1","r10":"Q1","bucket":"held_out","framing":"Choose?","answers":["Yes","No"],"extremes":["Yes","No"]}
    people=[{"slot":i,"name":"Test","context":"Fixture","weight":1,"demographics":{"location":"Urban" if i<6 else "Rural","gender":"Male" if i<6 else "Female"}} for i in range(1,11)]
    manifest={"method":method,"items":[blind],"participants":people,"system":"Fixture"}
    panel._exclusive_json(out/"r10_manifest_1.json",manifest)
    panel._exclusive_json(out/"r10_method_1.json",{"manifest_sha256":panel._sha((out/"r10_manifest_1.json").read_bytes())})
    (tmp_path/".env").write_text("SIM_LLM_API_KEY=fake\nSIM_LLM_MODEL=test-model\nSIM_LLM_BASE_URL=https://example.invalid/v1\n")
    return out,truth


def test_ask_without_truth_then_reveal_saved_answers(tmp_path,monkeypatch):
    import requests
    out,truth=fixture(tmp_path,monkeypatch)
    calls=[]
    class Reply:
        status_code=200
        def json(self):
            return {"model":"test-model","choices":[{"message":{"content":"ANSWER: Yes"},"finish_reason":"stop"}],
                    "usage":{"prompt_tokens":10,"completion_tokens":3,"total_tokens":13}}
    def fake(*a,**kw):
        calls.append(kw)
        return Reply()
    monkeypatch.setattr(requests,"post",fake)
    panel.ask_r10(1)  # Truth file does not exist at all during ask.
    assert len(calls)==10
    assert all(c["json"]["enable_thinking"] is False for c in calls)
    assert json.loads((out/"r10_receipt_1.json").read_bytes())["usage"]["total_tokens"]==130
    with pytest.raises(FileExistsError):
        panel.ask_r10(1)
    assert len(calls)==10
    panel._exclusive_json(out/"r10_item_list.json",{"items":[truth]})
    panel._exclusive_json(out/"r10_item_lock.json",{"files":{"r10_item_list.json":panel._sha((out/"r10_item_list.json").read_bytes())}})
    panel.reveal_r10(1)
    report=json.loads((out/"r10_results_1.json").read_bytes())
    assert report["summary"]["held_out"]["unweighted"]["mean_tvd_pp"]==50
    assert report["sample_weight_effective_n"]==10
    with (out/"r10_run_1.jsonl").open("a") as f:
        f.write(" ")
    with pytest.raises(ValueError,match="changed"):
        panel.reveal_r10(1)


def test_r10_excludes_minors_and_unknown_ages_before_sampling():
    people = [{"age": a} for a in [15, 17, 18, 65, None, float("nan"), True]]
    assert panel.eligible_adults(people) == [{"age":18},{"age":65}]
    assert len(people) == 7



def test_adult_sensitivity_excludes_minor_answers_without_new_calls(tmp_path, monkeypatch):
    import requests
    out, truth = fixture(tmp_path, monkeypatch)
    manifest_path = out / "r10_manifest_1.json"
    manifest = json.loads(manifest_path.read_bytes())
    library = tmp_path / "backend/app/data/persona_library/personas.json"
    library.parent.mkdir(parents=True)
    library.write_bytes(b"fixture-library")
    manifest["method"]["library_sha256"] = panel._sha(library.read_bytes())
    for person in manifest["participants"]:
        person["profile"] = {"age":17 if person["slot"]<=2 else 30}
        person["name"] = "Minor" if person["slot"]<=2 else "Adult"
    manifest_path.write_bytes(panel._json_bytes(manifest))
    (out/"r10_method_1.json").write_bytes(panel._json_bytes({"manifest_sha256":panel._sha(manifest_path.read_bytes())}))
    class Reply:
        status_code=200
        def __init__(self, answer): self.answer=answer
        def json(self):
            return {"model":"test-model","choices":[{"message":{"content":"ANSWER: "+self.answer},"finish_reason":"stop"}],
                    "usage":{"prompt_tokens":10,"completion_tokens":3,"total_tokens":13}}
    calls=[]
    def fake(*a,**kw):
        calls.append(1)
        return Reply("No" if "Minor" in kw["json"]["messages"][1]["content"] else "Yes")
    monkeypatch.setattr(requests,"post",fake)
    panel.ask_r10(1)
    monkeypatch.setattr(panel,"adult_subset_weights",lambda participants:({k:p for k,p in participants.items() if p["profile"]["age"]>=18},{"fixture":True}))
    panel._exclusive_json(out/"r10_item_list.json",{"items":[truth]})
    panel._exclusive_json(out/"r10_item_lock.json",{"files":{"r10_item_list.json":panel._sha((out/"r10_item_list.json").read_bytes())}})
    panel.reveal_r10(1,adults_only=True)
    report=json.loads((out/"r10_results_1_adults.json").read_bytes())
    assert report["room_size"]==8
    assert report["analysis_completed"]==8
    assert report["results"][0]["unweighted_counts"]=={"Yes":8}
    assert report["summary"]["held_out"]["unweighted"]["mean_tvd_pp"]==50
    assert len(calls)==10
