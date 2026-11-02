"""Synthetic generated-header/GCC joins with actual deterministic generators.
No compiler, ELF, hardware, resource authority or numerical PASS.
"""
import ast,copy,json,pathlib,unittest,hashlib
import first_fault_compilation as check
import first_fault_probe as scalar
import terminal_finite_probe as terminal
import test_first_fault_compilation as scalar_fixture
import first_fault_policy as policy
from test_first_fault_probe import synthetic_header
D=pathlib.Path(__file__).resolve().parent
class Tests(unittest.TestCase):
 def setUp(self):
  self.base=scalar_fixture.Tests();self.base.setUp();self.addCleanup(self.base.doCleanups)
  self.source=self.base.source;self.dep=self.base.dep;self.contract=copy.deepcopy(self.base.contract)
  self.repo=self.base.w/'repo';self.obj=self.base.w/'obj'
  schema=self.repo/'candidates/model_candidate_build_20261101/TERMINAL_FINITE_SCHEMA.json';schema.write_bytes((D/schema.name).read_bytes())
  config=schema.with_name('TERMINAL_FINITE_READONLY.vlt');config.write_bytes(terminal.config_bytes())
  doc,_=scalar.load_schema(D/'FIXED_NONHIER_SCHEMA.json')
  raw=synthetic_header(doc).replace(b'\n};',(''.join('\n    IData/*31:0*/ '+terminal.MEMBER_PREFIX+str(r)+'_'+str(c)+';'for r in range(16)for c in range(256))+'\n};').encode())
  root=self.obj/'VHostBlockTopV4___024root.h';root.write_bytes(raw)
  pin=lambda p:dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
  self.scalar_gen=self.source['readonly_probe']['accessor_generation'];self.scalar_gen['root_header']=pin(root)
  self.gen=terminal.generate(schema,config,root,self.obj/'readonly_terminal_finite_access.hpp',self.obj/'terminal_evidence.json')
  for key,role in [('schema_input','terminal_probe_schema'),('config','terminal_probe_config')]:
   row=self.gen[key];self.contract[role]=dict(repo_path=str(pathlib.Path(row['path']).relative_to(self.repo)),bytes=row['bytes'],sha256=row['sha256'])
   self.source['generation_input_pins'][row['path']]=row['sha256']
  for role,name in [('terminal_probe_generator','terminal_finite_probe.py'),('terminal_record_schema','TERMINAL_FINITE_RECORD_SCHEMA.json')]:
   # Record bytes deliberately synthetic until final contract fixture below.
   p=schema.with_name(name);p.write_bytes((D/name).read_bytes()if(D/name).exists()else b'{"scope":"synthetic-record"}\n');r=pin(p)
   self.contract[role]=dict(repo_path=str(p.relative_to(self.repo)),bytes=r['bytes'],sha256=r['sha256']);self.source['generation_input_pins'][str(p)]=r['sha256']
  for key in ('root_header','accessor'):
   row=self.gen[key];r={k:row[k]for k in ('path','bytes','sha256')};self.source['derived_generated_pins'][r['path']]=r['sha256'];self.dep['dependencies'][r['path']]=r
 def verify(self):return check.verify_terminal_probe(self.gen,self.scalar_gen,self.contract,self.source,self.dep,str(self.repo))
 def test_all4096_actual_generator_join(self):
  r=self.verify();self.assertEqual(r['word_count'],4096);self.assertFalse(r['numerical_pass']);self.assertFalse(r['output_raw_words'])
 def test_missing_terminal_dependency(self):
  del self.dep['dependencies'][self.gen['accessor']['path']]
  with self.assertRaises(ValueError):self.verify()
 def test_wrong_root_even_if_rehashed(self):
  self.gen['root_header']['sha256']='0'*64
  with self.assertRaises(ValueError):self.verify()
 def test_one_field_missing(self):
  self.gen['mappings'].pop()
  with self.assertRaises(ValueError):self.verify()
 def test_wrong_width(self):
  self.gen['mappings'][0]['width_bits']=31
  with self.assertRaises(ValueError):self.verify()
 def test_bool_index_rejected(self):
  self.gen['mappings'][0]['index']=False
  with self.assertRaises(ValueError):self.verify()
 def test_reordered_mapping(self):
  m=self.gen['mappings'];m[0],m[1]=m[1],m[0]
  with self.assertRaises(ValueError):self.verify()
 def test_forged_accessor_with_consistent_hashes(self):
  row=self.gen['accessor'];row['text']+='// not deterministic\n';row['bytes']=len(row['text'].encode());row['sha256']=check.sha(row['text'].encode());self.source['derived_generated_pins'][row['path']]=row['sha256'];self.dep['dependencies'][row['path']]={k:row[k]for k in ('path','bytes','sha256')}
  with self.assertRaises(ValueError):self.verify()
 def test_duplicate_basename_dependency(self):
  r=dict(self.dep['dependencies'][self.gen['accessor']['path']],path='/wrong/readonly_terminal_finite_access.hpp');self.dep['dependencies'][r['path']]=r
  with self.assertRaises(ValueError):self.verify()
 def test_record_role_not_generation_pinned(self):
  del self.source['generation_input_pins'][str(self.repo/self.contract['terminal_record_schema']['repo_path'])]
  with self.assertRaises(ValueError):self.verify()
 def test_extra_evidence_field(self):
  self.gen['accepted']=True
  with self.assertRaises(ValueError):self.verify()
 def test_global_config_even_rehashed(self):
  row=self.gen['config'];row['text']+='public_flat_rw\n';row['bytes']=len(row['text'].encode());row['sha256']=check.sha(row['text'].encode())
  with self.assertRaises(ValueError):self.verify()
 def test_raw_output_scope_rejected(self):
  self.gen['output_raw_words']=True
  with self.assertRaises(ValueError):self.verify()
class FullContractTests(Tests):
 def setUp(self):
  super().setUp()
  raw=(D/'FIRST_FAULT_TERMINAL_DRIVER_CONTRACT.json').read_bytes();self.contract=policy.decode_contract(raw)
  self.assertEqual(self.contract['schema'],'FIRST_FAULT_DRIVER_CONTRACT_V2')
  cp=self.repo/policy.contract_path(self.contract)
  contractpin=dict(path=str(cp),bytes=len(raw),sha256=policy.contract_sha(self.contract),text=raw.decode())
  olddriver=self.dep['driver'];self.dep['driver']=str(self.repo/self.contract['diagnostic_driver']['repo_path'])
  self.assertEqual(self.dep['driver'],olddriver)
  helper=self.repo/self.contract['host_observer']['repo_path'];h=self.contract['host_observer']
  self.dep['dependencies'][str(helper)]=dict(path=str(helper),bytes=h['bytes'],sha256=h['sha256'])
  self.source['readonly_probe'].update(schema='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V2',contract=contractpin,terminal_accessor_generation=self.gen)
  self.source['generation_input_pins'][str(cp)]=contractpin['sha256']
  for name in policy.contract_roles(self.contract):
   r=self.contract[name];self.source['generation_input_pins'][str(self.repo/r['repo_path'])]=r['sha256']
  self.source['driver_sha256']=self.contract['diagnostic_driver']['sha256']
  self.source['physical_closure']['initial_frontend_argv'].append(self.gen['config']['path'])
  self.manifest=copy.deepcopy(self.base.manifest);self.manifest['readonly_probe_contract']={k:contractpin[k]for k in ('bytes','sha256')};self.manifest['common']['driver']['sha256']=self.source['driver_sha256']
  self.receipt=dict(scope=policy.FIRST_FAULT_SCOPE,readonly_probe_contract_sha256=policy.contract_sha(self.contract))
 def verify(self):return check.verify_readonly_probe(self.manifest,self.source,self.receipt,self.dep)
 def test_all4096_actual_generator_join(self):
  r=self.verify();self.assertEqual(r['field_count'],114);self.assertEqual(r['terminal_accessor']['word_count'],4096);self.assertFalse(r['numerical_pass'])
 def test_missing_third_vlt(self):
  self.source['physical_closure']['initial_frontend_argv'].pop()
  with self.assertRaises(ValueError):self.verify()
 def test_reordered_vlt(self):
  a=self.source['physical_closure']['initial_frontend_argv'];a[-1],a[-2]=a[-2],a[-1]
  with self.assertRaises(ValueError):self.verify()
 def test_old_evidence_schema_cannot_carry_terminal(self):
  self.source['readonly_probe']['schema']='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1'
  with self.assertRaises(ValueError):self.verify()
 def test_missing_terminal_generation(self):
  del self.source['readonly_probe']['terminal_accessor_generation']
  with self.assertRaises((ValueError,KeyError)):self.verify()
 def test_old_helper_not_valid_for_v2(self):
  p=str(self.repo/self.contract['host_observer']['repo_path']);self.dep['dependencies'][p]['sha256']=self.base.contract['host_observer']['sha256']
  with self.assertRaises(ValueError):self.verify()

class ActualPackBranchTests(FullContractTests):
 def pack_branch(self,missing=False,tamper=False,legacy=False):
  spec=importlib.util.spec_from_file_location('_terminal_pack_branch_exact',D/'pack_model_candidate.py');pack=importlib.util.module_from_spec(spec);spec.loader.exec_module(pack)
  self.assertEqual(pathlib.Path(pack.__file__).resolve(),D/'pack_model_candidate.py')
  tree=ast.parse(pathlib.Path(pack.__file__).read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_pack_impl')
  branches=[n for n in fn.body if isinstance(n,ast.If)and ast.unparse(n.test)=='readonly is not None'and any(isinstance(x,ast.Constant)and x.value=='terminal_probe_evidence'for x in ast.walk(n))]
  self.assertEqual(len(branches),1)
  cp=self.obj/'contract.json';cp.write_text(self.source['readonly_probe']['contract']['text'])
  ep=self.obj/'scalar.json';ep.write_text(json.dumps(self.scalar_gen));tp=self.obj/'terminal.json';tp.write_text(json.dumps(self.gen))
  pin=lambda p:dict(path=str(p),bytes=p.stat().st_size,sha256=pack.sha(p))
  b=dict(readonly_probe_evidence=pin(ep),pins={str(ep):pack.sha(ep),str(tp):pack.sha(tp)})
  if not missing:b['terminal_probe_evidence']=pin(tp)
  if tamper:tp.write_text('{}')
  ns=dict(readonly=self.base.contract if legacy else self.contract,original={'first_fault_driver_contract':{'path':str(cp)}},b=b,regular=pack.regular,pin=pack.pin,need=pack.need,json_file=pack.json_file,source={})
  exec(compile(ast.fix_missing_locations(ast.Module(body=branches,type_ignores=[])),'actual_pack_readonly_evidence_branch','exec'),ns)
  return ns['source']['readonly_probe']
 def test_actual_pack_preserves_both_generated_evidences(self):
  out=self.pack_branch();self.assertEqual(out['schema'],'FIRST_FAULT_READONLY_BUILD_EVIDENCE_V2');self.assertEqual(out['accessor_generation'],self.scalar_gen);self.assertEqual(out['terminal_accessor_generation'],self.gen)
 def test_actual_pack_missing_terminal_evidence_rejected(self):
  with self.assertRaises(KeyError):self.pack_branch(missing=True)
 def test_actual_pack_changed_terminal_evidence_rejected(self):
  with self.assertRaises(ValueError):self.pack_branch(tamper=True)
 def test_actual_pack_v1_terminal_injection_rejected(self):
  with self.assertRaises(ValueError):self.pack_branch(legacy=True)

import os,re,shutil,sys,tempfile,importlib.util,subprocess
import first_fault_probe as probe
import candidate_dependency_proof as proof
import pack_model_candidate as pack
from test_first_fault_pack_end_to_end import need,sha,write,tp,pin,remap,pack_and_verify
P=pathlib.Path
R=D.parents[1]

def fixture_space_gate(w,*,space_policy=None,workspace_disk_root=None):
 """Explicit local synthetic-test opt-in; never a production DUT admission."""
 if space_policy is None and workspace_disk_root is None:
  need(shutil.disk_usage(w).free >= (8<<30)+(256<<20),'8GiB plus temporary SV copy reserve')
  return
 need(space_policy is not None and workspace_disk_root is not None,'both explicit filesystem-policy arguments required')
 # The supervised caller pins this test-only policy. It performs fresh OS checks,
 # not a boolean/preflight receipt, and rejects any non-exact owned filesystem.
 space_policy.construction(workspace_disk_root,w)

def construct_terminal(w,payload,oldrepo,*,space_policy=None,workspace_disk_root=None):
 """Small real source-role files only, not thousands of synthetic pin slots."""
 fixture_space_gate(w,space_policy=space_policy,workspace_disk_root=workspace_disk_root)
 host=payload/'hardware.sv';need(sha(host)==policy.ORIGINAL_SV_SHA,'original SV actual bytes')
 repo=w/'repo';obj=w/'obj';out=w/'run';obj.mkdir();out.mkdir()
 def copy_source(rel):
  choices=(R/rel,oldrepo/rel)
  q=next((q for q in choices if q.is_file()),None);need(q is not None,'missing source '+rel)
  return write(repo/rel,q.read_bytes())
 contract=policy.decode_contract((D/'FIRST_FAULT_TERMINAL_DRIVER_CONTRACT.json').read_bytes())
 for row in contract.values():
  if isinstance(row,dict)and 'repo_path'in row:
   p=copy_source(row['repo_path']);need(pin(p)['sha256']==row['sha256']and p.stat().st_size==row['bytes'],'actual role source')
 for rel in (policy.contract_path(contract),policy.SOURCE_CONTRACT_REPO_PATH):copy_source(rel)
 for p in D.glob('*.py'):write(repo/'candidates/model_candidate_build_20261101'/p.name,p.read_bytes())
 copy_source('candidates/model_candidate_build_20261101/MODEL_CANDIDATE_PRECONDITIONS.json')
 abi=copy_source('candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json')
 copy_source('candidates/split_build_only_20261031/seven_files.py')
 original=json.loads((payload/'source_manifest.json').read_text())
 ov=copy_source('candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json')
 rows=json.loads(ov.read_text())['files'];sc=__import__('model_source_evidence')
 for filename in sc.SCALA.values():copy_source(next(r['repo_path']for r in rows if r['name']==filename))
 for role in ('sparse_memory','program_manifest'):copy_source(original['model_source_evidence']['anchors'][role])
 for name in proof.OBSERVER_HEADER_PINS:copy_source(str(P(contract['diagnostic_driver']['repo_path']).parent/name))
 driver=repo/contract['diagnostic_driver']['repo_path'];helper=repo/contract['host_observer']['repo_path']
 olddep=original['model_candidate_build_evidence']['driver_dependency'];oldbuilder=olddep['driver'].split('/candidates/')[0]
 pairs=[(olddep['driver'],str(driver)),(olddep['cwd'],str(obj)),(oldbuilder,str(repo)),(P(olddep['driver']).stem,driver.stem)]
 dep=remap(olddep,pairs)
 # Original official global_make bytes retained exactly; other generated text is synthetic.
 for key in ('host_make','host_hierarchy','depfile'):
  r=dep[key];dep[key]=tp(P(r['path']),r['text'])
 gen={};derived={}
 for p in repo.rglob('*'):
  if p.is_file():gen[str(p)]=sha(p)
 # Frozen implementation hashes must match actual source bytes, never artifact-assigned values.
 for rel,h in proof.TERMINAL_IMPLEMENTATION_PINS.items():
  q=copy_source(rel);need(sha(q)==h,'independently frozen implementation source '+rel);gen[str(q)]=h
 need(sha(D/'pack_model_candidate.py')==proof.LOCAL_PACK_READER_SHA,'actual local pack map')
 schema=repo/contract['probe_schema']['repo_path'];config=repo/contract['probe_config']['repo_path'];doc,_=probe.load_schema(schema)
 combined=synthetic_header(doc).replace(b'\n};',(''.join('\n    IData/*31:0*/ '+terminal.MEMBER_PREFIX+str(r)+'_'+str(c)+';'for r in range(16)for c in range(256))+'\n};').encode())
 rh=write(obj/'VHostBlockTopV4___024root.h',combined);accessor=obj/'readonly_first_fault_access.hpp';ep=w/'probe.json'
 generated=probe.generate(schema,config,rh,accessor,ep)
 tconfig=repo/contract['terminal_probe_config']['repo_path'];taccessor=obj/'readonly_terminal_finite_access.hpp';tep=w/'terminal.json'
 terminal.generate(repo/contract['terminal_probe_schema']['repo_path'],tconfig,rh,taccessor,tep)
 ports=json.loads(abi.read_text());lines=[]
 for name,(direction,width)in ports.items():
  kind='8'if width<=8 else '16'if width<=16 else ''if width<=32 else '64'if width<=64 else 'W';suffix=','+str((width+31)//32)if width>64 else ''
  lines.append('VL_'+('IN'if direction=='input'else'OUT')+kind+'(&'+name+','+str(width-1)+',0'+suffix+');')
 hp=write(obj/'VHostBlockTopV4.h',('\n'.join(lines)+'\n').encode())
 dependencies={}
 for path,row in dep['dependencies'].items():
  p=P(path)
  if p==P(dep['driver']):p=driver
  if p.name=='VHostBlockTopV4.h':p=hp
  if p.exists():row=pin(p)
  else:row=dict(row,path=str(p)) # explicit synthetic compiler include metadata
  dependencies[str(p)]=row
 for p in (driver,hp,rh,accessor,taccessor,helper):dependencies[str(p)]=pin(p)
 dep['dependencies']=dependencies
 dep['depfile']=tp(obj/(driver.stem+'.d'),driver.stem+'.o: '+' '.join(dependencies)+'\n')
 for path,row in dependencies.items():
  (derived if str(obj)in path else gen)[path]=row['sha256']
 for key in ('host_make','host_hierarchy'):
  row=dep[key];write(P(row['path']),row['text'].encode());derived[row['path']]=row['sha256'];dep['make_closure_pins'][row['path']]=row['sha256']
 gen[dep['global_make']['path']]=dep['global_make']['sha256']
 dep['resolved_sparse_header']=dependencies[next(p for p in dependencies if P(p).name=='sparse_write_memory.hpp')]
 tool=json.loads((payload/'tool_manifest.json').read_text());toolp=write(w/'tool.json',tool)
 libs=re.findall(r'^VM_HIER_LIBS\s*:=\s*(.*)$',dep['host_hierarchy']['text'].replace('\\\n',' '),re.M)[0].split()
 argvs=proof.expected_phase_argv(str(obj),tool['compile_tools'],proof.CPP_O1_OVERRIDES,libs)
 phases=[];stagepins={}
 for name in pack.STAGES:
  argv=argvs.get(name,['SYNTHETIC_NOT_EXECUTED',name]);r={'native_exit':0,'errors':[],'argv':argv,'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
  rp=write(out/name/'RESULT.json',r);stagepins[name]=pin(rp)
  if name in argvs:
   product=write(P(argv[2])/argv[-1],b'\x7fELF\x02\x01SYNTHETIC_NEVER_EXECUTE'if name=='host_link'else b'SYNTHETIC_ARCHIVE')
   phases.append(dict(phase=name,argv=argv,output=pin(product),supervisor=r))
 dep['host_link_receipt']=phases[-1]['supervisor'];dep['host_link_argv']=phases[-1]['argv'];dep['binary']=phases[-1]['output'];dep['compilation_phases']=copy.deepcopy(phases)
 phases[-1]['driver_dependency']=dep
 built={'status':'BUILT_UNQUALIFIED','scope':'ARCHIVE_LINK_ONLY_NOT_DUT_PASS','cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES,'phases':phases,'binary':phases[-1]['output'],'plan':{'phases':[dict(name=r['phase'],argv=r['argv'])for r in phases],'cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES}}
 # Minimal generation ledger keeps every actual dependency and contract/implementation join.
 obs=copy.deepcopy(original['model_candidate_observation']);obs['source_closure']['source_commit']='a'*40;obs['source_closure']['source_overlay']={k:pin(ov)[k]for k in ('bytes','sha256')}
 obs['stage_receipts']=[dict(name=n,bytes=stagepins[n]['bytes'],sha256=stagepins[n]['sha256'])for n in pack.STAGES]
 catalogfiles=[]
 for p in repo.rglob('*'):
  if p.is_file():catalogfiles.append(dict(path=str(p.relative_to(repo)),bytes=p.stat().st_size,sha256=sha(p)))
 cat=write(repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json',{'schema':'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','files':catalogfiles});obs['source_closure']['source_pins_sha256']=sha(cat)
 op=write(w/'observation.json',obs)
 source={'source_commit':'a'*40,'sv_sha256':sha(host),'driver_sha256':sha(driver),'cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES,'generation_input_pins':gen,'derived_generated_pins':derived,'physical_closure':{'initial_frontend_argv':['verilator','--hierarchical',str(repo/doc['original_hierarchy_pin']['repo_path']),str(config),str(tconfig)]}}
 # Hierarchy exact source is retained as a role, not a synthesized implementation identity.
 hierarchy=copy_source(doc['original_hierarchy_pin']['repo_path']);gen[str(hierarchy)]=sha(hierarchy)
 sp=write(w/'source.json',source)
 identity=dict(run_id=1,artifact_name='SYNTHETIC_FIRST_FAULT_E2E',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path='ci_launch/synthetic.json',launch_manifest_blob_sha='c'*40)
 actualpins={str(p):sha(p)for p in repo.rglob('*')if p.is_file()}
 actualpins[str(ep)]=sha(ep);actualpins[str(tep)]=sha(tep)
 b={'repo':str(repo),'repo_sha':'a'*40,'artifact_identity':identity,'driver':str(driver),'pins':actualpins,'first_fault_driver_contract':{'path':str(repo/policy.contract_path(contract)),'sha256':policy.contract_sha(contract)},'generation_contract':str(repo/contract['hardware_generation_contract']['repo_path']),'generation_contract_sha256':contract['hardware_generation_contract']['sha256'],'model_source_contract':str(repo/policy.SOURCE_CONTRACT_REPO_PATH),'fixed_source_overlay':str(ov),'source_manifest':str(sp),'tool_manifest':str(toolp),'readonly_probe_evidence':pin(ep),'terminal_probe_evidence':pin(tep),'cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES,'admission':{'cpp_build_policy':pack.CPP_POLICY,'cpp_build_overrides':pack.CPP_OVERRIDES,'make_closure_pins':{str(hp):sha(hp)}}}
 return dict(binding=b,built=built,host=host,overlay=ov,out=out,observation_pin=pin(op),repo=repo)

@unittest.skipUnless(os.environ.get('FF_E2E_PAYLOAD')and os.environ.get('FF_E2E_SOURCE_ROOT'),'explicit actual metadata/SV fixture paths required')
class TerminalSevenFiles(unittest.TestCase):
 def test_actual_pack_export_seven_with_synthetic_compiler_authority(self):
  with tempfile.TemporaryDirectory(prefix='terminal_e2e_',dir=os.environ.get('FF_E2E_WORKSPACE',os.getcwd()))as temp:
   f=construct_terminal(P(temp).resolve(),P(os.environ['FF_E2E_PAYLOAD']).resolve(),P(os.environ['FF_E2E_SOURCE_ROOT']).resolve())
   root,result=pack_and_verify(f);self.assertFalse(result['numerical_pass'])
   spec=importlib.util.spec_from_file_location('_actual_terminal_fixture_proof',f['repo']/'candidates/model_candidate_build_20261101/candidate_dependency_proof.py');actualproof=importlib.util.module_from_spec(spec);spec.loader.exec_module(actualproof)
   manifest=json.loads((root/'frozen_artifact.json').read_text());source=json.loads((root/'source_manifest.json').read_text());receipt=json.loads((root/'build_receipt.json').read_text())
   self.assertEqual(source['readonly_probe']['schema'],'FIRST_FAULT_READONLY_BUILD_EVIDENCE_V2')
   def reseal(m,s,r):
    write(root/'source_manifest.json',s);r['source_manifest_sha256']=sha(root/'source_manifest.json');write(root/'build_receipt.json',r)
    for row in m['common'].values():p=root/row['path'];row.update(bytes=p.stat().st_size,sha256=sha(p))
    write(root/'frozen_artifact.json',m)
   mutations=[('missing_third_vlt',lambda m,s,r:s['physical_closure']['initial_frontend_argv'].pop()),('missing_terminal_dependency',lambda m,s,r:s['model_candidate_build_evidence']['driver_dependency']['dependencies'].pop(s['readonly_probe']['terminal_accessor_generation']['accessor']['path'])),('v1_schema_alias',lambda m,s,r:s['readonly_probe'].update(schema='FIRST_FAULT_READONLY_BUILD_EVIDENCE_V1')),('missing_terminal_evidence',lambda m,s,r:s['readonly_probe'].pop('terminal_accessor_generation'))]
   for name,mutate in mutations:
    with self.subTest(name=name):
     m,s,r=copy.deepcopy((manifest,source,receipt));mutate(m,s,r);reseal(m,s,r)
     with self.assertRaises((ValueError,KeyError)):actualproof.verify_candidate_compilation(m,s,r,root)
   reseal(manifest,source,receipt)
   self.assertEqual(actualproof.verify_candidate_compilation(manifest,source,receipt,root)['readonly_probe']['terminal_accessor']['word_count'],4096)


class FixtureSpacePolicyTests(unittest.TestCase):
 def test_default_original_disk_floor(self):
  from unittest.mock import patch
  from types import SimpleNamespace
  for free,ok in (((8<<30)+(256<<20),True),((8<<30)+(256<<20)-1,False)):
   with patch.object(shutil,'disk_usage',return_value=SimpleNamespace(free=free)):
    if ok:fixture_space_gate(P('/synthetic'))
    else:
     with self.assertRaises(ValueError):fixture_space_gate(P('/synthetic'))
 def test_explicit_policy_requires_both_arguments(self):
  for kw in ({'space_policy':object()},{'workspace_disk_root':P('/synthetic')}):
   with self.assertRaises(ValueError):fixture_space_gate(P('/synthetic'),**kw)
 def test_explicit_policy_calls_fresh_gate_with_exact_paths(self):
  calls=[]
  class Policy:
   def construction(self,workspace,owned):calls.append((workspace,owned))
  fixture_space_gate(P('/owned'),space_policy=Policy(),workspace_disk_root=P('/workspace-root'))
  self.assertEqual(calls,[(P('/workspace-root'),P('/owned'))])
 def test_explicit_policy_failure_not_swallowed(self):
  class Policy:
   def construction(self,workspace,owned):raise ValueError('insufficient actual tmpfs')
  with self.assertRaisesRegex(ValueError,'insufficient actual tmpfs'):
   fixture_space_gate(P('/owned'),space_policy=Policy(),workspace_disk_root=P('/workspace-root'))

if __name__=='__main__':unittest.main()
