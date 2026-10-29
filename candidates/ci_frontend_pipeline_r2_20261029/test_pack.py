"""Synthetic packer-only fixtures; no real ELF/compiler/DUT qualification."""
import argparse,pathlib,tempfile,json,unittest,hashlib
from pack_frozen_artifact import pack,pin
from build_producer import DRIVER_SHA
class Tests(unittest.TestCase):
 def fixture(self,d):
  d=pathlib.Path(d);obj=d/'obj';obj.mkdir();src=d/'src';src.mkdir()
  files={}
  for k,data in [('binary',b'\x7fELF\x02\x01'+b'fixture-not-executable'),('sv',b'// synthetic fixture'),('source_manifest',b'{"scope":"fixture"}'),('tool_manifest',b'{"scope":"fixture"}'),('overlay',b'fixture')]:
   files[k]=obj/k;files[k].write_bytes(data)
  driver=src/'driver.cpp';driver.write_bytes(DRIVER.read_bytes());self.assertEqual(pin(driver)['sha256'],DRIVER_SHA)
  identity=dict(run_id=40831060687,artifact_name='fixture',source_commit='5302e25382bf5a6dc8020e787e45e40988488953',launch_commit='efd271a45ec75befbd389c374fbc314768436b6f',launch_manifest_path='ci_launch/fixed_frontend_r7_20261029_once.json',launch_manifest_blob_sha='9d87613d9c3c076314996fd1b043b7f233ed94ca')
  original=dict(artifact_identity=identity,repo_sha=identity['source_commit'],driver=str(driver))
  b=dict(pins={str(p):pin(p)['sha256']for p in files.values()},admission=dict(make_closure_pins={str(files['overlay']):pin(files['overlay'])['sha256']},method='FIXTURE_ONLY'),source_manifest=str(files['source_manifest']),tool_manifest=str(files['tool_manifest']))
  phase=dict(phase='host_link',argv=['fixture-no-execution'],output=pin(files['binary']),supervisor=dict(native_exit=0,errors=[],cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP')))
  built=dict(status='BUILT_UNQUALIFIED',scope='ARCHIVE_LINK_ONLY_NOT_DUT_PASS',phases=[phase],binary=phase['output'],plan=dict(phases=[dict(name='host_link',argv=phase['argv'])]))
  return original,b,built,files
 def test_exact_seven_and_identity(self):
  with tempfile.TemporaryDirectory()as d:
   o,b,r,f=self.fixture(d);calls=[];result=pack(o,b,r,f['sv'],f['overlay'],pathlib.Path(d),calls.append);root=pathlib.Path(result['manifest']['path']).parent;manifest=json.loads((root/'frozen_artifact.json').read_text());receipt=json.loads((root/'build_receipt.json').read_text())
   self.assertEqual(len(list(root.iterdir())),7);self.assertEqual(manifest['profiles'],list(range(5)));self.assertNotEqual(receipt['source_commit'],receipt['launch_commit']);self.assertGreater(calls[0],0);self.assertEqual(calls[-1],0)
 def test_native_failure_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   o,b,r,f=self.fixture(d);r['phases'][0]['supervisor']['native_exit']=1
   self.assertRaises(ValueError,pack,o,b,r,f['sv'],f['overlay'],pathlib.Path(d),lambda n:None)
 def test_budget_rejects_before_artifact(self):
  with tempfile.TemporaryDirectory()as d:
   o,b,r,f=self.fixture(d)
   def reject(n):raise ValueError('fixture budget refusal')
   self.assertRaises(ValueError,pack,o,b,r,f['sv'],f['overlay'],pathlib.Path(d),reject);self.assertFalse((pathlib.Path(d)/'frozen_artifact').exists())
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--driver',type=pathlib.Path,required=True);v,rest=a.parse_known_args();DRIVER=v.driver.resolve();unittest.main(argv=['test']+rest)
