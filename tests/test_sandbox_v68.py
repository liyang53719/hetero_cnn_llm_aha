import json,math,struct
from pathlib import Path
import pytest
from heteronpu.quant_operand_frontend import StorageFormat,decode_block,frontend_dot,frontend_self_test
from heteronpu.state_commit_protocol import StateCommitModel,StateDomain,StateWrite,protocol_stress
from heteronpu.trace_schema import TraceBundle,compare_traces,synthetic_trace,trace_schema_report
from heteronpu.ggml_node_adapter import GGMLNodeAdapter,GGMLNodeView,GGMLTensorView,adapter_contract_report
from heteronpu.l5_join_sensitivity import SensitivityPoint,evaluate,sensitivity_report
ROOT=Path(__file__).resolve().parents[1]
def test_quant_random():
 r=frontend_self_test(100);assert r['status']=='PASS' and r['maximum_dot_difference']<=1e-9 and not r['contract']['format_specific_multiplier_array']
def test_q8_groups():
 b=decode_block(StorageFormat.Q8_0,struct.pack('<e',.25)+bytes(range(32)));assert len(b)==2 and [x.offset for x in b]==[0,16] and b[-1].last
def test_fp16_tail():
 v=[math.sin(i/7) for i in range(37)];p=b''.join(struct.pack('<e',x) for x in v);a=[math.cos(i/11) for i in range(37)];b=decode_block(StorageFormat.FP16,p,fp16_element_count=37);assert [x.valid_count for x in b]==[16,16,5];exp=sum(struct.unpack('<e',p[2*i:2*i+2])[0]*a[i] for i in range(37));assert abs(frontend_dot(StorageFormat.FP16,p,a,fp16_element_count=37)-exp)<1e-12
def test_state_stress():
 r=protocol_stress(300);assert r['status']=='PASS' and r['counters']['protocol_errors']==0
def test_state_barrier():
 m=StateCommitModel();g=m.start(1,2,2,[StateDomain.KV,StateDomain.QSA_KV]);m.record_write(1,StateWrite(0,StateDomain.KV,0,9));m.acknowledge(1,StateDomain.KV)
 with pytest.raises(RuntimeError):m.commit(1,1)
 m.acknowledge(1,StateDomain.QSA_KV);r=m.commit(1,1);assert m.snapshot(2)[(StateDomain.KV,0)]==9 and not m.response_is_current(2,g) and m.response_is_current(2,r.new_generation)
def test_trace_roundtrip():
 a=synthetic_trace();b=TraceBundle.from_json(a.to_json());assert not compare_traces(a,b) and a.sha256==b.sha256
def test_trace_mutation():
 a=synthetic_trace();r=json.loads(a.to_json());r['nodes'][1]['outputs'][0]['payload_hex']=None;r['nodes'][1]['outputs'][0]['sha256']='0'*64;r['nodes'][1]['outputs'][0]['samples'][0][1]=99;assert compare_traces(a,TraceBundle.from_dict(r))
def test_trace_report():assert trace_schema_report()['status']=='PASS'
def _t(i):return GGMLTensorView(i,i,'BF16',(1,16),(16,1))
def test_adapter_report():r=adapter_contract_report();assert r['status']=='PASS' and r['unsupported_nodes']==['vision']
def test_adapter_missing():
 with pytest.raises(ValueError):GGMLNodeAdapter().adapt((GGMLNodeView('n','GGML_OP_ADD',('missing',),_t('o')),))
def test_join_base():r=evaluate(SensitivityPoint());assert r.block_cycles==108_118_970 and abs(r.tokens_per_second-338.2517292888433)<1e-12
def test_join_penalty():assert evaluate(SensitivityPoint(1.1,1.1,1.25,.6,.03,.02,64)).tokens_per_second<evaluate(SensitivityPoint()).tokens_per_second
def test_join_boundary():r=sensitivity_report();assert r['passing_cases'] and r['failing_cases'] and r['closest_pass']['result']['passes_300tps'] and not r['closest_fail']['result']['passes_300tps']
def test_quant_rtl_contract():
 t=(ROOT/'rtl/quant/ggml_operand_group_decode.sv').read_text();assert 'FORMAT_Q8_0' in t and 'FORMAT_Q6_K' in t and 'FORMAT_Q3_K' in t and 'quant_o [0:15]' in t and t.count('endmodule')==1
def test_state_rtl_contracts():
 for p in ('state_epoch_table.sv','state_stale_response_filter.sv','state_commit_barrier.sv','state_dirty_domain_tracker.sv'):
  t=(ROOT/'rtl/state'/p).read_text();assert t.count('module ')==1 and t.count('endmodule')==1
 assert 'DOMAINS=10' in (ROOT/'rtl/state/state_commit_barrier.sv').read_text().replace(' ','')
