"""Local return persistence only. No subprocess, DUT or real runtime import."""
import ast,hashlib,json,pathlib,tempfile,types,unittest
D=pathlib.Path(__file__).resolve().parent
# Candidate flow/tail branches independently reviewed 2026-11-01; not a save-only delta.
BASE_AST={'controller/cloud_flow.py': '1d5f8f80511850394a4d8bb0bd2744c0ba3dfae82a6a98c65d981ded2691f9e4', 'controller/flow.py': '6640f4a848fc6cbc4300bb774c6d1e8e6ed8f055c29cc23e868cfc73ceaccfcf', 'numeric/numeric_tail.py': '4946ee900cd42024fd0f4e6c7589b29671fbc4b258c3a31906741c4e3bbb6232'}
EXPECTED={
 'controller/cloud_flow.py':"save(job / 'bindings' / (name + '_SUPERVISOR_RETURN.json'), r)",
 'controller/flow.py':"save(job / 'bindings' / (name + '_SUPERVISOR_RETURN.json'), r)",
 'numeric/numeric_tail.py':"save(out / 'phases' / (name + '_SUPERVISOR_RETURN.json'), r)",
}
class Test(unittest.TestCase):
 def tree(self,rel):return ast.parse((D/rel).read_text())
 def test_exact_save_and_reviewed_version_ast(self):
  for rel,wanted in EXPECTED.items():
   t=self.tree(rel)
   if rel=='controller/cloud_flow.py':
    # Undo only the separately reviewed finite prelaunch receipt, not arbitrary flow changes.
    fs=[n for n in ast.walk(t)if isinstance(n,ast.FunctionDef)and n.name=='upfront_disk_admission']
    cs=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='upfront_disk_admission']
    ds=[n for n in ast.walk(t)if isinstance(n,ast.If)and ast.unparse(n.test)=='evidence_path is not None']
    self.assertEqual((len(fs),len(cs),len(ds)),(1,1,1));f,c,d=fs[0],cs[0],ds[0]
    self.assertIn(d,f.body)
    self.assertEqual(ast.unparse(f.args),'snapshot, evidence_path=None, binding_sha=None')
    self.assertEqual(ast.unparse(c),"upfront_disk_admission(snapshot, P(binding_path).with_name(P(binding_path).name + '.UPFRONT_DISK.json'), binding_sha)")
    self.assertEqual(hashlib.sha256(ast.dump(d,include_attributes=False).encode()).hexdigest(),'c3bb48f0d043a3b02d43bfb69ab5a0a77a81b9938434cde2e836b573d72ba9ad')
    f.args.args=f.args.args[:1];f.args.defaults=[];f.body.remove(d);c.args=c.args[:1]
   class Strip(ast.NodeTransformer):
    count=0
    def visit_Expr(self,n):
     if ast.unparse(n)==wanted:self.count+=1;return None
     return self.generic_visit(n)
   st=Strip();t=st.visit(t)
   with self.subTest(rel=rel):self.assertEqual(st.count,1);self.assertEqual(hashlib.sha256(ast.dump(t).encode()).hexdigest(),BASE_AST[rel])
 def test_actual_stage_statement_order(self):
  for rel,wanted in EXPECTED.items():
   stage=next(n for n in ast.walk(self.tree(rel))if isinstance(n,ast.FunctionDef)and n.name=='stage')
   ix=next(i for i,n in enumerate(stage.body)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and ast.unparse(n.value.func)=='supervisor.execute')
   self.assertEqual(ast.unparse(stage.body[ix+1]),wanted)
   if 'numeric_tail'in rel:self.assertTrue(ast.unparse(stage.body[ix+2]).startswith('require_cleanup('))
   else:self.assertTrue(ast.unparse(stage.body[ix+2]).startswith('history.append('))
 def run_slice(self,rel,r,existing=False):
  stage=next(n for n in ast.walk(self.tree(rel))if isinstance(n,ast.FunctionDef)and n.name=='stage');ix=next(i for i,n in enumerate(stage.body)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and ast.unparse(n.value.func)=='supervisor.execute')
  # Real saved-return statement executes before the original following gate/pin.
  with tempfile.TemporaryDirectory()as td:
   root=pathlib.Path(td);(root/'bindings').mkdir();(root/'phases').mkdir();worker=root/'runs'/'profile0_dut'
   if existing:worker.mkdir(parents=True);(worker/'RESULT.json').write_text('ORIGINAL WORKER RECEIPT')
   def save(p,v):
    with p.open('x')as f:json.dump(v,f)
   def pin(p):return {'bytes':p.stat().st_size}
   def cleanup(receipt,*args):
    if (receipt.get('cleanup_proof')or{}).get('status')!='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP':raise ValueError('original cleanup rejection')
   ns=dict(P=pathlib.Path,supervisor=types.SimpleNamespace(__file__=__file__),job=root,out=root,name='profile0_dut',r=r,run_root=worker,run_dir=worker,save=save,pin=pin,sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),history=[],require_cleanup=cleanup)
   block=ast.fix_missing_locations(ast.Module(body=stage.body[ix+1:ix+3],type_ignores=[]))
   try:exec(compile(block,'<actual-stage-save-and-next-check>','exec'),ns)
   except (ValueError,FileNotFoundError):pass
   output=root/('phases'if 'numeric_tail'in rel else'bindings')/'profile0_dut_SUPERVISOR_RETURN.json';self.assertEqual(json.loads(output.read_text()),r)
   if existing:self.assertEqual((worker/'RESULT.json').read_text(),'ORIGINAL WORKER RECEIPT')
   else:self.assertFalse(worker.exists())
 def test_prelaunch_missing_worker_preserves_exact_error(self):
  for rel in EXPECTED:self.run_slice(rel,{'worker_started':False,'native_exit':None,'errors':['ValueError: locked memory gate'],'cleanup_proof':None})
 def test_existing_worker_failure_does_not_overwrite_receipt(self):
  for rel in EXPECTED:self.run_slice(rel,{'worker_started':True,'native_exit':1,'errors':[],'cleanup_proof':{}},True)
 def test_completed_return_remains_separate(self):
  for rel in EXPECTED:self.run_slice(rel,{'worker_started':True,'native_exit':0,'errors':[],'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'}},True)
if __name__=='__main__':unittest.main()
