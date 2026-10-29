"""Small mocked install trees only. No installed-site scan, imports or subprocess."""
import pathlib,sys,json,tempfile,unittest,copy,fcntl,types
from unittest.mock import patch,MagicMock
P=pathlib.Path
import argparse,hashlib
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=P,required=True)
ap.add_argument('--candidate-dir',type=P)
args,test_args=ap.parse_known_args()
REPO=args.repo.resolve();CANDIDATE=(args.candidate_dir or REPO/'candidates/same_job_materialization_20261029').resolve()
def checked(p,want):
 if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=want:raise ValueError('portable source pin mismatch: '+str(p))
checked(REPO/'candidates/ci_single_profile_runtime_20261029/derive_sidecar.py','e96130e044520444758b913ba38f7fe774ac752675daf85aaa95da77e136e274')
PINS={'shared_runtime.py': 'e853a724acefd26e7b3ef1f6883003376eaf968b808db505793e731ca0b1d302', 'prepare.py': '7e68337385898059a594c190878c7c238d1dfd2a706b62a83f591375f01bb01a', 'prepare_shared_runtime.py': '6dd9a1944ffd956ca96ea8df7924548752c3294c635be5253cbb03943dbcfa82'}
for name,want in PINS.items():checked(CANDIDATE/name,want)
sys.path.insert(0,str(CANDIDATE))
import shared_runtime as m
class T(unittest.TestCase):
 def setUp(self):
  disk=patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=9<<30));disk.start();self.addCleanup(disk.stop)
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.job=P(self.tmp.name);self.python=self.job/'python';self.python.write_bytes(b'MOCK_NOT_EXECUTABLE')
  self.entries={};self.contract={}
  sample_source=self.job/'sample.py';sample_source.write_text('# MOCK SAMPLE');sp=patch.object(m,'SAMPLE_SOURCE_SHA',m.sha(sample_source));sp.start();self.addCleanup(sp.stop)
  install_binding=self.job/'install_binding.json';install_binding.write_text(json.dumps(dict(schema='OFFLINE_RUNTIME_SAMPLING_BINDING_V1',output=str(self.job),source_pins={str(sample_source):m.sha(sample_source)})))
  lock=self.job/'WHEEL_LOCK.json';lock.write_text(json.dumps({'packages':[{'name':'MOCK','role':'runtime','sha256':'0'*64}]}));lock_patch=patch.object(m,'QWEN2_LOCK_SHA',m.sha(lock));lock_patch.start();self.addCleanup(lock_patch.stop)
  for key in m.KEYS:
   root=self.job/key;home=root if key=='qwen2' else root/'work/runtime';site=home/'site-packages';site.mkdir(parents=True);(site/'module.py').write_text('original');(site/'native.so').write_text('MOCK_NATIVE');(root/'src').mkdir(exist_ok=True)
   sc=self.job/(key+'_SIDECAR.json');sc.write_text(json.dumps(dict(framework_revision=m.CONTRACT[key][0],module_sha256={'model':m.sha(site/'module.py')},module_relative_paths={'model':'module.py'},native_file_sha256={'native.so':m.sha(site/'native.so')})))
   self.contract[key]=(m.CONTRACT[key][0],m.sha(sc))
   wrapper=home/'python.sh';pre='#!/usr/bin/env bash\nset -euo pipefail\nRUNTIME="$(cd "$(dirname "$0")" && pwd)"\n';common='unset PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE LD_PRELOAD LD_LIBRARY_PATH\n'
   if key=='qwen2':text=pre+'export PYTHONPATH="$RUNTIME/site-packages"\n'+common+'export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1\nexport ATEN_CPU_CAPABILITY=avx512 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 NUMEXPR_NUM_THREADS=4\nexec '+str(self.python)+' -S -B "$@"\n'
   else:text=pre+'ROOT='+str(root)+'\nexport PYTHONPATH="$RUNTIME/site-packages:$ROOT/src:$ROOT"\n'+common+'export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1\nexport PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 ATEN_CPU_CAPABILITY=default\nexport OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1\nCPU="$('+str(self.python)+" -S -c 'import os; print(min(os.sched_getaffinity(0)))')\"\n"+'exec taskset -c "$CPU" '+str(self.python)+' -S -B "$@"\n'
   wrapper.write_text(text);install=home/'runtime_install.json'
   doc=dict(status='INSTALLED_ISOLATED_NOT_REFERENCE_TESTED',python='3.12.mock',wheel_lock=m.pin(lock),installed_wheels=[{'name':'MOCK','sha256':'0'*64}],python_executable=m.pin(self.python)) if key=='qwen2' else dict(status='PASS_OFFLINE_LOCKED_INSTALL',artifacts={'wrapper':{'path':str(wrapper.relative_to(root)),'bytes':wrapper.stat().st_size,'sha256':m.sha(wrapper)}},checks={k:True for k in m.INSTALL_CHECKS},trust_boundary=dict(python='3.12.mock',host_interpreter=str(self.python),sha256=m.sha(self.python)))
   install.write_text(json.dumps(doc));sample=self.job/(key+'_SAMPLE.json');sample.write_text(json.dumps(dict(scope='NATIVE_INSTALL_ONLY_NOT_REFERENCE_OR_DUT',stage=key,no_historical_pass_transfer=True,installation_receipt=str(install),installation_receipt_sha256=m.sha(install))))
   native=self.job/(key+'_NATIVE.json');native.write_text(json.dumps(dict(argv=[str(self.python),'-B',str(sample_source),'--binding',str(install_binding),'--stage',key],native_exit=0,errors=[],cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'))))
   self.entries[key]=dict(install_binding=m.pin(install_binding),sample_source=m.pin(sample_source),installation_run=m.pin(native),home=str(home),import_root=str(root),site=str(site),wrapper=m.pin(wrapper),installation=m.pin(install),sample_receipt=m.pin(sample),python=m.pin(self.python),sidecar=m.pin(sc))
  self.patch=patch.object(m,'CONTRACT',self.contract);self.patch.start();self.addCleanup(self.patch.stop)
  self.binding=self.job/'binding.json';self.binding.write_text(json.dumps(dict(schema='EXISTING_THREE_INSTALLS_BINDING_V1',owner_root=str(self.job),entries=self.entries)))
  self.result=m.bind(self.binding,m.sha(self.binding),self.job/'shared');self.manifest=P(self.result['path']);self.out=self.job/'profile';self.out.mkdir()
 def lease(self,i=1):return m.lease(self.manifest,self.result['sha256'],self.job,i,self.out)
 def test_mapping_five_to_three(self):
  with patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=9<<30)):
   for i in (1,2,3,4):
    with self.lease(i) as rt:self.assertEqual(list(rt),[m.MAP[i]])
 def test_output_cannot_overlap_other_runtime_or_owner(self):
  for out in (self.job/'qwen35_35b/new_profile',self.manifest.parent/'bad',self.job):
   with self.subTest(out=out),self.assertRaises(ValueError):m.preflight_path(self.manifest,self.result['sha256'],self.job,out)
 def test_missing_sidecar(self):
  P(self.entries['qwen35_08b']['sidecar']['path']).unlink()
  with self.assertRaises(ValueError):
   with self.lease():pass
 def test_same_family_other_job_native_receipt(self):
  doc=m.read(self.manifest);e=doc['entries']['qwen35_08b'];p=P(e['installation_run']['path']);n=m.read(p);n['argv'][4]=str(self.job/'other_binding.json');p.write_text(json.dumps(n));e['installation_run']=m.pin(p);self.manifest.write_text(json.dumps(doc));self.result=m.pin(self.manifest)
  with self.assertRaisesRegex(ValueError,'exact original installation invocation'):
   with self.lease():pass
 def test_empty_native_install_checks(self):
  doc=m.read(self.manifest);e=doc['entries']['qwen35_08b'];p=P(e['installation']['path']);i=m.read(p);i['checks']={};p.write_text(json.dumps(i));e['installation']=m.pin(p);sp=P(e['sample_receipt']['path']);sample=m.read(sp);sample['installation_receipt_sha256']=m.sha(p);sp.write_text(json.dumps(sample));e['sample_receipt']=m.pin(sp);self.manifest.write_text(json.dumps(doc));self.result=m.pin(self.manifest)
  with self.assertRaisesRegex(ValueError,'install-only checks'):
   with self.lease():pass
 def test_wrong_external_pin(self):
  with self.assertRaises(ValueError):m.verify(self.manifest,'0'*64,self.job)
 def test_bool_profile(self):
  with self.assertRaises(ValueError):
   with self.lease(True):pass
 def test_wrong_family(self):
  d=m.read(self.manifest);d['entries']['qwen35_08b']=d['entries']['qwen35_35b'];self.manifest.write_text(json.dumps(d));self.result=m.pin(self.manifest)
  with self.assertRaises(ValueError):
   with self.lease():pass
 def test_extra_import_root_module(self):
  (self.job/'qwen35_08b/src/injected.py').write_text('bad')
  with self.assertRaisesRegex(ValueError,'tree drift'):
   with self.lease():pass
 def test_same_length_drift(self):
  (self.job/'qwen35_08b/work/runtime/site-packages/module.py').write_text('modified')
  with self.assertRaises(ValueError):
   with self.lease():pass
 def test_sidecar_self_rehash_not_enough(self):
  d=m.read(self.manifest);p=P(d['entries']['qwen35_08b']['sidecar']['path']);p.write_text('{}');d['entries']['qwen35_08b']['sidecar']=m.pin(p);self.manifest.write_text(json.dumps(d));self.result=m.pin(self.manifest)
  with self.assertRaisesRegex(ValueError,'original sidecar'):
   with self.lease():pass
 def test_wrapper_thread_change_even_repinned(self):
  d=m.read(self.manifest);e=d['entries']['qwen35_08b'];p=P(e['wrapper']['path']);p.write_text(p.read_text().replace('OMP_NUM_THREADS=1','OMP_NUM_THREADS=4'));e['wrapper']=m.pin(p);self.manifest.write_text(json.dumps(d));self.result=m.pin(self.manifest)
  with self.assertRaisesRegex(ValueError,'wrapper policy'):
   with self.lease():pass
 def test_external_directory_alias_rejected(self):
  (self.job/'qwen35_08b/src/escape').symlink_to('/tmp',target_is_directory=True)
  with self.assertRaises(ValueError):
   with self.lease():pass
 def test_finally_release_and_postcheck(self):
  with patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=9<<30)):
   with self.assertRaisesRegex(RuntimeError,'provider failed'):
    with self.lease():raise RuntimeError('provider failed')
  with (self.manifest.parent/'OWNER.lock').open('rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 def test_exclusive_owner_blocked_during_read_lease(self):
  with patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=9<<30)):
   with self.lease():
    with (self.manifest.parent/'OWNER.lock').open('rb') as f:
     with self.assertRaises(BlockingIOError):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 def test_original_free_gate(self):
  with patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=7<<30)):
   with self.assertRaisesRegex(ValueError,'8GiB'):
    with self.lease():pass
 def test_post_drift_raises(self):
  with patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=9<<30)):
   with self.assertRaises(ValueError):
    with self.lease():(self.job/'qwen35_08b/src/late.py').write_text('bad')
class SourceBounds(unittest.TestCase):
 def test_large_only_exact_interpreter_role(self):
  f=MagicMock();f.__str__.return_value='/original/python';f.is_file.return_value=True;f.is_symlink.return_value=False;f.stat.return_value=types.SimpleNamespace(st_size=30894944)
  pin={'path':'/original/python','bytes':30894944,'sha256':'a'*64}
  with patch.object(m,'sha',return_value='a'*64):
   m.verify_install_source(f,'a'*64,pin)
   with self.assertRaises(ValueError):m.verify_install_source(f,'b'*64,pin)
   with self.assertRaises(ValueError):m.verify_install_source(f,'a'*64,dict(pin,path='/other/python'))
class Wiring(unittest.TestCase):
 def test_shared_skips_install_and_publishes_after_postcheck(self):self.check(False)
 def test_failed_postcheck_does_not_publish_v3(self):self.check(True)
 def check(self,fail):
  import prepare,contextlib
  with tempfile.TemporaryDirectory() as td:
   job=P(td);out=job/'profile';manifest=job/'owner.json';manifest.write_text('{}');events=[]
   @contextlib.contextmanager
   def lease(*args):
    events.append('lease');yield {'qwen35_08b':{}};events.append('postcheck')
    if fail:raise ValueError('mock postcheck drift')
   fake=types.SimpleNamespace(add_arguments=lambda ap:None,preflight=lambda a:events.append('preflight'),connect=lambda a,o:events.append('connect'))
   argv=['prepare.py','--repo',td,'--output',str(out),'--profile','1','--shared-runtime-manifest',str(manifest),'--shared-runtime-sha256',m.sha(manifest),'--owning-job-root',td]
   with patch.dict(sys.modules,{'connect_bundle':fake}),patch.object(sys,'argv',argv),patch.object(prepare,'sources'),patch.object(prepare,'materialize',side_effect=lambda *a,**k:events.append('materialize')),patch.object(prepare,'run',side_effect=AssertionError('installer must not run')),patch.object(m,'preflight_path'),patch.object(m,'lease',lease):
    if fail:
     with self.assertRaisesRegex(ValueError,'postcheck'):prepare.main()
    else:prepare.main()
   self.assertEqual(events,['preflight','lease','materialize','postcheck']+([] if fail else ['connect']))
   self.assertEqual((out/'SHARED_RUNTIME_USE.json').exists(),not fail)
if __name__=='__main__':unittest.main(argv=[sys.argv[0],*test_args],verbosity=2)
