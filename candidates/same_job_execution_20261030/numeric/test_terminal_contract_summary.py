import hashlib,importlib.util,json,pathlib,tempfile,unittest,shutil,copy,os
P=pathlib.Path;D=P(__file__).resolve().parent
OLD=P(os.environ.get('TERMINAL_TEST_REPO',str(D.parents[2]))).resolve();NEW=OLD
C='candidates/model_candidate_build_20261101';E='candidates/same_job_execution_20261030'
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
class Contract(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name).resolve();self.m=load('c',D/'first_fault_driver_contract.py')
 def fixture(self,new=False):
  name='FIRST_FAULT_TERMINAL_DRIVER_CONTRACT.json'if new else'FIRST_FAULT_DRIVER_CONTRACT.json';src=(NEW if new else OLD)/C/name;doc=json.loads(src.read_text());out=self.root/C/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,out)
  roles=dict(self.m.ROLES,**self.m.TERMINAL_ROLES)if new else self.m.ROLES
  rows=[]
  for role,rel in roles.items():
   f=(NEW/rel)if(NEW/rel).exists()and new else OLD/rel
   if role=='host_observer'and not new:f=D/'fixtures/readonly_first_fault_v1.hpp'
   dest=self.root/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest);rows.append(dict(path=rel,bytes=dest.stat().st_size,sha256=sha(dest)))
  cat=self.root/'catalog.json';cat.write_text(json.dumps(dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=rows)));return out,cat
 def test_old_actual_roles(self):
  p,c=self.fixture();self.assertFalse(self.m.verify_source_contract(pin(p),str(self.root),pin(c))['terminal'])
 def test_new_actual_roles(self):
  p,c=self.fixture(True);self.assertTrue(self.m.verify_source_contract(pin(p),str(self.root),pin(c))['terminal'])
 def test_old_new_helper_must_reject(self):
  p,c=self.fixture();dest=self.root/self.m.ROLES['host_observer'];shutil.copyfile(NEW/self.m.ROLES['host_observer'],dest)
  with self.assertRaises(ValueError):self.m.verify_source_contract(pin(p),str(self.root),pin(c))
 def test_foreign_probe_and_role_drift(self):
  import sys
  p,c=self.fixture(True);sentinel=object();sys.modules['first_fault_probe']=sentinel
  try:
   checked=self.m.verify_source_contract(pin(p),str(self.root),pin(c));self.assertIs(sys.modules['first_fault_probe'],sentinel);self.assertIs(checked['terminal_generator'].scalar,checked['generator'])
  finally:sys.modules.pop('first_fault_probe')
  (self.root/self.m.TERMINAL_ROLES['terminal_record_schema']).write_text('{}')
  with self.assertRaises(ValueError):self.m.verify_source_contract(pin(p),str(self.root),pin(c))
 def test_actual_regenerator_terminal_evidence(self):
  p,c=self.fixture(True);checked=self.m.verify_source_contract(pin(p),str(self.root),pin(c));g=checked['terminal_generator'];contract=checked['contract']
  maps=[]
  for i in range(4096):
   member=g.MEMBER_PREFIX+str(i//256)+'_'+str(i%256);maps.append(dict(index=i,row=i//256,column=i%256,sv_var=g.PREFIX+str(i//256)+'_'+str(i%256),member=member,width_bits=32,declaration='IData/*31:0*/ '+member+';'))
  def textpin(name,raw):return dict(path='/synthetic/'+name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),text=raw.decode())
  header=dict(path='/synthetic/VHostBlockTopV4___024root.h',bytes=1,sha256='0'*64)
  t=dict(schema='ACTUAL_TERMINAL_FINITE_ACCESSOR_EVIDENCE_V1',scope='READ_ONLY_TERMINAL_CLASSIFICATION_NOT_NUMERICAL_ACCEPTANCE',schema_input=dict(path='/synthetic/schema',**{k:contract['terminal_probe_schema'][k]for k in ('bytes','sha256')}),config=textpin('config',g.config_bytes()),root_header=header,accessor=textpin('accessor',g.accessor_bytes(maps)),mappings=maps,word_count=4096,reads_hier_child_internals=False,extra_eval_or_clock=False,output_raw_words=False)
  self.m.verify_terminal_evidence(t,dict(root_header=header),checked)
  for mutation in ('header','index','declaration','raw','accessor'):
   bad=copy.deepcopy(t)
   if mutation=='header':bad['root_header']['path']='/different'
   elif mutation=='index':bad['mappings'][1]['index']=2
   elif mutation=='declaration':bad['mappings'][0]['declaration']='IData/*30:0*/ '+maps[0]['member']+';'
   elif mutation=='raw':bad['output_raw_words']=True
   else:bad['accessor']['text']+=' '
   with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.m.verify_terminal_evidence(bad,dict(root_header=header),checked)
class Loader(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name).resolve();self.base=self.root/C;self.base.mkdir(parents=True);self.rows=[]
  self.names=('first_fault_probe','terminal_finite_probe','first_fault_policy','pack_model_candidate','first_fault_compilation','candidate_dependency_proof')
  for name in self.names:
   src=NEW/C/(name+'.py');dest=self.base/src.name;shutil.copyfile(src,dest);self.rows.append(dict(path=str(dest.relative_to(self.root)),bytes=dest.stat().st_size,sha256=sha(dest)))
  self.cat=self.root/'catalog.json';self.cat.write_text(json.dumps(dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=self.rows)));self.m=load('handoff_test',D/'candidate_artifact_handoff.py')
 def test_real_v2_module_loading_and_restore(self):
  import sys
  before={n:sys.modules.get(n)for n in self.names};modules=self.m.load_candidate_checker(pin(self.cat),str(self.root),first_fault=True,terminal=True)
  self.assertEqual(tuple(modules),self.names);self.assertIs(modules['terminal_finite_probe'].scalar,modules['first_fault_probe'])
  self.assertEqual({n:sys.modules.get(n)for n in self.names},before)
 def test_v1_no_new_dependency(self):
  (self.base/'terminal_finite_probe.py').unlink();modules=self.m.load_candidate_checker(pin(self.cat),str(self.root),first_fault=True);self.assertNotIn('terminal_finite_probe',modules)
 def test_source_pin_and_foreign_cache_rejected(self):
  import sys
  sentinel=object();sys.modules['terminal_finite_probe']=sentinel
  try:
   with self.assertRaises(ValueError):self.m.load_candidate_checker(pin(self.cat),str(self.root),first_fault=True,terminal=True)
   self.assertIs(sys.modules['terminal_finite_probe'],sentinel)
  finally:sys.modules.pop('terminal_finite_probe')
  (self.base/'terminal_finite_probe.py').write_text('# drift')
  with self.assertRaises(ValueError):self.m.load_candidate_checker(pin(self.cat),str(self.root),first_fault=True,terminal=True)
class Summary(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=P(self.tmp.name).resolve();e=self.r/E;e.mkdir(parents=True);(e/'numeric').mkdir();(self.r/C).mkdir(parents=True)
  for f in ('terminal_finite_records.py','first_fault_driver_contract.py'):shutil.copyfile(D/f,e/'numeric'/f)
  for f in ('first_fault_records.py','FIXED_NONHIER_SCHEMA.json'):shutil.copyfile(OLD/E/'numeric'/f,e/'numeric'/f)
  shutil.copyfile(NEW/C/'TERMINAL_FINITE_RECORD_SCHEMA.json',self.r/C/'TERMINAL_FINITE_RECORD_SCHEMA.json');shutil.copyfile(D.parent/'summarize_cloud_execution.py',e/'summarize_cloud_execution.py')
  self.m=load('summary',e/'summarize_cloud_execution.py');self.b=dict(repo=str(self.r),pins={str(f):sha(f)for f in self.r.rglob('*')if f.is_file()});self.log=self.r/'log.txt';self.contract=load('checker',e/'numeric/first_fault_driver_contract.py').TERMINAL_CONTRACT_SHA
  old=load('old_parser',e/'numeric/first_fault_records.py');idx=next(i for i,r in enumerate(old.schema()['signals'])if r['sv_var']=='io_resetRequired'and r['module']=='HostBlockTopV4');v=[0]*114;v[idx]=1
  self.lines=[old.HEADER+'\n','HOST_FIRST_FAULT_SLOT_V1 slot=previous_healthy valid=1 cycle=10 active_cycle=8 completions=1 values='+','.join(['0']*114)+'\n','HOST_FIRST_FAULT_SLOT_V1 slot=current_fault valid=1 cycle=11 active_cycle=9 completions=1 values='+','.join(map(str,v))+'\n']
  schema=json.loads((self.r/C/'TERMINAL_FINITE_RECORD_SCHEMA.json').read_text());d={k:0 for k in schema['record_proposed_fields']};d.update(schema_sha256='10ef123a49d3490454b9f62ceb2ec63a1ac7325eb688cb001729b68af3c1fde4',sample_valid=1,accepted_samples=1,cycle=9,active_cycle=7,pc=1,completions=1,mapping='SUPPORTED',words=4096,finite=4096,effective_words=4096,first_nonfinite_index=4096,first_nonfinite_kind='NONE',first_nonfinite_region='NONE',fault_pc=1,fault_at_target_pc=1);self.terminal='HOST_TERMINAL_FINITE_SUMMARY_V1 '+' '.join(k+'='+str(d[k])for k in schema['record_proposed_fields'])+'\n'
 def test_real_projection_and_legacy_same(self):
  self.log.write_text(''.join(self.lines)+self.terminal);old=self.m.first_fault_snapshot(self.log,self.b);self.assertNotIn('terminal_finite_summary',old);new=self.m.first_fault_snapshot(self.log,self.b,self.contract);self.assertEqual(new['status'],'PRESENT_VALID');self.assertEqual(new['terminal_finite_summary']['status'],'PRESENT_VALID');self.assertEqual({k:v for k,v in new.items()if k!='terminal_finite_summary'},old)
 def test_duplicate_and_temporal_leave_original_present(self):
  for suffix in(self.terminal*2,self.terminal.replace('cycle=9 ','cycle=12 ')):
   self.log.write_text(''.join(self.lines)+suffix);r=self.m.first_fault_snapshot(self.log,self.b,self.contract);self.assertEqual(r['status'],'PRESENT_VALID');self.assertEqual(r['terminal_finite_summary']['status'],'MALFORMED');self.assertIs(r['numerical_pass'],False)
 def test_terminal_before_original_three_is_malformed(self):
  self.log.write_text(self.terminal+''.join(self.lines));r=self.m.first_fault_snapshot(self.log,self.b,self.contract);self.assertEqual(r['status'],'PRESENT_VALID');self.assertEqual(r['terminal_finite_summary']['status'],'MALFORMED')
 def test_missing_new_record_with_old_fault_is_malformed(self):
  self.log.write_text(''.join(self.lines));r=self.m.first_fault_snapshot(self.log,self.b,self.contract);self.assertEqual(r['status'],'PRESENT_VALID');self.assertEqual(r['terminal_finite_summary']['status'],'MALFORMED')
  self.log.write_text('unrelated bounded text\n');r=self.m.first_fault_snapshot(self.log,self.b,self.contract);self.assertEqual(r['status'],'ABSENT');self.assertEqual(r['terminal_finite_summary']['status'],'ABSENT')
 def test_unknown_contract_reject(self):
  self.log.write_text(''.join(self.lines))
  with self.assertRaises(ValueError):self.m.first_fault_snapshot(self.log,self.b,'0'*64)
if __name__=='__main__':unittest.main()
