"""Cold archive checks only; no model data, library loads, or execution."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,math,tempfile,unittest
HERE=Path(__file__).resolve().parent
SHA='16e73fb167eaca90058e5dfbf4a8f4a1013475a427329b90bcb698ad0c00cd7c'
FIELDS={'dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16'}
CLAIMS={'full_public_graph','full_m128','numerical_acceptance','full_29_node_gate','rtl','hardware_cycles','useful_wall_mac_90','official_hidden_state','previous_attempt_pass_inherited'}
PHASES={'candidate_transport_with_live_capture':9.899768301998847,'independent_fraction_reference_and_comparison':9.013514624006348,'observer_attach':0.2356036440032767,'observer_report_and_capture_hash_checks':0.018608729005791247}
KEYS={'schema','status','source_count','source_manifest_sha256','git_head','committed_cpp_sha256','library_sha256','input_observer_pins_sha256','input_transport_pins_sha256','generated_observer_pins_sha256','artifacts','case','capture_elapsed_seconds','launcher_elapsed_seconds','work_seconds','cleanup_seconds','receipt_reserve_seconds','outer_seconds','input_kind','source_projection','phase_scope','independent_numerical_fields','coverage_fields','claims'}

def need(condition):
 if not condition:raise ValueError('bounded tiled capture evidence mismatch')
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
def load(path):
 raw=path.read_bytes();need(len(raw)<20000 and hashlib.sha256(raw).hexdigest()==SHA)
 return json.loads(raw)
def validate(e):
 need(type(e)is dict and set(e)==KEYS and e['schema']=='packed-tiled-m17-capture-checkpoint-v1' and e['status']=='PASS_BOUNDED_NATIVE_CAPTURE')
 need(set(e['claims'])==CLAIMS and all(v is False for v in e['claims'].values()))
 need(type(e['source_count'])is int and e['source_count']==196 and e['git_head']=='be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5')
 need(e['source_manifest_sha256']=='f1b3560ca5fd2cfbe97f30835d865cf538da9384f2aaf3e6fe23178ac67f660b' and e['library_sha256']=='1ba0b6aa738dd4a409b91adf93cafbcec63fc3c0df1590f9b91cf8f223f54811')
 for k,v in (('work_seconds',45),('cleanup_seconds',5),('receipt_reserve_seconds',1),('outer_seconds',51)):need(type(e[k])is int and e[k]==v)
 need(type(e['launcher_elapsed_seconds'])is float and e['launcher_elapsed_seconds']==19.780646 and type(e['capture_elapsed_seconds'])is float and 0<e['capture_elapsed_seconds']<e['launcher_elapsed_seconds'])
 c=e['case'];o=c['observation'];need(type(c['rows'])is int and c['rows']==17 and c['all_ten_fields_complete']is True and c['panel_boundary_seen']is True and type(c['panel_ack_hold_edges'])is int and c['panel_ack_hold_edges']==7)
 need(c['full_public_graph']is False and c['rtl']is False and c['pv_store_hash_matches_acknowledged_output']is True and c['scores_match_original_fraction_oracle']is True)
 need(c['scalar_type']=='candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic.ScalarService' and c['all_enabled_fmas']==7704576 and c['owner_edges']==c['parent_edges']==132030)
 need(canonical(c['phase_seconds'])==canonical(PHASES) and sum(c['phase_seconds'].values())<=e['capture_elapsed_seconds'])
 need(e['independent_numerical_fields']==['pv_bf16','scores_bf16'] and set(e['coverage_fields'])==FIELDS)
 need(o['schema']==o['source_version']=='qwen2-packed-tiled-causal-observation-v1' and o['status']=='COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED' and o['observer_error']is None)
 need(o['native_acceptance']=='NOT_EVALUATED_BY_OBSERVER' and o['full_29_node_gate']is False and o['prior_observation_results_inherited']is False and o['future_scores_observed']is False and 'source_sha256' not in o)
 need(set(o['fields'])==FIELDS)
 for name,f in o['fields'].items():
  shape=[12,17,3]if name=='normalizer'else[12,17,128]if name.startswith('pv_')else[12,17,17,16]if name=='dot_parts'else[12,17,17]
  n=612 if name=='normalizer'else 26112 if name.startswith('pv_')else 29376 if name=='dot_parts'else 1836
  need(f['shape']==shape and type(f['words'])is int and f['words']==math.prod(shape))
  need(all(type(f[k])is int and f[k]==n for k in ('writes','observed_words')) and type(f['identical_repeats'])is int and f['identical_repeats']==0)
  need(set(f)=={'shape','words','writes','observed_words','identical_repeats','frequency_sha256','presence_sha256','raw_sha256'})
  for k in ('frequency_sha256','presence_sha256','raw_sha256'):need(type(f[k])is str and len(f[k])==64 and all(x in '0123456789abcdef'for x in f[k]))
 retirement=o['accepted_retirement'];need(retirement==dict(client_retired=True,matrix_released=True,matrix_reset_required=False,memory_pending=False,packed_memory_tag=False,poison=False,same_job=True,same_services=True,scalar_released=True,scratch_leased=False,scratch_pending=False,scratch_request=False,scratch_write_tag=False,state='idle'))
 need(o['packed_multiplicity']==dict(causal_field=1,legacy_normalizer_repeats='8*(query+1)',legacy_probability_repeats=8,normalizer_per_head_query=1,pv_word=1,synthetic_repeats=0))
 return e

class Evidence(unittest.TestCase):
 def setUp(self):self.e=load(HERE/'EVIDENCE.json')
 def test_original(self):validate(self.e)
 def test_safe_receipt_links(self):
  for name,key in (('POSTFLIGHT.json','original_postflight'),('SUPERVISOR.json','caller_supervisor')):
   raw=(HERE/name).read_bytes();self.assertEqual(dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),self.e['artifacts'][key])
  p=json.loads((HERE/'POSTFLIGHT.json').read_bytes());s=json.loads((HERE/'SUPERVISOR.json').read_bytes());self.assertEqual(p['capture_sha256'],self.e['artifacts']['original_capture']['sha256']);self.assertEqual(s['postflight_sha256'],self.e['artifacts']['original_postflight']['sha256']);self.assertEqual(s['launcher_exit_code'],0);self.assertEqual(p['returncode'],0);self.assertIs(p['cleanup_complete'],True)
 def test_scope(self):
  for key in CLAIMS:
   e=deepcopy(self.e);e['claims'][key]=True
   with self.assertRaises(ValueError):validate(e)
 def test_field_deletion(self):
  for name in FIELDS:
   e=deepcopy(self.e);del e['case']['observation']['fields'][name]
   with self.assertRaises(ValueError):validate(e)
 def test_multiplicity(self):
  for name in ('prob_bf16','normalizer','dot_parts'):
   e=deepcopy(self.e);e['case']['observation']['fields'][name]['writes']*=8
   with self.assertRaises(ValueError):validate(e)
 def test_phase_finite_and_exact(self):
  for v in (True,float('nan'),float('inf'),-1.0,45.0):
   e=deepcopy(self.e);e['case']['phase_seconds']['candidate_transport_with_live_capture']=v
   with self.assertRaises(ValueError):validate(e)
 def test_no_payload_and_m128_relabel(self):
  e=deepcopy(self.e);e['weights']=[]
  with self.assertRaises(ValueError):validate(e)
  e=deepcopy(self.e);e['case']['rows']=128
  with self.assertRaises(ValueError):validate(e)
 def test_terminal_and_boundary(self):
  e=deepcopy(self.e);e['case']['observation']['accepted_retirement']['memory_pending']=True
  with self.assertRaises(ValueError):validate(e)
  e=deepcopy(self.e);e['case']['panel_ack_hold_edges']=6
  with self.assertRaises(ValueError):validate(e)
 def test_changed_bytes_rejected(self):
  with tempfile.TemporaryDirectory()as td:
   p=Path(td)/'e.json'
   for raw in (b'{}',(HERE/'EVIDENCE.json').read_bytes()+b' ',b'{'*20001,b'{"x":1,"x":2}'):
    p.write_bytes(raw)
    with self.assertRaises(ValueError):load(p)

if __name__=='__main__':unittest.main()
