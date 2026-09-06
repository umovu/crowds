"""Invariant tests for the model-free, leave-one-person-out realism repair."""
import sys
from pathlib import Path
import pytest
np=pytest.importorskip("numpy")
pytest.importorskip("pyreadstat")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from check_r10_realism import prediction_weights, heldout_reduction, balance_weights


def test_singletons_cannot_explain_themselves():
    views=[{"group":str(i)} for i in range(20)]
    weights=np.ones(20)
    model,base,rungs=prediction_weights(views,weights,[["group"],[]])
    assert np.all(np.diag(model)==0) and np.all(np.diag(base)==0)
    assert np.allclose(model,base) and np.all(rungs==1)
    assert heldout_reduction([i%2 for i in range(20)],weights,model,base,2)["reduction"]==pytest.approx(0)


def test_own_answer_cannot_change_own_prediction():
    views=[{"group":"a"} for _ in range(8)]
    model,base,_=prediction_weights(views,np.ones(8),[["group"],[]])
    a=np.eye(2)[[0,0,0,1,1,1,0,1]]
    b=a.copy();b[0]=[0,1]
    assert np.allclose((model@a)[0],(model@b)[0])
    assert np.allclose((base@a)[0],(base@b)[0])


def test_real_group_signal_survives_holdout_but_balanced_noise_does_not():
    views=[{"group":str(i//10)} for i in range(20)]
    w=np.ones(20)
    model,base,_=prediction_weights(views,w,[["group"],[]])
    assert heldout_reduction([0]*10+[1]*10,w,model,base,2)["reduction"]==pytest.approx(1)
    assert heldout_reduction([0,1]*10,w,model,base,2)["reduction"] < 0


def test_small_or_weight_dominated_cells_back_off():
    views=[{"g":"a"}]*5+[{"g":"b"}]*6
    w=np.array([1]*5+[100,1,1,1,1,1],float)
    m,b,r=prediction_weights(views,w,[["g"],[]])
    assert np.all(r[:5]==1) # fewer than five OTHER people
    assert r[6]==1 # five peers, but one dominates their weights
    assert np.allclose(m.sum(axis=1),1) and np.allclose(np.diag(m),0)
    assert b[0,5]==pytest.approx(100/(w.sum()-w[0]))


def test_constant_answers_are_uninformative():
    v=[{"g":"a"}]*8
    m,b,_=prediction_weights(v,np.ones(8),[["g"],[]])
    assert heldout_reduction([0]*8,np.ones(8),m,b,2)["reduction"] is None


def test_balance_matches_targets_without_using_answers():
    lv=[{"g":"a"},{"g":"a"},{"g":"a"},{"g":"b"}]
    rv=[{"g":"a"},{"g":"b"}]
    w,info=balance_weights(lv,rv,[1,1],["g"])
    assert info["status"]=="converged"
    assert w[:3].sum()/w.sum()==pytest.approx(.5)
    assert w[3]/w.sum()==pytest.approx(.5)
    assert info["effective_n"]==pytest.approx(3)


def test_balance_does_not_invent_absent_people():
    w,info=balance_weights([{"g":"a"}],[{"g":"a"},{"g":"b"}],[1,1],["g"])
    assert w is None and info["status"]=="unsupported categories"


def test_bad_weights_rejected():
    with pytest.raises(ValueError):
        prediction_weights([{"g":"a"}]*2,[1,0],[["g"],[]])


def test_education_audit_separates_valid_qualifications_from_refusals(monkeypatch):
    from types import SimpleNamespace
    import check_r10_realism as check
    monkeypatch.setattr(check.ada,"_ab_education_band",lambda code: None)
    frame={"Q94":np.array([8,8,9,98])}
    meta=SimpleNamespace(variable_value_labels={"Q94":{8:"University completed",9:"Post-graduate",98:"Refused"}})
    audit=check.education_decode_audit(frame,meta)
    assert audit["valid_education_rejected_n"]==3
    assert not audit["rows"][-1]["valid_education_rejected"]
