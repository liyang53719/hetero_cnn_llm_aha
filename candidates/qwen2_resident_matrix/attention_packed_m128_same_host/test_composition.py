"""Exact source/control composition and fresh isolated startup; no numerics."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from . import contract as C, prepare as P


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.out=Path(cls.tmp.name)/'fresh'
        cls.result=P.compose(cls.out,git_head='1'*40,
            producer_package=P.ROOT/'candidates/qwen2_resident_matrix/portable_official_producer',
            producer_m128_package=P.ROOT/'candidates/qwen2_resident_matrix/portable_official_producer_m128')
        from ..attention_packed_m128_run_gate import prepare as old
        cls.old=old.compose(Path(cls.tmp.name)/'original')

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def child(self,code,*,timeout=20):
        script='import sys\nsys.path.insert(0,'+repr(str(self.out))+')\n'+code
        result=subprocess.run([sys.executable,'-I','-B','-c',script],cwd=self.out,capture_output=True,text=True,timeout=timeout)
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout

    def test_original_m128_executable_bodies_only_identity_metadata_changed(self):
        for name in P.TARGETS:
            before=(self.old/name).read_text();after=(self.out/name).read_text()
            self.assertEqual(after,P.rewrite(before,name),name)
        schedule='candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py'
        self.assertEqual((self.out/schedule).read_bytes(),(self.old/schedule).read_bytes())
        for leaf in ('capture.py','monitor.py'):
            name='candidates/qwen2_resident_matrix/attention_packed_tiled_observation/'+leaf
            self.assertEqual((self.out/name).read_bytes(),(self.old/name).read_bytes())
        contract=json.loads((self.out/C.PREFIX/C.SOURCE_FILE).read_bytes())
        self.assertEqual(contract['git_head'],'1'*40)
        self.assertEqual(contract['scope'],'FRESH_M128_ASSIGNED27_ONLY')

    def test_all24_originals_exact_and_repaired128_guard(self):
        expected=C.read_json(C.HERE/'compatible-sources.json')
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((self.out/name).read_bytes()).hexdigest(),digest)
        source=(self.out/P.TARGETS[0]).read_text()
        self.assertIn("require(validate_rows(pending['rows'])==128,",source)
        self.assertNotIn("require(validate_rows(pending['rows'])==16,",source)
        profile=(self.out/C.PREFIX/'profile.py').read_text()
        self.assertIn('type(job.m) is not int or job.m != 128',profile)
        schedule=(self.out/'candidates/qwen2_resident_matrix/attention_packed_owner/schedule.py').read_text()
        self.assertIn('range(0,token+1,16)',schedule.replace(' ',''))

    def test_inherited_control_ports_delta_is_exact_and_inverse_ast_identical(self):
        from ..attention_packed_m16_same_host import control_ports
        before=(self.old/control_ports.TARGET).read_bytes()
        after=(self.out/control_ports.TARGET).read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(),control_ports.BASELINE_SHA256)
        self.assertEqual(hashlib.sha256(after).hexdigest(),control_ports.CANDIDATE_SHA256)
        self.assertEqual(after,control_ports.transform(before))
        text=after.decode();self.assertEqual(text.count(control_ports.NEW),1)
        reversed_text=text.replace(control_ports.NEW,control_ports.OLD)
        self.assertEqual(reversed_text.encode(),before)
        self.assertEqual(ast.dump(ast.parse(reversed_text)),ast.dump(ast.parse(before)))
        self.assertEqual(self.result['source_sha256'][control_ports.TARGET],control_ports.CANDIDATE_SHA256)
        for prefix in ('attention_packed_observation','attention_packed_tiled_observation'):
            observer=json.loads((self.out/P.BASE/prefix/'pins.json').read_bytes())
            self.assertEqual(observer['runtime'][control_ports.TARGET],control_ports.CANDIDATE_SHA256)

    def test_terminal_numeric_resource_and_compatible_contracts_unchanged(self):
        self.assertTrue(P.check_terminal_scope())
        expected={
            'contract.py':'b11fc14f8128562c6d1f9bef4693e70c4dc57b36a6b72131881223754e5427a1',
            'compatible-sources.json':'72aedeb06e3ad9123b717a2d29e1c0427789884860dd451d94e7b43cde2e387e',
            'RESOURCE_PLAN.json':'44ac713f2d3a5ec50ee433e36bf0c0a87a97b3073fa59b2d9ba3d2c87f9aee26',
            'terminal_m16.py':'caf027af5688acbe8c29efb38ddba09a88a3223d0749572f6a002c42806aae20',
            'terminal_original.py':'f8ecc30ce4cff0a8ccafec86fe0e408ba71729f135a7622609782e019e86c2ad',
            'terminal_transform.py':'15ecb07061004462b31c558688f90aa02a94daca1a36a655e402a6ad0779137a',
            'terminal_validator.py':'ac569e60ee2d3422d1e8634867d51fbcce344978a098098cfa491e53290d507b',
        }
        for name,digest in expected.items():
            self.assertEqual(hashlib.sha256((self.out/C.PREFIX/name).read_bytes()).hexdigest(),digest,name)
        self.assertEqual((C.NUMERIC_SECONDS,C.WORK_SECONDS,C.CLEANUP_SECONDS,C.OUTER_SECONDS),(2400,2424,2429,2430))
        plan=C.read_json(C.HERE/'RESOURCE_PLAN.json')
        self.assertEqual((plan['rows'],plan['past_tokens'],plan['key_tile'],plan['word_beat']),(128,0,16,16))
        self.assertEqual((plan['public_completions'],plan['owner_jobs'],plan['assigned_gates'],plan['observed_stages']),(21,17,27,28))
        self.assertEqual(plan['terminal_json_max_bytes'],16*1024*1024)

    def test_isolated_fresh_contract_entry_terminal_startup_without_test_imports(self):
        code='''import sys
if not sys.flags.isolated or not sys.dont_write_bytecode:raise RuntimeError('isolated-B missing')
if 'unittest' in sys.modules:raise RuntimeError('ambient unittest')
from candidates.qwen2_resident_matrix.attention_packed_m128_same_host import contract,entry,terminal_validator,identity
sources=contract.snapshot()
if not sources or 'torch' in sys.modules or 'numpy' in sys.modules:raise RuntimeError('native startup')
if 'unittest' in sys.modules:raise RuntimeError('test dependency')
if terminal_validator.ROWS!=128 or terminal_validator.MAX_JSON!=16*1024*1024:raise RuntimeError('geometry')
print('PASS_ISOLATED_COLD_STARTUP')
'''
        self.assertIn('PASS_ISOLATED_COLD_STARTUP',self.child(code))

    def test_actual_original_host_prefixjob_type_guard_control_only(self):
        from ..attention_packed_m128_entry.test_profile import code
        original=code().replace('attention_packed_m128_entry.profile','attention_packed_m128_same_host.profile').replace(
            'attention_packed_m128_entry import contract','attention_packed_m128_same_host import contract')
        # Preserve assertion evaluation even if the outer cold suite uses -O.
        class ExplicitAssertions(ast.NodeTransformer):
            def visit_Assert(self,node):
                return ast.copy_location(ast.If(test=ast.UnaryOp(op=ast.Not(),operand=node.test),
                    body=[ast.Raise(exc=ast.Call(func=ast.Name(id='AssertionError',ctx=ast.Load()),
                        args=[node.msg or ast.Constant('original host control assertion')],keywords=[]),cause=None)],orelse=[]),node)
        tree=ast.fix_missing_locations(ExplicitAssertions().visit(ast.parse(original)))
        self.assertIn('PASS_ACTUAL_HOST',self.child(ast.unparse(tree)))

    def test_original_tiled_control_geometry(self):
        code='''from candidates.qwen2_resident_matrix.attention_packed_owner.schedule import PackedSchedule
from candidates.qwen2_resident_matrix.attention_packed_m128 import test_schedule
import unittest
suite=unittest.defaultTestLoader.loadTestsFromModule(test_schedule)
r=unittest.TextTestRunner().run(suite)
if not r.wasSuccessful():raise RuntimeError('original tiled schedule cold tests failed')
print('PASS_ORIGINAL_TILED_CONTROL')
'''
        script='import sys\nsys.path.insert(0,'+repr(str(P.ROOT))+')\n'+code
        result=subprocess.run([sys.executable,'-I','-B','-c',script],cwd=P.ROOT,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS_ORIGINAL_TILED_CONTROL',result.stdout)


if __name__=='__main__':unittest.main()
