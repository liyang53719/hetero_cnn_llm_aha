"""Actual isolated git launch + identity; no CI or compiler execution."""
import unittest,json,os,pathlib,subprocess,tempfile,hashlib
from validate_build_local_data_r2_launch import validate,LAUNCH
class T(unittest.TestCase):
 def fixture(self):
  raw=pathlib.Path(__file__).with_name('LOCAL_DATA_R1_APPROVED_LAUNCH_FIXTURE.json').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'494218b6469c2ce0daaae3d3ac3d7c3c8dc4ebdb472954a31f962efc044c3850')
  m=json.loads(raw);m['schema']='BUILD_ONLY_LOCAL_DATA_R2_ONE_SHOT_V1';m['nonce']='fixed_build_local_data_r2_20261029_once';return m
 def test_profile_and_scope_negative(self):
  m=self.fixture();s=m['source_sha'];h='2'*40;e=dict(ref='refs/heads/main',before=s,after=h)
  self.assertEqual(validate(e,m,'1',h,s,'A\t'+LAUNCH+'\n'),s)
  for profile in ['FIXED4096_VECTOR32_BUILD_ONLY','FIXED4096_VECTOR42_BUILD_ONLY','FIXED512_VECTOR32_BUILD_ONLY','FIXED4096_VECTOR32_FRONTEND_ONLY']:
   with self.assertRaises(ValueError):validate(e,dict(m,profile=profile),'1',h,s,'A\t'+LAUNCH+'\n')
  for attempt,diff in [('2','A\t'+LAUNCH+'\n'),('1','M\t'+LAUNCH+'\n'),('1','A\tother.json\n')]:
   with self.assertRaises(ValueError):validate(e,m,attempt,h,s,diff)
 def test_actual_git_cli_identity(self):
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d);temp=p/'runner_temp';temp.mkdir()
   def git(*a):return subprocess.check_output(['git','-C',d,*a],text=True).strip()
   git('init','-q');git('config','user.email','test@example.invalid');git('config','user.name','test');(p/'guard.py').write_bytes(pathlib.Path(__file__).with_name('validate_build_local_data_r2_launch.py').read_bytes());git('add','guard.py');git('commit','-qm','source');s=git('rev-parse','HEAD')
   m=self.fixture();m['source_sha']=s;f=p/LAUNCH;f.parent.mkdir();f.write_text(json.dumps(m));git('add',LAUNCH);git('commit','-qm','launch');h=git('rev-parse','HEAD');blob=git('rev-parse','HEAD:'+LAUNCH)
   e=p/'event.json';e.write_text(json.dumps(dict(ref='refs/heads/main',before=s,after=h)));out=p/'out';env=dict(os.environ,GITHUB_EVENT_PATH=str(e),GITHUB_OUTPUT=str(out),GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='1234',GITHUB_SHA=h,RUNNER_TEMP=str(temp))
   r=subprocess.run(['python3','-B',str(p/'guard.py')],cwd=d,env=env,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   identity=json.loads((temp/'hetero-build-artifact-identity.json').read_text());self.assertEqual(identity,dict(run_id=1234,artifact_name='hetero-common-dut-1234',source_commit=s,launch_commit=h,launch_manifest_path=LAUNCH,launch_manifest_blob_sha=blob));self.assertEqual(out.read_text(),'source_sha='+s+'\n')
   self.assertNotEqual(subprocess.run(['python3','-B',str(p/'guard.py')],cwd=d,env=env,capture_output=True).returncode,0)
 def test_summary_only_workflow(self):
  w=(pathlib.Path(__file__).resolve().parents[2]/'.github/workflows/hetero-fixed-common-build-local-data-r2.yml').read_text()
  self.assertEqual(w.count('actions/upload-artifact@'),1)
  self.assertIn('path: ${{ runner.temp }}/build-only-summary.json',w)
  for forbidden in ('/frozen_artifact/','verify_build_upload.py','name: hetero-common-dut-'):
   self.assertNotIn(forbidden,w)
  self.assertIn('bootstrap_build_only.py',w);self.assertIn('timeout-minutes: 350',w)
if __name__=='__main__':unittest.main()
