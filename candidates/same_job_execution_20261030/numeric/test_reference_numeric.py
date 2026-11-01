import ast,importlib.util,pathlib,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
if not (D/'live_budget.py').is_file():D=D/'source/candidates/same_job_execution_20261030/numeric'
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class Tests(unittest.TestCase):
 def test_budget_tight_cap(self):
  m=load('actual_live',D/'live_budget.py');s=dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1',complete=True,bytes=100,free_bytes=20<<30,finished_monotonic=100.)
  kw=dict(extra_bytes=20,phase_seconds=10,job_started=90.,now=100.)
  self.assertEqual(m.admit(s,**kw),m.admit(s,**kw,tree_cap=m.TREE_CAP))
  self.assertEqual(m.admit(s,**kw,tree_cap=120)['resulting_byte_ceiling'],120)
  for cap in (119,0,-1,True,m.TREE_CAP+1):
   with self.assertRaises(ValueError):m.admit(s,**kw,tree_cap=cap)
 def test_default_copy_authority_rejects_stray_fields(self):
  m=load('actual_provider',D/'provider_from_frozen.py')
  with self.assertRaisesRegex(ValueError,'no implicit'):m.copy_reference({},pathlib.Path('/unused'),0,reuse_context={})
 def test_fixed_helper_rejects_foreign_path(self):
  m=load('actual_provider_fixed',D/'provider_from_frozen.py')
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'reference_data_reuse.py';p.write_text('raise RuntimeError("must not import")')
   with self.assertRaisesRegex(ValueError,'fixed reference'):m.reference_reuse_module(m.pin(p))
 def test_supervised_stage_cap_forward(self):
  tree=ast.parse((D/'numeric_tail.py').read_text());calls=[x for x in ast.walk(tree)if isinstance(x,ast.Call)and isinstance(x.func,ast.Name)and x.func.id=='dict' and any(k.arg=='admission_output'for k in x.keywords)]
  self.assertEqual(len(calls),1);value=next(k.value for k in calls[0].keywords if k.arg=='tree_cap');self.assertEqual(ast.unparse(value),"b['tree_cap']")
 def test_exact_before_after_dut(self):
  tree=ast.parse((D/'numeric_tail.py').read_text());run=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='run')
  lists=[x.body for x in ast.walk(run)if isinstance(x,ast.With)]
  matching=[]
  for body in lists:
   for i,n in enumerate(body):
    if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='dut_outer'for t in n.targets):matching.append((body,i))
  self.assertEqual(len(matching),1);body,i=matching[0]
  for n in (body[i-1],body[i+1]):
   self.assertIsInstance(n,ast.If);self.assertEqual(ast.unparse(n.test),'reference_reuse is not None')
   self.assertEqual(ast.unparse(n.body[0]),"verify_reference_with_deadline(b, reference_reuse, profile, i, reference_reuse_context)")
 def test_post_reference_rejection_not_swallowed_by_native2(self):
  tree=ast.parse((D/'numeric_tail.py').read_text());run=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='run')
  body=next(x.body for x in ast.walk(run)if isinstance(x,ast.With)and any(isinstance(y,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='dut_outer'for t in y.targets)for y in x.body))
  i=next(i for i,n in enumerate(body)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='dut_outer'for t in n.targets))
  segment=ast.Module(body=body[i-1:i+2],type_ignores=[]);calls=[]
  class Gate:
   def verify_materialized(self,*args):
    calls.append('verify')
    if len(calls)==2:raise ValueError('actual post data changed')
  scope=dict(verify_reference_with_deadline=lambda b,h,p,i,c:h.verify_materialized(b['references'][str(i)],p,i,b['reference_data_reuse'],c),reference_reuse=Gate(),b={'references':{'0':{}},'reference_data_reuse':{}},profile=pathlib.Path('/synthetic'),i=0,reference_reuse_context={},generated=[],outer_seconds=1,lease_root=pathlib.Path('/synthetic'),stage=lambda *a,**kw:{'native_exit':2})
  with self.assertRaisesRegex(ValueError,'post data changed'):exec(compile(segment,'actual_tail_segment','exec'),scope)
  self.assertEqual(calls,['verify','verify']);self.assertEqual(scope['dut_outer']['native_exit'],2)
 def test_original_deadline_before_after_hash(self):
  tree=ast.parse((D/'numeric_tail.py').read_text());fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='verify_reference_with_deadline')
  import types
  def need(v,m):
   if not v:raise ValueError(m)
  class Helper:
   def verify_materialized(self,*args):return 'same-inode'
  b=dict(job_started_monotonic=10.,job_budget_seconds=20,references={'0':{}},reference_data_reuse={})
  for ticks,expected in (([11.,29.],None),([11.,31.],'exceeded'),([31.],'original')):
   it=iter(ticks);scope=dict(time=types.SimpleNamespace(monotonic=lambda:next(it)),need=need)
   exec(compile(ast.Module(body=[fn],type_ignores=[]),'real_deadline','exec'),scope)
   if expected:
    with self.assertRaisesRegex(ValueError,expected):scope['verify_reference_with_deadline'](b,Helper(),None,0,{})
   else:self.assertEqual(scope['verify_reference_with_deadline'](b,Helper(),None,0,{}),'same-inode')
 def test_locked_phase_passes_tighter_cap(self):
  tree=ast.parse((D/'locked_phase.py').read_text());calls=[x for x in ast.walk(tree)if isinstance(x,ast.Call)and ast.unparse(x.func)=='live_budget.admit'];self.assertEqual(len(calls),1)
  self.assertEqual(ast.unparse(next(k.value for k in calls[0].keywords if k.arg=='tree_cap')),"b.get('tree_cap', live_budget.TREE_CAP)")
 def test_no_reference_core_write_or_copy_fallback(self):
  s=(D/'provider_from_frozen.py').read_text();self.assertIn('return reference_reuse_module(reuse_source_pin).link_reference',s)
  self.assertNotIn('except OSError',s);self.assertNotIn('chmod',s)
if __name__=='__main__':unittest.main()
