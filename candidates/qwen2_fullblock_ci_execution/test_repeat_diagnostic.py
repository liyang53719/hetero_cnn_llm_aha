import os,unittest
from unittest.mock import patch
from . import repeat_diagnostic as D
class RepeatTests(unittest.TestCase):
 def test_unknown_run_rejects(self):
  with self.assertRaises(ValueError):
   with D.configured('ci03'):pass
 def test_default_profile_rejects(self):
  with patch.object(D.runtime_profile,'mkldnn_enabled',return_value=None):
   with self.assertRaises(ValueError):
    with D.configured('ci01'):pass
 def test_separate_authorization_restored(self):
  old=D.B.AUTH;env=dict(os.environ)
  with patch.object(D.runtime_profile,'mkldnn_enabled',return_value=False):
   with D.configured('ci02'):
    self.assertEqual(os.environ['QWEN2_REFERENCE_REPEAT_RUN'],'ci02')
    self.assertTrue(D.B.AUTH.endswith('/ci02'));self.assertIn('ci02',D.B.CERTIFICATE)
  self.assertEqual(old,D.B.AUTH);self.assertEqual(env,dict(os.environ))
 def test_two_independent_single_args(self):
  with patch.object(D.B,'pins',return_value=('a'*64,'b'*64)):
   self.assertEqual(D.arguments('--execute','ci02')[-2:],['--run-id','ci02'])
 def test_first_incomplete_stops_second(self):
  import tempfile,types,pathlib,contextlib
  calls=[]
  @contextlib.contextmanager
  def configured(run):calls.append(run);yield
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);(root/'work/logs').mkdir(parents=True)
   with patch.object(D,'configured',configured),patch.object(D,'ROOT',root),patch.object(D.B,'LOGS','work/logs'),patch.object(D.B.inputs,'safe_path',side_effect=lambda r,p:r/p),patch.object(D.B,'pins',return_value=('a','b')),patch.object(D.B,'call'),patch.object(D.subprocess,'check_output',return_value='fixed\n'),patch.dict(os.environ,{'GITHUB_SHA':'fixed'}),patch.object(D.subprocess,'Popen',return_value=types.SimpleNamespace(wait=lambda **_:2)),patch.object(D,'validated_failure',side_effect=ValueError('incomplete')):
    with self.assertRaises(ValueError):D.capture()
  self.assertEqual(calls,['ci01'])
 def test_guard_inventory_same_size_corruption_rejected(self):
  import tempfile,pathlib
  with tempfile.TemporaryDirectory() as d:
   out=pathlib.Path(d);p=out/D.O.DIRECTORY;p.mkdir();f={'partial_files':{}}
   for name in (*D.O.FILES,D.O.META):
    path=p/name;path.write_bytes(b'abc');f['partial_files'][D.O.DIRECTORY+'/'+name]=D.file_identity(path)
   D.verify_partial_files(out,f)
   (p/D.O.FILES[0]).write_bytes(b'xyz')
   with self.assertRaises(ValueError):D.verify_partial_files(out,f)
