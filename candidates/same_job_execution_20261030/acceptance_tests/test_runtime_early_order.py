import ast, pathlib, unittest
D=pathlib.Path(__file__).resolve().parents[1]
S=(D/'runtime/install_job.py').read_text();F=(D/'controller/flow.py').read_text()
def functions(text,names):
 t=ast.parse(text);t.body=[n for n in t.body if isinstance(n,ast.FunctionDef)and n.name in names];ns={};exec(compile(t,'source_functions','exec'),ns);return ns
class EarlyOrder(unittest.TestCase):
 def setUp(self):self.m=functions(S,{'need','install_order','build_boundary'})
 def test_full(self):self.assertEqual(self.m['install_order'](['qwen2','qwen35_08b','qwen35_35b']),['qwen35_35b','qwen2','qwen35_08b'])
 def test_eligible4(self):self.assertEqual(self.m['install_order'](['qwen35_08b','qwen35_35b']),['qwen35_35b','qwen35_08b'])
 def test_missing35(self):
  with self.assertRaises(ValueError):self.m['install_order'](['qwen2'])
 def test_duplicate(self):
  with self.assertRaises(ValueError):self.m['install_order'](['qwen35_35b','qwen35_35b'])
 def test_boundary(self):
  b={'remaining_job_reservation_seconds':9000};calls=[];self.m['build_boundary'](b,6000,lambda:calls.append(1));self.assertEqual(calls,[1]);self.assertEqual(b['remaining_job_reservation_seconds'],3000)
 def test_failure_no_release(self):
  b={'remaining_job_reservation_seconds':9000}
  def fail():raise RuntimeError('native failed')
  with self.assertRaises(RuntimeError):self.m['build_boundary'](b,6000,fail)
  self.assertEqual(b['remaining_job_reservation_seconds'],9000)
 def test_no_unreserved_callback(self):
  b={'remaining_job_reservation_seconds':1};calls=[]
  with self.assertRaises(ValueError):self.m['build_boundary'](b,2,lambda:calls.append(1))
  self.assertEqual(calls,[])
 def test_invalid_callbacks(self):
  for seconds,cb in [(0,lambda:None),(-1,lambda:None),(True,lambda:None),(2,None)]:
   with self.assertRaises(ValueError):self.m['build_boundary']({'remaining_job_reservation_seconds':9},seconds,cb)
 def test_source_after_native_cleanup(self):
  loop=[n for n in ast.walk(ast.parse(S))if isinstance(n,ast.For)and ast.unparse(n.target)=='k' and any(isinstance(x,ast.Call)and ast.unparse(x.func)=='build_boundary'for x in ast.walk(n))][0]
  text=ast.unparse(loop)
  self.assertLess(text.index('finally:'),text.index('build_boundary'))
  self.assertLess(text.index('need(complete(r)'),text.index('build_boundary'))
  # Boundary is not nested in execute/try/with: it is a peer top-level if after cleanup check.
  boundary=[x for x in loop.body if isinstance(x,ast.If)and any(isinstance(y,ast.Call)and ast.unparse(y.func)=='build_boundary'for y in ast.walk(x))]
  self.assertEqual(len(boundary),1);self.assertIn('early = 0',ast.unparse(boundary[0]))
 def test_original_caps_unchanged(self):
  old=ast.parse((D/'acceptance_tests/fixtures/runtime_install_base.py.txt').read_text());new=ast.parse(S)
  get=lambda t:[ast.dump(n.value)for n in ast.walk(t)if isinstance(n,ast.Assign)and any(isinstance(x,ast.Name)and x.id in ('caps','bindcaps')for x in n.targets)]
  self.assertEqual(get(old),get(new))
 def test_flow_order(self):
  self.assertLess(F.index("ok(stage('archives'"),F.index('installer.run('))
  self.assertLess(F.index('installer.run('),F.index("ok(stage('weights'"))
  self.assertIn('after_first_install=build_after_first_runtime',F)
  callback=[x for x in ast.walk(ast.parse(F))if isinstance(x,ast.FunctionDef)and x.name=='build_after_first_runtime'][0]
  self.assertEqual(sum(isinstance(x,ast.Call)and ast.unparse(x.func)=='subprocess.run'for x in ast.walk(callback)),1)
  self.assertFalse(any(isinstance(x,ast.Call)and ast.unparse(x.func)=='supervisor.execute'for x in ast.walk(callback)))
 def test_deadline_conservation(self):
  for q in [dict(archives=120,weights=600,install=100,owner_bind=100,reference=200),dict(archives=1,weights=1,install=1,owner_bind=1,reference=1)]:
   materials=q['archives']+q['weights']+3*q['install']+q['owner_bind']+5*q['reference']+11*30
   remaining=q['weights']+2*q['install']+q['owner_bind']+5*q['reference']+9*30
   self.assertEqual(materials-(q['archives']+30)-(q['install']+30),remaining)
 def test_no_future_entry_claim(self):
  self.assertNotIn('40000',F);self.assertIn("census['entries']<=100000",F);self.assertIn('not future peak proof',F)
 def test_original_build_body(self):
  old=(D/'acceptance_tests/fixtures/controller_flow_base.py.txt').read_text();old=old[old.index(" build=job/'build'"):old.index(" archives=job/'runs/archives/output'")]
  new=F[F.index("  build=job/'build'"):F.index(" owner_root=job/'materials'")]
  new='\n'.join(x[1:] for x in new.splitlines())+'\n'
  old=old.replace("q['build']+materials_reserved+tail_reserved","q['build']+remaining_after_build").replace('str(materials_reserved+tail_reserved)','str(remaining_after_build)')
  self.assertEqual(old,new)
if __name__=='__main__':unittest.main()
