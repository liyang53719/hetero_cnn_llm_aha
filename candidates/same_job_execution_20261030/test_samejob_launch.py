import hashlib,importlib.util,json,os,pathlib,subprocess,sys,tempfile,unittest
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('launch',D/'validate_samejob_calibration_launch.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
FIXTURE_SHA='541b3e5fc92f43d0cf39d21df531c9e44af989177ba694cea726b9bf1545fa25'
ACTUAL_R2_LAUNCH='ef6a5fcd95ff643c3d6527f91e4a80e5a1c914a6'
def manifest(source=None):
 raw=(D/'ACTUAL_R2_LAUNCH_FIXTURE.json').read_bytes()
 if len(raw)!=209 or hashlib.sha256(raw).hexdigest()!=FIXTURE_SHA:raise ValueError('actual acdb R2 fixture')
 m=json.loads(raw)
 m['schema']='FIVE_M128_SAMEJOB_CALIBRATION_LOCAL_DATA_ONE_SHOT_V1'
 m['profile']='FIXED4096_VECTOR32_FIVE_M128_CALIBRATION_LOCAL_DATA'
 m['nonce']='five_m128_samejob_diagnostic_r2_20261030_once'
 if source is not None:m['source_sha']=source
 return m
class T(unittest.TestCase):
 def args(self):
  m=manifest();head=ACTUAL_R2_LAUNCH;return [dict(ref='refs/heads/main',before=m['source_sha'],after=head),m,'1',head,m['source_sha'],'A\t'+g.LAUNCH+'\n']
 def test_actual_distinct_fixture_missing_commit_arrays(self):
  args=self.args();self.assertNotEqual(args[3],args[4]);self.assertNotIn('commits',args[0]);self.assertEqual(g.validate(*args),args[4])
 def test_retry_and_wrong_resource_rejected(self):
  a=self.args();a[2]='2'
  with self.assertRaises(ValueError):g.validate(*a)
  for resource in ('VECTOR42','VECTOR52','MATRIX512'):
   a=self.args();a[1]['profile']=a[1]['profile'].replace('VECTOR32',resource)
   with self.assertRaises(ValueError):g.validate(*a)
 def test_modification_extra_file_wrong_parent_or_event(self):
  for diff in ('M\t'+g.LAUNCH+'\n','A\t'+g.LAUNCH+'\nA\tother\n','A\tci_launch/old.json\n'):
   a=self.args();a[5]=diff
   with self.assertRaises(ValueError):g.validate(*a)
  a=self.args();a[4]=a[3]
  with self.assertRaises(ValueError):g.validate(*a)
  a=self.args();a[0]['before']=a[3]
  with self.assertRaises(ValueError):g.validate(*a)
 def test_consumed_nonce_path_and_wrong_identity_rejected(self):
  a=self.args();a[1]['nonce']='five_m128_samejob_calibration_20261030_once'
  with self.assertRaises(ValueError):g.validate(*a)
  a=self.args();a[5]='A\tci_launch/five_m128_samejob_calibration_20261030_once.json\n'
  with self.assertRaises(ValueError):g.validate(*a)
  for key,value in [('ref','refs/heads/other'),('after',self.args()[4])]:
   a=self.args();a[0][key]=value
   with self.assertRaises(ValueError):g.validate(*a)
  a=self.args();a[1]['extra']=True
  with self.assertRaises(ValueError):g.validate(*a)
  a=self.args();a[1]['source_sha']='7c545226'
  with self.assertRaises(ValueError):g.validate(*a)
 def test_new_trigger_matches_guard_and_preserves_consumed_manifest(self):
  workflow=D.parents[1]/'.github/workflows/hetero-five-m128-samejob-calibration-local-data.yml'
  text=workflow.read_text();self.assertIn('paths: ['+g.LAUNCH+']',text)
  self.assertNotIn('paths: [ci_launch/five_m128_samejob_calibration_20261030_once.json]',text)
  self.assertEqual(g.LAUNCH,'ci_launch/five_m128_samejob_diagnostic_r2_20261030_once.json')
 def test_real_two_commit_cli_identity(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);repo=root/'repo';repo.mkdir();run=root/'temp';run.mkdir()
   def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
   git('init','-q','-b','main');(repo/'SOURCE.txt').write_text('reviewed source fixture\n');consumed=repo/'ci_launch/five_m128_samejob_calibration_20261030_once.json';consumed.parent.mkdir();consumed.write_text('historical consumed manifest fixture\n');old_bytes=consumed.read_bytes();git('add','SOURCE.txt',str(consumed.relative_to(repo)));git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','source');source=git('rev-parse','HEAD')
   p=repo/g.LAUNCH;p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(manifest(source))+'\n');git('add',g.LAUNCH);git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','unique launch');head=git('rev-parse','HEAD')
   event=root/'event.json';event.write_text(json.dumps(dict(ref='refs/heads/main',before=source,after=head)));output=root/'GITHUB_OUTPUT';output.touch()
   env=dict(os.environ,GITHUB_EVENT_PATH=str(event),GITHUB_RUN_ATTEMPT='1',GITHUB_SHA=head,GITHUB_RUN_ID='123',RUNNER_TEMP=str(run),GITHUB_OUTPUT=str(output))
   subprocess.run([sys.executable,*(['-O']if not __debug__ else []),'-B',str(D/'validate_samejob_calibration_launch.py')],cwd=repo,env=env,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   identity=json.loads((run/'hetero-five-m128-identity.json').read_text());self.assertEqual(set(identity),{'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'});self.assertEqual(identity['source_commit'],source);self.assertEqual(identity['launch_commit'],head);self.assertEqual(identity['launch_manifest_blob_sha'],git('rev-parse','HEAD:'+g.LAUNCH));self.assertEqual(output.read_text(),'source_sha='+source+'\n');self.assertEqual(consumed.read_bytes(),old_bytes)
 def test_workflow_fixed_summary_only_and_clock_first(self):
  workflow=D.parents[1]/'.github/workflows/hetero-five-m128-samejob-calibration-local-data.yml';text=workflow.read_text()
  self.assertEqual(text.count('uses: actions/upload-artifact@'),1);self.assertIn('path: ${{ runner.temp }}/five-m128-summary.json',text);self.assertIn("steps.summary.outcome == 'success'",text)
  self.assertNotIn('continue-on-error:',text);self.assertNotIn('workflow_dispatch:',text);self.assertNotIn('dut.bin',text);self.assertNotIn('hardware.sv',text)
  self.assertIn('group: hetero-exclusive-numeric-bootstrap',text);self.assertIn('runs-on: ubuntu-24.04',text);self.assertIn('timeout-minutes: 350',text)
  self.assertLess(text.index('Record owning job monotonic start'),text.index('uses: actions/checkout@'))
  self.assertEqual(text.count('GH_TOKEN: ${{ github.token }}'),1);self.assertEqual(text.count('persist-credentials: false'),2)
if __name__=='__main__':unittest.main()
