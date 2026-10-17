"""Stdlib-only cold contracts. No packages, weights, compilation or model runs."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    exec(compile(Path(path).read_bytes(),str(path),'exec'),m.__dict__);return m

D=load('cold_m128_driver',HERE/'driver.py')
V=load('cold_m128_verifier',HERE/'verify.py')
B=D.baseline()


def context_fixture(job,start=1000):
    ci=dict(commit='a'*40,run_id='123',run_attempt='1')
    value=dict(schema=1,profile=D.CONTEXT_PROFILE,parent_pid=1234,root=str(ROOT),workspace=str(job/'producer128'),
        upstream_workspace=str(job/'m16/setup/producer'),created_ns=start,producer_deadline_ns=start+260*10**9,
        deadline_ns=start+290*10**9,cleanup_deadline_ns=start+299*10**9,receipt_deadline_ns=start+300*10**9,
        attempt_nonce='b'*64,ci=ci,host=dict(host_sha256='c'*64,boot_sha256='d'*64,machine='x86_64',system='Linux'),
        driver_sha256=D.IMPORTED_DRIVER_SHA,source_lock_sha256=D.IMPORTED_LOCK_SHA,
        python=str(job/'m16/setup/venv/bin/python'),upstream={k:{} for k in D.UPSTREAM_KEYS})
    return value


def check_context(value):
    job=Path(value['workspace']).parent
    return D.validate_context(value,ROOT,job/'producer128',1000+290*10**9,'b'*64,
        dict(commit='a'*40,run_id='123',run_attempt='1'),parent_pid=1234,now_ns=1001,
        host=dict(host_sha256='c'*64,boot_sha256='d'*64,machine='x86_64',system='Linux'),python=job/'m16/setup/venv/bin/python')


class ColdDriver(unittest.TestCase):
    def test_import_does_not_load_numerical_packages(self):
        self.assertNotIn('numpy',sys.modules);self.assertNotIn('torch',sys.modules)
        self.assertNotIn('transformers',sys.modules)

    def test_exact_source_closure(self):
        sources,lock=D.verify_sources(ROOT)
        self.assertEqual(len(sources),75)
        self.assertEqual(sources[D.BASE_REL+'driver.py'],D.BASE_SHA)
        self.assertEqual(sources[D.BASE_REL+'owned_commands.py'],'23170d4f016900c074a3a446fe4529f7465060c039cdf2aad27bce6a009c6c49')
        self.assertEqual(lock,D.IMPORTED_LOCK_SHA)
        self.assertTrue(all(D.PREREQUISITE_REL+n in sources for n in D.PREREQUISITE_FILES))

    def test_source_drift_rejected_before_numerical_import(self):
        p=ROOT/'spec/numerical_contract.md';raw=p.read_bytes()
        try:
            p.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(ValueError,'source drift'):D.verify_sources(ROOT)
        finally:p.write_bytes(raw)
        D.verify_sources(ROOT)

    def test_source_cache_rejected(self):
        target=ROOT/'scripts/qwen2_layer0_model_gate.pyc'
        self.assertFalse(target.exists())
        try:
            target.write_bytes(b'not bytecode')
            with self.assertRaisesRegex(ValueError,'source cache'):D.verify_sources(ROOT)
        finally:target.unlink()

    def test_fresh_context_exact_deadlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            value=context_fixture(Path(tmp));self.assertEqual(check_context(value),value)
            for key,bad in (('parent_pid',1235),('attempt_nonce','0'*64),('producer_deadline_ns',1000+261*10**9),
                            ('deadline_ns',True),('cleanup_deadline_ns',1000+300*10**9),('receipt_deadline_ns',1000+301*10**9),
                            ('driver_sha256','0'*64),('source_lock_sha256','0'*64),('python','/usr/bin/python')):
                candidate=copy.deepcopy(value);candidate[key]=bad
                with self.subTest(key=key),self.assertRaises(ValueError):check_context(candidate)
            for key,bad in (('ci',dict(value['ci'],run_attempt='2')),('host',dict(value['host'],boot_sha256='0'*64))):
                candidate=copy.deepcopy(value);candidate[key]=bad
                with self.subTest(key=key),self.assertRaises(ValueError):check_context(candidate)
            candidate=copy.deepcopy(value);candidate['rows']=16
            with self.assertRaises(ValueError):check_context(candidate)

    def test_private_fresh_directories_and_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'raw_stages';D.fresh_directory(p)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700)
            with self.assertRaises(FileExistsError):D.fresh_directory(p)
            (p/'existing').write_text('preserve')
            with self.assertRaises(FileExistsError):D.fresh_directory(p)
            self.assertEqual((p/'existing').read_text(),'preserve')
            alias=Path(tmp)/'alias';alias.symlink_to(p)
            with self.assertRaises(ValueError):D.fresh_directory(alias)

    def test_output_namespace_and_rooted_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp);workspace=job/'producer128';workspace.mkdir()
            up=job/'m16/setup/producer';up.mkdir(parents=True)
            p=up/'payload.bin';p.write_bytes(b'payload')
            value=dict(roots=dict(current=str(workspace),upstream=str(up)))
            item=D.rooted(B.record(up,p),'upstream')
            self.assertEqual(D.resolve_artifact(workspace,value,item),p)
            with self.assertRaises(ValueError):D.resolve_artifact(workspace,value,dict(item,path='../payload.bin'))
            with self.assertRaises(ValueError):D.resolve_artifact(workspace,value,dict(item,root='history'))
            q=up/'alias';os.link(p,q)
            with self.assertRaises(ValueError):D.resolve_artifact(workspace,value,item)
            q.unlink()
            p.write_bytes(b'changed')
            with self.assertRaises(ValueError):D.resolve_artifact(workspace,value,item)

    def test_no_isa_assignment_or_unowned_spawn(self):
        tree=ast.parse((HERE/'driver.py').read_bytes())
        forbidden={'subprocess.run','subprocess.Popen','subprocess.check_output','os.system','rms.generate_tables'}
        calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertFalse(set(calls)&forbidden)
        self.assertTrue(any(c.endswith("['owner'].run") for c in calls))
        for n in ast.walk(tree):
            if isinstance(n,(ast.Assign,ast.AugAssign)):
                self.assertNotIn('os.environ[',ast.unparse(n))

    def test_true128_native_scalar_and_arena_calls(self):
        tree=ast.parse((HERE/'driver.py').read_bytes());calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
        native=[n for n in calls if ast.unparse(n.func)=='native.run_gate'];self.assertEqual(len(native),1)
        keywords={k.arg:ast.unparse(k.value) for k in native[0].keywords}
        self.assertEqual(keywords['tokens'],'128');self.assertEqual(keywords['carried'],'False')
        self.assertEqual(keywords['threads'],'4');self.assertIn('native16/RESULT.json',keywords['small_gate'])
        arena=next(n for n in calls if ast.unparse(n.func)=='rms.write_arena')
        self.assertEqual(ast.literal_eval(arena.args[2]),128);self.assertEqual(ast.literal_eval(arena.args[3]),0)
        self.assertEqual(D.CAPS,dict(compile=10,arena_and_table=30,native128=120,scalar=45,independent_postflight=30))
        self.assertIn("'128',str(raw),'0'",(HERE/'driver.py').read_text())

    def test_full128_output_geometry(self):
        W=load('cold_original_workload',ROOT/'candidates/qwen2_resident_matrix/dense_block_reduce/reference/workload.py')
        inventory=W.output_inventory(128)
        self.assertEqual(len(inventory),22)
        self.assertEqual(inventory['scores.f32le'],12*128*128*4)
        self.assertEqual(inventory['cache_k.f32le'],128*2*128*4)
        self.assertEqual(inventory['phase_10_gate_recipe.f32le'],128*8960*4)
        sealed={n:dict(bytes=size) for n,size in inventory.items()};W.validate_sealed_inventory(128,sealed)
        for mutation in (dict(sealed,extra=dict(bytes=4)),{n:r for n,r in sealed.items() if n!='scores.f32le'}):
            with self.assertRaises(ValueError):W.validate_sealed_inventory(128,mutation)
        sealed['scores.f32le']['bytes']=16*16*12*4
        with self.assertRaises(ValueError):W.validate_sealed_inventory(128,sealed)
        for rows in (True,16.0,127,129):
            with self.assertRaises(ValueError):W.output_inventory(rows)

    def test_m128_dispatch_roles_use_original_parser(self):
        diag=load('cold_original_dispatch',ROOT/'candidates/qwen2_resident_matrix/raw_kv_native_qk_run/dispatch_diagnostic.py')
        self.assertEqual(diag._role('matmul','12x128x128:12x128x128'),'ATTENTION_SQUARE')
        empty=diag.parse_verbose(b'');m=dict(gate=types.SimpleNamespace(diagnostic=diag))
        self.assertEqual(D.check_dispatch(m,dict(bf16=empty,fp32=empty)),dict(bf16=empty,fp32=empty))
        with self.assertRaises(ValueError):D.check_dispatch(m,dict(bf16=empty))
        tree=ast.parse((HERE/'driver.py').read_bytes());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='check_dispatch')
        self.assertIn('ATTENTION_SQUARE=2',ast.unparse(node));self.assertNotIn('QK=1',ast.unparse(node))

    def test_plain_isolated_entry_probes(self):
        for filename in ('driver.py','verify.py'):
            done=subprocess.run([sys.executable,'-I','-B',str(HERE/filename),'--help'],capture_output=True,text=True,timeout=10)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertIn('--context-sha256',done.stdout)


class OwnedBoundaries(unittest.TestCase):
    def test_exact_owned_zero_and_nonzero(self):
        owner=load('cold_owned_commands',ROOT/D.BASE_REL/'owned_commands.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            result=owner.run(ROOT,[sys.executable,'-I','-B','-c','print("source-only child")'],cwd=out,
                log=out/'zero.log',end_ns=time.monotonic_ns()+8*10**9)
            self.assertEqual(result['observed_exit_code'],0);self.assertEqual(result['reaped_exit_code'],0)
            self.assertIs(result['cleanup_complete'],True)
            with self.assertRaises(ValueError):owner.run(ROOT,[sys.executable,'-I','-B','-c','raise SystemExit(7)'],cwd=out,
                log=out/'nonzero.log',end_ns=time.monotonic_ns()+8*10**9)

    def test_owned_timeout_and_descendant_cleanup(self):
        owner=load('cold_owned_timeout',ROOT/D.BASE_REL/'owned_commands.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);pidfile=out/'descendant.pid'
            program='import pathlib,subprocess,sys,time; p=subprocess.Popen([sys.executable,"-I","-B","-c","import time; time.sleep(60)"]); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)'
            with self.assertRaises((ValueError,TimeoutError,InterruptedError)):
                owner.run(ROOT,[sys.executable,'-I','-B','-c',program,str(pidfile)],cwd=out,
                    log=out/'timeout.log',end_ns=time.monotonic_ns()+7*10**9)
            self.assertTrue(pidfile.exists())
            pid=int(pidfile.read_text())
            self.assertFalse((Path('/proc')/str(pid)).exists(),'owned descendant not reaped')


if __name__=='__main__':unittest.main()
