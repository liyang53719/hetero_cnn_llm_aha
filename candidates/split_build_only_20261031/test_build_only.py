"""Synthetic metadata/ZIP/launch tests only; never compiles or runs a DUT."""
import copy,hashlib,json,pathlib,stat,tempfile,unittest,zipfile,os,time,shutil,types
from unittest.mock import patch
import validate_launch as guard
from receive_zip import receive
from seven_files import NAMES,sha,verify
from export_build import strict,STAGES,PREP
P=pathlib.Path

def write(p,v):p.write_text(json.dumps(v))
class Fixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=P(self.tmp.name);self.payload=self.root/'payload';self.payload.mkdir()
  self.i=dict(run_id=9,artifact_name='hetero-common-dut-9',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path=guard.LAUNCH,launch_manifest_blob_sha='c'*40)
  for k,n in NAMES.items():
   if k!='build_receipt':(self.payload/n).write_bytes(b'\x7fELF\x02\x01toy'if k=='binary'else b'{}')
  rows={k:dict(path=n,bytes=(self.payload/n).stat().st_size,sha256=sha(self.payload/n))for k,n in NAMES.items()if k!='build_receipt'}
  phases=[dict(phase=n,native_exit=0,supervisor_receipt_sha256='f'*64,output_sha256=rows['binary']['sha256'])for n in STAGES[-5:]]
  receipt=dict(status='BINARY_BUILD_ONLY_NO_NUMERICS',scope='CHISEL_TEST_BACKEND_NOT_FINAL_RTL_REPLAY',config_only=False,software_arithmetic_substitution=False,source_commit=self.i['source_commit'],launch_commit=self.i['launch_commit'],phases=phases,**{k+'_sha256':r['sha256']for k,r in rows.items()})
  write(self.payload/'build_receipt.json',receipt);rows['build_receipt']=dict(path='build_receipt.json',bytes=(self.payload/'build_receipt.json').stat().st_size,sha256=sha(self.payload/'build_receipt.json'))
  manifest=dict(schema='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2',profiles=list(range(5)),matrix_macs=4096,vector_lanes=32,artifact_identity=self.i,common={k:v for k,v in rows.items()if k!='tool_manifest'},tool_manifest=rows['tool_manifest'])
  write(self.payload/'frozen_artifact.json',manifest);self.mh=sha(self.payload/'frozen_artifact.json')
 def archive(self,change=None):
  p=self.root/'payload.zip'
  with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED)as z:
   for f in self.payload.iterdir():
    if change is None:z.write(f,f.name)
    else:change(z,f)
  api=self.root/'api.json';write(api,dict(schema='AUTHENTICATED_GITHUB_ARTIFACT_RECEIPT_V1',artifact_id=4,name=self.i['artifact_name'],run_id=9,source_commit='a'*40,launch_commit='b'*40,expired=False,api_size_in_bytes=p.stat().st_size+999,downloaded_zip_bytes=p.stat().st_size,archive_sha256=sha(p),api_verified=True));return p,api
 def receive(self,p,a):return receive(p,sha(p),a,sha(a),self.root/'out',self.i,self.mh)
 def test_exact_seven(self):
  p,a=self.archive();r=self.receive(p,a);self.assertFalse(r['numerical_pass']);self.assertEqual(len(list((self.root/'out').iterdir())),7)
  self.assertTrue(all(stat.S_IMODE(f.stat().st_mode)==0o600 for f in(self.root/'out').iterdir()))
 def test_bad_zip_hash(self):
  p,a=self.archive()
  with self.assertRaises(ValueError):receive(p,'0'*64,a,sha(a),self.root/'out',self.i,self.mh)
 def test_api_wrong_run(self):
  p,a=self.archive();r=json.loads(a.read_text());r['run_id']=10;write(a,r)
  with self.assertRaises(ValueError):self.receive(p,a)
 def test_api_expired(self):
  p,a=self.archive();r=json.loads(a.read_text());r['expired']=True;write(a,r)
  with self.assertRaises(ValueError):self.receive(p,a)
 def test_api_wrong_size(self):
  p,a=self.archive();r=json.loads(a.read_text());r['downloaded_zip_bytes']+=1;write(a,r)
  with self.assertRaises(ValueError):self.receive(p,a)
 def test_zip_slip(self):
  p,a=self.archive(lambda z,f:z.write(f,'../'+f.name))
  with self.assertRaises(ValueError):self.receive(p,a)
  self.assertFalse((self.root/'out').exists())
 def test_symlink(self):
  def add(z,f):
   q=zipfile.ZipInfo(f.name);q.create_system=3;q.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(q,f.read_bytes())
  p,a=self.archive(add)
  with self.assertRaises(ValueError):self.receive(p,a)
 def test_extra_file(self):
  p,a=self.archive()
  with zipfile.ZipFile(p,'a')as z:z.writestr('local.npz',b'not allowed')
  r=json.loads(a.read_text());r.update(downloaded_zip_bytes=p.stat().st_size,archive_sha256=sha(p));write(a,r)
  with self.assertRaises(ValueError):self.receive(p,a)
 def test_payload_drift(self):
  (self.payload/'hardware.sv').write_text('drift');p,a=self.archive()
  with self.assertRaises(ValueError):self.receive(p,a)
 def test_manifest_pin(self):
  with self.assertRaises(ValueError):verify(self.payload,self.i,'0'*64)
 def test_missing_file(self):
  (self.payload/'driver.cpp').unlink()
  with self.assertRaises(ValueError):verify(self.payload,self.i)
 def test_wrong_builder_identity(self):
  i=dict(self.i,run_id=10)
  with self.assertRaises(ValueError):verify(self.payload,i)
 def test_failed_strict(self):
  p=self.root/'result.json';r=dict(native_exit=0,errors=[],cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True));write(p,r);strict(p)
  for change in [dict(native_exit=1),dict(errors=['bad']),dict(log_capture=dict(pipe_eof_observed=False,gzip_finalized=True)),dict(cleanup_proof={})]:
   write(p,dict(r,**change))
   with self.assertRaises(ValueError):strict(p)
class Export(unittest.TestCase):
 setUp=Fixture.setUp
 def test_complete_export_chain(self):
  import export_build
  work=self.root/'job';build=work/'shared/build';front=build/'frontend';front.mkdir(parents=True)
  shutil.copytree(self.payload,front/'frozen_artifact')
  r=dict(native_exit=0,errors=[],cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True))
  for name in PREP:
   p=build/('stage_'+name);p.mkdir();write(p/'RESULT.json',r)
  for name in STAGES:
   p=front/name;p.mkdir(exist_ok=True);write(p/'RESULT.json',r)
  write(front/'stage_exits.json',[dict(name=n)for n in STAGES])
  payload=verify(front/'frozen_artifact',self.i)
  write(front/'BUILD_ONLY_RESULT.json',dict(status='PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS',artifact=dict(manifest=dict(sha256=self.mh),expanded_bytes=payload['expanded_bytes'])))
  write(work/'BUILD_INVOCATION.json',dict(artifact_identity=self.i,source_pins_sha256='f'*64,job_started_monotonic=time.monotonic()))
  identity=self.root/'identity.json';write(identity,self.i);output=self.root/'summary.json';gh=self.root/'ghout'
  a=types.SimpleNamespace(repo=self.root,work=work,identity=identity,output=output)
  with patch.object(export_build,'source_pins',return_value='f'*64),patch.object(export_build,'ACCEPTED_TRANSFER_APPROVAL_SHA256','e'*64),patch.dict(os.environ,dict(GITHUB_RUN_ID='9',GITHUB_SHA='b'*40,GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(gh))):
   export_build.run(a)
  result=json.loads(output.read_text());self.assertEqual(len(result['stages']),28);self.assertFalse(result['numerical_pass']);self.assertIn('artifact_name=hetero-common-dut-9',gh.read_text())

class Launch(unittest.TestCase):
 def setUp(self):
  self.event=dict(ref='refs/heads/main',before='a'*40,after='b'*40);self.man=dict(schema=guard.SCHEMA,source_sha='a'*40,nonce=guard.NONCE,transfer_approval_sha256='f'*64)
 def call(self,**kw):
  args=dict(event=self.event,manifest=self.man,attempt='1',head='b'*40,parent='a'*40,diff='A\t'+guard.LAUNCH+'\n');args.update(kw);return guard.validate(**args)
 def test_pending_approval_rejects(self):
  self.assertIsNone(guard.ACCEPTED_TRANSFER_APPROVAL_SHA256)
  with self.assertRaises(ValueError):self.call()
 def test_synthetic_approved_and_directparent(self):
  with patch.object(guard,'ACCEPTED_TRANSFER_APPROVAL_SHA256','f'*64):
   self.assertEqual(self.call(),'a'*40)
   for kw in (dict(attempt='2'),dict(parent='c'*40),dict(diff='M\t'+guard.LAUNCH+'\n'),dict(diff='A\t'+guard.LAUNCH+'\nA\tx\n')):
    with self.assertRaises(ValueError):self.call(**kw)
 def test_budget_scope(self):
  import prepare_build
  self.assertEqual(prepare_build.BUILD_SECONDS,7200);self.assertEqual(prepare_build.WHOLE_SECONDS,9000);self.assertEqual(len(PREP),8);self.assertEqual(len(STAGES),20)
if __name__=='__main__':unittest.main()
