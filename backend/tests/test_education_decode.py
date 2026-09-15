"""Education has its own missing codes; 8 and 9 are qualifications."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import attitude_donor_adapter as ada

@pytest.mark.parametrize("code,want",[(0,"none"),(1,"none"),(2,"primary"),(3,"primary"),
 (4,"secondary"),(5,"secondary"),(6,"tertiary"),(7,"tertiary"),(8,"tertiary"),(9,"tertiary"),
 (-1,None),(98,None),(99,None)])
def test_q94_education_codes(code,want):
    assert ada._ab_education_band(code)==want


def test_other_question_missing_codes_unchanged():
    assert ada._AB_MISSING=={-1.,8.,9.,98.,99.,998.,999.}


@pytest.mark.parametrize("code",[None,float("nan"),10,998,999])
def test_invalid_education_is_not_tertiary(code):
    assert ada._ab_education_band(code) is None


def test_refresh_changes_only_attitude_fields(monkeypatch):
    pytest.importorskip("pyreadstat")
    import copy
    import refresh_education_attitudes as fix
    original={"seed":1,"count":1,"personas":[{"id":"stable","name":"same","age":25,
     "income":1234,"beliefs":["keep"],"circumstances":[{"value":"keep"}],
     "attitudes":[{"topic":"gov_trust","stance":"low","source":"afrobarometer_r9_sa"}],
     "attitude_match_quality":"race_only"}]}
    snapshot=copy.deepcopy(original)
    def fake_fuse(people,seed,donors,source):
        assert seed==1 and source=="afrobarometer_r9_sa"
        return [{"name":"must not copy","income":99999,"beliefs":["new"],
         "attitudes":[{"topic":"gov_trust","stance":"high","source":source}],
         "attitude_match_quality":"exact"}]
    monkeypatch.setattr(fix,"fuse_attitudes",fake_fuse)
    updated,_=fix.refresh(original,[{}])
    assert original==snapshot
    assert fix.non_attitude_bytes(original)==fix.non_attitude_bytes(updated)
    assert updated["personas"][0]["attitudes"][0]["stance"]=="high"


def test_new_report_cannot_overwrite_old_tag(tmp_path,monkeypatch):
    pytest.importorskip("pyreadstat")
    import check_r10_realism as check
    monkeypatch.setattr(check,"OUT",tmp_path)
    (tmp_path/"realism_repair_results_test.json").write_text("keep")
    with pytest.raises(FileExistsError):
        check.repaired_main("test")
    assert (tmp_path/"realism_repair_results_test.json").read_text()=="keep"
    with pytest.raises(ValueError):
        check.repaired_main("../escape")
