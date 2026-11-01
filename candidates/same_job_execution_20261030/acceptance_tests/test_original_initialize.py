"""Bounded real five-profile initialize smoke, NOT provider/DUT numerical PASS.
Only run after exact REPO_DEPENDENCIES diff/source closure independent approval.
Calls original provider.initialize under original strict supervisor, serially.
No acquisition, torch forward, hardware build, loader or DUT execution.
"""
import argparse,hashlib,importlib.util,json,pathlib,sys,time
P=pathlib.Path;GIB=1<<30
CAPS=dict(wall_seconds=120,cleanup_seconds=30,file_bytes=2<<30,tree_bytes=256<<20,watch_tree_bytes=12081306272,min_free_disk_bytes=8<<30,log_bytes=16<<20,raw_log_bytes=32<<20,max_entries=100000,per_process_as_bytes=2684354560,per_process_cpu_seconds=120,rss_bytes=2684354560,cpu_seconds=120)
RESOURCE=dict(min_available_memory=2684354560+(5<<30)+(1<<30),min_disk_free=8<<30)
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap):
 p=P(p);need(p.is_absolute()and p==p.resolve()and p.is_file()and all(not x.is_symlink()for x in(p,*p.parents))and 0<p.stat().st_size<=cap,'canonical bounded file');return p
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def save(p,d):
 with p.open('x')as f:json.dump(d,f,indent=2);f.write('\n')
def strict(r):
 return type(r.get('native_exit'))is int and r['native_exit']==0 and r.get('errors')==[]and(r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True

def verify_output(out,index,row,program_pins):
 need(json.loads((out/'INITIALIZED.json').read_text())==dict(profile=index,reference=row),'actual initializer completion exact input')
 ref=out/'reference';need(pin(ref/'RESULT.json')['sha256']==row['sha256'],'reference receipt preserved byte-for-byte')
 doc=json.loads((ref/'RESULT.json').read_text());total=0
 for r in doc['tensor_records'].values():
  p=regular(ref/r['file'],128<<20);need(p.is_relative_to(ref)and p.stat().st_size==r['bytes']and sha(p)==r['sha256'],'every copied reference tensor exact');total+=r['bytes']
 programs=out/'programs'
 if index==0:need(programs.is_dir()and list(programs.iterdir())==[],'original P0 no programs emitted')
 else:
  expected=program_pins['profiles'][index]['files'];dest=programs/f'profile{index}'
  need({p.name for p in dest.iterdir()}==set(expected),'original complete program file set')
  for name,r in expected.items():
   p=regular(dest/name,128<<20);need(p.stat().st_size==r['bytes']and sha(p)==r['sha256'],'original program pin exact')
 return dict(profile=index,copied_tensor_bytes=total,reference_result_sha256=row['sha256'],programs_original_pins_equal=True,initializer_completed=True,dut_executed=False,numerical_pass=False)

def run(repo,source_sha,refs_path,refs_sha,out):
 repo=P(repo);out=P(out);refs_path=regular(refs_path,65536)
 need(repo.is_absolute()and repo==repo.resolve()and repo.is_dir(),'actual source root')
 need(sha(refs_path)==refs_sha,'independent original references pin');refs=json.loads(refs_path.read_text());need(set(refs['references'])==set(map(str,range(5))),'exact all five references')
 source=regular(repo/'candidates/same_job_execution_20261030/SOURCE_PINS.json',2<<20);need(sha(source)==source_sha,'independent reviewed source closure pin');catalog=json.loads(source.read_text());need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','reviewed catalog')
 pins={}
 for row in catalog['files']:
  name=P(row['path']);need(not name.is_absolute()and '..'not in name.parts,'relative source entry');p=regular(repo/name,32<<20);need(p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'complete source closure unchanged');pins[str(p)]=row['sha256']
 python=P(sys.executable).resolve();pins[str(python)]=sha(python)
 provider=repo/'candidates/same_job_execution_20261030/numeric/provider_from_frozen.py';materializer=repo/'candidates/same_job_materialization_20261029';supervisor_dir=repo/'candidates/ci_frontend_pipeline_r2_20261029'
 for p in [provider,materializer/'prepare.py',materializer/'REPO_DEPENDENCIES.json',supervisor_dir/'supervise_multiroot.py',supervisor_dir/'strict_cleanup.py',supervisor_dir/'lossless_log.py']:need(str(p)in pins,'actual executable/helper dependency pinned')
 programs=json.loads((repo/'candidates/five_profile_byte_provider/PROGRAM_PINS.json').read_text())
 need(out.is_absolute()and out==out.resolve()and not out.exists()and all(not p.is_symlink()for p in(out,*out.parents)),'fresh isolated run output')
 # Nothing executed before all source/provenance checks. Owner5GiB reservation
 # remains independent of whether the old process happens to appear in ps.
 out.mkdir();(out/'bindings').mkdir();(out/'runs').mkdir();(out/'cache').mkdir()
 sys.path.insert(0,str(supervisor_dir));spec=importlib.util.spec_from_file_location('initialize_original_supervisor',supervisor_dir/'supervise_multiroot.py');supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
 started=time.monotonic();stages=[];summary=dict(scope='FIVE_ORIGINAL_INITIALIZE_ONLY_NOT_PROVIDER_OR_DUT',source_pins_sha256=source_sha,references_manifest_sha256=refs_sha,profiles=[],stages=stages,dut_executed=False,reference_recomputed=False,hardware_built=False,numerical_pass=False)
 try:
  for i in range(5):
   need(780-(time.monotonic()-started)>=(5-i)*(120+30),'remaining original stage/cleanup reservations plus30s parent allowance')
   row=refs['references'][str(i)];p=regular(row['path'],1<<20);need(p.is_relative_to(refs_path.parent)and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'original selected reference pin')
   root=out/'runs'/f'profile{i}';target=root/'material';binding=out/'bindings'/f'profile{i}.json';save(binding,dict(repo=str(repo),materializer=str(materializer),output=str(target),profile=i,reference=row))
   env=dict(PATH='/usr/bin:/bin',LANG='C.UTF-8',LC_ALL='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1');cache=out/'cache'/f'profile{i}';cache.mkdir()
   for k in('HOME','TMPDIR','XDG_CACHE_HOME','HF_HOME','TRANSFORMERS_CACHE','TORCH_HOME'):
    p=cache/k;p.mkdir();env[k]=str(p)
   caps=dict(CAPS,extra_watch_roots=[str(out),str(repo),str(refs_path.parent)])
   stagepins=dict(pins,**{str(binding):sha(binding)})
   r=supervisor.execute([str(python),'-B',str(provider),'--initialize-binding',str(binding),'--sha256',sha(binding)],str(root),str(out/'exclusive.lock'),caps,env,stagepins,resource_gate=RESOURCE)
   stages.append(dict(profile=i,receipt=pin(root/'RESULT.json'),strict_complete=strict(r),native_exit=r.get('native_exit'),elapsed_seconds=r.get('elapsed_seconds'),observed_peak_rss=r.get('observed_peak_rss')))
   need(strict(r),'actual initialization stage failed; no DUT or hidden retry')
   summary['profiles'].append(verify_output(target,i,row,programs))
  summary['status']='ALL_FIVE_ORIGINAL_INITIALIZE_COMPLETED_NOT_NUMERICAL'
 finally:
  summary['elapsed_seconds']=time.monotonic()-started;summary.setdefault('status','INCOMPLETE_INITIALIZE_ONLY');save(out/'INITIALIZE_FIVE_SUMMARY.json',summary)
 return summary

# Portable synthetic tests validate the smoke driver's strict output projection.
# They do not initialize real profiles, import torch, execute a loader or DUT.
import tempfile,unittest
class InitializeTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.out=P(self.t.name)/'out';self.out.mkdir();ref=self.out/'reference';ref.mkdir();(ref/'input_only').mkdir();tensor=ref/'input_only/hidden.bin';tensor.write_bytes(b'synthetic')
  self.doc={'tensor_records':{'hidden':dict(file='input_only/hidden.bin',bytes=tensor.stat().st_size,sha256=sha(tensor))}};save(ref/'RESULT.json',self.doc);self.row=pin(ref/'RESULT.json');self.i=1;save(self.out/'INITIALIZED.json',dict(profile=self.i,reference=self.row));(self.out/'programs').mkdir();dest=self.out/'programs/profile1';dest.mkdir();data=b'synthetic-program';(dest/'commands.bin').write_bytes(data);self.programs={'profiles':[{} for _ in range(5)]};self.programs['profiles'][1]={'files':{'commands.bin':{'bytes':len(data),'sha256':sha(dest/'commands.bin')}}}
 def verify(self):return verify_output(self.out,self.i,self.row,self.programs)
 def test_actual_shape_projection(self):self.assertFalse(self.verify()['numerical_pass'])
 def test_reference_byte_drift(self):
  (self.out/'reference/input_only/hidden.bin').write_bytes(b'wrong')
  with self.assertRaises(ValueError):self.verify()
 def test_program_byte_drift(self):
  (self.out/'programs/profile1/commands.bin').write_bytes(b'wrong')
  with self.assertRaises(ValueError):self.verify()
 def test_extra_program_reject(self):
  (self.out/'programs/profile1/extra').write_bytes(b'wrong')
  with self.assertRaises(ValueError):self.verify()
 def test_initialization_identity_reject(self):
  (self.out/'INITIALIZED.json').write_text('{}')
  with self.assertRaises(ValueError):self.verify()
 def test_symlink_tensor_reject(self):
  p=self.out/'reference/input_only/hidden.bin';other=self.out/'outside';p.rename(other);p.symlink_to(other)
  with self.assertRaises(ValueError):self.verify()
 def test_p0_original_empty_programs(self):
  d=self.out/'programs/profile1';(d/'commands.bin').unlink();d.rmdir();self.i=0;(self.out/'INITIALIZED.json').write_text(json.dumps(dict(profile=0,reference=self.row)));self.assertTrue(self.verify()['initializer_completed'])
 def test_supervisor_bounds(self):
  self.assertEqual(CAPS['wall_seconds'],120);self.assertEqual(CAPS['cleanup_seconds'],30);self.assertEqual(CAPS['max_entries'],100000);self.assertEqual(CAPS['file_bytes'],2<<30);self.assertEqual(RESOURCE['min_available_memory'],2684354560+(5<<30)+(1<<30));self.assertEqual(RESOURCE['min_disk_free'],8<<30)
 def test_strict_does_not_accept_exit_only(self):self.assertFalse(strict({'native_exit':0,'errors':[]}))
 def test_strict_complete_and_boolean_exit_reject(self):
  r=dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True});self.assertTrue(strict(r));r['native_exit']=False;self.assertFalse(strict(r))

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo',type=P,required=True);a.add_argument('--source-pins-sha256',required=True);a.add_argument('--references-manifest',type=P,required=True);a.add_argument('--references-sha256',required=True);a.add_argument('--output',type=P,required=True);a.add_argument('--execute-reviewed-initialize-only',action='store_true',required=True);v=a.parse_args();print(json.dumps(run(v.repo,v.source_pins_sha256,v.references_manifest,v.references_sha256,v.output)))
