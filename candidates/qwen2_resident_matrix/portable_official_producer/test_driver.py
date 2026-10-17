"""Cold source/control tests only: no weights, compiler, recipe ELF or forward."""
import argparse
import ast
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module

d = load(HERE/'driver.py', 'cold_fresh_driver')
o = load(HERE/'owned_commands.py', 'cold_owned_commands')

class ColdDriver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='producer-cold-')
        self.out = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def context(self):
        workspace = self.out/'producer'
        now = time.monotonic_ns(); end = now+60*10**9
        ci = dict(commit='a'*40, run_id='1', run_attempt='1')
        boot = Path('/proc/sys/kernel/random/boot_id').read_bytes().strip()
        value = dict(schema=1, profile='qwen2-fresh-same-host-producer-context-v1',
            parent_pid=os.getppid(), root=str(ROOT), workspace=str(workspace),
            created_ns=now, deadline_ns=end, attempt_nonce='b'*64, ci=ci,
            host=dict(host_sha256=d.sha(os.uname().nodename.encode()), boot_sha256=d.sha(boot),machine='x86_64',system='Linux'),
            driver_sha256=d.IMPORTED_DRIVER_SHA, source_lock_sha256=d.verify_sources(ROOT)[1],tiny_result_sha256='c'*64)
        return workspace,end,ci,value
    def admit(self,value,workspace,end,ci):
        path=self.out/'PRODUCER_CONTEXT.json';path.write_bytes(d.encoded(value))
        return d.launch_context(ROOT,workspace,end,'b'*64,ci,path,d.sha(path.read_bytes()))
    def test_01_import_remains_cold(self):
        code='''import importlib.util,sys
from pathlib import Path
p=Path(sys.argv[1]);s=importlib.util.spec_from_file_location('fresh_driver',p);m=importlib.util.module_from_spec(s)
exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__)
assert not ({'numpy','torch','ctypes'} & set(sys.modules))
print('PASS_COLD_DRIVER_IMPORT')'''
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(HERE/'driver.py')],capture_output=True,text=True,check=True,timeout=10)
        self.assertEqual(result.stdout.strip(),'PASS_COLD_DRIVER_IMPORT')
    def test_02_strict_json_rejections(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):d.strict(raw)
    def test_03_source_lock_is_complete_and_exact(self):
        sources,lock=d.verify_sources(ROOT)
        self.assertEqual(len(sources),67)
        for name in ('cgra_sfu','command','config','kv_engine','matrix_engine','scheduler','dtypes','abi_validation'):
            self.assertIn('src/heteronpu/'+name+'.py',sources)
        self.assertEqual(lock,d.IMPORTED_LOCK_SHA)
    def test_04_source_postflight_equality(self):
        raw=(HERE/'source-lock.json').read_bytes()
        value=d.strict(raw);value['sources'].pop(next(iter(value['sources'])))
        old=Path.read_bytes
        def altered(path):return d.encoded(value) if path==HERE/'source-lock.json' else old(path)
        with patch.object(Path,'read_bytes',altered),self.assertRaisesRegex(ValueError,'source lock drift'):
            d.verify_sources(ROOT)
    def test_05_workspace_admission(self):
        self.assertEqual(d.workspace_path(ROOT,self.out/'producer'),self.out/'producer')
        for value in (ROOT,ROOT/'work',ROOT.parent,ROOT/'..'/'escape'):
            with self.subTest(value=value),self.assertRaises(ValueError):d.workspace_path(ROOT,value)
        link=self.out/'link';link.symlink_to(self.out,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symlink'):d.workspace_path(ROOT,link/'producer')
    def test_06_bad_workspace_has_no_side_effect(self):
        out=ROOT/'forbidden-cold-producer-work'
        with patch.object(d,'collect_fresh_payload',side_effect=AssertionError('acquisition called')):
            with self.assertRaisesRegex(ValueError,'disjoint'):
                d.produce_m16(ROOT,out,time.monotonic_ns()+10**9,attempt_nonce='b'*64,ci={},context_path=self.out/'missing',context_sha256='0'*64)
        self.assertFalse(out.exists())
    def test_07_artifact_aliases_and_traversal(self):
        path=self.out/'one';path.write_bytes(b'cold')
        rec=d.record(self.out,path);self.assertEqual(d.resolve(self.out,rec),path)
        with self.assertRaises(ValueError):d.record(self.out,self.out/'sub'/'..'/'one')
        alias=self.out/'alias';os.link(path,alias)
        with self.assertRaises(ValueError):d.record(self.out,path)
        alias.unlink(); alias.symlink_to(path)
        with self.assertRaises(ValueError):d.record(self.out,alias)
    def test_08_valid_context_is_metadata_only(self):
        w,end,ci,v=self.context();self.assertEqual(self.admit(v,w,end,ci),v);self.assertFalse(w.exists())
    def test_09_context_rejections(self):
        w,end,ci,v=self.context()
        for field,new in [('parent_pid',os.getpid()),('attempt_nonce','d'*64),('deadline_ns',end+1),('source_lock_sha256','d'*64),('driver_sha256','d'*64),('tiny_result_sha256','d'),('schema',True),('root','/incorrect')]:
            wrong=copy.deepcopy(v);wrong[field]=new
            with self.subTest(field=field),self.assertRaises(ValueError):self.admit(wrong,w,end,ci)
        wrong=copy.deepcopy(v);wrong['host']['boot_sha256']='d'*64
        with self.assertRaises(ValueError):self.admit(wrong,w,end,ci)
        wrong=copy.deepcopy(v);wrong['ci']['run_id']=True
        with self.assertRaises(ValueError):self.admit(wrong,w,end,wrong['ci'])
    def test_10_context_hash_and_location(self):
        w,end,ci,v=self.context();path=self.out/'PRODUCER_CONTEXT.json';path.write_bytes(d.encoded(v))
        with self.assertRaises(ValueError):d.launch_context(ROOT,w,end,'b'*64,ci,path,'0'*64)
        with self.assertRaises(ValueError):d.launch_context(ROOT,w,end,'b'*64,ci,self.out/'other.json',d.sha(path.read_bytes()))
    def test_11_bounded_restores_timer_handlers(self):
        signals=(signal.SIGALRM,signal.SIGTERM,signal.SIGINT);old={s:signal.getsignal(s) for s in signals}
        with self.assertRaises(TimeoutError):
            with d.bounded(time.monotonic_ns()+20_000_000):time.sleep(.1)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.));self.assertEqual(old,{s:signal.getsignal(s) for s in signals})
    def test_12_owned_import_exact_despite_cached_contract(self):
        previous=sys.modules.get('contract');sentinel=types.ModuleType('contract');sys.modules['contract']=sentinel
        try:
            before=list(sys.path);helper=o.load_owner(ROOT)
            self.assertIs(sys.modules['contract'],sentinel);self.assertEqual(sys.path,before)
            self.assertEqual(Path(helper.c.__file__),ROOT/o.HELPER.replace('run_ci.py','contract.py'))
        finally:
            if previous is None:sys.modules.pop('contract',None)
            else:sys.modules['contract']=previous
    def test_13_exact_exec_and_observed_cleanup(self):
        code='import os,signal;print(os.getpid());print(len(signal.pthread_sigmask(signal.SIG_BLOCK,set()) & {signal.SIGALRM,signal.SIGTERM,signal.SIGINT}))'
        result=o.run(ROOT,[sys.executable,'-I','-B','-c',code],cwd=self.out,log=self.out/'exec.log',end_ns=time.monotonic_ns()+10*10**9)
        self.assertEqual((self.out/'exec.log').read_text().splitlines(),[str(result['ownership']['pid']),'0'])
        self.assertEqual((result['observed_exit_code'],result['reaped_exit_code'],result['cleanup_complete']),(0,0,True))
        self.assertFalse(Path('/proc',str(result['ownership']['pid'])).exists())
    def test_14_nonzero_child_rejected_and_reaped(self):
        pid=self.out/'pid'
        code='import os,pathlib;pathlib.Path('+repr(str(pid))+').write_text(str(os.getpid()));raise SystemExit(7)'
        with self.assertRaisesRegex(ValueError,'failed'):
            o.run(ROOT,[sys.executable,'-I','-B','-c',code],cwd=self.out,log=self.out/'nonzero.log',end_ns=time.monotonic_ns()+10*10**9)
        self.assertFalse(Path('/proc',pid.read_text()).exists())
    def test_15_timeout_child_rejected_and_reaped(self):
        pid=self.out/'pid';code='import os,pathlib,time;pathlib.Path('+repr(str(pid))+').write_text(str(os.getpid()));time.sleep(30)'
        with self.assertRaises((TimeoutError,InterruptedError)):
            o.run(ROOT,[sys.executable,'-I','-B','-c',code],cwd=self.out,log=self.out/'timeout.log',end_ns=time.monotonic_ns()+6_200_000_000)
        self.assertFalse(Path('/proc',pid.read_text()).exists());self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
    def test_16_interrupted_child_rejected_and_reaped(self):
        pid=self.out/'pid';code='import os,pathlib,time,signal;pathlib.Path('+repr(str(pid))+').write_text(str(os.getpid()));os.kill(os.getppid(),signal.SIGTERM);time.sleep(30)'
        with self.assertRaises(InterruptedError):
            o.run(ROOT,[sys.executable,'-I','-B','-c',code],cwd=self.out,log=self.out/'interrupt.log',end_ns=time.monotonic_ns()+10*10**9)
        self.assertFalse(Path('/proc',pid.read_text()).exists());self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
    def test_17_owned_invalid_launch_does_not_execute(self):
        for argv,end in [(['relative'],time.monotonic_ns()+10**10),([sys.executable],True),([sys.executable],time.monotonic_ns()+10**9)]:
            with self.subTest(argv=argv,end=end),self.assertRaises((ValueError,TimeoutError)):
                o.run(ROOT,argv,cwd=self.out,log=self.out/'invalid.log',end_ns=end)
        self.assertFalse((self.out/'invalid.log').exists())
    def test_18_original_phase_caps_and_revalidation(self):
        tree=ast.parse((HERE/'driver.py').read_bytes());functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
        run=ast.unparse(functions['run_m16']);self.assertIn('phase_end(end_ns, 60)',run)
        self.assertIn('validate_small(m, native, workspace, identity)',run)
        self.assertIn('tokens=16',run);self.assertIn('threads=4',run);self.assertIn('carried=False',run)
        self.assertEqual(d.CLAIMS,dict(actual_chain_executed=False,full_public_admission=False,full_29_node_acceptance=False,rtl_execution=False,hardware_recipe_acceptance=False,old_pass_inherited=False))
    def test_19_source_preparation_exact_runner(self):
        m,sources,_=d.modules(ROOT);out=self.out/'generated'
        result=m['prepare'].prepare(out)
        self.assertEqual(result['generated_module_sha256'],m['patch'].INTERMEDIATE_GENERATED_MODULE_SHA256)
        m['patch'].apply_dispatch_patch(out,{'sources':sources})
        self.assertEqual(m['gate'].verify_runner(ROOT,out/m['qk'].ORIGINAL),d.RUNNER_SHA)
        self.assertNotIn('torch',sys.modules)
        for module in list(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).resolve().is_relative_to(ROOT):
                rel=Path(path).resolve().relative_to(ROOT).as_posix()
                self.assertTrue(rel in sources or rel.endswith('/test_driver.py') or rel.endswith('/driver.py'),rel)
        self.assertEqual(m['capture'].fenv_snapshot(),dict(status='OBSERVED',x87_round=0,sse_round=0,ftz=False,daz=False))
    def test_20_sequential_reduced_source_regeneration(self):
        m,_,_=d.modules(ROOT);fixture=self.out/'git-fixture';fixture.mkdir()
        name='chisel/continuous_prefill/tests/qwen2_block.cpp';target=fixture/name;target.parent.mkdir(parents=True);target.write_bytes((ROOT/name).read_bytes())
        env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_AUTHOR_NAME='Cold Test',GIT_AUTHOR_EMAIL='cold@example.invalid',GIT_COMMITTER_NAME='Cold Test',GIT_COMMITTER_EMAIL='cold@example.invalid')
        for argv in (['git','init','-q'],['git','add',name],['git','commit','-qm','Source-only cold fixture']):subprocess.run(argv,cwd=fixture,env=env,check=True,capture_output=True,timeout=10)
        with patch.dict(os.environ,{'GIT_DIR':str(fixture/'.git'),'GIT_WORK_TREE':str(fixture)}):
            original,header,_=m['builder'].regenerate_sources(ROOT)
        reduced,audit=m['builder'].transform(original,(ROOT/m['builder'].PROFILE_REL).read_bytes())
        self.assertEqual(d.sha(original),m['assets'].CPP_SHA256['sequential'])
        self.assertEqual(d.sha(reduced),m['assets'].CPP_SHA256['reduced'])
        self.assertEqual(d.sha(header),m['assets'].HEADER_SHA256);self.assertTrue(audit['all_other_source_byte_exact'])
        self.assertEqual(len(m['workload'].output_inventory(16)),22)
        self.assertNotIn('torch',sys.modules)
    def test_21_bytecode_and_initializer_rejected(self):
        target=ROOT/'scripts/qwen2_layer0_payload.py'
        original=Path.glob
        def bytecode(path,pattern):
            return iter([self.out/'stale.pyc']) if path==target.parent/'__pycache__' and pattern==target.stem+'.*.pyc' else original(path,pattern)
        with patch.object(Path,'glob',bytecode),self.assertRaisesRegex(ValueError,'bytecode cache'):
            d.modules(ROOT)
        initializer=ROOT/'candidates/__init__.py';original_exists=Path.exists
        def exists(path):return True if path==initializer else original_exists(path)
        with patch.object(Path,'exists',exists),self.assertRaisesRegex(ValueError,'unpinned package initializer'):
            d.modules(ROOT)


    def scalar_entry_boundary(self,workspace,observe):
        """Execute the actual per-role prelaunch prefix, never the numerical phase.

        The AST is copied directly from build_scalar_references through its
        owned-command call. Only that owner is substituted with an observer;
        no candidate binary, payload, compiler or model operation is invoked.
        This is an entry-boundary test, not a full producer/numerical test.
        """
        tree=ast.parse((HERE/'driver.py').read_bytes())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_scalar_references')
        loops=[n for n in function.body if isinstance(n,ast.For) and
               isinstance(n.target,ast.Name) and n.target.id=='role' and
               ast.literal_eval(n.iter)==('sequential','reduced')]
        self.assertEqual(len(loops),1)
        loop=copy.deepcopy(loops[0])
        calls=[i for i,n in enumerate(loop.body) if isinstance(n,ast.Assign) and
               isinstance(n.value,ast.Call) and ast.unparse(n.value.func)=="m['owner'].run"]
        self.assertEqual(len(calls),1)
        loop.body=loop.body[:calls[0]+1]
        loop.orelse=[]
        prefix=ast.Module(body=[loop],type_ignores=[])
        namespace=dict(workspace=workspace,ro=workspace/'readonly',root=ROOT,
            m={'owner':types.SimpleNamespace(run=observe)},phase_end=d.phase_end,
            end_ns=time.monotonic_ns()+60*10**9)
        exec(compile(ast.fix_missing_locations(prefix),str(HERE/'driver.py'),'exec'),namespace)

    def test_22_scalar_prelaunch_creates_fresh_private_directories(self):
        workspace=self.out/'scalar_boundary';workspace.mkdir()
        for role in ('sequential','reduced'):(workspace/role).mkdir()
        (workspace/'readonly').mkdir()
        seen=[]
        def observe(root,argv,*,cwd,log,end_ns):
            role=('sequential','reduced')[len(seen)]
            out=workspace/role;raw=out/'raw_stages';empty=out/'empty_cache.f32le'
            self.assertEqual(root,ROOT)
            self.assertEqual(argv,[str(out/'candidate'),str(workspace/'readonly/readonly_arena.f32le'),
                                  '16',str(raw),'0',str(empty),str(empty)])
            self.assertEqual(cwd,out);self.assertEqual(log,out/'stdout.log')
            self.assertIs(type(end_ns),int)
            self.assertTrue(raw.is_dir());self.assertFalse(raw.is_symlink())
            self.assertEqual(list(raw.iterdir()),[])
            self.assertEqual(raw.stat().st_mode&0o777,0o700)
            self.assertEqual(empty.read_bytes(),b'')
            self.assertFalse((out/'candidate').exists())
            seen.append(role)
            return {'control_only_observation':True}
        old_mask=os.umask(0o022)
        try:self.scalar_entry_boundary(workspace,observe)
        finally:os.umask(old_mask)
        self.assertEqual(seen,['sequential','reduced'])
        self.assertNotEqual((workspace/'sequential/raw_stages').stat().st_ino,
                            (workspace/'reduced/raw_stages').stat().st_ino)

    def test_23_scalar_prelaunch_rejects_existing_directory_file_symlink(self):
        for role in ('sequential','reduced'):
            for kind in ('directory','file','symlink'):
                with self.subTest(role=role,kind=kind):
                    workspace=self.out/(role+'_'+kind);workspace.mkdir()
                    for name in ('sequential','reduced'):(workspace/name).mkdir()
                    (workspace/'readonly').mkdir()
                    raw=workspace/role/'raw_stages'
                    if kind=='directory':raw.mkdir()
                    elif kind=='file':raw.write_bytes(b'existing-control-sentinel')
                    else:
                        target=workspace/'external_target';target.mkdir()
                        (target/'sentinel').write_bytes(b'do-not-follow')
                        raw.symlink_to(target,target_is_directory=True)
                    before=raw.lstat();seen=[]
                    def observe(root,argv,*,cwd,log,end_ns):
                        seen.append(cwd.name)
                        return {'control_only_observation':True}
                    with self.assertRaises(FileExistsError):self.scalar_entry_boundary(workspace,observe)
                    self.assertEqual(seen,[] if role=='sequential' else ['sequential'])
                    after=raw.lstat()
                    self.assertEqual((before.st_dev,before.st_ino,before.st_mode),
                                     (after.st_dev,after.st_ino,after.st_mode))
                    if kind=='directory':self.assertEqual(list(raw.iterdir()),[])
                    elif kind=='file':self.assertEqual(raw.read_bytes(),b'existing-control-sentinel')
                    else:
                        self.assertTrue(raw.is_symlink())
                        self.assertEqual((target/'sentinel').read_bytes(),b'do-not-follow')

if __name__=='__main__':unittest.main(verbosity=2)
