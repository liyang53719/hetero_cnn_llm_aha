import resource
resource.setrlimit(resource.RLIMIT_AS,(64<<20,64<<20));resource.setrlimit(resource.RLIMIT_CPU,(10,10))
import ast,copy,hashlib,importlib.util,json,pathlib,sys,time,types,unittest
# Explicit source-only baseline dependency; never fetch, compile, or run a DUT.
import os
D=pathlib.Path(__file__).resolve().parent;REPO=D.parents[1]
if 'FINITE_LONG_BASELINE_REPO'not in os.environ:raise SystemExit('Set FINITE_LONG_BASELINE_REPO to an exact source tree of 75b9fc21e6d8a4a13bb82307969d9a0d9a953a79; no fetch is performed.')
BASELINE=pathlib.Path(os.environ['FINITE_LONG_BASELINE_REPO']).resolve()
raw_catalog=(BASELINE/'candidates/same_job_execution_20261030/SOURCE_PINS.json').read_bytes()
if hashlib.sha256(raw_catalog).hexdigest()!='84b119b9f8f81adab76813cf8ada99b7e4485eae271816a37f602eb2551b6ff0':raise ValueError('fixed 75b9 baseline catalog drift')
for row in json.loads(raw_catalog)['files']:
 path=BASELINE/row['path']
 if not path.is_file()or path.is_symlink()or path.stat().st_size!=row['bytes']or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('fixed 75b9 baseline source drift: '+row['path'])
B=BASELINE/'candidates/same_job_execution_20261030';C=REPO/'candidates/same_job_execution_20261030'

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load(C/'execution_mode.py','candidate_mode');old=load(B/'execution_mode.py','baseline_mode');start=time.monotonic()
# Tests are pure: mock evidence-pin I/O only, never produce an approved artifact.
m.pin=lambda *args:None
artifact='a'*64

def policy(new=True):return dict(schema=m.FULL_LONG_SCHEMA,driver_sha256=m.FULL_LONG_DRIVER_SHA256 if new else m.FULL_ORIGINAL_DRIVER_SHA256,artifact_manifest_sha256=artifact,max_active_cycles=1290000000 if new else 1000000000)
def fixture(new=True,long=True):
 row=dict(wall_seconds=150*86400 if long else 31*86400,cpu_seconds=100,max_active_cycles=1290000000 if new and long else 1000000000,log_raw_bytes=1024,rss_telemetry_raw_bytes=1024,log_compressed_bytes=64<<20,rss_telemetry_compressed_bytes=64<<20)
 for phase in m.FULL_V2_HOST_PHASES:
  for kind in ('wall','cpu'):row[phase+'_'+kind+'_seconds']=30
 doc=dict(schema=m.FULL_V3_SCHEMA,queue_policy=m.FULL_V3_QUEUE_POLICY,selected_profiles=[3],profiles={str(i):dict(state='BLOCKED_NOT_RUN',reason='SYNTHETIC_ONLY',analysis={})for i in range(5)},budget_contract=m.FULL_V2_CONTRACT,completion_guaranteed=False,log_policy=m.FULL_V2_LOG_POLICY,rss_telemetry_policy=m.FULL_V2_RSS_POLICY,executor_source_commit='synthetic',executor_source_pins_sha256='x',basis={k:{}for k in ('cycle_analysis','host_rate_evidence','independent_budget_review')},driver_sha256=policy(new)['driver_sha256'],artifact_manifest_sha256=artifact)
 doc['profiles']['3']=dict(state='READY_FULL_PREFILL',watchdog=row) # synthetic function fixture, not written as admission
 if long:doc['finite_long_policy']=policy(new)
 binding=dict(execution_context='CLOUD_EXECUTOR_V1',execution_mode=m.FULL,identity={'source_commit':'synthetic'},source_pins={'sha256':'x'})
 req={'sha256':'b'*64};cloud=dict(execution_mode=m.FULL,full_block_budget=req,dut_rss_bytes=2<<30,dut_address_space_bytes=2684354560,consumer_address_space_bytes=512<<20,reserved_other_owner_bytes=5<<30)
 return doc,binding,req,cloud

def admit(parts):
 d,b,r,c=parts;return m.full_v3_document(b,d,r,c)
def original_bundle():return dict(schema='SINGLE_PROFILE_RUNTIME_BUNDLE_V3',hardware_executed=False,raw_payloads_upload_allowed=False,profiles=[dict(id=3,runtime={'sentinel':'unchanged'},views={'sentinel':'unchanged'},reference_result={'sentinel':'unchanged'})],limits=dict(max_active_cycles=1000000000,wall_seconds=20000,cpu_seconds=18000,file_bytes=64<<20,address_space_bytes=12<<30),local_runtime_abi={'sentinel':'unchanged'})
def extract(path,name,extra=None):
 tree=ast.parse(path.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name);ns={'__builtins__':__builtins__,**(extra or {})};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns);return ns[name]
class Tests(unittest.TestCase):
 def test_long_document_and_boundaries(self):
  a=admit(fixture());self.assertTrue(m.finite_long(a));self.assertEqual(m.profile_wall_ceiling(a),12960000);self.assertEqual(a['profile_max_active_cycles']['3'],1290000000)
  for key,values in [('max_active_cycles',[1290000001,True,1.0,0,-1]),('wall_seconds',[12960001,True,1.0,0,-1])]:
   for v in values:
    f=fixture();f[0]['profiles']['3']['watchdog'][key]=v
    with self.subTest(key=key,v=v),self.assertRaises(ValueError):admit(f)
 def test_original_driver_longwall_cap_remains_1b(self):
  a=admit(fixture(new=False));self.assertEqual(m.finite_cycle_cap(a),1000000000)
  f=fixture(new=False);f[0]['profiles']['3']['watchdog']['max_active_cycles']=1000000001
  with self.assertRaises(ValueError):admit(f)
 def test_old_document_limits_not_broadened(self):
  a=admit(fixture(long=False));self.assertFalse(m.finite_long(a));self.assertEqual(m.profile_wall_ceiling(a),31*86400)
  for key,v in [('max_active_cycles',1000000001),('wall_seconds',31*86400+1)]:
   f=fixture(long=False);f[0]['profiles']['3']['watchdog'][key]=v
   with self.assertRaises(ValueError):admit(f)
 def test_policy_exact_identity_and_modes(self):
  for key,v in [('max_active_cycles',1290000001),('max_active_cycles',True),('schema','other'),('driver_sha256','e'*64),('artifact_manifest_sha256','short')]:
   p=policy();p[key]=v
   with self.assertRaises(ValueError):m.validate_finite_long_policy(p,m.FULL_LONG_DRIVER_SHA256,artifact)
  p=policy();p['extra']=1
  with self.assertRaises(ValueError):m.validate_finite_long_policy(p,m.FULL_LONG_DRIVER_SHA256,artifact)
  a=admit(fixture())
  for mode in [m.CALIBRATION,m.STAGE,m.FIRST_FAULT]:
   b=copy.deepcopy(a);b['mode']=mode
   with self.assertRaises(ValueError):m.finite_long(b)
  for version in [1,2,True,3.0]:
   b=copy.deepcopy(a);b['budget_version']=version
   with self.assertRaises(ValueError):m.finite_long(b)
  with self.assertRaises(ValueError):m.verify_finite_driver(a,m.FULL_ORIGINAL_DRIVER_SHA256,artifact)
  with self.assertRaises(ValueError):m.verify_finite_driver(a,m.FULL_LONG_DRIVER_SHA256,'f'*64)
 def test_provider_to_runtime_override(self):
  a=admit(fixture());before=original_bundle();original=copy.deepcopy(before)
  fn=extract(C/'numeric/provider_from_frozen.py','finite_long_runtime_metadata')
  new=fn(before,a,3,m);self.assertEqual(before,original);self.assertEqual(new['limits']['max_active_cycles'],1290000000)
  inverse=copy.deepcopy(new);inverse['limits']['max_active_cycles']=1000000000;self.assertEqual(inverse,original)
  m.validate_runtime_cycles(new['limits'],a,m.FULL_LONG_DRIVER_SHA256,artifact)
  out=m.consumer_limits(new['limits'],a,3);self.assertEqual(out['wall_seconds'],12960000);self.assertEqual(out['max_active_cycles'],1290000000)
  self.assertEqual(out['file_bytes'],original['limits']['file_bytes']);self.assertEqual(out['address_space_bytes'],original['limits']['address_space_bytes'])
  with self.assertRaises(ValueError):m.consumer_limits(original['limits'],a,3)
  with self.assertRaises(ValueError):m.validate_runtime_cycles(new['limits'],None,m.FULL_LONG_DRIVER_SHA256,artifact)
  with self.assertRaises(ValueError):m.validate_runtime_cycles(new['limits'],a,m.FULL_ORIGINAL_DRIVER_SHA256,artifact)
  for i in [0,1,2,4,True]:
   with self.assertRaises(ValueError):fn(before,a,i,m)
  with self.assertRaises(ValueError):fn(new,a,3,m)
 def test_runtime_overcap_and_boolean(self):
  a=admit(fixture())
  for v in [1290000001,True,1.0,0,-1]:
   with self.assertRaises(ValueError):m.validate_runtime_cycles({'max_active_cycles':v},a,m.FULL_LONG_DRIVER_SHA256,artifact)
 def test_resources_still_failclosed(self):
  for key,val in [('rss_telemetry_raw_bytes',49<<30),('rss_telemetry_compressed_bytes',3<<30),('log_compressed_bytes',256<<20),('rss_telemetry_verification_wall_seconds',86400)]:
   f=fixture();f[0]['profiles']['3']['watchdog'][key]=val
   with self.assertRaises(ValueError):admit(f)
  for key,v in [('dut_rss_bytes',(2<<30)+1),('dut_address_space_bytes',2684354561),('reserved_other_owner_bytes',0)]:
   f=fixture();f[3][key]=v
   with self.assertRaises(ValueError):admit(f)
 def test_old_pure_results_exact(self):
  originals=[dict(max_active_cycles=1000000000,wall_seconds=20000,cpu_seconds=18000,file_bytes=64<<20)]
  for orig in originals:
   for mode in [m.CALIBRATION,m.FULL,m.STAGE,m.FIRST_FAULT]:
    a=dict(mode=mode,profile_seconds={'0':500},profile_max_active_cycles={'0':900})
    if mode==m.FIRST_FAULT:a['diagnostic_profiles']=[0]
    self.assertEqual(m.consumer_limits(orig,a,0),old.consumer_limits(orig,a,0))
  for args in [{'calibration_seconds':{str(i):300 for i in range(5)}},{'calibration_seconds':{str(i):20000 for i in range(5)}}]:self.assertEqual(m.admit(args),old.admit(args))
 def test_cpu_reservations(self):
  a=admit(fixture());a['profile_cpu_seconds']['3']=12960000
  self.assertEqual(m.dut_parent_cpu_seconds(a,3),12960060)
  self.assertEqual(m.consumer_phase_seconds(a,3),12960060)
  self.assertEqual(m.profile_reserved_seconds(a)['3'],12960120)
 def test_connector_and_consumer_integration_anchors(self):
  c=(C/'numeric/consumer_owned.py').read_text();k=(C/'numeric/connect_owned.py').read_text()
  self.assertEqual(c.count('args.runtime_bundle,args.profile,source_relocation,admission)'),3)
  self.assertIn('mode.validate_runtime_cycles(limits,admission,common[',c)
  self.assertIn('finite_long_runtime_metadata(result,long_admission,args.profile,consumer.finite_long_mode())',k)
  self.assertIn('staged,args.profile,source_relocation,long_admission)',k)
  self.assertIn('source_guard()',k);self.assertIn('mode.admit(binding)',c)
 def test_original_compare_and_driver_reject_new_cap(self):
  compare=(B/'numeric/run_compare.py').read_text();self.assertIn("need(0 < limits['max_active_cycles'] <= 1000000000",compare)
  legacy=[n for n in ast.walk(ast.parse(compare))if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='need'and len(n.args)>1 and isinstance(n.args[1],ast.Constant)and n.args[1].value=='driver cycle bound'];self.assertEqual(len(legacy),1)
  expression=compile(ast.Expression(legacy[0].args[0]),'<legacy compare>','eval')
  self.assertTrue(eval(expression,{'limits':{'max_active_cycles':1000000000}}));self.assertFalse(eval(expression,{'limits':{'max_active_cycles':1290000000}}))
  rel='candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi_finite_long.cpp';new=(REPO/rel).read_text();original=(BASELINE/rel.replace('_finite_long.cpp','.cpp')).read_text()
  self.assertEqual(new.replace('maxCycles<=1290000000ULL','maxCycles<=1000000000ULL'),original)
 def test_no_selected_resource_claim_written(self):
  for rel in ('candidates/same_job_execution_20261030/numeric/MODEL_P0_FINITE_LONG_SOURCE_CONTRACT.json','candidates/model_candidate_build_20261101/FINITE_WATCHDOG_TEST_INVERSE.json'):self.assertNotIn('READY_FULL_PREFILL',(REPO/rel).read_text())
 def test_real_connect_p0_branch_preserves_long_cap(self):
  # Execute actual connect() control flow + actual attach_bundle.assemble().
  # Synthetic file pins and producer/ABI gates are explicit fixtures, not evidence.
  import tempfile,os
  from unittest.mock import patch
  def need(v,msg):
   if not v:raise ValueError(msg)
  def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
  def pin(p):
   p=pathlib.Path(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
  for long_enabled in (False,True):
   with self.subTest(long_enabled=long_enabled),tempfile.TemporaryDirectory(prefix='finite_long_p0_') as td:
    root=pathlib.Path(td);out=root/'out';out.mkdir()
    def put(name,value):
     p=root/name;p.write_text(json.dumps(value));return p
    original=original_bundle();original['schema']='SINGLE_PROFILE_RUNTIME_BUNDLE_V1';original['profiles'][0]['id']=0
    original['profiles'][0]['runtime']=dict(path='synthetic-runtime',bytes=10,sha256='1'*64)
    original['profiles'][0]['views']=dict(path='synthetic-views',bytes=11,sha256='2'*64)
    source=out/'runtime_bundle.json';source.write_text(json.dumps(original));before=source.read_bytes()
    ap=put('artifact.json',{'schema':'FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2'});bp=put('bindings.json',{});ep=put('evidence.json',{});abi=put('abi.json',{})
    args=types.SimpleNamespace(profile=0,artifact_manifest=ap,artifact_manifest_sha256=sha(ap),p0_bindings=bp,p0_bindings_sha256=sha(bp),consumption_evidence=ep,consumption_evidence_sha256=sha(ep),local_runtime_abi=abi,local_runtime_abi_sha256=sha(abi),expected_run_id=1,expected_launch_commit='synthetic',expected_source_commit='synthetic',owned_environment=root/'env',owned_environment_sha256='e'*64,local_build_result=root/'build',local_build_result_sha256='b'*64)
    a=admit(fixture()) if long_enabled else None
    if a is not None:
     for key in ('profile_seconds','profile_max_active_cycles','profile_cpu_seconds'):
      if key in a:a[key]['0']=a[key].pop('3')
     a['selected_profiles']=[0]
     a['blocked_profiles']['3']=a['blocked_profiles'].pop('0')
     # Actual queue selector derives selected ready keys; adjust all profile maps.
     for key,value in a.items():
      if isinstance(value,dict) and '3'in value and len(value)==1:value['0']=value.pop('3')
    observed=[]
    def checked(row):
     p=pathlib.Path(row['path']);need(pin(p)==row,'fixture pin drift');return p
    fake=types.SimpleNamespace(need=need,sha=sha,pin=checked,finite_long_connection_admission=lambda args:a,finite_long_mode=lambda:m,verify_frozen=lambda p,h:need(sha(p)==h,'fixture frozen'),FIRST_FAULT_SCHEMA='first-fault',artifact_identity=lambda *x:None,verify_local_build=lambda *x:{'synthetic':True},approved_source_relocation=lambda *x:None,verify_runtime_abi=lambda *x:None,executor_context=lambda *x:None)
    def check_binding(*values):
     doc=json.loads(values[2].read_text());observed.append(doc)
     need(doc['limits']['max_active_cycles']==(1290000000 if long_enabled else 1000000000),'P0 staged finite cap lost')
     need(doc['profiles'][0]['original_runtime']==original['profiles'][0]['runtime'],'P0 original runtime retained')
     need(doc['profiles'][0]['runtime']['path']=='synthetic-corrected','P0 correction preserved')
    fake.load_binding=check_binding
    def correct(runtime,rsha,views,vsha,bindings,dest):
     dest.mkdir();(dest/'OBSERVATION_POLICY.json').write_text(json.dumps(dict(original_runtime=original['profiles'][0]['runtime'],views=original['profiles'][0]['views'],corrected_runtime=dict(path='synthetic-corrected',bytes=12,sha256='3'*64))))
    correction=types.ModuleType('correct_observation_policy');correction.apply=correct
    provider=types.ModuleType('provider_from_frozen');provider.finite_long_runtime_metadata=extract(C/'numeric/provider_from_frozen.py','finite_long_runtime_metadata')
    assemble=extract(B/'numeric/attach_bundle.py','assemble',dict(copy=copy,json=json,consumer=fake))
    env=dict(P=pathlib.Path,json=json,os=os,sys=sys,consumer=fake,pin=pin,source_guard=lambda:None,candidate_contract=lambda x:None,attach_bundle=types.SimpleNamespace(assemble=assemble),HERE=C/'numeric')
    env['base']=extract(C/'numeric/connect_owned.py','base',dict(copy=copy,consumer=fake))
    connect=extract(C/'numeric/connect_owned.py','connect',env)
    with patch.dict(sys.modules,{'provider_from_frozen':provider,'correct_observation_policy':correction}):result=connect(args,out)
    self.assertEqual(source.read_bytes(),before);self.assertEqual(len(observed),1)
    self.assertEqual(json.loads((out/'runtime_bundle.v3.json').read_text()),observed[0]);self.assertFalse((out/'runtime_bundle.v3.UNADMITTED.json').exists())
 def test_watchdog_actual_bytes_and_source_contract(self):
  w=load(REPO/'candidates/model_candidate_build_20261101/finite_watchdog_policy.py','watchdog_bytes')
  oldraw=(B.parent.parent/w.OLD_REL).read_bytes();newraw=(REPO/w.NEW_REL).read_bytes()
  self.assertEqual(w.inverse(oldraw,newraw),w.RELATION)
  for changed in [newraw+b'\n',newraw.replace(b'1290000000',b'1290000001'),newraw.replace(b'eval()',b'EVAL()',1),oldraw]:
   with self.assertRaises(ValueError):w.inverse(oldraw,changed)
  oldcontract=json.loads((B/'numeric/MODEL_P0_SOURCE_CONTRACT.json').read_text());newcontract=json.loads((REPO/w.SOURCE_REL).read_text())
  newcontract['sources']['driver']['sha256']=w.OLD_SHA;self.assertEqual(newcontract,oldcontract)
 def test_actual_generation_gate_with_real_small_source_closure(self):
  import tempfile,shutil
  from unittest.mock import patch
  repo0=B.parent.parent;candidate=REPO;grel='candidates/model_candidate_build_20261101/'
  w=load(candidate/(grel+'finite_watchdog_policy.py'),'watchdog_generation')
  gate=load(candidate/(grel+'candidate_generation_gate.py'),'watchdog_gate')
  first=load(repo0/(grel+'first_fault_policy.py'),'first_fault_fixture')
  with tempfile.TemporaryDirectory(prefix='finite_generation_')as td:
   repo=pathlib.Path(td);overlay=json.loads((repo0/'candidates/transposed_tile_address_fix_20261103/MODEL_SOURCE_OVERLAY.json').read_text())
   names={r['repo_path']for r in overlay['files']}|{w.OLD_REL,w.NEW_REL,w.SOURCE_REL,w.SELF_REL,'candidates/transposed_tile_address_fix_20261103/MODEL_SOURCE_OVERLAY.json','candidates/transposed_tile_address_fix_20261103/GENERATION_CONTRACT.json',grel+'MODEL_SOURCE_OVERLAY.json',grel+'MODEL_CANDIDATE_PRECONDITIONS.json',grel+'candidate_generation_gate.py','candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json','candidates/ci_frontend_materialization_r2_20261029/FIXED_SOURCE_OVERLAY_R2.json','candidates/same_job_execution_20261030/SOURCE_PINS.json','candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json'}
   total=0
   for rel in names:
    source=candidate/rel if(candidate/rel).is_file()else repo0/rel;target=repo/rel;target.parent.mkdir(parents=True,exist_ok=True);raw=source.read_bytes();total+=len(raw);target.write_bytes(raw)
   self.assertLess(total,16<<20)
   b=dict(repo=str(repo),hardware_source='transposed-tile-address-v1',finite_watchdog_driver=dict(w.RELATION),driver=str(repo/w.NEW_REL),model_source_contract=str(repo/w.SOURCE_REL),generation_contract=str(repo/'candidates/transposed_tile_address_fix_20261103/GENERATION_CONTRACT.json'),generation_contract_sha256=w.GENERATION_SHA,fixed_source_overlay=str(repo/'candidates/transposed_tile_address_fix_20261103/MODEL_SOURCE_OVERLAY.json'),unchanged_module_contract=str(repo/grel/'MODEL_CANDIDATE_PRECONDITIONS.json'),host_port_contract=str(repo/'candidates/ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json'),candidate_status='UNREVIEWED_MODEL_BUILD',numeric_execution_authorized=False,pins={str(repo/rel):hashlib.sha256((repo/rel).read_bytes()).hexdigest()for rel in names})
   with patch.dict(sys.modules,{'first_fault_policy':first,'finite_watchdog_policy':w}):
    result=gate.require_generation_binding(b);self.assertEqual(result['driver_sha256'],w.OLD_SHA)
    self.assertEqual(w.expected_driver_sha(b),w.NEW_SHA)
    if hasattr(self,'generation_callback'):self.generation_callback(repo,b,w,gate)
    for field,value in [('hardware_source','legacy'),('driver',str(repo/w.OLD_REL)),('generation_contract_sha256','f'*64),('first_fault_driver_contract',{})]:
     broken=copy.deepcopy(b);broken[field]=value
     with self.assertRaises((ValueError,KeyError)):gate.require_generation_binding(broken)
 def test_actual_retained_contract_driver_relation(self):
  # Real retained contract, actual old/new driver bytes; the independent review
  # reader is a pinned synthetic stub, explicitly not operator approval evidence.
  import tempfile
  w=load(REPO/'candidates/model_candidate_build_20261101/finite_watchdog_policy.py','watchdog_retained')
  r=load(C/'runtime/retained_materials.py','retained_candidate')
  def need(v,msg):
   if not v:raise ValueError(msg)
  with tempfile.TemporaryDirectory(prefix='finite_retained_')as td:
   root=pathlib.Path(td)
   def put(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value if isinstance(value,bytes)else json.dumps(value).encode());return dict(path=str(p),bytes=p.stat().st_size,sha256=r.sha(p))
   olddriver=(B.parent.parent/w.OLD_REL).read_bytes();newdriver=(REPO/w.NEW_REL).read_bytes()
   def artifact(home,schema,driver):
    dp=put(home/'driver.cpp',driver);return put(home/'frozen_artifact.json',dict(schema=schema,profiles=list(range(5)),matrix_macs=4096,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',common={'driver':dict(dp,path='driver.cpp')}))
   before=artifact(root/'old', 'FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2',olddriver);after=artifact(root/'new',r.CANDIDATE_SCHEMA,newdriver)
   data=dict(weights=[{'synthetic':'all70 represented by digest fixture'}],references={'synthetic':'allfive represented by digest fixture'})
   retained=put(root/'retained.json',data);catalog=put(root/'catalog.json',{'synthetic':True})
   sources=[dict(path='synthetic/reference'+str(i),bytes=1,sha256='a'*64)for i in range(51)]
   contract=dict(schema='MODEL_CANDIDATE_DATA_REFERENCE_ONLY_V1',scope=r.CANDIDATE_SCOPE,old_artifact_manifest_sha256=before['sha256'],new_artifact_manifest_sha256=after['sha256'],retained_materials_sha256=retained['sha256'],old_source_pins_sha256=catalog['sha256'],reference_sources=sources,weights_sha256=r.domain_sha(data['weights']),references_sha256=r.domain_sha(data['references']),profiles=list(range(5)),tokens=128,routing='UNMODIFIED_OFFICIAL_TORCH_TOPK',finite_watchdog_driver=dict(w.RELATION))
   review=put(root/'review.json',dict(scope=r.REVIEW_SCOPE,data_reference_contract=contract))
   helper=root/'repo/candidates/same_job_execution_20261030/numeric/candidate_admission.py'
   helpertext="import json,importlib.util\ndef verify(pin,b):\n return json.load(open(pin['path']))\ndef finite_watchdog_module(repo,catalog):\n s=importlib.util.spec_from_file_location('fixture_watchdog',"+repr(str(REPO/w.SELF_REL))+");m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m\n"
   hp=put(helper,helpertext.encode());b=dict(repo=str(root/'repo'),pins={str(helper):hp['sha256']},artifact_manifest=after,execution_context='CLOUD_EXECUTOR_V1',model_candidate_review=review,source_pins=catalog);oldbinding=dict(artifact_manifest=before,source_pins=catalog)
   self.assertEqual(r.candidate_material_contract(retained,data,oldbinding,b),contract)
   for key,value in [('weights_sha256','0'*64),('references_sha256','0'*64),('new_artifact_manifest_sha256','0'*64),('finite_watchdog_driver',{})]:
    bad=copy.deepcopy(contract);bad[key]=value;b['model_candidate_review']=put(root/'review.json',dict(scope=r.REVIEW_SCOPE,data_reference_contract=bad))
    with self.assertRaises(ValueError):r.candidate_material_contract(retained,data,oldbinding,b)
   bad=copy.deepcopy(contract);bad.pop('finite_watchdog_driver');b['model_candidate_review']=put(root/'review.json',dict(scope=r.REVIEW_SCOPE,data_reference_contract=bad))
   with self.assertRaises(ValueError):r.candidate_material_contract(retained,data,oldbinding,b)
 def test_candidate_catalog_all_changed_files(self):
  rows={r['path']:r for r in json.loads((C/'SOURCE_PINS.json').read_text())['files']}
  for rel in ['candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi_finite_long.cpp', 'candidates/same_job_execution_20261030/execution_mode.py', 'candidates/same_job_execution_20261030/numeric/consumer_owned.py', 'candidates/same_job_execution_20261030/numeric/provider_from_frozen.py', 'candidates/same_job_execution_20261030/numeric/connect_owned.py', 'candidates/same_job_execution_20261030/numeric/MODEL_P0_FINITE_LONG_SOURCE_CONTRACT.json', 'candidates/model_candidate_build_20261101/finite_watchdog_policy.py', 'candidates/model_candidate_build_20261101/materialize_model_binding.py', 'candidates/model_candidate_build_20261101/candidate_generation_gate.py', 'candidates/model_candidate_build_20261101/candidate_build_producer.py', 'candidates/model_candidate_build_20261101/candidate_conditional_admission.py', 'candidates/model_candidate_build_20261101/one_job_model_candidate.py', 'candidates/model_candidate_build_20261101/model_source_evidence.py', 'candidates/model_candidate_build_20261101/pack_model_candidate.py', 'candidates/same_job_execution_20261030/numeric/correct_model_observation_policy.py', 'candidates/same_job_execution_20261030/numeric/candidate_observation_contract.py', 'candidates/same_job_execution_20261030/numeric/candidate_admission.py', 'candidates/same_job_execution_20261030/runtime/retained_materials.py', 'candidates/same_job_execution_20261030/numeric/candidate_artifact_handoff.py', 'candidates/model_candidate_build_20261101/candidate_dependency_proof.py', 'candidates/model_candidate_build_20261101/restore_model_inputs.py', 'candidates/model_candidate_build_20261101/FINITE_WATCHDOG_TEST_INVERSE.json', 'candidates/model_candidate_build_20261101/finite_watchdog_test_inverse.py', 'candidates/model_candidate_build_20261101/test_original_ir_diagnostic.py', 'candidates/model_candidate_build_20261101/test_post_build_diagnostic.py', 'candidates/model_candidate_build_20261101/test_pack_diagnostics.py', 'candidates/model_candidate_build_20261101/test_finite_stage_diagnostic.py', 'candidates/model_candidate_build_20261101/test_finite_diagnostic_revision.py', 'candidates/same_job_execution_20261030/numeric/test_candidate_observation_contract.py', 'candidates/same_job_execution_20261030/acceptance_tests/test_lifecycle.py', 'candidates/model_candidate_build_20261101/test_address_source_selection.py', 'candidates/model_candidate_build_20261101/check_finite_long_regression.py', 'candidates/same_job_execution_20261030/numeric/CONNECTION_OWNED_SOURCE_PINS.json']:
   raw=(REPO/rel).read_bytes();self.assertEqual(rows[rel]['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(rows[rel]['bytes'],len(raw))
 def test_actual_review_and_p0_source_contract_selection(self):
  import tempfile
  from unittest.mock import patch
  w=load(REPO/'candidates/model_candidate_build_20261101/finite_watchdog_policy.py','watchdog_review')
  gate=load(C/'numeric/candidate_admission.py','finite_review')
  observer=load(C/'numeric/candidate_observation_contract.py','finite_observer')
  repo=REPO
  def pin(p):return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
  catalog=pin(C/'SOURCE_PINS.json');contractpin=pin(repo/w.SOURCE_REL)
  with tempfile.TemporaryDirectory(prefix='finite_review_')as td:
   root=pathlib.Path(td)
   def put(name,obj):
    p=root/name;p.write_text(json.dumps(obj));return pin(p)
   identity=dict(source_commit='a'*40)
   overlay=put('overlay.json',dict(schema='MODEL_SOURCE_OVERLAY_V1',source_count=159,files=[{}]*159))
   # Source-overlay domain is exact in the producer relation; use the actual file.
   overlay=pin(B.parent.parent/'candidates/transposed_tile_address_fix_20261103/MODEL_SOURCE_OVERLAY.json')
   observation=dict(schema='MODEL_CANDIDATE_OBSERVATION_V1',status='OBSERVED_UNREVIEWED',source_closure=dict(source_commit=identity['source_commit'],source_count=159,source_overlay={k:overlay[k]for k in('bytes','sha256')},generation_contract_sha256=w.GENERATION_SHA))
   dp=str(repo/w.NEW_REL)
   source=dict(source_commit=identity['source_commit'],driver_sha256=w.NEW_SHA,finite_watchdog_driver=dict(w.RELATION),model_candidate_observation=observation,model_source_evidence=dict(schema='MODEL_CANDIDATE_P0_SOURCE_EVIDENCE_V1',contract=dict(contractpin,text=(repo/w.SOURCE_REL).read_text()),files=[],anchors={},program_contract={}),generation_input_pins={str(repo/w.NEW_REL):w.NEW_SHA,str(repo/w.OLD_REL):w.OLD_SHA,str(repo/w.SOURCE_REL):w.SOURCE_SHA},model_candidate_build_evidence={'driver_dependency':{'driver':dp,'dependencies':{dp:{'sha256':w.NEW_SHA}}}})
   sp=put('source_manifest.json',source)
   artifactdoc=dict(schema=gate.SCHEMA,status='UNREVIEWED_MODEL_BUILD',cpp_build_policy='CPP_O1_STRICT_V1',cpp_build_overrides=gate.POLICY,profiles=list(range(5)),layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',matrix_macs=4096,vector_lanes=32,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',artifact_identity=identity,common={'source_manifest':dict(sp,path='source_manifest.json'),'driver':{'sha256':w.NEW_SHA}},tool_manifest={},model_candidate_observation_sha256=gate.canonical_sha(observation),numerical_pass=False,final_rtl_executed=False,model_numerical_evaluation_authorized=False,external_review_required=True)
   ap=put('frozen_artifact.json',artifactdoc)
   structural=put('structural.json',dict(schema='MODEL_CANDIDATE_STRUCTURAL_REVIEW_V1',status='VERIFIED_SOURCE_AND_ACTUAL_STRUCTURE_NOT_NUMERICAL',artifact_manifest_sha256=ap['sha256'],observation_sha256=gate.canonical_sha(observation),source_overlay_sha256=overlay['sha256'],source_contract_sha256=contractpin['sha256'],matrix_macs=4096,shared_vector_banks=1,bank_alu_instances=32,profiles=list(range(5)),typed_port_count=122,numerical_pass=False,final_rtl_executed=False))
   review=dict(schema=gate.REVIEW_SCHEMA,status='REVIEWED_FOR_MODEL_NUMERICAL_EVALUATION',scope=gate.SCOPE,builder_identity=identity,artifact_manifest=ap,source_manifest_sha256=sp['sha256'],observation_sha256=gate.canonical_sha(observation),source_overlay=overlay,source_contract=contractpin,structural_review=structural,data_reference_contract={'finite_watchdog_driver':dict(w.RELATION)},numerical_pass=False,final_rtl_executed=False)
   rp=put('review.json',review)
   result=gate.verify_review(rp,ap,identity,repo=str(repo),current_source_pins_pin=catalog)
   self.assertEqual(result['data_reference_contract']['finite_watchdog_driver'],w.RELATION)
   context=dict(candidate_scope=observer.SCOPE,model_candidate_review=rp,model_source_contract=contractpin,repo=str(repo),current_source_pins_pin=catalog,builder_identity=identity,source_manifest_sha256=sp['sha256'])
   actual=observer.corrector(context);self.assertEqual(actual.contract(),json.loads((repo/w.SOURCE_REL).read_text()))
   view=observer.source_view(source,context);self.assertEqual(view['observation_policy_bindings']['P0']['contract_sha256'],w.SOURCE_SHA)
   for key in ('finite_driver_sha256','max_active_cycles'):
    bad=copy.deepcopy(review);bad['data_reference_contract']['finite_watchdog_driver'][key]='wrong';badpin=put('badreview.json',bad)
    with self.assertRaises(ValueError):gate.verify_review(badpin,ap,identity,repo=str(repo),current_source_pins_pin=catalog)
   missing=copy.deepcopy(source);missing['model_candidate_build_evidence']['driver_dependency']['dependencies']={}
   with self.assertRaises((ValueError,KeyError)):w.artifact_policy(missing,w.NEW_SHA)
 def test_legacy_pack_regressions_on_candidate_reader(self):
  from unittest.mock import patch
  import io
  repo=B.parent.parent;g='candidates/model_candidate_build_20261101/'
  w=load(REPO/(g+'finite_watchdog_policy.py'),'finite_pack_policy')
  first=load(repo/(g+'first_fault_policy.py'),'legacy_pack_policy')
  candidate=types.ModuleType('candidate_pack_regression');candidate.__file__=str(repo/(g+'pack_model_candidate.py'))
  exec(compile((REPO/(g+'pack_model_candidate.py')).read_text(),candidate.__file__,'exec'),candidate.__dict__)
  t=load(repo/(g+'test_pack_model_candidate.py'),'old_pack_regression_suite');t.m=candidate
  with patch.dict(sys.modules,{'finite_watchdog_policy':w,'first_fault_policy':first}),patch('subprocess.Popen',side_effect=AssertionError('no child')):
   suite=unittest.defaultTestLoader.loadTestsFromTestCase(t.PackTests);result=unittest.TextTestRunner(stream=io.StringIO()).run(suite)
  self.assertTrue(result.wasSuccessful(),str(result.errors)+str(result.failures));self.assertGreaterEqual(result.testsRun,10)
 def test_real_finite_pack_and_export_branches(self):
  # Real generation, source-role collector, pack and export validator. Receipts,
  # ELF-like bytes, and structural observations are explicitly synthetic.
  from unittest.mock import patch
  repo0=B.parent.parent;g='candidates/model_candidate_build_20261101/'
  candidate=types.ModuleType('finite_pack_positive');candidate.__file__=str(repo0/(g+'pack_model_candidate.py'))
  exec(compile((REPO/(g+'pack_model_candidate.py')).read_text(),candidate.__file__,'exec'),candidate.__dict__)
  t=load(repo0/(g+'test_pack_model_candidate.py'),'finite_pack_fixture');t.m=candidate
  collector=load(REPO/(g+'model_source_evidence.py'),'finite_actual_source_collector')
  def run(repo,b,w,gate):
   case=t.PackTests('test_pack_exact_seven_unreviewed');case.setUp()
   try:
    producerproof=load(REPO/(g+'candidate_dependency_proof.py'),'fixture_producer_pin_map')
    needed=set(producerproof.FINITE_WATCHDOG_IMPLEMENTATION_PINS)|{g+'candidate_dependency_proof.py','candidates/host_runtime_non_dpi_backend/source/sparse_write_memory.hpp','candidates/p0_newboundary_input_provider_20261028/PROGRAM_MANIFEST.json'}
    for rel in sorted(needed):
     src=REPO/rel if(REPO/rel).is_file()else repo0/rel
     dest=repo/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(src.read_bytes());b['pins'][str(dest)]=candidate.sha(dest)
    case.original.update(copy.deepcopy(b));case.original['repo_sha']='1'*40
    case.b.update(copy.deepcopy(b));case.overlay=pathlib.Path(b['fixed_source_overlay'])
    sparse=repo/'candidates/host_runtime_non_dpi_backend/source/sparse_write_memory.hpp'
    dep=case.built['phases'][-1]['driver_dependency'];dep.update(driver=b['driver'],resolved_sparse_header=candidate.pin(sparse));dep['dependencies'][b['driver']]=candidate.pin(b['driver']);dep['dependencies'][str(sparse)]=candidate.pin(sparse)
    sourcepath=pathlib.Path(case.b['source_manifest']);source=json.loads(sourcepath.read_text());source.update(driver_sha256=w.NEW_SHA,generation_input_pins=b['pins'],fixed_source_overlay=b['fixed_source_overlay']);sourcepath.write_text(json.dumps(source))
    case.obs['source_closure'].update(source_overlay={k:candidate.pin(case.overlay)[k]for k in('bytes','sha256')},generation_contract_sha256=w.GENERATION_SHA,source_pins_sha256=candidate.sha(repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json'))
    case.obsp.write_text(json.dumps(case.obs))
    with patch.dict(sys.modules,{'finite_watchdog_policy':w,'candidate_generation_gate':gate,'model_source_evidence':collector}),patch('subprocess.Popen',side_effect=AssertionError('no child')):
     result=case.runpack();root=pathlib.Path(result['manifest']['path']).parent;valid=candidate.validate_export(root)
     self.assertEqual(valid['files'],7);self.assertFalse(valid['numerical_pass'])
     actual=json.loads((root/'source_manifest.json').read_text());self.assertEqual(w.artifact_policy(actual,w.NEW_SHA),w.RELATION)
     self.assertEqual(actual['model_source_evidence']['contract']['sha256'],w.SOURCE_SHA)
     self.assertEqual((root/'driver.cpp').read_bytes(),(REPO/w.NEW_REL).read_bytes())
     proof=load(REPO/(g+'candidate_dependency_proof.py'),'finite_producer_selector')
     with patch.dict(sys.modules,{'finite_watchdog_policy':w}):chosen=proof.selector_producer_policy(actual,None)
     self.assertEqual(chosen,proof.FINITE_WATCHDOG_IMPLEMENTATION_PINS)
     handoff=load(C/'numeric/candidate_artifact_handoff.py','finite_full_handoff')
     manifestpath=root/'frozen_artifact.json';frozen=json.loads(manifestpath.read_text());identity=frozen['artifact_identity'];catalog=candidate.pin(C/'SOURCE_PINS.json');manifestpin=candidate.pin(manifestpath)
     def outside(name,obj):return candidate.pin(case.write(name,obj))
     contractpin=candidate.pin(pathlib.Path(b['model_source_contract']));overlaypin=candidate.pin(case.overlay);oh=frozen['model_candidate_observation_sha256']
     structural=outside('handoff_structural.json',dict(schema='MODEL_CANDIDATE_STRUCTURAL_REVIEW_V1',status='VERIFIED_SOURCE_AND_ACTUAL_STRUCTURE_NOT_NUMERICAL',artifact_manifest_sha256=manifestpin['sha256'],observation_sha256=oh,source_overlay_sha256=overlaypin['sha256'],source_contract_sha256=contractpin['sha256'],matrix_macs=4096,shared_vector_banks=1,bank_alu_instances=32,profiles=list(range(5)),typed_port_count=122,numerical_pass=False,final_rtl_executed=False))
     review=outside('handoff_review.json',dict(schema='INDEPENDENT_MODEL_CANDIDATE_REVIEW_V1',status='REVIEWED_FOR_MODEL_NUMERICAL_EVALUATION',scope='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL',builder_identity=identity,artifact_manifest=manifestpin,source_manifest_sha256=frozen['common']['source_manifest']['sha256'],observation_sha256=oh,source_overlay=overlaypin,source_contract=contractpin,structural_review=structural,data_reference_contract={'finite_watchdog_driver':w.RELATION},numerical_pass=False,final_rtl_executed=False))
     # Use the actual schema literal rather than assume its spelling.
     admission=load(C/'numeric/candidate_admission.py','handoff_actual_review_schema');rd=json.loads(pathlib.Path(review['path']).read_text());rd['schema']=admission.REVIEW_SCHEMA;review=outside('handoff_review.json',rd)
     hp=outside('handoff.json',dict(schema='VERIFIED_SEVEN_FILE_BUILD_HANDOFF_V1',scope='BUILD_BYTES_ONLY_REVALIDATE_EXECUTOR_ABI_AND_NUMERICS',builder_identity=identity,source_pins_sha256=catalog['sha256'],artifact_manifest_sha256=manifestpin['sha256'],artifact_expanded_bytes=sum(p.stat().st_size for p in root.iterdir()),remote_receipt=dict(artifact_id=1,archive_sha256='a'*64,verified_api_receipt_sha256='b'*64,source_commit=identity['source_commit'],run_id=identity['run_id']),numerical_pass=False,final_rtl_executed=False))
     receipt=json.loads((root/'build_receipt.json').read_text())
     # Complete small checker view: unchanged preconditions already copied by
     # generation fixture, plus baseline/overlay modules copied above.
     with patch.dict(sys.modules,{name:None for name in ('finite_watchdog_policy','pack_model_candidate','candidate_dependency_proof')}):
      try:handoff.verify_compilation_policy(frozen,root,receipt,catalog,str(repo))
      except Exception as error:
       self.assertIsInstance(error,KeyError);self.assertEqual(error.args,('schema',))
      else:self.fail('synthetic absent GCC dependency proof must reject')
     # The sole bypass is explicit synthetic compilation proof. All handoff
     # member/identity/catalog/actual review/finite helper calls run unmodified.
     with patch.object(handoff,'verify_compilation_policy',return_value={'fixture_only':'NO_ACTUAL_COMPILATION'}) as compilation:
      got=handoff.verify(hp['path'],hp['sha256'],manifestpath,manifestpin['sha256'],frozen,dict(source_commit=identity['source_commit']),current_source_pins_pin=catalog,repo=str(REPO),model_candidate_review=review)
      self.assertEqual(got['scope'],'MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL');self.assertFalse(got['numerical_pass']);compilation.assert_called_once()
     # Full compilation verifier must still reject missing real recipe/tool proof.
     self.assertNotIn('compilation_phases',actual['model_candidate_build_evidence']['driver_dependency'])
   finally:case.doCleanups()
  self.generation_callback=run
  try:self.test_actual_generation_gate_with_real_small_source_closure()
  finally:del self.generation_callback
 def test_new_producer_ledger_preserves_nonfinite_modes(self):
  from unittest.mock import patch
  g='candidates/model_candidate_build_20261101/';w=load(REPO/(g+'finite_watchdog_policy.py'),'watchdog_nonfinite');p=load(REPO/(g+'candidate_dependency_proof.py'),'nonfinite_dependency')
  for generation,(directory,overlay) in p.SELECTOR_GENERATION_PAIRS.items():
   policies=[None] if directory.endswith('transposed_tile_address_fix_20261103')else[None,{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V1'},{'schema':'FIRST_FAULT_DRIVER_CONTRACT_V2'}]
   for readonly in policies:
    with self.subTest(generation=generation,readonly=readonly):
     expected=p.FINITE_WATCHDOG_IMPLEMENTATION_PINS if readonly is None else p.FINITE_POLICY_TERMINAL_IMPLEMENTATIONS if readonly['schema'].endswith('V2')else p.FINITE_POLICY_FIRST_FAULT_IMPLEMENTATIONS
     pins={'/synthetic-producer/'+rel:h for rel,h in expected.items()};pins.update({'/synthetic-producer/'+directory+'/GENERATION_CONTRACT.json':generation,'/synthetic-producer/'+directory+'/MODEL_SOURCE_OVERLAY.json':overlay})
     source=dict(driver_sha256=w.OLD_SHA,generation_input_pins=pins,fixed_source_overlay='/synthetic-producer/'+directory+'/MODEL_SOURCE_OVERLAY.json',model_candidate_observation={'source_closure':dict(generation_contract_sha256=generation,source_overlay={'sha256':overlay},source_count=159)})
     with patch.dict(sys.modules,{'finite_watchdog_policy':w}):self.assertEqual(p.selector_producer_policy(source,readonly),expected)
     for rel,h in expected.items():
      actual=REPO/rel if(REPO/rel).exists()else B.parent.parent/rel
      self.assertEqual(hashlib.sha256(actual.read_bytes()).hexdigest(),h)
     # Original capability remains original when no finite binding field exists.
     first=load(B.parent.parent/(g+'first_fault_policy.py'),'nonfinite_default_policy')
     with patch.dict(sys.modules,{'first_fault_policy':first}):self.assertEqual(w.expected_driver_sha({}),w.OLD_SHA)
     bad=copy.deepcopy(source);bad['model_candidate_observation']['source_closure']['source_count']=155
     with patch.dict(sys.modules,{'finite_watchdog_policy':w}),self.assertRaises(ValueError):p.selector_producer_policy(bad,readonly)
     bad=copy.deepcopy(source);bad['finite_watchdog_driver']=dict(w.RELATION)
     if readonly is not None:
      with patch.dict(sys.modules,{'finite_watchdog_policy':w}),self.assertRaises(ValueError):p.selector_producer_policy(bad,readonly)
 def test_pin_map_closure(self):
  p=C/'numeric/CONNECTION_OWNED_SOURCE_PINS.json';pins=json.loads(p.read_text())
  for rel in ['consumer_owned.py','connect_owned.py','provider_from_frozen.py','../execution_mode.py']:
   target=p.parent/rel;self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),pins[rel])
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests);result=unittest.TextTestRunner(verbosity=2).run(suite)
 print(json.dumps(dict(scope='PURE_SYNTHETIC_NO_DUT_NO_BUILD_EVIDENCE_IO_MOCKED',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),seconds=time.monotonic()-start,rlimit_as_bytes=64<<20,rlimit_cpu_seconds=10),indent=2));sys.exit(not result.wasSuccessful())
