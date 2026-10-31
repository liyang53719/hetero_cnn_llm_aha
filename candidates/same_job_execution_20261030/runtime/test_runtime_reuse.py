"""Tiny synthetic bytes/mocked native stages only. Never actual runtime import/PASS."""
import copy,hashlib,importlib.util,json,pathlib,sys,tempfile,time,types,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(D))
import runtime_reuse as r
import runtime_reuse_phase as phase
import reuse_archives as archive
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)
 def write(self,p,value):
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value)if not isinstance(value,str)else value);return r.pin(p)
 def b(self):
  started=time.monotonic()
  return dict(execution_context='CLOUD_EXECUTOR_V1',identity={'started_monotonic':started},job_started_monotonic=started,job_budget_seconds=600,runtime_reuse_manifest={'sha256':'a'*64},stage_resources={'install':{'rss_bytes':2<<30,'as_bytes':2<<30}},reserved_other_owner_bytes=5<<30,pins={str(D/'runtime_reuse.py'):r.sha(D/'runtime_reuse.py')})
 def test_operator_budget_must_bind_manifest(self):
  b=self.b();budget=dict(b,runtime_mode='IMPORT_EXISTING_PINNED_RUNTIME',archive_mode='READ_EXISTING_PINNED_ARCHIVES')
  identity=types.SimpleNamespace(verify_current=lambda v:v,verify_owner=lambda v:v)
  with patch.object(r,'module',side_effect=lambda name,*a:identity if name=='reuse_executor_identity'else types.SimpleNamespace(admit=lambda _:budget)):
   self.assertIs(r.admit(b),budget)
   budget['runtime_reuse_manifest']={'sha256':'b'*64}
   with self.assertRaisesRegex(ValueError,'independently approved'):r.admit(b)
 def test_no_unapproved_admission(self):
  b=self.b();identity=types.SimpleNamespace(verify_current=lambda v:v,verify_owner=lambda v:v)
  def reject(_):raise ValueError('operator input missing')
  with patch.object(r,'module',side_effect=lambda name,*a:identity if name=='reuse_executor_identity'else types.SimpleNamespace(admit=reject)):
   with self.assertRaisesRegex(ValueError,'operator input missing'):r.admit(b)
 def test_pin_alias_drift_and_size(self):
  pin=self.write(self.root/'a','source');self.assertEqual(r.checked(pin),self.root/'a')
  (self.root/'a').write_text('drift')
  with self.assertRaises(ValueError):r.checked(pin)
  link=self.root/'alias';link.symlink_to(self.root/'a')
  with self.assertRaises(ValueError):r.checked(dict(r.pin(self.root/'a'),path=str(link)))
 def entry_fixture(self):
  home=self.root/'old-runtime';site=home/'site-packages';site.mkdir(parents=True);lib=site/'native.so';lib.write_bytes(b'tiny-synthetic-native')
  wrapper=self.write(home/'python.sh','unchanged-policy');install=self.write(home/'runtime_install.json',{'status':'HISTORICAL_INSTALL_ONLY'});side=self.write(home/'SOURCE_SIDECAR.json',{'synthetic':True});python=self.write(self.root/'python','python-bytes')
  def tree(*args):return {'site-packages/native.so':r.pin(lib)['sha256']}
  whole=self.write(self.root/'approved-tree.json',tree());entry=dict(import_root=str(home),home=str(home),site=str(site),wrapper=wrapper,installation=install,sidecar=side,whole_tree=whole)
  helper=types.SimpleNamespace(tree=tree,wrapper_policy=lambda *a:None,sidecar=lambda *a:None)
  return {'entries':{'qwen2':entry},'python':python},helper,lib
 def test_whole_tree_drift_rejected_not_old_install_status(self):
  m,h,lib=self.entry_fixture();self.assertEqual(r.verify_entry({},'qwen2',m,h),m['entries']['qwen2'])
  lib.write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'entire runtime'):r.verify_entry({},'qwen2',m,h)
 def test_actual_phase_uses_original_wrapper_and_fresh_receipt(self):
  out=self.root/'new-job';(out/'results').mkdir(parents=True);b=dict(owner_root=str(out),result_root=str(out/'results'),python=str(pathlib.Path(sys.executable).resolve()),pins={},identity={'execution_id':'synthetic'},runtime_reuse_manifest={'sha256':'a'*64})
  bp=self.write(out/'binding.json',b);e=dict(site=str(self.root/'old/site'),wrapper={'path':'/old/pinned/python.sh'},whole_tree={'sha256':'b'*64});m={'entries':{'qwen35_35b':e}}
  with patch.object(r,'admit'),patch.object(r,'manifest',return_value=(m,None)),patch.object(r,'verify_entry',return_value=e)as check,patch.object(phase.subprocess,'run')as native:
   phase.run(pathlib.Path(bp['path']),bp['sha256'],'qwen35_35b')
  self.assertEqual(check.call_count,2);argv=native.call_args.args[0];self.assertEqual(argv[:2],['/old/pinned/python.sh','-c']);self.assertNotIn('assert ',argv[2]);self.assertIn('raise ValueError',argv[2]);self.assertNotIn('forward(',argv[2]);result=json.loads((out/'results/qwen35_35b_IMPORT_VALIDATED.json').read_text());self.assertEqual(result['scope'],r.SCOPE);self.assertFalse(result['numerical_qualified']);self.assertFalse(result['reference_qualified'])
 def test_native_import_failure_has_no_validation_receipt(self):
  out=self.root/'new-job';(out/'results').mkdir(parents=True);b=dict(owner_root=str(out),result_root=str(out/'results'),python=str(pathlib.Path(sys.executable).resolve()),pins={},identity={},runtime_reuse_manifest={});bp=self.write(out/'binding.json',b);e=dict(site='/old/site',wrapper={'path':'/old/wrapper'},whole_tree={})
  with patch.object(r,'admit'),patch.object(r,'manifest',return_value=({},None)),patch.object(r,'verify_entry',return_value=e),patch.object(phase.subprocess,'run',side_effect=RuntimeError('synthetic failed import')):
   with self.assertRaises(RuntimeError):phase.run(pathlib.Path(bp['path']),bp['sha256'],'qwen35_35b')
  self.assertFalse((out/'results/qwen35_35b_IMPORT_VALIDATED.json').exists())
 def test_native_receipt_cleanup_and_eof(self):
  valid=dict(status='PASS_PROCESS_ONLY',native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True});self.assertTrue(r.complete(valid))
  for field,val in [('native_exit',1),('errors',['failure']),('cleanup_proof',{}),('log_capture',{})]:
   self.assertFalse(r.complete(dict(valid,**{field:val})))
 def test_archives_no_download_or_extraction(self):
  text=(D/'reuse_archives.py').read_text()
  for word in ('urlopen','requests.','shutil.','os.link','extractall','acquire('):self.assertNotIn(word,text)
 def test_role_caps_not_hardware_or_threads(self):
  b=self.b();b.update(install_wall_seconds=180,owned_roots=['/synthetic']);c=r.phase_caps(b)
  self.assertEqual(c['rss_bytes'],2<<30);self.assertEqual(c['per_process_as_bytes'],2<<30);self.assertEqual(c['cpu_seconds'],180)
if __name__=='__main__':unittest.main()

class ArchiveContractTests(unittest.TestCase):
 def test_exact_original_union_metadata_without_download(self):
  # Synthetic metadata/sealed file verifier mock; never hashes real305MB here.
  rows=[{'path':'/old-cache/f'+str(i),'bytes':305867713 if i==0 else 0,'sha256':format(i,'064x')}for i in range(53)]
  items=[dict(filename=pathlib.Path(x['path']).name,bytes=x['bytes'],sha256=x['sha256'])for x in rows]
  inspected=[];locked=types.SimpleNamespace(artifacts=lambda:(items,{},None),check_wheel_metadata=lambda x,p:inspected.append(x['filename']))
  b={'source_dir':'/locked-source','pins':{}};m={'archives':rows}
  with patch.object(r,'module',return_value=locked),patch.object(r,'checked',side_effect=lambda row,*args:pathlib.Path(row['path'])):
   self.assertEqual(r.original_archives(b,m),rows);self.assertEqual(len(inspected),53)
   bad=copy.deepcopy(m);bad['archives'][1]['sha256']='f'*64
   with self.assertRaisesRegex(ValueError,'official archive'):r.original_archives(b,bad)
   bad=copy.deepcopy(m);bad['archives'][1]=bad['archives'][0]
   with self.assertRaisesRegex(ValueError,'unique original'):r.original_archives(b,bad)
