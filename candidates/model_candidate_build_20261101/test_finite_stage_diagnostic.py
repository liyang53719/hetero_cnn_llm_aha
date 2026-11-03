"""Finite stage-error diagnostic projection tests only; no build/EDA.
Frozen orchestration AST fingerprint comes from original 79020 source.
"""
import ast,hashlib,json,pathlib,tempfile,unittest
H=pathlib.Path(__file__).resolve().parent;PROP=H/'one_job_model_candidate.py'
NAMES={'BUILD_STAGE_NAMES','BUILD_ERROR_CODES','build_error_details','build_stage_diagnostic','sha'}
def functions(p):
 t=ast.parse(p.read_text());body=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in NAMES or isinstance(n,ast.Assign) and any(isinstance(q,ast.Name) and q.id in NAMES for q in n.targets)];ns={'pathlib':pathlib,'hashlib':hashlib,'json':json};exec(compile(ast.Module(body=body,type_ignores=[]),str(p),'exec'),ns);return ns
O={'BUILD_ERROR_CODES':{'ValueError: wall cap': 'WALL_CAP', 'InterruptedError: signal 14': 'MONITOR_SIGALRM', 'ValueError: prelaunch work deadline': 'PRELAUNCH_DEADLINE', 'ValueError: sampled observed aggregate RSS cap': 'SAMPLED_RSS_CAP', 'ValueError: sampled observed aggregate CPU cap': 'SAMPLED_CPU_CAP', 'ValueError: locked memory gate': 'PRELAUNCH_MEMORY_GATE', 'ValueError: locked disk gate': 'PRELAUNCH_DISK_GATE', 'ValueError: entry cap': 'ENTRY_CAP', 'ValueError: file cap': 'FILE_CAP', 'ValueError: sampled aggregate writable-root cap': 'AGGREGATE_TREE_CAP', 'ValueError: sampled stage output tree cap': 'STAGE_TREE_CAP', 'ValueError: sampled disk reserve': 'DISK_RESERVE', 'ValueError: sampled log cap': 'LOG_CAP', 'ValueError: log reader failure': 'LOG_READER_FAILURE', 'ValueError: log EOF missing after cleanup': 'LOG_EOF_MISSING', 'RuntimeError: capture missing EOF; no full log claim': 'LOG_EOF_MISSING', 'ValueError: reader completion deadline': 'READER_DEADLINE', 'ValueError: reader join deadline': 'READER_DEADLINE', 'ValueError: post-cleanup deadline': 'POST_CLEANUP_DEADLINE'}};P=functions(PROP)
class Tests(unittest.TestCase):
 def project(self,errors,ns=P):return json.loads(ns['build_stage_diagnostic']('host_archive',{'errors':errors},H/'NO_SUCH_RECEIPT.json'))
 def test_real_os_class_errno_no_path(self):
  q=self.project(['ProcessLookupError: [Errno 3] No such process: /private/SECRET_TOKEN']);self.assertEqual(q['error_details'][0],{'origin':'SUPERVISOR','exception_class':'ProcessLookupError','errno':3,'reason_code':'UNCLASSIFIED_SUPERVISOR_ERROR'});self.assertNotIn('SECRET',json.dumps(q));self.assertNotIn('/private',json.dumps(q))
 def test_no_arbitrary_class(self):
  self.assertEqual(self.project(['SECRET_CLASS: SECRET_BODY'])['error_details'][0]['exception_class'],'UNKNOWN')
 def test_no_prefix_reason_guess(self):
  q=self.project(['ValueError: nonregular output SECRET']);self.assertEqual(q['error_categories'],['UNCLASSIFIED_SUPERVISOR_ERROR']);self.assertNotIn('SECRET',json.dumps(q))
 def test_existing_codes_preserved(self):
  for e,c in O['BUILD_ERROR_CODES'].items():self.assertEqual(self.project([e])['error_categories'],[c])
 def test_new_finite_codes(self):
  for e,c in P['BUILD_ERROR_CODES'].items():self.assertEqual(self.project([e])['error_details'][0]['reason_code'],c)
 def test_budget(self):
  q=self.project(['ValueError: SECRET']*1000);self.assertEqual(len(q['error_details']),16);self.assertTrue(q['error_details_truncated']);self.assertLess(len(json.dumps(q)),8192)
 def test_malformed(self):
  for e in (None,{},'bad',True):self.assertEqual(self.project(e)['error_details'],[])
  self.assertEqual(self.project([{}])['error_details'][0]['reason_code'],'MALFORMED_ERROR')
 def test_errno_limits(self):
  for e in ('OSError: [Errno 9999] SECRET','ValueError: [Errno 3] SECRET','OSError: [Errno 3X] SECRET'):
   self.assertIsNone(self.project([e])['error_details'][0]['errno'])
 def test_log_reader(self):
  q=self.project(['log_reader: OSError: [Errno 5] SECRET']);self.assertEqual(q['error_details'][0]['origin'],'LOG_READER');self.assertEqual(q['error_details'][0]['errno'],5);self.assertNotIn('SECRET',json.dumps(q))
 def test_no_orchestration_change(self):
  def rest(p):return ast.dump(ast.Module(body=[n for n in ast.parse(p.read_text()).body if not(isinstance(n,ast.FunctionDef) and n.name in {'build_error_details','build_stage_diagnostic'} or isinstance(n,ast.Assign) and any(isinstance(q,ast.Name)and q.id=='BUILD_ERROR_CODES'for q in n.targets))],type_ignores=[]))
  self.assertEqual(hashlib.sha256(rest(PROP).encode()).hexdigest(),'aecb99b17acd89aae11030564041fa2ba930ed0197d538722812cbe960db5332')
if __name__=='__main__':unittest.main(verbosity=2)
