"""Cold metadata and profile scope checks; no native execution."""
import ast,json,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
from . import profile as p
class Cold(unittest.TestCase):
    def test_default_no_execute(self):
        r=subprocess.run([sys.executable,'-B','-m',p.__name__],cwd=p.ROOT,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['status'],'NOT_EXECUTED')
    def test_no_private_work_in_cold(self):
        original=Path.read_bytes
        def read(path,*a,**kw):
            if path.is_relative_to(p.ROOT/'work'):raise AssertionError('private cold read')
            return original(path,*a,**kw)
        with patch.object(Path,'read_bytes',read):self.assertGreater(len(p.sources_now()),60)
    def test_scope_and_fixed_cases(self):
        self.assertEqual(p.CASES,('UNPROFILED_TWO_TILES','CPROFILE_TWO_TILES'))
        text=Path(p.__file__).read_text();self.assertIn('for target in (1,2):',text)
        self.assertIn('full_projection=False,fullblock=False',text);self.assertNotIn('candidate_project_raw',text)
        self.assertIn('resource.RLIMIT_CPU,(20,20)',text)
    def test_existing_source_identity_without_wrapping(self):
        from candidates.qwen2_exact64_projection_integration.driver import Exact64PublicDriver
        from candidates.qwen2_exact64_projection_integration.owner import Exact64ProjectionOwner
        self.assertIs(p.Exact64PublicDriver,Exact64PublicDriver);self.assertIs(p.Exact64ProjectionOwner,Exact64ProjectionOwner)
        tree=ast.parse(Path(p.__file__).read_text())
        for n in ast.walk(tree):
            if isinstance(n,(ast.Assign,ast.AnnAssign)):
                targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                self.assertFalse(any(isinstance(t,ast.Attribute) and t.attr in ('tick','acquire','bind_dense_job','state','jobs','completed','pc') for t in targets))
    def test_protocol_and_profile_boundaries(self):
        text=Path(p.__file__).read_text()
        order=[text.index(x) for x in ('execute_prefix_owner(x','physical.publish(j0','j1=x.advance_to_request','driver=Exact64PublicDriver','profiler.enable()','for target in (1,2):','profiler.disable()','driver.tick(abort=True)')]
        self.assertEqual(order,sorted(order));self.assertIn("x.host.state=='locked'",text)
        self.assertIn("lib.matrix_dense_fmas()==lib.matrix_normal_fmas()==0",text)
    def test_supervisor_group_cleanup(self):
        text=(p.HERE/'supervise.py').read_text()
        self.assertIn('signals.start()',text);self.assertIn('finally:',text);self.assertIn('os.killpg(proc.pid,signal.SIGKILL)',text)
        self.assertIn('wall=29',text);self.assertIn('cpu>=19',text);self.assertIn('size>=7<<20',text)
if __name__=='__main__':unittest.main()
