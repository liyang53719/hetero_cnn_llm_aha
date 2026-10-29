"""Source-only tests. Pass --repo to an existing checkout containing commit 7a22; no fetch."""
import argparse,json,pathlib,subprocess,sys,tempfile,unittest
from fixed_sources import validate_overlay,checked_paths,COMMIT
D=pathlib.Path(__file__).parent
args=argparse.ArgumentParser();args.add_argument('--repo',required=True,type=pathlib.Path);opt,rest=args.parse_known_args();sys.argv=[sys.argv[0]]+rest
def git(rel):return subprocess.check_output(['git','-C',str(opt.repo),'show',COMMIT+':'+rel])
ORIGINAL=json.loads(git('candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json'))
RAW=(D/'FIXED_SOURCE_OVERLAY_R2.json').read_bytes()
class Tests(unittest.TestCase):
 def test_fixed155(self):self.assertEqual(len(validate_overlay(RAW,ORIGINAL)),155)
 def test_old155_rejected(self):
  with self.assertRaises(ValueError):validate_overlay(json.dumps(ORIGINAL).encode(),ORIGINAL)
 def test_wrong_published_overlay_rejected(self):
  with self.assertRaises(ValueError):validate_overlay(git('candidates/attention_policy_count_fix_20261029T0054/SOURCE_OVERLAY.json'),ORIGINAL)
 def test_overlay_tamper_rejected(self):
  with self.assertRaises(ValueError):validate_overlay(RAW.replace(b'8cea5e',b'0cea5e'),ORIGINAL)
 def test_all_source_blobs_and_source_tamper(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d)
   for x in validate_overlay(RAW,ORIGINAL):
    p=root/x['repo_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(git(x['repo_path']))
   self.assertEqual(len(checked_paths(root,D/'FIXED_SOURCE_OVERLAY_R2.json',ORIGINAL)),155)
   p=root/json.loads(RAW)['files'][0]['repo_path'];p.write_bytes(p.read_bytes()+b'\n')
   with self.assertRaises(ValueError):checked_paths(root,D/'FIXED_SOURCE_OVERLAY_R2.json',ORIGINAL)
if __name__=='__main__':unittest.main()
