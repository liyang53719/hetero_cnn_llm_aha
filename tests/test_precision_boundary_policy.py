import json
from pathlib import Path
import pytest
from heteronpu.precision_policy import fp32_boundary_indices,node_dtype

def test_producer_policy_applies_to_alias_consumers():
    producer={'operation':'l0.oproj','roots':{'dst':4136},'root_bindings':{'4136':{'kind':'ggml_node','index':26}}}
    ids=fp32_boundary_indices([producer])
    assert node_dtype({'kind':'ggml_node','index':26,'name':'consumer_alias'},ids)=='FP32'
    assert node_dtype({'kind':'ggml_node','index':25},ids)=='BF16'
    assert node_dtype({'kind':'ggml_node','index':26},frozenset())=='BF16'

def test_reject_non_node_boundary():
    with pytest.raises(ValueError):
        fp32_boundary_indices([{'operation':'l0.down','roots':{'dst':1},'root_bindings':{'1':{'kind':'gguf_tensor'}}}])

def test_real_28_layer_manifest():
    root=Path(__file__).resolve().parents[1]
    commands=[json.loads(s) for s in (root/'reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl').read_text().splitlines()]
    ids=fp32_boundary_indices(commands)
    assert len(ids)==28*4
    for c in commands:
        op=c['operation'].rsplit('.',1)[-1]
        for role,idx in c['roots'].items():
            if str(idx) not in c['root_bindings']:continue
            b=c['root_bindings'][str(idx)]
            if b['kind']!='ggml_node':continue
            dtype=node_dtype(b,ids)
            if op in {'q','k','v','oproj','gate','up','down'} and role=='src0':
                assert dtype=='BF16', (c['operation'],role)
            if op in {'oproj','down','attn_residual','residual'} and role=='dst':
                assert dtype=='FP32'
