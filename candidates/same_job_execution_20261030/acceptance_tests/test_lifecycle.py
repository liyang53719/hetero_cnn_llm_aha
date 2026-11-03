# Only historical source/AST assertions use the exact finite-layer inverse.
# Runtime tests still import and execute the actual candidate implementations.
import pathlib as _finite_pathlib, importlib.util as _finite_importlib
_finite_path=_finite_pathlib.Path(__file__).resolve().parents[3]/'candidates/model_candidate_build_20261101/finite_watchdog_test_inverse.py'
_finite_spec=_finite_importlib.spec_from_file_location('finite_watchdog_test_inverse',_finite_path)
_finite_module=_finite_importlib.module_from_spec(_finite_spec);_finite_spec.loader.exec_module(_finite_module)
prior_text=_finite_module.prior_text;prior_sha=_finite_module.prior_sha
import hashlib
import argparse,ast,importlib.util,json,pathlib,tempfile,types,unittest
from unittest.mock import patch
import os,copy
D=pathlib.Path(os.environ.get('FIRST_FAULT_LEGACY_TEST_SOURCE',str(pathlib.Path(__file__).resolve().parents[1]))).resolve()/'numeric'
import sys
sys.path.insert(0,str(D))
spec=importlib.util.spec_from_file_location('owned',D/'consumer_owned.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE=D.parent/'acceptance_tests/fixtures/consumer_r2_baseline.py.txt'
FIRST_FAULT_FUNCTION_INVERSE = {'artifact_identity': [('2d8f6018425ba181ef78c0d4d1e6028497c6fe7ff499a02ff45bc7281b69a909',
                        "if frozen['schema'] == FIRST_FAULT_SCHEMA:\n"
                        "    need(source_relocation is not None and source_relocation.get('candidate_scope') "
                        "== FIRST_FAULT_SCOPE and (source_relocation.get('builder_identity') == "
                        "frozen['artifact_identity']), 'independently admitted first fault artifact')\n"
                        "elif frozen['schema'] == 'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1':\n"
                        "    need(source_relocation is not None and source_relocation.get('candidate_scope') "
                        "== 'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' and "
                        "(source_relocation.get('builder_identity') == frozen['artifact_identity']), "
                        "'independently admitted model candidate, not a legacy schema alias')\n"
                        'else:\n'
                        "    need(frozen['schema'] == 'FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2', 'frozen "
                        "artifact schema')",
                        "if frozen['schema'] == 'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1':\n"
                        "    need(source_relocation is not None and source_relocation.get('candidate_scope') "
                        "== 'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' and "
                        "(source_relocation.get('builder_identity') == frozen['artifact_identity']), "
                        "'independently admitted model candidate, not a legacy schema alias')\n"
                        'else:\n'
                        "    need(frozen['schema'] == 'FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2', 'frozen "
                        "artifact schema')")],
 'coverage_policy': [('2151b5a7b72927bbff88f3c6fd8c40b761920f4000c9ed9be43f77128c306498',
                      "if source_relocation is not None and source_relocation.get('candidate_scope') == "
                      'FIRST_FAULT_SCOPE:\n'
                      "    path = path.with_name('first_fault_observation_contract.py')\n"
                      "    row = source_relocation['candidate_observation_checker']\n"
                      "    need(pin(row) == path, 'admitted first fault observation checker')\n"
                      "elif source_relocation is not None and source_relocation.get('candidate_scope') == "
                      "'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL':\n"
                      "    path = path.with_name('candidate_observation_contract.py')\n"
                      "    row = source_relocation['candidate_observation_checker']\n"
                      "    need(pin(row) == path, 'admitted candidate observation checker')\n"
                      'else:\n'
                      '    need(sha(path) == '
                      "'b8401fd6c8c238757103c3c093ea7dc6f3a0d37aab5f0d423e2a7edf2c293e71', 'reviewed "
                      "observation contract module')",
                      "if source_relocation is not None and source_relocation.get('candidate_scope') == "
                      "'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL':\n"
                      "    path = path.with_name('candidate_observation_contract.py')\n"
                      "    row = source_relocation['candidate_observation_checker']\n"
                      "    need(pin(row) == path, 'admitted candidate observation checker')\n"
                      'else:\n'
                      '    need(sha(path) == '
                      "'b8401fd6c8c238757103c3c093ea7dc6f3a0d37aab5f0d423e2a7edf2c293e71', 'reviewed "
                      "observation contract module')")],
 'load_binding': [('e33c535544b5c6b002f5dd003ebedbd7deb4b4bcd2d332a33e20b6c60ee44127',
                   "if frozen['schema'] == FIRST_FAULT_SCHEMA:\n"
                   "    need(type(profile) is int and profile == 0, 'first fault execution is P0 only')\n"
                   "    diagnostic_driver(frozen, source_relocation, common['driver'])\n"
                   'else:\n'
                   "    need(common['driver']['sha256'] == V3_DRIVER_SHA256, 'exact original V3 driver, no "
                   "config-only replacement')",
                   "need(common['driver']['sha256'] == V3_DRIVER_SHA256, 'exact original V3 driver, no "
                   "config-only replacement')")],
 'verify_local_build': [('832633b7f44c56396020619899f974129d869a1112bee4084c6ea9670a0f8481',
                         'if cloud is not None:\n'
                         "    need(getattr(args, 'local_build_result', None) is None and getattr(args, "
                         "'local_build_result_sha256', None) is None, 'imported build is not same-job "
                         "retained result')\n"
                         '    binding = cloud_invocation(args)\n'
                         "    candidate = frozen['schema'] in "
                         "('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1', FIRST_FAULT_SCHEMA)\n"
                         '    path = '
                         "pathlib.Path(__file__).resolve().with_name('candidate_artifact_handoff.py' if "
                         "candidate else 'artifact_handoff.py')\n"
                         '    if candidate:\n'
                         "        need(binding['pins'].get(str(path)) == sha(path), 'reviewed candidate "
                         "build verifier source')\n"
                         '    else:\n'
                         '        need(sha(path) == '
                         "'06ac175b7c1f8ca5b1dc19891a52c09f58f17fec521ee96e0f581ca4011ef0c5', 'reviewed "
                         "imported build verifier')\n"
                         "    spec = importlib.util.spec_from_file_location('verified_builder_handoff', "
                         'path)\n'
                         '    m = importlib.util.module_from_spec(spec)\n'
                         '    spec.loader.exec_module(m)\n'
                         "    need(frozen['artifact_identity']['run_id'] == args.expected_run_id and "
                         "frozen['artifact_identity']['launch_commit'] == args.expected_launch_commit, "
                         "'expected builder identity distinct from executor')\n"
                         "    kwargs = dict(executor_adaptation=binding.get('executor_adaptation'))\n"
                         '    if candidate:\n'
                         "        kwargs.update(current_source_pins_pin=binding['source_pins'], "
                         "repo=binding['repo'], "
                         "model_candidate_review=binding.get('model_candidate_review'))\n"
                         '    return m.verify(args.builder_handoff, args.builder_handoff_sha256, '
                         'args.artifact_manifest, args.artifact_manifest_sha256, frozen, cloud, **kwargs)',
                         'if cloud is not None:\n'
                         "    need(getattr(args, 'local_build_result', None) is None and getattr(args, "
                         "'local_build_result_sha256', None) is None, 'imported build is not same-job "
                         "retained result')\n"
                         '    binding = cloud_invocation(args)\n'
                         "    candidate = frozen['schema'] == "
                         "'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'\n"
                         '    path = '
                         "pathlib.Path(__file__).resolve().with_name('candidate_artifact_handoff.py' if "
                         "candidate else 'artifact_handoff.py')\n"
                         '    if candidate:\n'
                         "        need(binding['pins'].get(str(path)) == sha(path), 'reviewed candidate "
                         "build verifier source')\n"
                         '    else:\n'
                         '        need(sha(path) == '
                         "'06ac175b7c1f8ca5b1dc19891a52c09f58f17fec521ee96e0f581ca4011ef0c5', 'reviewed "
                         "imported build verifier')\n"
                         "    spec = importlib.util.spec_from_file_location('verified_builder_handoff', "
                         'path)\n'
                         '    m = importlib.util.module_from_spec(spec)\n'
                         '    spec.loader.exec_module(m)\n'
                         "    need(frozen['artifact_identity']['run_id'] == args.expected_run_id and "
                         "frozen['artifact_identity']['launch_commit'] == args.expected_launch_commit, "
                         "'expected builder identity distinct from executor')\n"
                         "    kwargs = dict(executor_adaptation=binding.get('executor_adaptation'))\n"
                         '    if candidate:\n'
                         "        kwargs.update(current_source_pins_pin=binding['source_pins'], "
                         "repo=binding['repo'], "
                         "model_candidate_review=binding.get('model_candidate_review'))\n"
                         '    return m.verify(args.builder_handoff, args.builder_handoff_sha256, '
                         'args.artifact_manifest, args.artifact_manifest_sha256, frozen, cloud, **kwargs)')]}
def undo_first_fault_function(test,tree,relative):
 import copy
 for digest,new_text,old_text in FIRST_FAULT_FUNCTION_INVERSE[relative]:
  want=ast.parse(new_text).body;replacement=ast.parse(old_text).body
  test.assertEqual(hashlib.sha256(ast.dump(ast.Module(body=want,type_ignores=[]),include_attributes=False).encode()).hexdigest(),digest)
  count=0
  want_dump=[ast.dump(n,include_attributes=False)for n in want]
  def visit(node):
   nonlocal count
   for field,value in ast.iter_fields(node):
    if isinstance(value,list):
     i=0
     while i<=len(value)-len(want):
      if all(type(n)is type(w)for n,w in zip(value[i:i+len(want)],want)) and [ast.dump(n,include_attributes=False)for n in value[i:i+len(want)]]==want_dump:
       value[i:i+len(want)]=copy.deepcopy(replacement);count+=1;i+=len(replacement)
      else:i+=1
     for item in value:
      if isinstance(item,ast.AST):visit(item)
    elif isinstance(value,ast.AST):visit(value)
  visit(tree);test.assertEqual(count,1,'exact reviewed inverse snippet matched once: '+digest)
 return tree

class Tests(unittest.TestCase):
 def test_original_functions_ast(self):
  old={n.name:n for n in ast.parse(BASE.read_text()).body if isinstance(n,ast.FunctionDef)}
  new={n.name:n for n in ast.parse(prior_text(D/'consumer_owned.py')).body if isinstance(n,ast.FunctionDef)}
  for name in FIRST_FAULT_FUNCTION_INVERSE:undo_first_fault_function(self,new[name],name)
  dump=lambda n:ast.dump(n,include_attributes=False)
  # Only this reviewed split dispatch may precede the unchanged original path.
  expected=ast.parse("""
cloud=executor_context(args)
if cloud is not None:
    need(getattr(args,'local_build_result',None) is None and getattr(args,'local_build_result_sha256',None) is None,'imported build is not same-job retained result')
    binding=cloud_invocation(args)
    candidate=frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'
    path=pathlib.Path(__file__).resolve().with_name('candidate_artifact_handoff.py' if candidate else 'artifact_handoff.py')
    if candidate:need(binding['pins'].get(str(path))==sha(path),'reviewed candidate build verifier source')
    else:need(sha(path)=='HANDOFF_SHA','reviewed imported build verifier')
    spec=importlib.util.spec_from_file_location('verified_builder_handoff',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    need(frozen['artifact_identity']['run_id']==args.expected_run_id and frozen['artifact_identity']['launch_commit']==args.expected_launch_commit,'expected builder identity distinct from executor')
    kwargs=dict(executor_adaptation=binding.get('executor_adaptation'))
    if candidate:kwargs.update(current_source_pins_pin=binding['source_pins'],repo=binding['repo'],model_candidate_review=binding.get('model_candidate_review'))
    return m.verify(args.builder_handoff,args.builder_handoff_sha256,args.artifact_manifest,args.artifact_manifest_sha256,frozen,cloud,**kwargs)
need(getattr(args,'builder_handoff_sha256',None) is None,'no unpaired handoff')
""".replace('HANDOFF_SHA',hashlib.sha256((D/'artifact_handoff.py').read_bytes()).hexdigest())).body
  actual=new['verify_local_build'];self.assertEqual(list(map(dump,actual.body[1:4])),list(map(dump,expected)))
  actual.body=actual.body[:1]+actual.body[4:]
  # Exact failed-Popen tightening and successful-Popen tightening inside the
  # existing cleanup try. Restoring these two additions must recover old AST.
  old_with=next(n for n in old['execute'].body if isinstance(n,ast.With))
  new_with=next(n for n in new['execute'].body if isinstance(n,ast.With))
  wrapper=new_with.body[0]
  self.assertIsInstance(wrapper,ast.Try);self.assertEqual(wrapper.finalbody,[]);self.assertEqual(wrapper.orelse,[]);self.assertEqual(len(wrapper.body),1)
  actual_argv=wrapper.body[0].value.args[0]
  expected_argv=ast.parse("runtime_abi_module().execution_argv(binary,runtime,output,limits['max_active_cycles']) if WORKSPACE_LOADER is not None else [str(binary),str(runtime),str(output),str(limits['max_active_cycles'])]",mode='eval').body
  self.assertEqual(dump(actual_argv),dump(expected_argv))
  wrapper.body[0].value.args[0]=actual_argv.orelse
  self.assertEqual(dump(wrapper.body[0]),dump(old_with.body[0]))
  expected_handler=ast.parse('try:\n pass\nexcept BaseException:\n if CLOUD_MEMORY is not None:CLOUD_MEMORY.after_popen()\n raise').body[0].handlers
  self.assertEqual(list(map(dump,wrapper.handlers)),list(map(dump,expected_handler)))
  original_try=new_with.body[1];self.assertIsInstance(original_try,ast.Try)
  expected_call=ast.parse('if CLOUD_MEMORY is not None:CLOUD_MEMORY.after_popen()').body[0]
  self.assertEqual(dump(original_try.body[0]),dump(expected_call));original_try.body=original_try.body[1:]
  new_with.body=wrapper.body+new_with.body[1:]
  # Each approved dependency lock is the sole permitted constant change;
  # neither function's coverage/environment logic may change.
  configured=new['runtime_abi_module']
  expected_workspace=ast.parse('if WORKSPACE_LOADER is not None:m.configure_workspace_loader(*WORKSPACE_LOADER)').body[0]
  self.assertEqual(dump(configured.body[-2]),dump(expected_workspace));configured.body.pop(-2)
  for function,dependency in [('runtime_abi_module','runtime_abi_owned.py'),('coverage_policy','observation_contract.py')]:
   previous=[n for n in ast.walk(old[function])if isinstance(n,ast.Constant)and isinstance(n.value,str)and len(n.value)==64]
   current=[n for n in ast.walk(new[function])if isinstance(n,ast.Constant)and isinstance(n.value,str)and len(n.value)==64]
   self.assertEqual(len(previous),1,function);self.assertEqual(len(current),1,function)
   self.assertEqual(current[0].value,hashlib.sha256((D/dependency).read_bytes()).hexdigest(),function);previous[0].value=current[0].value
  # Candidate selection must remain the exact reviewed branch; normalize only
  # that branch to the unchanged original historical observation check.
  coverage=new['coverage_policy']
  expected_candidate=ast.parse("""
if source_relocation is not None and source_relocation.get('candidate_scope')=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL':
    path=path.with_name('candidate_observation_contract.py');row=source_relocation['candidate_observation_checker'];need(pin(row)==path,'admitted candidate observation checker')
else:need(sha(path)=='OBS_SHA','reviewed observation contract module')
""".replace('OBS_SHA',hashlib.sha256((D/'observation_contract.py').read_bytes()).hexdigest())).body[0]
  self.assertEqual(dump(coverage.body[2]),dump(expected_candidate));coverage.body[2:3]=coverage.body[2].orelse
  artifact=new['artifact_identity']
  self.assertEqual([a.arg for a in artifact.args.args],['frozen','source_relocation']);self.assertEqual(list(map(dump,artifact.args.defaults)),[dump(ast.Constant(value=None))])
  expected_identity=ast.parse("""
if frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1':
    need(source_relocation is not None and source_relocation.get('candidate_scope')=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' and source_relocation.get('builder_identity')==frozen['artifact_identity'],'independently admitted model candidate, not a legacy schema alias')
else:need(frozen['schema']=='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2','frozen artifact schema')
""").body[0]
  self.assertEqual(dump(artifact.body[0]),dump(expected_identity));artifact.body[:1]=artifact.body[0].orelse;artifact.args.args.pop();artifact.args.defaults.pop()
  artifact_calls=[n for n in ast.walk(new['load_binding'])if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='artifact_identity']
  self.assertEqual(len(artifact_calls),1);self.assertEqual(list(map(dump,artifact_calls[0].args)),[dump(ast.Name(id='frozen',ctx=ast.Load())),dump(ast.Name(id='source_relocation',ctx=ast.Load()))]);artifact_calls[0].args.pop()
  # Precisely normalize only this optional internal relocation context. It is
  # never supplied by a bundle field; original None branch must be exact old AST.
  for name in ('coverage_policy','load_binding'):
   actual=new[name];prior=old[name]
   self.assertEqual([arg.arg for arg in actual.args.args],[arg.arg for arg in prior.args.args]+['source_relocation'])
   self.assertEqual(list(map(dump,actual.args.defaults)),list(map(dump,prior.args.defaults))+[dump(ast.Constant(value=None))])
   actual.args.args.pop();actual.args.defaults.pop()
  coverage=new['coverage_policy']
  approved_tail=ast.parse("if source_relocation is None:return module.validate(profile,common,identity,bundle_root)\nreturn module.validate(profile,common,identity,bundle_root,source_relocation)").body
  self.assertEqual(list(map(dump,coverage.body[-2:])),list(map(dump,approved_tail)))
  coverage.body=coverage.body[:-2]+[old['coverage_policy'].body[-1]]
  links=[n for n in ast.walk(new['load_binding'])if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='coverage_policy']
  prior_links=[n for n in ast.walk(old['load_binding'])if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='coverage_policy']
  self.assertEqual(len(links),1);self.assertEqual(len(prior_links),1)
  self.assertEqual(list(map(dump,links[0].args)),list(map(dump,prior_links[0].args))+[dump(ast.Name(id='source_relocation',ctx=ast.Load()))])
  links[0].args.pop()
  for name in old:
   if name not in ('main','compare','router_compare','classify_observed_profile'):self.assertEqual(dump(old[name]),dump(new[name]),name)
 def test_candidate_relocation_merges_context_without_duplicate_keywords(self):
  # The candidate context already contains source_manifest_sha256. Preserve
  # every reviewed context field, then explicitly set the authoritative common
  # join fields; never pass overlapping **context and keyword arguments.
  functions={n.name:n for n in ast.parse((D/'consumer_owned.py').read_text()).body if isinstance(n,ast.FunctionDef)}
  expected=ast.parse("""
result=dict(context or {})
result.update(schema='ADMITTED_CLOUD_P0_SOURCE_RELOCATION_V1',controller_binding=dict(path=str(args.cloud_binding),bytes=args.cloud_binding.stat().st_size,sha256=args.cloud_binding_sha256),executor_adaptation_sha256=binding['executor_adaptation']['sha256'],artifact_manifest_sha256=args.artifact_manifest_sha256,source_manifest_sha256=source_row['sha256'],builder_source_commit=frozen['artifact_identity']['source_commit'],executor_source_commit=provenance['executor_identity']['source_commit'],executor_source_pins_sha256=adaptation['executor_source_pins_sha256'],anchors=anchors)
return result
""").body
  dump=lambda n:ast.dump(n,include_attributes=False)
  self.assertEqual(list(map(dump,functions['approved_source_relocation'].body[-3:])),list(map(dump,expected)))
 def test_limits_only_wall_copy(self):
  original=dict(wall_seconds=20000,cpu_seconds=18000,address_space_bytes=12*1024**3,file_bytes=64*1024**2,max_active_cycles=1000000000)
  actual=m.owned_execution_limits(original,120)
  self.assertEqual(actual,dict(original,wall_seconds=120));self.assertEqual(original['wall_seconds'],20000)
  self.assertEqual(m.owned_execution_limits(original,None),original)
 def test_wall_reject(self):
  for value in (0,-1,20001,True,1.5):
   with self.assertRaises(ValueError):m.owned_execution_limits({'wall_seconds':20000},value)
 def test_outer_context(self):
  with patch.object(m.os,'getpid',return_value=5),patch.object(m.os,'getpgrp',return_value=5),patch.object(m.os,'getsid',return_value=5):
   m.require_outer_context(True)
   with self.assertRaises(ValueError):m.require_outer_context(False)
  with patch.object(m.os,'getpid',return_value=5),patch.object(m.os,'getpgrp',return_value=4),patch.object(m.os,'getsid',return_value=4):
   with self.assertRaises(ValueError):m.require_outer_context(True)
 def invoke(self,timeout=False):
  proc=types.SimpleNamespace(pid=71,poll=lambda:None,kill=unittest.mock.Mock(),wait=unittest.mock.Mock())
  state=None if timeout else types.SimpleNamespace(si_status=0,si_code=m.os.CLD_EXITED)
  with patch.object(m,'sha',return_value='a'*64),tempfile.TemporaryDirectory() as t,patch.object(m.subprocess,'Popen',return_value=proc) as popen,patch.object(m.os,'waitid',return_value=state),patch.object(m.os,'killpg') as killpg,patch.object(m.time,'monotonic',side_effect=[0,2] if timeout else [0]),patch.object(m,'runtime_abi_module',return_value=types.SimpleNamespace(clean_env=lambda:{'LANG':'C'})):
   limits={'address_space_bytes':1024**3,'cpu_seconds':1,'file_bytes':1024,'max_active_cycles':123,'wall_seconds':1}
   if timeout:
    with self.assertRaises(TimeoutError):m.execute(pathlib.Path('/fake/dut'),pathlib.Path('/fake/runtime'),pathlib.Path('/fake/output'),pathlib.Path(t)/'log',limits)
   else:self.assertEqual(m.execute(pathlib.Path('/fake/dut'),pathlib.Path('/fake/runtime'),pathlib.Path('/fake/output'),pathlib.Path(t)/'log',limits),0)
   self.assertNotIn('start_new_session',popen.call_args.kwargs);self.assertNotIn('process_group',popen.call_args.kwargs)
   killpg.assert_not_called();proc.kill.assert_called_once();proc.wait.assert_called_once()
   self.assertEqual(popen.call_args.args[0],['/fake/dut','/fake/runtime','/fake/output','123'])
 def test_normal_inherits_group(self):self.invoke()
 def test_timeout_inherits_group_cleanup(self):self.invoke(True)
 def test_inner_never_self_approves_outer_cleanup(self):
  tree=ast.parse((D/'consumer_owned.py').read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  self.assertTrue(any(isinstance(n,ast.Raise) and ast.unparse(n.exc)=="SystemExit(1 if summary['status'] == 'FAIL_EXACT_REFERENCE' else 2)" for n in ast.walk(main)))

class FirstFaultInverseNegativeTests(unittest.TestCase):
 def test_every_fixed_fragment_duplicate_rejected(self):
  for name,rows in FIRST_FAULT_FUNCTION_INVERSE.items():
   for _,text,_ in rows:
    fixture=ast.parse('\n'.join(row[1]for row in rows))
    fixture.body.extend(ast.parse(text).body)
    with self.subTest(name=name,fragment=text[:60]),self.assertRaises(AssertionError):undo_first_fault_function(self,fixture,name)
 def test_every_fixed_fragment_mutation_rejected(self):
  for name,rows in FIRST_FAULT_FUNCTION_INVERSE.items():
   for index,(_,text,_)in enumerate(rows):
    parts=[ast.parse(row[1]).body for row in rows]
    # Mutate one literal in this exact fragment; no production code runs.
    constants=[n for stmt in parts[index]for n in ast.walk(stmt)if isinstance(n,ast.Constant)and isinstance(n.value,str)]
    self.assertTrue(constants);constants[0].value='UNREVIEWED_FIRST_FAULT_TEST_MUTATION'
    fixture=ast.Module(body=[n for part in parts for n in part],type_ignores=[])
    with self.subTest(name=name,fragment=text[:60]),self.assertRaises(AssertionError):undo_first_fault_function(self,fixture,name)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=pathlib.Path,required=True);args,rest=parser.parse_known_args();BASE=args.baseline
 unittest.main(argv=[__file__]+rest)
