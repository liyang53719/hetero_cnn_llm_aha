"""Source-level wiring only. No tool inventory, compiler, EDA or DUT execution."""
import ast,pathlib,unittest,argparse
D=pathlib.Path(__file__).parent
class Tests(unittest.TestCase):
 def test_compile_frontend_same(self):
  old=BASE.read_text();new=(D/'one_job_build_only.py').read_text()
  a=old[old.index("  stage('compile155'"):old.index("  frontend_receipt=")]
  b=new[new.index("  stage('compile155'"):new.index("  frontend_receipt=")]
  self.assertEqual(a,b)
 def test_no_numeric_runtime_calls(self):
  s=(D/'one_job_build_only.py').read_text()
  for name in ['runtime_prepare_argv','runtime_compare_script','prepare_five','run_compare_five','cpp_build']:self.assertNotIn(name,s)
  self.assertLess(s.index('run_frontend_serial(stage'),s.index('build_binding=admit_build'))
  self.assertLess(s.index('build_binding=admit_build'),s.index('built=run('));self.assertLess(s.index('built=run('),s.index('artifact=pack('))
 def test_new_scope_and_aliases(self):
  s=BOOTSTRAP.read_text();self.assertIn("bound['mode']='BUILD_ONLY'",s);self.assertIn("os.environ['GITHUB_SHA']",s);self.assertIn("os.environ['GITHUB_RUN_ATTEMPT']=='1'",s);self.assertIn("tool_inventory['pins']",s)
 def test_artifact_names_and_budget(self):
  s=(D/'pack_frozen_artifact.py').read_text();self.assertIn('budget_check(projected);root.mkdir()',s);self.assertIn('budget_check(0)',s);self.assertIn("len(list(root.iterdir()))==7",s);self.assertIn("source_commit=original['artifact_identity']['source_commit']",s);self.assertIn("launch_commit=original['artifact_identity']['launch_commit']",s)
 def test_parse_all(self):
  for n in ['one_job_build_only.py','pack_frozen_artifact.py']:ast.parse((D/n).read_text())
  ast.parse(BOOTSTRAP.read_text())
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--pipeline-dir',type=pathlib.Path,default=D);a.add_argument('--bootstrap',type=pathlib.Path,default=D.parent/'ci_frontend_materialization_r2_20261029/bootstrap_build_only.py');a.add_argument('--baseline-entry',type=pathlib.Path,default=D/'one_job_entry_fixed_r2.py');v,rest=a.parse_known_args();BASE=v.baseline_entry;D=v.pipeline_dir;BOOTSTRAP=v.bootstrap;unittest.main(argv=['test']+rest)
