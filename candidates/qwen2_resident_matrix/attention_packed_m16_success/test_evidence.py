"""Cold checks for this historical safe projection; cannot authenticate a new run."""
import copy
import hashlib
import json
import math
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent
FIELDS={'dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16'}
CAUSAL={'scores','logits','prob','softmax_fp32'}
FALSE=('numerical_acceptance','full_29_node_acceptance','m128_acceptance','rtl_execution','hardware_recipe_acceptance','useful_wall_mac_90_percent','old_pass_inherited','future_score_materialization','new_official_forward_executed')
COUNTS=dict(rows=16,runtime_source_files=316,public_completions=21,owner_jobs=17,sealed_actual_outputs=19,assigned_official_gates=27,official_observed_stages=28,diagnostic_fp32_stages=1)
BUDGET=dict(numeric_seconds=900,work_seconds=924,cleanup_seconds=5,outer_seconds=930)
TOP_KEYS=set('actual_chain_completion_verified artifacts assigned_official_gates budget capture_fields cleanup_complete committed_cpp_sha256 contract_sha256 diagnostic_fp32_stages fixed_arithmetic_pass full_29_node_acceptance future_score_materialization generated_entry_pins_sha256 git_head hardware_recipe_acceptance m128_acceptance missing_nodes native_execution_reused new_official_forward_executed new_reference_producers_executed_before_this_run numerical_acceptance numerical_run_started observed_exit_codes official_observed_gates official_observed_stages old_pass_inherited original_entry_pins_sha256 owner_jobs packed_multiplicity partially_observed_nodes previous_failed_attempt_preserved profile public_completions repair_pins_sha256 rows rtl_execution runtime_source_files schema sealed_actual_outputs source_manifest_compact_sha256 source_manifest_pretty_sha256 status timing useful_wall_mac_90_percent wrapper_filemap_sha256 wrapper_manifest_sha256'.split())
GATE_KEYS={'coverage','observed_elements','unobserved_elements','passed','contract','max_abs','mean_abs','actual_f32_sha256','reference_f32_sha256'}
CAPTURE_KEYS={'frequency_sha256','identical_repeats','observed_words','presence_sha256','raw_sha256','shape','words','writes'}
def need(ok):
    if not ok:raise ValueError('invalid historical evidence')
def validate(e):
    json.dumps(e,allow_nan=False)
    need(type(e) is dict and set(e)==TOP_KEYS)
    need(e['profile']=='qwen2-packed-m16-host-job-success-evidence-v1' and e['status']=='PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY')
    need(e['contract_sha256']=='f5e3c0ecc342019923dc8759168e9097c9d0e1ffc1d7eac0a56032569fa33882')
    need(e['source_manifest_compact_sha256']=='c27020ddcc0965e18026063640e54d2daa2e00ec7f17fbbb82730bd9c233bfdf')
    need(e['source_manifest_pretty_sha256']=='0153488576891aa9d54e0f2aef231a3f08a8ad1c10d96765a52e4052d8453a8e')
    for k,v in COUNTS.items():need(type(e[k])is int and e[k]==v)
    for k in FALSE:need(e[k] is False)
    for k in ('actual_chain_completion_verified','cleanup_complete','fixed_arithmetic_pass','numerical_run_started','previous_failed_attempt_preserved','native_execution_reused','new_reference_producers_executed_before_this_run'):need(e[k] is True)
    need(set(e['observed_exit_codes'])=={'launcher','child'})
    need(all(type(v)is int and v==0 for v in e['observed_exit_codes'].values()))
    need(set(e['budget'])==set(BUDGET))
    for k,v in BUDGET.items():need(type(e['budget'][k])is int and e['budget'][k]==v)
    need(e['missing_nodes']==['explicit_mask_tensor'] and set(e['partially_observed_nodes'])==CAUSAL)
    gates=e['official_observed_gates'];need(len(gates)==28 and CAUSAL<=set(gates))
    for name,g in gates.items():
        need(type(g)is dict and set(g)==GATE_KEYS)
        need(g['passed'] is (None if name=='softmax_fp32' else True))
        need(g['contract'] is None if name=='softmax_fp32' else g['contract'] in ('spec/numerical_contract.md:operator','spec/numerical_contract.md:block'))
        for k in ('max_abs','mean_abs'):need(type(g[k])in(int,float) and math.isfinite(g[k]) and g[k]>=0)
        for k in ('observed_elements','unobserved_elements'):need(type(g[k])is int and g[k]>=0)
        if name in CAUSAL:need(g['coverage']=='actual_causal_positions_only' and g['observed_elements']==1632 and g['unobserved_elements']==1440)
        else:need(g['coverage']=='complete' and g['unobserved_elements']==0)
    need(set(e['capture_fields'])==FIELDS)
    for name,f in e['capture_fields'].items():
        need(set(f)==CAPTURE_KEYS)
        expected=26112 if name=='dot_parts' else 576 if name=='normalizer' else 24576 if name in {'pv_raw','pv_bf16'} else 1632
        need(type(f['writes'])is int and f['writes']==expected and f['observed_words']==expected and f['identical_repeats']==0)
    need(e['packed_multiplicity']==dict(causal_field=1,legacy_normalizer_repeats='8*(query+1)',legacy_probability_repeats=8,normalizer_per_head_query=1,pv_word=1,synthetic_repeats=0))
    need(e['timing']['launcher_wall_seconds']==591.28026 and e['timing']['numeric_host_wall_seconds']<900)

class HistoricalCheckpoint(unittest.TestCase):
    def setUp(self):self.e=json.loads((HERE/'EVIDENCE.json').read_bytes())
    def bad(self,f):
        e=copy.deepcopy(self.e);f(e)
        with self.assertRaises(ValueError):validate(e)
    def test_original(self):validate(self.e)
    def test_safe_original_identities(self):
        for name,key in [('summary.json','safe_launcher_summary'),('SUPERVISOR.json','safe_caller_supervisor'),('progress.json','safe_final_progress')]:
            b=(HERE/name).read_bytes();self.assertEqual(self.e['artifacts'][key],dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
    def test_observed_exit_binding(self):
        u=json.loads((HERE/'SUPERVISOR.json').read_bytes());s=json.loads((HERE/'summary.json').read_bytes());p=json.loads((HERE/'progress.json').read_bytes())
        self.assertIs(type(u['outer_exit_code']),int);self.assertEqual(u['outer_exit_code'],0)
        self.assertEqual(u['terminal_chunk'],'6db973');self.assertEqual(u['tool_session'],17628)
        self.assertEqual(u['summary_sha256'],hashlib.sha256((HERE/'summary.json').read_bytes()).hexdigest())
        self.assertEqual(u['contract_sha256'],s['contract_sha256']);self.assertEqual(p['phase'],'complete')
        self.assertEqual(p['context_sha256'],s['context_sha256']);self.assertEqual(s['validation']['assigned_official_gates'],27)
    def test_no_broader_pass(self):
        for k in FALSE:
            with self.subTest(k=k):self.bad(lambda e:e.update({k:True}))
    def test_unknown_payload(self):self.bad(lambda e:e.update(tensor=[1]))
    def test_missing_field(self):self.bad(lambda e:e['capture_fields'].pop('pv_raw'))
    def test_missing_gate(self):self.bad(lambda e:e['official_observed_gates'].pop('y'))
    def test_diagnostic_gate_invented(self):self.bad(lambda e:e['official_observed_gates']['softmax_fp32'].update(passed=True))
    def test_gate_failure(self):self.bad(lambda e:e['official_observed_gates']['y'].update(passed=False))
    def test_causal_completion_invented(self):self.bad(lambda e:e['official_observed_gates']['scores'].update(unobserved_elements=0))
    def test_duplicate_capture(self):self.bad(lambda e:e['capture_fields']['prob_bf16'].update(writes=3264))
    def test_type_alias(self):self.bad(lambda e:e['observed_exit_codes'].update(launcher=False))
    def test_source_encoding_confusion(self):self.bad(lambda e:e.update(source_manifest_pretty_sha256=e['source_manifest_compact_sha256']))
    def test_nonfinite(self):self.bad(lambda e:e['official_observed_gates']['y'].update(max_abs=float('nan')))
    def test_budget_increase(self):self.bad(lambda e:e['budget'].update(numeric_seconds=901))
    def test_no_private_paths(self):
        for p in HERE.glob('*.json'):
            raw=p.read_text();self.assertNotIn('/workspace/',raw);self.assertNotIn('/home/',raw);self.assertNotIn('tensor_data',raw)
if __name__=='__main__':unittest.main()
