import hashlib,io,json,tempfile,tarfile,unittest,ast
from pathlib import Path
import export_source as e
class Cold(unittest.TestCase):
 def test_expected_lock(self):e.check_lock(Path(__file__).with_name('Bender.lock.expected'))
 def test_lock_drift(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'lock';p.write_text('wrong')
   with self.assertRaises(ValueError):e.check_lock(p)
 def test_recipe_scope(self):
  steps=e.stages('/reviewed/bender','/reviewed/uv')
  self.assertEqual(len(steps),7)
  self.assertEqual(steps[5][0][-2:],['target/rtl/idma_generated.sv','target/rtl/include/idma/compute.svh'])
  self.assertNotIn('verilator',[s[0][0] for s in steps])
  self.assertTrue(all(s[0][0] not in ['firtool','vcs','yosys','sbt','java'] for s in steps))
 def test_dep_identity(self):
  self.assertEqual(len(e.DEPS),7);self.assertEqual(e.DEPS['axi'],'0ccc838fe06aeeb857eb83c6be9a915c4bf99566')
  self.assertEqual(e.DEPS['common_cells'],'63b7c50d43e462b59506f69d341ff1e40202866d')
 def test_tool_hash(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'tool';p.write_text('bytes');h=hashlib.sha256(b'bytes').hexdigest()
   self.assertEqual(e.tool(p,h),p)
   with self.assertRaises(ValueError):e.tool(p,'0'*64)
 def test_archive_escape(self):
  bio=io.BytesIO()
  with tarfile.open(fileobj=bio,mode='w') as t:
   info=tarfile.TarInfo('../escape');info.size=1;t.addfile(info,io.BytesIO(b'x'))
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(tarfile.FilterError):e.unpack_archive(bio.getvalue(),Path(d)/'out')
   self.assertFalse((Path(d)/'escape').exists())
 def test_archive_reject_existing(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(FileExistsError):e.unpack_archive(b'',Path(d))
 def test_malformed_export(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'COMMITS.json').write_text('{}');(p/'SHA256SUMS.json').write_text('{}')
   with self.assertRaises(ValueError):e.verify_export(p)
 def test_command_preparation_precedes_alarm_handoff(self):
  source=Path(e.__file__).read_text();tree=ast.parse(source)
  cmd=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='cmd')
  body=ast.get_source_segment(source,cmd)
  self.assertLess(body.index('shutil.which'),body.index('signal.setitimer(signal.ITIMER_REAL,0)'))
  self.assertLess(body.index('signal.setitimer(signal.ITIMER_REAL,0)'),body.index('bounded_run.execute'))
  self.assertIn('finally:arm()',body)
 def test_preprocessor_flag_is_request_not_execution_claim(self):
  source=Path(e.__file__).read_text()
  self.assertIn("'preprocessor_requested':False",source)
  self.assertNotIn('preprocessor_executed',source)
if __name__=='__main__':unittest.main()
