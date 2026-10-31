"""Synthetic end-to-end provenance join. Never actual installed bytes or imports."""
import json,pathlib,sys,tempfile,time,types,unittest
from unittest.mock import patch
import runtime_reuse as r
D=pathlib.Path(r.__file__).resolve().parent
class Tests(unittest.TestCase):
 def test_three_fresh_validation_receipts_and_new_owner_lease(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);job=root/'job';job.mkdir();sup=root/'supervisor';sup.mkdir();pins={}
   for n in ('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):
    p=sup/n;p.write_text('# synthetic');pins[str(p)]=r.sha(p)
   for n in ('runtime_reuse.py','runtime_reuse_phase.py'):pins[str(D/n)]=r.sha(D/n)
   def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v));return r.pin(p)
   identity=dict(execution_id='synthetic-current',started_monotonic=time.monotonic());entries={}
   python=write(root/'historical-python',{});archives=[write(root/'old-cache'/str(i),{})for i in range(53)]
   for key in r.KEYS:
    old=root/('old-'+key);old.mkdir();home=old if key=='qwen2'else old/'work/runtime';home.mkdir(parents=True,exist_ok=True);site=home/'site-packages';site.mkdir()
    entries[key]=dict(runtime=key,revision='synthetic-pinned',import_root=str(old),home=str(home),site=str(site),wrapper=write(home/'python.sh',{}),installation=write(home/'runtime_install.json',{'status':'HISTORICAL_NOT_CURRENT'}),sidecar=write(home/'SOURCE_SIDECAR.json',{}),whole_tree=write(root/'old-audit'/(key+'.json'),{}))
   m=dict(python=python,entries=entries,archives=archives);mp=write(root/'reviewed-runtime-manifest.json',m)
   b=dict(execution_context='CLOUD_EXECUTOR_V1',identity=identity,execution_policy={'mode':'FULL_FIVE_ORIGINAL_HOST_POLICY'},python=sys.executable,pins=pins,runtime_reuse_manifest=mp,job_root=str(job),owner_root=str(job/'materials'),owned_roots=[str(root)],supervisor_dir=str(sup),lock=str(job/'lock'),job_started_monotonic=identity['started_monotonic'],job_budget_seconds=43200,stage_resources={'install':{'rss_bytes':2<<30,'as_bytes':2<<30}},reserved_other_owner_bytes=5<<30,install_wall_seconds=180,remaining_job_reservation_seconds=1000)
   ab=write(job/'archive_binding.json',dict(identity=identity,runtime_reuse_manifest=mp,output=str(job/'archives')));b['archive_binding']=ab
   archive_output=write(job/'archives/ARCHIVES.json',dict(scope='READ_EXISTING_PINNED_ARCHIVES_NO_INSTALL',identity=identity,runtime_reuse_manifest=mp,archives=archives));b['archive_output_manifest']=archive_output
   def complete(argv,caps=None):return dict(status='PASS_PROCESS_ONLY',native_exit=0,errors=[],argv=argv,caps=caps,cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True})
   argv=[b['python'],'-B',str(D/'reuse_archives.py'),'--binding',ab['path'],'--binding-sha256',ab['sha256']]
   b['archive_validation_receipt']=write(job/'archives-stage/RESULT.json',complete(argv));bp=write(job/'reuse-controller.json',b);calls=[]
   def execute(argv,out,lock,caps,env,pins,resource_gate):
    key=argv[-1];calls.append(key);self.assertEqual(resource_gate['min_available_memory'],8<<30);self.assertEqual(caps['rss_bytes'],2<<30);self.assertEqual(caps['per_process_as_bytes'],2<<30)
    self.assertTrue(all(str(job/'materials')in env[k]for k in ('HOME','TMPDIR','HF_HOME')))
    result=dict(schema='FRESH_RUNTIME_IMPORT_VALIDATION_V1',scope=r.SCOPE,identity=identity,runtime=key,runtime_reuse_manifest=mp,whole_tree=entries[key]['whole_tree'],smoke_import_exit=0,reference_qualified=False,numerical_qualified=False)
    write(job/'materials/results'/(key+'_IMPORT_VALIDATED.json'),result);native=complete(argv,caps);write(pathlib.Path(out)/'RESULT.json',native);return native
   original=pathlib.Path.read_text
   def text(path,*args,**kwargs):return 'avx512f'if str(path)=='/proc/cpuinfo'else original(path,*args,**kwargs)
   helper=types.SimpleNamespace()
   def require_same(a,b):
    if a['execution_policy']!=b['execution_policy']:raise ValueError('execution policy identity drift')
   policy=types.SimpleNamespace(FULL='FULL_FIVE_ORIGINAL_HOST_POLICY',checked=lambda b:b['execution_policy'],require_same=require_same)
   with patch.object(r,'module',return_value=policy),patch.object(r,'admit',return_value={}),patch.object(r,'manifest',return_value=(m,helper)),patch.dict(sys.modules,{'supervise_multiroot':types.SimpleNamespace(execute=execute)}),patch.object(pathlib.Path,'read_text',text):
    _,_,owner=r.run(b,pathlib.Path(bp['path']),bp['sha256']);doc,_=r.verify(owner,r.sha(owner),b['owner_root']);self.assertEqual(calls,['qwen35_35b','qwen2','qwen35_08b']);self.assertEqual(doc['scope'],r.SCOPE);self.assertFalse(doc['numerical_qualified'])
    output=job/'materials/consumer-output';output.mkdir()
    import shutil
    with patch.object(r,'verify_entry',side_effect=lambda b,k,*a:entries[k])as check,patch.object(shutil,'disk_usage',return_value=types.SimpleNamespace(free=20<<30)):
     with r.lease(owner,r.sha(owner),b['owner_root'],3,output)as selected:
      self.assertEqual(selected['qwen35_35b']['receipt'],entries['qwen35_35b']['installation']);self.assertIn('validation_receipt',selected['qwen35_35b'])
     self.assertEqual(check.call_count,2)
    saved_policy=doc['execution_policy'];doc['execution_policy']={'mode':'WRONG'};owner.write_text(json.dumps(doc))
    with self.assertRaisesRegex(ValueError,'execution policy'):r.verify(owner,r.sha(owner),b['owner_root'])
    doc['execution_policy']=saved_policy;doc['entries']['qwen35_35b']['argv']=['old-install-command'];owner.write_text(json.dumps(doc))
    with self.assertRaisesRegex(ValueError,'supervised import'):r.verify(owner,r.sha(owner),b['owner_root'])
if __name__=='__main__':unittest.main()
