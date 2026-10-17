"""Cold immutable failure-archive tests; stdlib only, no execution imports."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,math,tempfile,unittest
HERE=Path(__file__).resolve().parent
PINS={'EVIDENCE.json': 'b7dedb493e5fbabf8bb4221f7d658eb64481e194c143b778ed877b3ee725089b', 'SUPERVISOR.json': 'e5b5d9dc1d0a3f6d04b4ae02ccd0f95255f9c315738ca427c7e60ea9ee972609', 'progress.json': 'b90fec98c24ddfcf75985d2000782e7ed49f9509c11d24d0c2e14e1c91fc3d32', 'summary.json': '9c3bf942839a5563b3cba2df86bf2ec5c020fe3e99b123f25c8c38bc7f10d1fc'}
CANONICAL='2b82c072000387094164e0ed03656c4547ac5814cf5bd4f7d4ca93c900475a90'
def need(ok):
 if not ok:raise ValueError('original M128 failure archive mismatch')
def compact(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
def walk(value):
 if type(value) is float:need(math.isfinite(value))
 elif type(value) is dict:
  for key,child in value.items():need(type(key) is str);walk(child)
 elif type(value) is list:
  for child in value:walk(child)
 else:need(type(value) in (str,int,bool,type(None)))
def strict(raw):
 need(type(raw) is bytes and len(raw)<20000)
 def pairs(items):
  out={}
  for key,value in items:need(key not in out);out[key]=value
  return out
 def bad(_):raise ValueError('nonfinite JSON')
 value=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad);walk(value);return value
def validate(value):
 walk(value)
 # This is one immutable historical checkpoint, not a general run validator.
 # Canonical identity rejects added/deleted fields at every depth and type drift.
 need(type(value) is dict and hashlib.sha256(compact(value)).hexdigest()==CANONICAL)
 return value
def load(name,path=None):
 raw=(HERE/name if path is None else path).read_bytes()
 need(name in PINS and hashlib.sha256(raw).hexdigest()==PINS[name]);return strict(raw)
class Evidence(unittest.TestCase):
 def setUp(self):self.e=load('EVIDENCE.json')
 def rejected(self,change):
  value=deepcopy(self.e);change(value)
  with self.assertRaises(ValueError):validate(value)
 def test_original(self):validate(self.e)
 def test_original_safe_copies_and_links(self):
  for name,key in (('summary.json','safe_launcher_summary'),('progress.json','safe_last_progress'),('SUPERVISOR.json','safe_caller_supervisor')):
   value=load(name);raw=(HERE/name).read_bytes();self.assertEqual(self.e['artifacts'][key],dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
  s=load('summary.json');g=load('progress.json');u=load('SUPERVISOR.json')
  self.assertEqual(s['status'],'FAILED');self.assertEqual(s['child_exit_code'],1);self.assertEqual(u['launcher_exit_code'],1)
  self.assertEqual(s['contract_sha256'],self.e['contract_sha256']);self.assertEqual(u['contract_sha256'],self.e['contract_sha256'])
  self.assertEqual(u['summary_sha256'],PINS['summary.json']);self.assertEqual(u['source_proof_sha256'],self.e['artifacts']['private_source_proof']['sha256'])
  self.assertEqual(u['context_sha256'],g['context_sha256']);self.assertEqual(g['context_sha256'],self.e['artifacts']['private_context']['sha256'])
  self.assertEqual(g['phase'],'numeric');self.assertEqual(g['pid'],6);self.assertEqual(g['elapsed_seconds'],self.e['caller']['numeric_entry_elapsed_seconds'])
  self.assertIs(s['numerical_run_started'],True);self.assertIs(s['actual_chain_completion_verified'],False);self.assertIs(s['cleanup_complete'],True)
 def test_all_acceptance_flags_rejected(self):
  for key in self.e['acceptance']:
   with self.subTest(key=key):self.rejected(lambda e:e['acceptance'].__setitem__(key,True))
 def test_no_execution_relabel_rejected(self):
  for key in ('numerical_run_started','numerical_entry_called'):
   self.rejected(lambda e:e['execution'].__setitem__(key,False))
 def test_invented_progress_or_retry_rejected(self):
  for key,value in self.e['execution'].items():
   if value is False:self.rejected(lambda e:e['execution'].__setitem__(key,True))
 def test_pass_status_rejected(self):
  for value in ('PASS','PASS_BOUNDED_NATIVE_CAPTURE','PASS_ASSIGNED_OFFICIAL_OBSERVED_GATES_ONLY','PLAN_ONLY_NO_EXECUTION'):
   self.rejected(lambda e:e.__setitem__('status',value))
 def test_nonfinite_and_bool_drift_rejected(self):
  for value in (float('nan'),float('inf'),-float('inf'),True,0,-1,31,2431.0):
   self.rejected(lambda e:e['caller'].__setitem__('elapsed_seconds',value))
 def test_unknown_or_deleted_fields_at_all_depths(self):
  def paths(value,path=()):
   if type(value) is dict:
    yield path
    for key,child in value.items():yield from paths(child,path+(key,))
   elif type(value) is list:
    for i,child in enumerate(value):yield from paths(child,path+(i,))
  for path in paths(self.e):
   def target(e):
    for part in path:e=e[part]
    return e
   self.rejected(lambda e:target(e).__setitem__('unknown_field',True))
   node=target(self.e)
   if node:
    key=next(iter(node));self.rejected(lambda e:target(e).__delitem__(key))
 def test_duplicate_and_nonfinite_json_rejected(self):
  for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}',b'{"a":-Infinity}',b'{"a":1e999}'):
   with self.assertRaises(ValueError):strict(raw)
 def test_mutated_copy_bytes_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'test.json'
   for name in PINS:
    for raw in (b'{}',(HERE/name).read_bytes()+b' ',b'{'*20001):
     p.write_bytes(raw)
     with self.assertRaises(ValueError):load(name,p)
 def test_source_identity_and_frame_drift_rejected(self):
  for key,value in (('count',345),('source_mismatches',1),('source_manifest_sha256','0'*64),('git_head','0'*40)):
   self.rejected(lambda e:e['source'].__setitem__(key,value))
  self.rejected(lambda e:e['failure']['traceback_frames'][-2].__setitem__('line',308))
 def test_private_content_rejected(self):
  for key,value in (('weights',[]),('raw_stderr','example'),('private_path','example')):
   self.rejected(lambda e:e.__setitem__(key,value))
 def test_bounded_input_scope_rejected(self):
  for value in (16,17,True,128.0):self.rejected(lambda e:e.__setitem__('rows',value))
 def test_timing_and_outer_exit_rejected(self):
  for key,value in (('outer_exit_code',0),('child_exit_code',0),('cleanup_complete',False),('tool_session_id',0),('terminal_chunk','unknown')):
   self.rejected(lambda e:e['caller'].__setitem__(key,value))
 def test_source_order_and_failure_scope(self):
  f=self.e['failure'];self.assertEqual(f['rejecting_source_line'],306)
  self.assertTrue(all(line>306 for line in f['not_reached_source_lines'].values()))
  self.assertTrue(all(line<306 for line in f['passed_source_lines']))
  self.assertFalse(any(self.e['acceptance'].values()));self.assertFalse(self.e['execution']['public_run_loop_entered'])
if __name__=='__main__':unittest.main()
