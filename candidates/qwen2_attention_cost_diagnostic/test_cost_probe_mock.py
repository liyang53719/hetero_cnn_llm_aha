"""Fake-call and source-static tests only; never import DUT or NumPy/native ELF."""
import argparse,ast,hashlib,importlib.util,json,os,resource,signal,sys,types,unittest
from pathlib import Path
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_AS,(1<<30,)*2)
resource.setrlimit(resource.RLIMIT_CPU,(30,30));signal.alarm(45)
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cost_probe',HERE/'cost_probe.py')
p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--lease-source',type=Path,required=True);parser.add_argument('--lease-sha',required=True);parser.add_argument('--reviewed-tests-root',type=Path,required=True)
args,remaining=parser.parse_known_args()
LEASE=p.load_reviewed_lease(dict(monitor_lease_source=str(args.lease_source),files={str(args.lease_source):dict(bytes=args.lease_source.stat().st_size,sha256=args.lease_sha)}))
def make_probe(codes,**kwargs):return p.SelectiveProbe(codes,lease=LEASE,**kwargs)
class MockProbe(unittest.TestCase):
 def test_scalar_counts_and_cpu_are_measured_on_fake_calls(self):
  def fake(operation,a):return a+1
  probe=make_probe({fake.__code__:'scalar_op'})
  with probe:
   self.assertEqual(fake('bf',7),8);self.assertEqual(fake('add',4),5)
  self.assertIsNone(probe.error);self.assertFalse(probe.active)
  self.assertEqual(probe.rows['scalar_op:bf']['starts'],1)
  self.assertEqual(probe.rows['scalar_op:add']['returns'],1)
  self.assertGreaterEqual(probe.rows['scalar_op:bf']['inclusive_instrumented_cpu_ns'],0)
  self.assertIsNone(sys.monitoring.get_tool(2))
 def test_generator_yield_resume_accounting(self):
  def fake():
   x=yield 8
   return x+1
  probe=make_probe({fake.__code__:'matrix_step'})
  with probe:
   g=fake();self.assertEqual(next(g),8)
   with self.assertRaises(StopIteration) as ctx:g.send(6)
   self.assertEqual(ctx.exception.value,7)
  self.assertIsNone(probe.error);self.assertFalse(probe.active)
  self.assertEqual({k:v for k,v in probe.rows['matrix_step'].items() if k!='inclusive_instrumented_cpu_ns'},dict(starts=1,resumes=1,returns=1,yields=1,unwinds=0))
 def test_bound_failure_does_not_substitute_output(self):
  def fake():return 42
  probe=make_probe({fake.__code__:'mock'},max_callbacks=1)
  with probe:self.assertEqual(fake(),42)
  self.assertIn('bounded single-thread',probe.error);self.assertIsNone(sys.monitoring.get_tool(2))
 def test_original_exception_propagates_and_cleans_tool(self):
  def fake():raise RuntimeError('original fault')
  probe=make_probe({fake.__code__:'mock'})
  with self.assertRaisesRegex(RuntimeError,'original fault'):
   with probe:fake()
  self.assertIsNone(sys.monitoring.get_tool(2));self.assertTrue(probe.closed)
  with self.assertRaisesRegex(ValueError,'failed or incomplete'):probe.seal({})
 def test_busy_slot_is_not_taken(self):
  mon=sys.monitoring;mon.use_tool_id(2,'unrelated-owner')
  try:
   probe=make_probe({})
   with self.assertRaisesRegex(ValueError,'busy'):probe.__enter__()
   self.assertEqual(mon.get_tool(2),'unrelated-owner')
  finally:mon.free_tool_id(2)
 def test_exact_free_function_source_binding_and_rejection(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   file=Path(d)/'mock_source.py';file.write_text('def fake(a):\n    return a + 1\n')
   ns={};exec(compile(file.read_text(),str(file),'exec'),ns)
   code=p.free_function_code(ns['fake'],file,hashlib.sha256(file.read_bytes()).hexdigest())
   self.assertIs(code,ns['fake'].__code__)
   with self.assertRaisesRegex(ValueError,'source pin'):p.free_function_code(ns['fake'],file,'0'*64)
   file.write_text('def fake(a):\n    return a + 2\n')
   with self.assertRaisesRegex(ValueError,'complete code'):p.free_function_code(ns['fake'],file,hashlib.sha256(file.read_bytes()).hexdigest())
 def test_no_global_monitor_events_or_unsupported_local_unwind(self):
  source=(HERE/'cost_probe.py').read_text()
  self.assertNotIn('set_events(',source)
  self.assertNotIn('PY_UNWIND',p.SelectiveProbe.EVENTS)
  self.assertNotIn('sys.setprofile',source)
 def test_no_global_profile_or_target_imports(self):
  self.assertIsNone(sys.getprofile());self.assertNotIn('numpy',sys.modules)
  self.assertFalse(any(n.startswith('candidates.') for n in sys.modules))
 def test_unchanged_core_sources_and_known_source_witness_interface(self):
  h=ast.parse((HERE/'harness.py').read_text())
  run=next(n for n in h.body if isinstance(n,ast.FunctionDef) and n.name=='run_owner')
  scalar=[n for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='ScalarService']
  self.assertEqual(len(scalar),1)
  self.assertEqual({n.arg for n in scalar[0].keywords},{'committed_source_witness','committed_source_manifest'})
  self.assertFalse(any(isinstance(n,ast.Assign) and any(isinstance(x,ast.Attribute) and x.attr in ('op','_op','tick','bf') for x in n.targets) for n in ast.walk(h)))
 def test_four_arm_control_pairs(self):
  arms=[dict(count_enabled=c,id=i) for i,c in enumerate((False,False,True,True))];calls=[]
  def pair(a):calls.append([x['id'] for x in a]);return 'PASS'
  result=p.compare_four(arms,pair)
  self.assertEqual(calls,[[0,1],[2,3],[0,3],[2,1]])
  self.assertEqual(result['clean_timing_arms'],[0,1])
 def test_stage_clock_nonnegative(self):
  s=p.Stages();s.mark('mock');self.assertGreaterEqual(s.rows[0]['cpu_ns'],0)
 def test_worker_waits_all_four_terminals_before_reference(self):
  s=(HERE/'worker.py').read_text();self.assertLess(s.index('control=compare_four'),s.index('guard.terminal=True'))
  self.assertLess(s.index('guard.terminal=True'),s.index('comparison=compare_original'))
  self.assertIn('choices=(2,)',s)
 def test_runtime_source_only_gates_and_exact_launch_go(self):
  s=(HERE/'worker.py').read_text();self.assertIn('source-only import cache policy',s)
  l=(HERE/'launch.py').read_text();self.assertIn('fresh exact root GO required',l)
  self.assertIn("attempt.open('x')",l);self.assertIn('proc.wait(timeout=45)',l)
  self.assertNotIn('previous=json.loads',l)
if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+remaining)
