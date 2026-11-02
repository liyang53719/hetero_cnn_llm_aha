"""Real N review/probe/P0 validators, synthetic metadata authority; no DUT/materialization."""
import hashlib,importlib.util,json,os,pathlib,shutil,tempfile,types,unittest,sys
sys.dont_write_bytecode=True
P=pathlib.Path;HERE=P(__file__).resolve().parent
NDIR=P(os.environ.get('FIRST_FAULT_P0_REUSE_NUMERIC',str(HERE))).resolve()
JOINT=NDIR.parents[2];E='candidates/same_job_execution_20261030';N=E+'/numeric'
HELPER=P(os.environ.get('FIRST_FAULT_P0_REUSE_SOURCE',str(HERE/'p0_provider_data_reuse.py'))).resolve()
class FixtureIO:
 MODE='P0_FIRST_FAULT_DIAGNOSTIC'
 @staticmethod
 def pin(path):
  path=P(path).resolve();raw=path.read_bytes();return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 @staticmethod
 def read(path):return json.loads(P(path).read_text())
 @staticmethod
 def checked(row):
  if FixtureIO.pin(row['path'])!=row:raise ValueError('fixture pin drift')
  return FixtureIO.read(row['path'])
p=FixtureIO

def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name).resolve()
  self.support=module(JOINT/N/'test_support_first_fault.py','input_n_support')
  with_env={'FIRST_FAULT_TEST_REPO':str(JOINT),'FIRST_FAULT_TEST_FIXTURES':str(JOINT/N/'fixtures/p0_reuse')}
  previous={k:os.environ.get(k)for k in with_env};os.environ.update(with_env)
  try:self.n=self.support.build(self.root/'base')
  finally:
   for k,v in previous.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
  n=self.n;self.repo=n['repo'];self.control=self.root/'newcontrol';self.data=self.root/'data';self.data.mkdir()
  def save(path,obj):return self.support.put(path,obj)
  self.save=save
  for rel in ('numeric/p0_provider_data_reuse.py','numeric/reference_data_reuse.py'):
   dest=self.repo/E/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(JOINT/E/rel,dest)
  shutil.copyfile(HELPER,self.repo/N/'p0_provider_data_reuse.py')
  ps=module(JOINT/N/'test_support_p0_reuse.py','input_p0_support');self.p0=ps.build_fixture(self.root/'p0')
  rs=module(JOINT/N/'test_reference_data_reuse.py','input_reference_support')
  (self.root/'refs').mkdir();self.ref,_,self.refcontext,_,_=rs.fixture(self.root/'refs')
  # Reference fixture's profile0 hidden source must match original P0 input dimensions.
  rd=self.ref;rr=p.checked(rd['references']['0']);v=rr['tensor_records'].pop('1');oldfile=P(rd['references']['0']['path']).parent/v['file'];v.update(file='input_only/hidden_storage.bin',bytes=786432,sha256=rs.zero_hash(786432));oldfile.rename(P(rd['references']['0']['path']).parent/v['file']);rr['tensor_records']['hidden_storage']=v
  first=rr['tensor_records']['0'];first['bytes']-=786431;first['sha256']=rs.zero_hash(first['bytes'])
  for row in (v,first):
   with(P(rd['references']['0']['path']).parent/row['file']).open('r+b')as stream:stream.truncate(row['bytes'])
  rd['references']['0']=save(P(rd['references']['0']['path']),rr);rd['tensor_files']['0']=rs.core.inventory(rd['references']['0'],rr)
  d=self.p0['document'];d['reference_result']=rd['references']['0'];d['inputs']['x']['sha256']=v['sha256']
  for key,row in d['source_contract'].items():
   rel=ps.core.SOURCE_CONTRACT[key][0];new=self.repo/rel;new.parent.mkdir(parents=True,exist_ok=True);new.write_bytes(P(row['path']).read_bytes());d['source_contract'][key]=p.pin(new)
  # Metadata-only synthetic tensor lineage; no actual-data or runtime PASS is asserted.
  sm=p.checked(d['metadata']['source_manifest'])
  for row in sm['sources']:
   if row['name']=='x':row['sha256']=v['sha256']
  d['metadata']['source_manifest']=save(P(d['metadata']['source_manifest']['path']),sm)
  ss=p.checked(d['metadata']['source_spec']);ss.update(provider_manifest_sha256=d['metadata']['source_manifest']['sha256'],provenance_sha256=d['metadata']['source_manifest']['sha256']);d['metadata']['source_spec']=save(P(d['metadata']['source_spec']['path']),ss)
  pr=p.checked(d['metadata']['provider_result']);pr['source_spec_sha256']=d['metadata']['source_spec']['sha256'];pr['logical_ro']['x']['sha256']=v['sha256'];d['metadata']['provider_result']=save(P(d['metadata']['provider_result']['path']),pr)
  oldart=save(self.data/'old_artifact.json',{'synthetic_history':True});oldcat=save(self.data/'old_catalog.json',{'files':[]});oldb=save(self.data/'oldbinding.json',dict(artifact_manifest=oldart,source_pins=oldcat))
  retained=dict(old_controller_binding=oldb,weights=p.checked(self.p0['context']['retained_materials'])['weights'],references={k:{'result':v}for k,v in rd['references'].items()})
  retainedpin=save(self.data/'retained.json',retained)
  binary=save(n['out']/'dut.bin',b'SYNTHETIC_NOT_EXECUTABLE');tool=save(n['out']/'tool_manifest.json',{'synthetic':True});n['artifact']['common']['binary']=dict(binary,path='dut.bin');n['artifact']['tool_manifest']=dict(tool,path='tool_manifest.json');ap=save(n['out']/'frozen_artifact.json',n['artifact'])
  context=dict(repo=str(self.repo),artifact_manifest=ap,retained_materials=retainedpin);d['context']=dict(context);rd.update(context=dict(context),execution_mode=p.MODE)
  p0pin=save(self.data/'p0reuse.json',d);refpin=save(self.data/'reference_reuse.json',rd)
  legacy_dir=self.data/'legacy';legacy_dir.mkdir();legacy_driver=save(legacy_dir/'driver.cpp',(self.repo/n['helper'].ROLES['legacy_driver']).read_bytes());legacy_art=dict(schema='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1',profiles=list(range(5)),matrix_macs=4096,common={'sv':n['artifact']['common']['sv'],'driver':dict(legacy_driver,path='driver.cpp')});legacy_pin=save(legacy_dir/'frozen_artifact.json',legacy_art)
  prior=p.checked(d['prior_controller_binding']);prior.update(artifact_manifest=legacy_pin,retained_materials=retainedpin);d['prior_controller_binding']=save(P(d['prior_controller_binding']['path']),prior);origin=d['evidence_origins']['prior'];d['evidence_origins']['prior']=save(P(origin['path']),prior)
  doc=n['doc'];hist=p.checked(doc['basis']['historical_stage_binding']);hist['artifact_manifest']=legacy_pin;doc['basis']['historical_stage_binding']=save(P(doc['basis']['historical_stage_binding']['path']),hist)
  summary=p.checked(doc['basis']['historical_stage_summary']);summary.update(binding_sha256=doc['basis']['historical_stage_binding']['sha256'],artifact_manifest_sha256=legacy_pin['sha256']);doc['basis']['historical_stage_summary']=save(P(doc['basis']['historical_stage_summary']['path']),summary)
  doc['artifact_manifest_sha256']=ap['sha256'];doc['stimulus']['retained_materials_sha256']=retainedpin['sha256'];doc['watchdog']={'wall_seconds':10800,'max_active_cycles':1500000}
  wr=p.checked(doc['basis']['independent_watchdog_review']);wr.update(artifact_manifest_sha256=ap['sha256'],watchdog=doc['watchdog'],historical_stage_binding_sha256=doc['basis']['historical_stage_binding']['sha256'],historical_stage_summary_sha256=doc['basis']['historical_stage_summary']['sha256']);doc['basis']['independent_watchdog_review']=save(P(doc['basis']['independent_watchdog_review']['path']),wr)
  review=n['review'];review.update(artifact_manifest=ap,first_fault_diagnostic=save(n['control']/'diagnostic.json',doc))
  st=p.checked(review['structural_review']);st['artifact_manifest_sha256']=ap['sha256'];review['structural_review']=save(P(review['structural_review']['path']),st)
  rp=save(n['control']/'review.json',review)
  rows=[dict(p.pin(x),path=str(x.relative_to(self.repo)))for x in sorted(self.repo.rglob('*'))if x.is_file()];catalog=save(self.repo/E/'SOURCE_PINS.json',dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=rows))
  d['schema']='P0_DATA_REUSE_FIRST_FAULT_BINDING_V1';d['context'].update(execution_mode=p.MODE,model_candidate_review=rp,source_pins=catalog);p0pin=save(self.data/'p0reuse.json',d)
  self.args=types.SimpleNamespace(p0_provider_reuse=p0pin['path'],model_candidate_review=rp['path'])
 def reuse_check(self):
  core=module(self.repo/N/'p0_provider_data_reuse.py','checked_reuse')
  d=p.read(self.args.p0_provider_reuse);return core.verify_metadata(p.pin(self.args.p0_provider_reuse),d['context'])
 def rebind_legacy(self,field,value):
  d=p.read(self.args.p0_provider_reuse);prior=p.checked(d['prior_controller_binding']);old=p.checked(prior['artifact_manifest']);old['common'][field].update(value);prior['artifact_manifest']=self.save(P(prior['artifact_manifest']['path']),old)
  d['prior_controller_binding']=self.save(P(d['prior_controller_binding']['path']),prior);d['evidence_origins']['prior']=self.save(P(d['evidence_origins']['prior']['path']),prior)
  review=p.read(self.args.model_candidate_review);doc=p.checked(review['first_fault_diagnostic']);h=p.checked(doc['basis']['historical_stage_binding']);h['artifact_manifest']=prior['artifact_manifest'];doc['basis']['historical_stage_binding']=self.save(P(doc['basis']['historical_stage_binding']['path']),h)
  sm=p.checked(doc['basis']['historical_stage_summary']);sm.update(binding_sha256=doc['basis']['historical_stage_binding']['sha256'],artifact_manifest_sha256=prior['artifact_manifest']['sha256']);doc['basis']['historical_stage_summary']=self.save(P(doc['basis']['historical_stage_summary']['path']),sm)
  wr=p.checked(doc['basis']['independent_watchdog_review']);wr.update(historical_stage_binding_sha256=doc['basis']['historical_stage_binding']['sha256'],historical_stage_summary_sha256=doc['basis']['historical_stage_summary']['sha256']);doc['basis']['independent_watchdog_review']=self.save(P(doc['basis']['independent_watchdog_review']['path']),wr)
  review['first_fault_diagnostic']=self.save(P(review['first_fault_diagnostic']['path']),doc);rp=self.save(P(self.args.model_candidate_review),review);d['context']['model_candidate_review']=rp;self.save(P(self.args.p0_provider_reuse),d)
 def test_new_reuse_scope_exact_reads(self):
  v=self.reuse_check();self.assertEqual(v['watch_scope'],'PURE_PROVIDER_FINITE_EVIDENCE_AND_DIAGNOSTIC_AUTHORITY_V1');self.assertEqual(v['roots'][2:],v['authority_roots']);self.assertIn(str(self.data/'legacy'),v['authority_roots']);self.assertIn(str(self.repo),v['authority_roots'])
 def test_detached_review_evidence_root_is_watched(self):
  review=p.read(self.args.model_candidate_review);newroot=self.root/'detached_review_evidence';newroot.mkdir();review['structural_review']=self.save(newroot/'structure.json',p.checked(review['structural_review']));rp=self.save(P(self.args.model_candidate_review),review);d=p.read(self.args.p0_provider_reuse);d['context']['model_candidate_review']=rp;self.save(P(self.args.p0_provider_reuse),d)
  self.assertIn(str(newroot),self.reuse_check()['authority_roots'])
 def test_old_reuse_schema_cross_artifact_rejected(self):
  d=p.read(self.args.p0_provider_reuse);d['schema']='P0_DATA_REUSE_BINDING_V1';d['context']={k:d['context'][k]for k in('repo','artifact_manifest','retained_materials')};self.save(P(self.args.p0_provider_reuse),d)
  with self.assertRaisesRegex(ValueError,'same artifact'):self.reuse_check()
 def test_wrong_legacy_sv_rejected(self):
  self.rebind_legacy('sv',{'sha256':'1'*64})
  with self.assertRaisesRegex(ValueError,'original raw SV'):self.reuse_check()
 def test_wrong_legacy_driver_rejected(self):
  self.rebind_legacy('driver',{'sha256':'2'*64})
  with self.assertRaisesRegex(ValueError,'original stimulus driver'):self.reuse_check()
 def test_reuse_missing_catalog_rejected(self):
  d=p.read(self.args.p0_provider_reuse);d['context'].pop('source_pins');self.save(P(self.args.p0_provider_reuse),d)
  with self.assertRaisesRegex(ValueError,'context domain'):self.reuse_check()
 def test_reuse_wrong_review_rejected(self):
  d=p.read(self.args.p0_provider_reuse);d['context']['model_candidate_review']=self.save(self.data/'wrongreview.json',{'schema':'wrong'});self.save(P(self.args.p0_provider_reuse),d)
  with self.assertRaises((ValueError,KeyError)):self.reuse_check()

class OriginalBytes(unittest.TestCase):
 def test_exact_inverse_entire_legacy_module(self):
  s=HELPER.read_text()
  lo=s.index("FIRST_FAULT_MODE=");hi=s.index('def verify_metadata(',lo);block=s[lo:hi]
  self.assertEqual(hashlib.sha256(block.encode()).hexdigest(),'e90bce33b530f270d61f74cf18235c143faedb4cca5997cc31e8de89dc6c79b7');self.assertEqual(s.count('def first_fault_relation('),1);s=s[:lo]+s[hi:]
  old=" first_fault=d['schema']==FIRST_FAULT_SCHEMA\n need((first_fault or d['schema']=='P0_DATA_REUSE_BINDING_V1')and";self.assertEqual(s.count(old),1);s=s.replace(old," need(d['schema']=='P0_DATA_REUSE_BINDING_V1'and")
  old=" fields={'repo','artifact_manifest','retained_materials'}\n if first_fault:fields|={'execution_mode','model_candidate_review','source_pins'}\n need(set(d['context'])==fields,'context domain')";self.assertEqual(s.count(old),1);s=s.replace(old," need(set(d['context'])=={'repo','artifact_manifest','retained_materials'},'context domain')")
  old=" additional_roots=first_fault_relation(d,b,artifact,prior)if first_fault else []\n if not first_fault:need(prior['artifact_manifest']==b['artifact_manifest'],'same artifact bytes for retained P0 data')";self.assertEqual(s.count(old),1);s=s.replace(old," need(prior['artifact_manifest']==b['artifact_manifest'],'same artifact bytes for retained P0 data')")
  old=" result=dict(watch_scope='PURE_PROVIDER_AND_FINITE_EVIDENCE_V1',roots=[str(root),str(evidence),*additional_roots]";self.assertEqual(s.count(old),1);s=s.replace(old," return dict(watch_scope='PURE_PROVIDER_AND_FINITE_EVIDENCE_V1',roots=[str(root),str(evidence)]")
  old=" if first_fault:result.update(watch_scope='PURE_PROVIDER_FINITE_EVIDENCE_AND_DIAGNOSTIC_AUTHORITY_V1',authority_roots=additional_roots)\n return result\n";self.assertEqual(s.count(old),1);s=s.replace(old,'')
  self.assertEqual(hashlib.sha256(s.encode()).hexdigest(),'d57affb008ac58ed8024b2b38a40609b687be9061d01bf99c17fe450089409a5')

if __name__=='__main__':unittest.main()
