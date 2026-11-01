"""Synthetic call-return preservation; no runtime import, supervisor, or DUT launch."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest

D=Path(__file__).resolve().parent
SOURCE=D/'runtime_reuse.py'
spec=importlib.util.spec_from_file_location('tested_runtime_reuse',SOURCE)
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
BASE_AST_SHA='08bf52625c7476752dcd2f03b7b7ea6e3d3e6f0c7e35f75d70db0daa9e3da063'

def selected(tree):
 run=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='run')
 loop=next(x for x in run.body if isinstance(x,ast.For)and isinstance(x.iter,ast.Name)and x.iter.id=='VALIDATION_ORDER')
 start=next(i for i,x in enumerate(loop.body)if isinstance(x,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='receipt'for t in x.targets))
 return loop,start

class Preservation(unittest.TestCase):
 def test_only_one_diagnostic_save_added(self):
  tree=ast.parse(SOURCE.read_text());loop,start=selected(tree)
  expected=ast.parse("save(root/'results'/(key+'_SUPERVISOR_RETURN.json'),receipt)").body[0]
  self.assertEqual(ast.dump(loop.body[start+1]),ast.dump(expected))
  del loop.body[start+1]
  self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),BASE_AST_SHA)
 def exercise(self,receipt,worker_result,success):
  with tempfile.TemporaryDirectory()as temp:
   root=Path(temp);(root/'results').mkdir();key='qwen35_08b';output=root/'runs'/key
   if worker_result is not None:
    output.mkdir(parents=True);runtime.save(output/'RESULT.json',worker_result)
   if success:runtime.save(root/'results'/(key+'_IMPORT_VALIDATED.json'),{'synthetic':True})
   before=(output/'RESULT.json').read_bytes()if worker_result is not None else None
   calls=[]
   def execute(*args,**kwargs):calls.append((args,kwargs));return copy.deepcopy(receipt)
   env=dict(runtime.__dict__,root=root,key=key,output=output,argv=['synthetic-no-exec'],
    b={'lock':'synthetic-lock','reserved_other_owner_bytes':5<<30},caps={'rss_bytes':256},env={},pins={},
    supervisor=types.SimpleNamespace(execute=execute),entries={},m={'entries':{key:{'synthetic':True}}})
   tree=ast.parse(SOURCE.read_text());loop,start=selected(tree)
   block=ast.Module(body=loop.body[start:],type_ignores=[])
   code=compile(block,str(SOURCE),'exec')
   if success:exec(code,env)
   else:
    with self.assertRaisesRegex(ValueError,'fresh import validation failed or incomplete'):exec(code,env)
   self.assertEqual(len(calls),1)
   self.assertEqual(json.loads((root/'results'/(key+'_SUPERVISOR_RETURN.json')).read_text()),receipt)
   if before is None:self.assertFalse(output.exists())
   else:self.assertEqual((output/'RESULT.json').read_bytes(),before)
   if success:
    self.assertEqual(env['entries'][key]['validation_receipt'],runtime.pin(output/'RESULT.json'))
    self.assertNotEqual(env['entries'][key]['validation_receipt']['path'],str(root/'results'/(key+'_SUPERVISOR_RETURN.json')))
   else:self.assertEqual(env['entries'],{})
 def test_prelaunch_no_worker_directory(self):
  self.exercise({'status':'REFUSED','native_exit':None,'errors':['synthetic local diagnostic detail'],'worker_started':False},None,False)
 def test_failure_preserves_existing_worker_result(self):
  self.exercise({'status':'FAIL','native_exit':1,'errors':['synthetic failure']},{'original_worker':'unchanged'},False)
 def test_success_still_uses_original_strict_result(self):
  receipt={'status':'PASS_PROCESS_ONLY','native_exit':0,'errors':[],
   'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},
   'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
  self.exercise(receipt,receipt,True)

if __name__=='__main__':unittest.main()
