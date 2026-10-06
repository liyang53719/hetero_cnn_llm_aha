"""Independent-chain plumbing, admitted embedding IDs and fail-closed links."""
from copy import deepcopy

import numpy as np
import pytest

from heteronpu import qwen35_prefix_reference as prefix
from heteronpu.model_geometry import ModelContractError


def inputs():
    return np.arange(128,dtype=np.int64).reshape(1,128), np.arange(256*1024,dtype=np.float32).reshape(256,1024)/1024


def test_exact_original_embedding_indices_no_remapping():
    ids,rows=inputs();ids=ids[:,::-1]
    actual=prefix.embedding_lookup(ids,rows)
    assert actual.dtype==np.float64 and np.array_equal(actual,rows[ids])
    actual[0,0,0]=99
    assert rows[127,0]!=99


@pytest.mark.parametrize("change",[
    lambda ids,rows:(ids.astype(np.float32),rows),lambda ids,rows:(ids.astype(bool),rows),
    lambda ids,rows:(ids[0],rows),lambda ids,rows:(ids-1,rows),lambda ids,rows:(ids+200,rows),
    lambda ids,rows:(ids,rows[:-1]),lambda ids,rows:(ids,rows.astype(np.int32)),
    lambda ids,rows:(ids,rows*np.nan),
])
def test_embedding_rejects_invalid_scope(change):
    with pytest.raises(ModelContractError):prefix.embedding_lookup(*change(*inputs()))


def test_full_prefix_passes_own_activations_and_own_carried_states(monkeypatch):
    ids,rows=inputs();seen=[]
    def fake(x,w,past=None,**kwargs):
        layer=w["layer"]
        seen.append((layer,x.copy(),past,kwargs))
        y=x+(layer+1)+(0 if past is None else 0.5)
        state_shape=(1,2,128,256) if layer==3 else (1,)
        return y,(np.full(state_shape,layer+11.0),np.full(state_shape,layer+21.0))
    monkeypatch.setattr(prefix,"gdn_forward",fake);monkeypatch.setattr(prefix,"attention_forward",fake)
    weights={i:{"layer":i} for i in range(4)}
    emb,cold,state=prefix.forward(ids,rows,weights)
    emb2,carried,state2=prefix.forward(ids+128,rows,weights,state,position_start=128)
    assert [x[0] for x in seen]==[0,1,2,3]*2
    for records,offset in ((cold,0),(carried,4)):
        for i in range(1,4):assert np.array_equal(seen[offset+i][1],records[i-1]["output"])
    for i in range(4):
        assert seen[i][2] is None
        assert np.array_equal(seen[i+4][2][0],state[i][0])
    assert np.array_equal(cold[3]["output"],emb+10)
    assert np.array_equal(carried[3]["output"],emb2+12)
    assert seen[7][3]["position_start"]==128


@pytest.mark.parametrize("mutate",[
    lambda r:r.pop(),lambda r:r.reverse(),lambda r:r[1].update(layer=True),
    lambda r:r[1].update(input=np.zeros((1,128,1024))),
    lambda r:r[2].update(output=np.full((1,128,1024),np.nan)),
    lambda r:r[0].update(input=np.zeros((1,127,1024))),
])
def test_activation_chain_rejects_replacement_reorder_nonfinite(mutate):
    x=np.zeros((1,128,1024));records=[{"layer":i,"input":x+i,"output":x+i+1} for i in range(4)]
    assert prefix.verify_activation_links(x,records)
    mutate(records)
    with pytest.raises(ModelContractError):prefix.verify_activation_links(x,records)


@pytest.mark.parametrize("past,offset",[(None,128),({},0),({},128),(None,True),(None,-1),(None,256)])
def test_state_position_pair_rejected(past,offset):
    with pytest.raises(ModelContractError):prefix.forward(*inputs(),{i:{} for i in range(4)},past,position_start=offset)


def test_missing_layer_rejected():
    with pytest.raises(ModelContractError):prefix.forward(*inputs(),{i:{} for i in range(3)})


def test_runner_validation_failure_never_publishes_success(tmp_path,monkeypatch):
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/"scripts/run_qwen35_prefix_chain.py"
    spec=importlib.util.spec_from_file_location("qwen35_prefix_runner_test",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def reject(*args):raise ModelContractError("injected corrupt payload")
    monkeypatch.setattr(module.pinned_gdn_payload,"load_payload",reject)
    target=tmp_path/"new_output"
    with pytest.raises(ModelContractError,match="corrupt payload"):
        module.run(tmp_path,tmp_path,tmp_path,tmp_path,target)
    assert not target.exists()
    target.mkdir();(target/"result.json").write_text("old result")
    with pytest.raises(ModelContractError,match="fresh or empty"):
        module.run(tmp_path,tmp_path,tmp_path,tmp_path,target)
    assert (target/"result.json").read_text()=="old result"
