import unittest,json,os,pathlib,subprocess,tempfile
from validate_r6_one_shot_launch import validate,LAUNCH
class T(unittest.TestCase):
 def test_real_manifest_integration(self):
  # Exact approved R4 launch bytes; change only named version fields.
  import hashlib
  raw=pathlib.Path(__file__).with_name('R4_APPROVED_LAUNCH_FIXTURE.json').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'70ca7d7fd5c964a552cbf76535caa441002f7722d16710f0b4c97a23b0b2cf5b')
  manifest=json.loads(raw);source=manifest['source_sha'];head='2'*40
  manifest['schema']='FRONTEND_R6_ONE_SHOT_V1';manifest['nonce']='fixed_frontend_r6_20261029_once'
  self.assertEqual(manifest['profile'],'FIXED4096_VECTOR32_FRONTEND_ONLY')
  event={'ref':'refs/heads/main','before':source,'after':head}
  self.assertEqual(validate(event,manifest,'1',head,source,'A\t'+LAUNCH+'\n'),source)
  for profile in ['FIXED4096_VECTOR42_FRONTEND_ONLY','FIXED4096_VECTOR52_FRONTEND_ONLY','FIXED512_VECTOR32_FRONTEND_ONLY']:
   with self.assertRaises(ValueError):validate(event,dict(manifest,profile=profile),'1',head,source,'A\t'+LAUNCH+'\n')
 def test_actual_git_cli(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)
   def git(*args):return subprocess.check_output(['git','-C',d,*args],text=True).strip()
   git('init','-q');git('config','user.email','test@example.invalid');git('config','user.name','test')
   script=pathlib.Path(__file__).with_name('validate_r6_one_shot_launch.py');(p/'guard.py').write_bytes(script.read_bytes());git('add','guard.py');git('commit','-qm','source');source=git('rev-parse','HEAD')
   m=json.loads(pathlib.Path(__file__).with_name('R4_APPROVED_LAUNCH_FIXTURE.json').read_bytes());m['schema']='FRONTEND_R6_ONE_SHOT_V1';m['nonce']='fixed_frontend_r6_20261029_once';m['source_sha']=source
   f=p/LAUNCH;f.parent.mkdir();f.write_text(json.dumps(m));git('add',LAUNCH);git('commit','-qm','launch');head=git('rev-parse','HEAD')
   e=p/'event.json';e.write_text(json.dumps({'ref':'refs/heads/main','before':source,'after':head}));out=p/'out';env=dict(os.environ,GITHUB_EVENT_PATH=str(e),GITHUB_OUTPUT=str(out),GITHUB_RUN_ATTEMPT='1')
   result=subprocess.run(['python3','-B',str(p/'guard.py')],cwd=d,env=env,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(out.read_text(),'source_sha='+source+'\n')
   env['GITHUB_RUN_ATTEMPT']='2';self.assertNotEqual(subprocess.run(['python3','-B',str(p/'guard.py')],cwd=d,env=env,capture_output=True).returncode,0)
if __name__=='__main__':unittest.main()
