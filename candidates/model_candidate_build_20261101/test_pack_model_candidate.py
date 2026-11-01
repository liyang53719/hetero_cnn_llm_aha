"""Synthetic packaging only; no compiler/ELF execution or actual hardware proof."""
import copy,hashlib,importlib.util,json,pathlib,tempfile,unittest,sys,types
from unittest import mock
D=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('candidate_pack_tested',D/'pack_model_candidate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PackTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.w=pathlib.Path(self.tmp.name).resolve();self.out=self.w/'run';self.out.mkdir()
  def write(name,data):
   p=self.w/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data if isinstance(data,bytes)else json.dumps(data).encode());return p
  self.record=mock.Mock(return_value={'synthetic':True});self.modpatch=mock.patch.dict(sys.modules,{'model_source_evidence':types.SimpleNamespace(record=self.record)});self.modpatch.start();self.addCleanup(self.modpatch.stop)
  self.write=write;driver=write('driver.cpp',b'synthetic test driver\n');self.patch=mock.patch.object(m,'DRIVER_SHA',m.sha(driver));self.patch.start();self.addCleanup(self.patch.stop)
  self.host=write('host.sv',b'module synthetic; endmodule\n');self.overlay=write('overlay.json',{'files':[]});tool=write('tool.json',{'synthetic':True});inputfile=write('input.txt',b'pinned source\n');header=write('obj/VHostBlockTopV4.h',b'// synthetic pinned header\n')
  source=write('source.json',{'source_commit':'1'*40,'sv_sha256':m.sha(self.host),'driver_sha256':m.sha(driver),'cpp_build_policy':m.CPP_POLICY,'cpp_build_overrides':m.CPP_OVERRIDES})
  self.original={'artifact_identity':dict(run_id=1,artifact_name='synthetic',source_commit='1'*40,launch_commit='2'*40,launch_manifest_path='ci_launch/synthetic.json',launch_manifest_blob_sha='3'*40),'repo_sha':'1'*40,'driver':str(driver)}
  phases=[];plans=[];stagepins={}
  for name in m.STAGES:
   dest=self.out/name;dest.mkdir();argv=['synthetic-not-executed',name];r={'native_exit':0,'errors':[],'argv':argv,'cleanup_proof':{'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},'log_capture':{'pipe_eof_observed':True,'gzip_finalized':True}}
   p=dest/'RESULT.json';p.write_text(json.dumps(r,indent=2)+'\n');stagepins[name]=m.sha(p)
   if name in m.STAGES[-5:]:
    product=dest/'product';product.write_bytes(b'\x7fELF\x02\x01synthetic_not_executable'if name=='host_link'else b'archive')
    phases.append(dict(phase=name,argv=argv,supervisor=r,output=m.pin(product)));plans.append(dict(name=name,argv=argv))
  phases[-1]['driver_dependency']={'dependencies':{str(header):m.pin(header)},'synthetic':True}
  self.b={'pins':{str(inputfile):m.sha(inputfile)},'admission':{'make_closure_pins':{str(header):m.sha(header)},'cpp_build_policy':m.CPP_POLICY,'cpp_build_overrides':m.CPP_OVERRIDES},'cpp_build_policy':m.CPP_POLICY,'cpp_build_overrides':m.CPP_OVERRIDES,'source_manifest':str(source),'tool_manifest':str(tool)}
  self.built={'status':'BUILT_UNQUALIFIED','scope':'ARCHIVE_LINK_ONLY_NOT_DUT_PASS','cpp_build_policy':m.CPP_POLICY,'cpp_build_overrides':m.CPP_OVERRIDES,'plan':{'phases':plans,'cpp_build_policy':m.CPP_POLICY,'cpp_build_overrides':m.CPP_OVERRIDES},'phases':phases,'binary':phases[-1]['output']}
  pre=json.loads((D/'MODEL_CANDIDATE_PRECONDITIONS.json').read_text());z='0'*64;fakepin={'bytes':2,'sha256':z};ann=dict(fakepin,count=1,target_dir_count=1,ordered_sha256=hashlib.sha256(b'[]').hexdigest(),ordered_bytes=2)
  sv={'schema':'MODEL_CANDIDATE_SV_OBSERVATION_V1','status':'OBSERVED_UNREVIEWED','phase':'complete','scope':'ACTUAL_BYTES_ONLY_NOT_STRUCTURE_OR_NUMERICAL_ACCEPTANCE','raw_sha256':m.sha(self.host),'actual_normalized_sha256':z,'bytes':self.host.stat().st_size,'counts':{'modules':1},'modules':[dict(module='synthetic',bytes=self.host.stat().st_size,raw_sha256=m.sha(self.host),normalized_sha256=z,sourceinfo_count=0)],'scanner_sha256':m.SCANNER_SHA,'inventory_sha256':m.INVENTORY_SHA,'numerical_pass':False,'sv_accepted':False}
  providers=[dict(path='root.p'+str(i),module='Provider'+str(i),defname='qwen2_matrix_command_endpoint'if i<8 else 'tc_clk_gating'if i<16 else 'idma_backend_rw_axi_flat_wrap')for i in range(17)];instances=[dict(path='',module='HostBlockTopV4',defname='')]+providers+[dict(path='root.bank',module='UnifiedVectorElement32BankV4',defname='')]+[dict(path='root.bank.alu'+str(i),module='HeteroFP32Alu',defname='')for i in range(32)]
  mh={r['name']:r['sha256']for r in pre['unchanged_modules']};mh.update({'HostBlockTopV4':z,'HeteroFP32Alu':next(r['sha256']for r in pre['bank_subtree_reference_modules']if r['name']=='HeteroFP32Alu'),**{r['module']:z for r in providers}});mods=[dict(name=n,sha256=h)for n,h in mh.items()];bankmods=[dict(name=n,sha256=mh[n])for n in ('UnifiedVectorElement32BankV4','HeteroFP32Alu')]
  structure={'schema':'MODEL_CANDIDATE_STRUCTURE_OBSERVATION_V1','scope':'CANDIDATE_GENERATION_PRECONDITIONS_ONLY_UNREVIEWED','sv':{'bytes':sv['bytes'],'sha256':sv['raw_sha256']},'preconditions_sha256':m.PRECONDITIONS_SHA,'fixed_module_checks':pre['unchanged_modules'],'structure':{'reachable_instance_count':len(instances),'providers':providers,'shared_vector_bank_path':'root.bank','shared_vector_bank_instances':1,'bank_alu_instances':32,'all_reachable_alu_instances':32,'bank_subtree_modules':bankmods,'instances':instances},'numerical_pass':False,'post_build_structure_accepted':False}
  self.obs={'schema':'MODEL_CANDIDATE_OBSERVATION_V1','status':'OBSERVED_UNREVIEWED','source_closure':{'source_commit':'1'*40,'source_overlay':{'bytes':self.overlay.stat().st_size,'sha256':m.sha(self.overlay)},'source_count':159,'generation_contract_sha256':z,'source_pins_sha256':z},'high':{'schema':'MODEL_CANDIDATE_HIGH_DESCRIPTOR_V1','scope':'OBSERVED_UNREVIEWED_NOT_NUMERICAL_OR_STRUCTURE_ACCEPTANCE','main':'HostBlockTopV4','high':fakepin,'annotations':ann,'canonical_tsv':fakepin,'circuit_sha256':z,'modules':mods},'annotations':dict(ann,ordered_json_text='[]'),'low_ports':{'schema':'MODEL_CANDIDATE_LOW_PORTS_OBSERVATION_V1','scope':'CANDIDATE_GENERATION_PRECONDITIONS_ONLY_UNREVIEWED','port_observation_stage':'OFFICIAL_LOW_AND_TERMINAL_AST_EXACT_ORDERED_TYPES','ports':pre['typed_ports'],'low':fakepin,'abi_accepted_for_execution':False},'sv':sv,'structure':structure,'stage_receipts':[dict(name=n,bytes=(self.out/n/'RESULT.json').stat().st_size,sha256=stagepins[n])for n in m.STAGES]}
  self.obsp=write('observation.json',self.obs)
 def runpack(self):return m.pack(self.original,self.b,self.built,self.host,self.overlay,self.out,lambda _:None,{'path':str(self.obsp),'bytes':self.obsp.stat().st_size,'sha256':m.sha(self.obsp)})
 def test_pack_exact_seven_unreviewed(self):
  result=self.runpack();root=pathlib.Path(result['manifest']['path']).parent;v=m.validate_export(root);self.assertEqual(v['files'],7);self.assertFalse(v['numerical_pass']);self.assertEqual((root/'dut.bin').stat().st_mode&0o777,0o600)
  manifest=json.loads((root/'frozen_artifact.json').read_text());self.assertNotEqual(manifest['schema'],'FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2');self.assertFalse(manifest['model_numerical_evaluation_authorized']);self.assertTrue(manifest['external_review_required'])
  source=json.loads((root/'source_manifest.json').read_text());self.assertEqual(set(source['model_candidate_build_evidence']['actual_stage_receipts']),set(m.STAGES))
 def test_actual_helper_root(self):
  m.validate_observation(self.obs)
 def test_duplicate_root(self):
  q=self.obs['structure']['structure'];q['instances'].insert(1,copy.deepcopy(q['instances'][0]));q['reachable_instance_count']+=1
  with self.assertRaises(ValueError):m.validate_observation(self.obs)
 def test_nonfirst_root(self):
  q=self.obs['structure']['structure'];q['instances'][0],q['instances'][1]=q['instances'][1],q['instances'][0]
  with self.assertRaises(ValueError):m.validate_observation(self.obs)
 def test_root_wrong_type(self):
  for key,value in [('module','OtherTop'),('defname','external'),('path',None)]:
   x=copy.deepcopy(self.obs);x['structure']['structure']['instances'][0][key]=value
   with self.assertRaises(ValueError):m.validate_observation(x)
 def test_missing_stage(self):
  (self.out/m.STAGES[4]/'RESULT.json').unlink()
  with self.assertRaises((ValueError,FileNotFoundError)):self.runpack()
 def test_missing_eof(self):
  p=self.out/m.STAGES[3]/'RESULT.json';r=json.loads(p.read_text());r['log_capture'].pop('pipe_eof_observed');p.write_text(json.dumps(r))
  with self.assertRaises(ValueError):self.runpack()
 def test_native_nonzero(self):
  p=self.out/m.STAGES[-1]/'RESULT.json';r=json.loads(p.read_text());r['native_exit']=1;p.write_text(json.dumps(r))
  with self.assertRaises(ValueError):self.runpack()
 def test_wrong_argv(self):
  self.built['phases'][0]['argv']=['extra-shell']
  with self.assertRaises(ValueError):self.runpack()
 def test_source_ledger_sv_drift(self):
  p=pathlib.Path(self.b['source_manifest']);r=json.loads(p.read_text());r['sv_sha256']='f'*64;p.write_text(json.dumps(r))
  with self.assertRaises(ValueError):self.runpack()
 def test_missing_model_source_evidence(self):
  self.record.return_value={}
  with self.assertRaises(ValueError):self.runpack()
 def test_observation_is_not_acceptance(self):
  self.obs['status']='ACCEPTED';self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_wrong_sv_observation(self):
  self.obs['sv']['raw_sha256']='0'*64;self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_wrong_stage_pin(self):
  self.obs['stage_receipts'][0]['sha256']='0'*64;self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_extra_artifact_file(self):
  r=self.runpack();root=pathlib.Path(r['manifest']['path']).parent;(root/'raw.log').write_text('forbidden')
  with self.assertRaises(ValueError):m.validate_export(root)
 def test_payload_symlink(self):
  r=self.runpack();root=pathlib.Path(r['manifest']['path']).parent;p=root/'hardware.sv';p.unlink();p.symlink_to(self.host)
  with self.assertRaises(ValueError):m.validate_export(root)
 def test_self_authorized_manifest(self):
  r=self.runpack();p=pathlib.Path(r['manifest']['path']);d=json.loads(p.read_text());d['model_numerical_evaluation_authorized']=True;p.write_text(json.dumps(d))
  with self.assertRaises(ValueError):m.validate_export(p.parent)
 def test_zero_error_list_required(self):
  p=self.out/m.STAGES[0]/'RESULT.json';r=json.loads(p.read_text());r.pop('errors');p.write_text(json.dumps(r))
  with self.assertRaises(ValueError):self.runpack()
 def test_duplicate_json_key(self):
  self.obsp.write_text('{"schema":"one","schema":"two"}')
  with self.assertRaises(ValueError):self.runpack()
 def test_bad_policy(self):
  self.built['cpp_build_overrides']=['OPT_FAST=-Ofast']
  with self.assertRaises(ValueError):self.runpack()
 def test_extra_raw_high_payload_refused(self):
  self.obs['high']['raw_ir']='module secret raw';self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_typed_abi_drift_refused(self):
  self.obs['low_ports']['ports'][0]['width']=2;self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_observed_source_count_exact(self):
  self.obs['source_closure']['source_count']=155;self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_structure_high_hash_mismatch(self):
  self.obs['high']['modules'][0]['sha256']='f'*64;self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_hierarchy_count_not_self_report(self):
  self.obs['structure']['structure']['instances'][-1]['module']='Provider0';self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_no_self_structure_approval(self):
  self.obs['structure']['post_build_structure_accepted']=True;self.obsp.write_text(json.dumps(self.obs))
  with self.assertRaises(ValueError):self.runpack()
 def test_result_bool_native_not_zero(self):
  p=self.out/m.STAGES[0]/'RESULT.json';r=json.loads(p.read_text());r['native_exit']=False;p.write_text(json.dumps(r))
  with self.assertRaises(ValueError):self.runpack()
 def test_old_v2_manifest_refused(self):
  r=self.runpack();p=pathlib.Path(r['manifest']['path']);d=json.loads(p.read_text());d['schema']='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2';p.write_text(json.dumps(d))
  with self.assertRaises(ValueError):m.validate_export(p.parent)
 def test_external_identity_pin_before_compilation(self):
  r=self.runpack();p=pathlib.Path(r['manifest']['path']);wrong=dict(self.original['artifact_identity'],run_id=9)
  with self.assertRaises(ValueError):m.verify_candidate_seven(p.parent,wrong,m.sha(p))
  with self.assertRaises(ValueError):m.verify_candidate_seven(p.parent,self.original['artifact_identity'],'f'*64)
 def import_fixture(self):
  repo=self.w/'checkout';c=repo/'candidates/model_candidate_build_20261101';c.mkdir(parents=True)
  for name in ('pack_model_candidate.py','MODEL_CANDIDATE_PRECONDITIONS.json'):(c/name).write_bytes((D/name).read_bytes())
  # Import-isolation fixture ONLY, never an actual compilation proof.
  (c/'candidate_dependency_proof.py').write_text("def verify_candidate_compilation(*args):\n raise ValueError('EXPLICIT_LOCAL_PROOF_SENTINEL')\n")
  rows=[dict(path=str((c/n).relative_to(repo)),bytes=(c/n).stat().st_size,sha256=m.sha(c/n))for n in ('pack_model_candidate.py','candidate_dependency_proof.py')]
  cat=repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json';cat.parent.mkdir();cat.write_text(json.dumps({'schema':'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','files':rows}))
  self.obs['source_closure']['source_pins_sha256']=m.sha(cat);self.obsp.write_text(json.dumps(self.obs));result=self.runpack();root=pathlib.Path(result['manifest']['path']).parent
  spec=importlib.util.spec_from_file_location('synthetic_checkout_pack',c/'pack_model_candidate.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.DRIVER_SHA=m.DRIVER_SHA
  return module,cat,root
 def test_wrong_builder_catalog_refused_before_import(self):
  module,cat,root=self.import_fixture();cat.write_text(cat.read_text()+' ')
  with self.assertRaisesRegex(ValueError,'same builder source catalog'):module.verify_candidate_seven(root,self.original['artifact_identity'],m.sha(root/'frozen_artifact.json'))
 def test_same_name_sys_modules_injection_ignored(self):
  module,cat,root=self.import_fixture()
  poison=types.SimpleNamespace(verify_candidate_compilation=lambda *a:(_ for _ in()).throw(RuntimeError('INJECTED')))
  with mock.patch.dict(sys.modules,{'candidate_dependency_proof':poison}):
   with self.assertRaisesRegex(ValueError,'EXPLICIT_LOCAL_PROOF_SENTINEL'):module.verify_candidate_seven(root,self.original['artifact_identity'],m.sha(root/'frozen_artifact.json'))
 def test_local_proof_bytes_drift_refused(self):
  module,cat,root=self.import_fixture();p=pathlib.Path(module.__file__).with_name('candidate_dependency_proof.py');p.write_text(p.read_text()+'# drift\n')
  with self.assertRaisesRegex(ValueError,'source closure'):module.verify_candidate_seven(root,self.original['artifact_identity'],m.sha(root/'frozen_artifact.json'))
if __name__=='__main__':unittest.main()
