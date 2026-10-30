import pathlib,tempfile,unittest
import numeric_tail as n,locked_phase as phase
class T(unittest.TestCase):
 def fixture(self,t):
  root=pathlib.Path(t);cache=root/'cache';e=n.owned_environment({},cache)
  return dict(cache_root=str(cache),owned_roots=[str(root)],environment=e)
 def test_explicit_all(self):
  with tempfile.TemporaryDirectory()as t:phase.check_environment(self.fixture(t))
 def test_home_not_inherited(self):
  with tempfile.TemporaryDirectory()as t:
   b=self.fixture(t);b['environment']['HOME']='/outside'
   with self.assertRaises(ValueError):phase.check_environment(b)
 def test_missing_hf(self):
  with tempfile.TemporaryDirectory()as t:
   b=self.fixture(t);b['environment'].pop('HF_HOME')
   with self.assertRaises(KeyError):phase.check_environment(b)
 def test_alias_and_unknown_env(self):
  with tempfile.TemporaryDirectory()as t:
   b=self.fixture(t);p=pathlib.Path(b['environment']['XDG_CACHE_HOME']);p.rmdir();p.symlink_to('/outside')
   with self.assertRaises(ValueError):phase.check_environment(b)
   with self.assertRaises(ValueError):n.owned_environment({'GH_TOKEN':'not-a-token'},pathlib.Path(t)/'new')
if __name__=='__main__':unittest.main()
