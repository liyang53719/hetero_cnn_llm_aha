"""Synthetic producer plumbing ONLY. No real artifacts, weights, runtime, or DUT."""
import hashlib,importlib.util,json,pathlib,sys,tempfile,time,types,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).parent.resolve()
spec=importlib.util.spec_from_file_location('mocked_cloud_flow',D/'controller/cloud_flow.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class Tests(unittest.TestCase):
 def test_fresh_flow_orders_stages_without_any_build(self):self.exercise(False)
 def test_reuse_flow_orders_stages_without_any_build(self):self.exercise(True)
 def exercise(self,reuse):
  with tempfile.TemporaryDirectory()as t:
   base=pathlib.Path(t);repo=base/'repo';package=repo/'candidates/same_job_execution_20261030';controller=package/'controller';runtime=package/'runtime';numeric=package/'numeric';sup=repo/'supervisor';artifact=base/'artifact';job=base/'job'
   for p in(controller,runtime,numeric,sup,artifact):p.mkdir(parents=True)
   files=[controller/'cloud_flow.py',package/'prepare_cloud_execution.py',sup/'supervise_multiroot.py',sup/'strict_cleanup.py',sup/'lossless_log.py',package/'python',base/'binding.json',artifact/'frozen_artifact.json',runtime/'runtime_reuse.py']
   for p in files:p.write_text('{}')
   pins={str(p):f.sha(p)for p in files};seen=[]
   identity=dict(source_commit='a'*40,started_monotonic=time.monotonic());builder=dict(run_id=42,source_commit='a'*40,launch_commit='b'*40)
   q=dict(archives=600,weights=3600,install=180,owner_bind=120,reference=180,provider=180,parent=600,calibration_seconds={str(i):300 for i in range(5)})
   b=dict(execution_context='CLOUD_EXECUTOR_V1',schema='CLOUD_FIVE_M128_EXECUTION_BINDING_V1',job_budget_seconds=43200,job_started_monotonic=identity['started_monotonic'],identity=identity,artifact_identity=builder,profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,payload_uploads=False,final_rtl_replay=False,repo=str(repo),job_root=str(job),pins=pins,runtime_package=str(runtime),numeric_package=str(numeric),python=str(package/'python'),supervisor_dir=str(sup),shared_runtime_helper='synthetic',materializer='synthetic',budgets=q,dut_rss_bytes=8<<30,dut_address_space_bytes=12<<30,stage_resources={'install':{'rss_bytes':2<<30,'as_bytes':2<<30},'reference':{'rss_bytes':2<<30,'as_bytes':2<<30}},consumer_address_space_bytes=512<<20,reserved_other_owner_bytes=5<<30,numeric_reserved_increment_bytes=512<<20,execution_mode='BOUNDED_CALIBRATION')
   for k in('artifact_manifest','builder_handoff','executor_identity_pin','cloud_budget','source_pins','execution_approval'):b[k]=f.pin(artifact/'frozen_artifact.json')
   b.update(runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME'if reuse else'FRESH_ORIGINAL_RUNTIME_INSTALL',archive_mode='READ_EXISTING_PINNED_ARCHIVES'if reuse else'DOWNLOAD_ORIGINAL_ARCHIVES',runtime_reuse_manifest=f.pin(artifact/'frozen_artifact.json')if reuse else None)
   imported=base/'readonly-runtime';imported.mkdir();cache=base/'readonly-cache';cache.mkdir();arc=cache/'synthetic.whl';arc.write_bytes(b'')
   inventory={'entries':{key:{'import_root':str(imported)}for key in ('qwen2','qwen35_08b','qwen35_35b')},'archives':[f.pin(arc)]}
   owner_module=str(runtime/('runtime_reuse.py'if reuse else'owner_fresh.py'))
   qualified=dict(status='INCOMPLETE',numerical_pass=False)
   def execute(argv,runroot,*args,**kw):
    root=pathlib.Path(runroot);root.mkdir(parents=True);seen.append(root.name)
    self.assertIn('min_available_memory',kw['resource_gate']);self.assertEqual(kw['resource_gate']['min_disk_free'],8<<30);self.assertEqual(kw['resource_gate']['min_available_memory'],(256<<20 if root.name=='archives'else 512<<20)+(1<<30)+(5<<30))
    out=root/'output';out.mkdir()
    if root.name=='archives':
     self.assertEqual(pathlib.Path(argv[2]).name,'reuse_archives.py'if reuse else'acquire_archives.py')
     if reuse:self.assertNotIn('HTTPS_PROXY',args[2]);self.assertNotIn('HTTP_PROXY',args[2])
     (out/'ARCHIVES.json').write_text(json.dumps({'archives':inventory['archives']if reuse else[]}))
    elif root.name=='weights':
     (out/'SUMMARY.json').write_text(json.dumps(dict(tensors=70,tensor_bytes=3531306272)));folder=out/'synthetic';folder.mkdir()
     for i in range(70):
      p=folder/(str(i)+'.bin');p.write_bytes(b'');(folder/(str(i)+'.receipt.json')).write_text(json.dumps(dict(actual_bytes=0,actual_sha256=f.sha(p))))
    r=dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture=dict(pipe_eof_observed=True,gzip_finalized=True));(root/'RESULT.json').write_text(json.dumps(r));return r
   def install(binding,*args,**kw):
    seen.append('reuse'if reuse else'install');self.assertEqual(kw,{});self.assertEqual(binding['early_build_seconds'],0);self.assertEqual(binding['identity'],identity);self.assertEqual(binding['job_budget_seconds'],43200);self.assertEqual(binding['reserved_other_owner_bytes'],5<<30)
    if reuse:
     self.assertEqual(binding['job_root'],str(job));self.assertEqual(binding['runtime_reuse_manifest'],b['runtime_reuse_manifest'])
     for key,path in [('archive_binding',job/'bindings/ARCHIVES.json'),('archive_validation_receipt',job/'runs/archives/RESULT.json'),('archive_output_manifest',job/'runs/archives/output/ARCHIVES.json')]:self.assertEqual(binding[key],f.pin(path))
     ab=json.loads(pathlib.Path(binding['archive_binding']['path']).read_text());self.assertEqual(ab['identity'],identity);self.assertEqual(ab['job_root'],str(job));self.assertEqual(ab['runtime_reuse_manifest'],b['runtime_reuse_manifest'])
     self.assertIn(str(imported),binding['owned_roots']);self.assertIn(str(cache),binding['owned_roots'])
    else:self.assertNotIn('archive_validation_receipt',binding)
    root=pathlib.Path(binding['owner_root']);root.mkdir();p=root/'owner.json';p.write_text('{}');return None,None,p
   def reference(binding,stage):seen.append('reference');self.assertEqual(binding['identity'],identity);self.assertEqual(binding['owner_module'],owner_module);return {str(i):{}for i in range(5)}
   def tail(binding,*args):
    seen.append('tail');self.assertEqual(binding['owner_module'],owner_module);self.assertEqual(binding['identity'],identity);self.assertEqual(binding['run_id'],42);self.assertNotIn('build_result',binding);self.assertEqual(binding['job_budget_seconds'],43200)
    out=pathlib.Path(binding['output']);out.mkdir();(out/'RESULT.json').write_text(json.dumps(dict(actual_dut_reports=[],qualification=qualified,status='INCOMPLETE',numerical_pass=False)))
   modules={'cloud_imported_runtime':types.SimpleNamespace(manifest=lambda _: (inventory,None)),'actual_runtime_revalidator':types.SimpleNamespace(run=install),'actual_fresh_installer':types.SimpleNamespace(run=install),'actual_original_references':types.SimpleNamespace(run=reference),'actual_five_diagnostics':types.SimpleNamespace(run=tail),'actual_full128_acceptance':types.SimpleNamespace(aggregate=lambda _:qualified)}
   realpin=f.pin
   def synthetic_pin(p):
    r=realpin(p)
    if pathlib.Path(p).suffix=='.bin':r['bytes']=3531306272 if pathlib.Path(p).stem=='0' else 0
    return r
   with patch.object(f,'D',controller),patch.object(f,'admitted_inputs',return_value=({},{})),patch.object(f,'execution_admission',return_value=dict(mode='BOUNDED_CALIBRATION',profile_seconds=q['calibration_seconds'])),patch.object(f.profile_policy,'require_source_pin'),patch.object(f.profile_policy,'require_cpu'),patch.object(f.subprocess,'check_output',return_value='a'*40),patch.object(f,'mod',side_effect=lambda name,path:modules[name]),patch.object(f,'pin',side_effect=synthetic_pin),patch.dict(sys.modules,{'supervise_multiroot':types.SimpleNamespace(execute=execute)}):
    # Disk only is mocked: phase resource admission calls above remain checked.
    import shutil
    with patch.object(shutil,'disk_usage',return_value=types.SimpleNamespace(free=100<<30)):code=f.run(b,base/'binding.json',f.sha(base/'binding.json'))
   self.assertEqual(code,2);self.assertEqual(seen,['archives','reuse'if reuse else'install','weights','reference','tail']);result=json.loads((job/'FLOW_RESULT.json').read_text());self.assertEqual(result['identity'],identity);self.assertEqual(result['artifact_identity'],builder);self.assertFalse(result['qualification']['numerical_pass'])
if __name__=='__main__':unittest.main()
