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

REVIEWED_AGGREGATE_PHASE_CAPS_AST='8c1404d08105a65707976b5839856beec6ddc8275c975f007c123d8ad117ef02'
HISTORICAL_PHASE_CAPS_SOURCE="def phase_caps(b):\n role=b['stage_resources']['install'];wall=b['install_wall_seconds']\n tree_cap=12_081_306_272\n if 'aggregate_tree_cap_bytes'in b:\n  tree_cap=admit(b)['aggregate_tree_cap_bytes']\n need(type(wall)is int and 0<wall<=1800,'original finite import validation wall')\n return dict(wall_seconds=wall,cleanup_seconds=30,file_bytes=2<<30,tree_bytes=tree_cap,watch_tree_bytes=tree_cap,extra_watch_roots=b['owned_roots'],min_free_disk_bytes=1610612736,log_bytes=16777216,raw_log_bytes=33554432,max_entries=150000,per_process_as_bytes=role['as_bytes'],per_process_cpu_seconds=wall,rss_bytes=role['rss_bytes'],cpu_seconds=wall)"
REVIEWED_AGGREGATE_RUNTIME_AST='fff525fd96825f599884ae1a716bd3d1fd2dad9e22ef4bfe25c19edda8fd3ccc'
HISTORICAL_AGGREGATE_RUNTIME_AST="if 'aggregate_tree_cap_bytes'in b or 'aggregate_tree_cap_bytes'in budget:\n need(type(b.get('aggregate_tree_cap_bytes'))is int and b['aggregate_tree_cap_bytes']==budget.get('aggregate_tree_cap_bytes')==12037043872,'runtime exact reviewed aggregate cap')"
def undo_approved_aggregate_runtime(test,tree):
 tree=copy.deepcopy(tree)
 functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='admit'];test.assertEqual(len(functions),1,'one runtime admit')
 function=functions[0]
 expected=ast.parse(HISTORICAL_AGGREGATE_RUNTIME_AST).body[0]
 matches=[n for n in function.body if isinstance(n,ast.If)and ast.dump(n.test)==ast.dump(expected.test)]
 test.assertEqual(len(matches),1,'one exact aggregate runtime branch')
 node=matches[0];test.assertEqual(hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest(),REVIEWED_AGGREGATE_RUNTIME_AST,'exact reviewed aggregate runtime branch')
 function.body[function.body.index(node)]=expected
 caps=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='phase_caps'];test.assertEqual(len(caps),1,'one exact phase_caps')
 test.assertEqual(hashlib.sha256(ast.dump(caps[0],include_attributes=False).encode()).hexdigest(),REVIEWED_AGGREGATE_PHASE_CAPS_AST,'exact reviewed aggregate phase_caps')
 tree.body[tree.body.index(caps[0])]=ast.parse(HISTORICAL_PHASE_CAPS_SOURCE).body[0]
 return tree

def selected(tree):
 run=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='run')
 loop=next(x for x in run.body if isinstance(x,ast.For)and isinstance(x.iter,ast.Name)and x.iter.id=='VALIDATION_ORDER')
 start=next(i for i,x in enumerate(loop.body)if isinstance(x,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='receipt'for t in x.targets))
 return loop,start

class Preservation(unittest.TestCase):
 def test_only_one_diagnostic_save_added(self):
  tree=undo_approved_aggregate_runtime(self,ast.parse(SOURCE.read_text()));loop,start=selected(tree)
  expected=ast.parse("save(root/'results'/(key+'_SUPERVISOR_RETURN.json'),receipt)").body[0]
  self.assertEqual(ast.dump(loop.body[start+1]),ast.dump(expected))
  del loop.body[start+1]
  # Invert only the independently reviewed reference-reuse cap branch.
  # Every statement must match exactly before removing it; old BASE stays fixed.
  admit=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='admit')
  expected=ast.parse("if 'aggregate_tree_cap_bytes'in b or 'aggregate_tree_cap_bytes'in budget:\n need(type(b.get('aggregate_tree_cap_bytes'))is int and b['aggregate_tree_cap_bytes']==budget.get('aggregate_tree_cap_bytes')==12037043872,'runtime exact reviewed aggregate cap')").body[0]
  self.assertEqual(ast.dump(admit.body[-2]),ast.dump(expected));del admit.body[-2]
  caps=next(x for x in tree.body if isinstance(x,ast.FunctionDef)and x.name=='phase_caps')
  expected=ast.parse("tree_cap=12_081_306_272\nif 'aggregate_tree_cap_bytes'in b:\n tree_cap=admit(b)['aggregate_tree_cap_bytes']").body
  self.assertEqual([ast.dump(x)for x in caps.body[2:4]],[ast.dump(x)for x in expected]);del caps.body[2:4]
  call=caps.body[-1].value
  self.assertIsInstance(call,ast.Call)
  for name in ('tree_bytes','watch_tree_bytes'):
   value=next(k for k in call.keywords if k.arg==name)
   self.assertEqual(ast.dump(value.value),ast.dump(ast.Name(id='tree_cap',ctx=ast.Load())))
   value.value=ast.Constant(value=12_081_306_272)
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

class AggregateInverseNegatives(unittest.TestCase):
 def test_missing_mutated_duplicate_aggregate_branch_rejected(self):
  for case in ('missing','mutated','duplicate'):
   tree=ast.parse(SOURCE.read_text());function=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='admit');node=function.body[-2]
   if case=='missing':function.body.remove(node)
   elif case=='duplicate':function.body.insert(len(function.body)-1,copy.deepcopy(node))
   else:
    names=[x for x in ast.walk(node)if isinstance(x,ast.Name)];self.assertTrue(names);names[-1].id='UNREVIEWED_RUNTIME_CHANGE'
   with self.subTest(case=case),self.assertRaises(AssertionError):undo_approved_aggregate_runtime(self,tree)
 def test_phase_caps_missing_mutated_duplicate_rejected(self):
  for case in ('missing','mutated','duplicate'):
   tree=ast.parse(SOURCE.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='phase_caps')
   if case=='missing':tree.body.remove(node)
   elif case=='duplicate':tree.body.append(copy.deepcopy(node))
   else:
    names=[x for x in ast.walk(node)if isinstance(x,ast.Name)];names[-1].id='UNREVIEWED_PHASE_CAPS_CHANGE'
   with self.subTest(case=case),self.assertRaises(AssertionError):undo_approved_aggregate_runtime(self,tree)
 def test_unrelated_change_survives_inverse_and_fails_original_baseline(self):
  from unittest.mock import patch
  tree=ast.parse(SOURCE.read_text());tree.body.extend(ast.parse('UNREVIEWED_OUTSIDE_AGGREGATE = 1').body);before=ast.dump(tree)
  restored=undo_approved_aggregate_runtime(self,tree);self.assertEqual(ast.dump(tree),before);self.assertIn('UNREVIEWED_OUTSIDE_AGGREGATE',ast.unparse(restored))
  with tempfile.TemporaryDirectory()as tmp:
   path=Path(tmp)/'runtime.py';path.write_text(ast.unparse(tree))
   with patch.dict(globals(),SOURCE=path),self.assertRaises(AssertionError)as error:Preservation('test_only_one_diagnostic_save_added').test_only_one_diagnostic_save_added()
   self.assertIn(BASE_AST_SHA,str(error.exception));self.assertNotIn('exact reviewed aggregate runtime branch',str(error.exception))

if __name__=='__main__':unittest.main()
