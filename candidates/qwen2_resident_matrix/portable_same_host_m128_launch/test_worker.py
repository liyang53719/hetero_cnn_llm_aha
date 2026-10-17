"""Stdlib-only adversarial worker tests; no model/native/real-entry execution."""
import copy
import hashlib
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
from unittest import mock

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


W = load('cold_same_host_m128_worker', HERE / 'worker.py')
R = load('cold_same_host_m128_parent', HERE / 'run.py')
I = load('cold_same_host_m128_identity', HERE.parent / 'attention_packed_m128_same_host/identity.py')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def sha(raw): return hashlib.sha256(raw).hexdigest()


def digest(value, length=64):
    return type(value) is str and len(value) == length and all(c in '0123456789abcdef' for c in value)


def safe(path, limit=2*1024*1024):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('symlink')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError('type/alias/size')
    return path.read_bytes()


def write(path, value, *, replace=False):
    raw = encoded(value)
    with Path(path).open('wb' if replace else 'xb') as stream: stream.write(raw)
    return sha(raw)


projected_identity = I.terminal_identity


class WorkerTests(unittest.TestCase):
    def setUp(self):
        parent = mock.patch.object(os, 'getppid', return_value=4242)
        parent.start(); self.addCleanup(parent.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.origin, self.out = self.base/'origin', self.base/'out'
        self.origin.mkdir(); self.out.mkdir()
        self.source = self.out/'source128'; self.source.mkdir()
        (self.source/'.git').write_bytes(b'gitdir: /fake/repo/.git/worktrees/source128\n')
        (self.out/'producer128').mkdir()
        self.commit = 'a'*40
        self.host = dict(host_sha256='b'*64, boot_sha256='c'*64, machine='x86_64', system='Linux')
        self.ci = dict(commit=self.commit, run_id='123', run_attempt='1')
        self.nonce = 'd'*64
        self.runtime = {'python': '3.12.15', 'measured_fixture': True}
        self.L = types.SimpleNamespace(sha=sha, encoded=encoded, digest=digest,
            strict=lambda raw, limit=2*1024*1024: json.loads(raw), safe=safe,
            host=lambda: self.host, write_new=write, import_path_guard=mock.Mock())
        self.static = {'candidates/example.py': sha(b'# exact source\n')}
        contract = dict(schema=1, profile=W.PROFILE, git_head=self.commit,
            sources=self.static, scope='FRESH_M128_ASSIGNED27_ONLY')
        self.raws = {'candidates/example.py': b'# exact source\n', W.SOURCE_CONTRACT: encoded(contract)}
        self.sources = {name: sha(raw) for name, raw in self.raws.items()}
        for name, raw in self.raws.items():
            path=self.source/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        self.pins = dict(inputs={}, composed_sources=self.static)
        self.api = types.SimpleNamespace(read_context=R.read_context, validate_composition=R.validate_composition,
                                         load_pins=mock.Mock(return_value=self.pins))
        self.library = dict(origin_root=str(self.out/'m16/setup/tiny/source'),
            receipt=dict(path=str(self.out/'m16/setup/tiny/build/official_bf16_compile.json'), sha256='1'*64),
            binary=dict(path=str(self.out/'m16/setup/tiny/build/official_bf16_matrix_silu.so'), bytes=256, sha256='2'*64))
        self.m16 = dict(schema=1, profile='qwen2-fresh-same-host-m16-prerequisite-v1',
            status='VERIFIED_CURRENT_JOB_FULL_M16_SAME_ELF', parent_pid=os.getppid(), m16_root=str(self.out/'m16'),
            ci=self.ci, attempt_nonce=self.nonce, host_sha256=sha(encoded(self.host)),
            runtime_identity_sha256=sha(encoded(self.runtime)), library=self.library,
            source_manifest_sha256='6'*64, records={key:dict(sha256='7'*64) for key in
                ('producer_manifest','producer_qualification','actual','snapshot','child_result','full_receipt')},
            observed_full=dict(pid=3131, observed_exit_code=0, final_exit_code=0, owned_group_cleanup_complete=True),
            full_29_node_acceptance=False, m128_verdict_inherited=False, old_pass_inherited=False)
        self.producer_context = dict(profile='qwen2-fresh-same-host-m128-context-v1', parent_pid=os.getppid(),
            root=str(self.origin), workspace=str(self.out/'producer128'), upstream_workspace=str(self.out/'m16/setup/producer'),
            python=str(self.out/'m16/setup/venv/bin/python'), attempt_nonce=self.nonce, ci=self.ci, host=self.host, upstream={})
        self.producer = dict(rows=128, past_tokens=0, attempt_nonce=self.nonce, ci=self.ci, host=self.host,
            runtime_identity=self.runtime, source_manifest_sha256='3'*64, upstream={}, native=dict(result=dict(sha256='4'*64)))
        self.qualified = dict(schema=1, profile='qwen2-fresh-same-host-m128-producer-qualified-v1',
            status='PASS_FRESH_M128_PRODUCER', attempt_nonce=self.nonce, ci=self.ci,
            host_sha256=sha(encoded(self.host)), runtime_identity_sha256=sha(encoded(self.runtime)),
            producer_source_manifest_sha256='3'*64, verifier_receipt_sha256='5'*64,
            child_pid=3232, child_exit_code=0, owned_group_cleanup_complete=True,
            original_array_gate_revalidated=True, claims={key: False for key in W.CLAIMS})
        self.context = dict(schema=1, profile='same-host-m128-prepare-v1', parent_pid=os.getppid(),
            origin=str(self.origin), out=str(self.out), ci=self.ci, host=self.host, attempt_nonce=self.nonce,
            deadline_ns=time.monotonic_ns()+60_000_000_000)
        self.args = types.SimpleNamespace(mode='compose', commit=self.commit, context=self.out/'M128_PREPARE_CONTEXT.json')
        self.rebind()
        env=mock.patch.dict(os.environ, GITHUB_SHA=self.commit, GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')
        env.start(); self.addCleanup(env.stop)

    def rebind(self):
        """Refresh fixture byte bindings so semantic attacks reach semantic checks."""
        msha=write(self.out/'M16_PREREQUISITE.json', self.m16, replace=True)
        pointer=dict(path=str(self.out/'M16_PREREQUISITE.json'), sha256=msha)
        self.producer_context['upstream']['m16_prerequisite']=pointer
        csha=write(self.out/'M128_CONTEXT.json', self.producer_context, replace=True)
        self.producer.update(parent_context_sha256=csha, upstream=dict(m16_prerequisite=pointer))
        psha=write(self.out/'producer128/PRODUCER_M128.json', self.producer, replace=True)
        self.qualified.update(parent_context_sha256=csha, producer_manifest_sha256=psha)
        qsha=write(self.out/'M128_QUALIFICATION.json', self.qualified, replace=True)
        self.context.update(m16_prerequisite_sha256=msha, producer_context_sha256=csha, producer_receipt_sha256=qsha)
        self.args.context_sha256=write(self.args.context,self.context,replace=True)

    def prepared(self):
        write(self.out/'M128_COMPOSED.json', W.composition_value(self.L,self.sources,self.commit))
        self.manifest = dict(source_sha256=self.sources, source_manifest_sha256=sha(encoded(self.sources)),
            producer_origin=str(self.origin), producer_workspace=str(self.out/'producer128'),
            producer_manifest=dict(path=str(self.out/'producer128/PRODUCER_M128.json'),sha256=self.qualified['producer_manifest_sha256']),
            producer_receipt=dict(path=str(self.out/'M128_QUALIFICATION.json'),sha256=self.context['producer_receipt_sha256']),
            producer_context=dict(path=str(self.out/'M128_CONTEXT.json'),sha256=self.context['producer_context_sha256']),
            m16_prerequisite=dict(path=str(self.out/'M16_PREREQUISITE.json'),sha256=self.context['m16_prerequisite_sha256']),
            library=copy.deepcopy(self.library))
        self.C=types.SimpleNamespace(ROOT=self.source,snapshot=mock.Mock(return_value=self.sources),
            git_context=mock.Mock(return_value=dict(commit=self.commit)),authorize_run=mock.Mock())
        self.A=types.SimpleNamespace(read_manifest=mock.Mock(return_value=self.manifest),terminal_identity=projected_identity)
        self.order=[]
        self.entry=types.SimpleNamespace(configure_backend=mock.Mock(side_effect=lambda:self.order.append('configure')),
            run=mock.Mock(side_effect=lambda *args,**kwargs:self.order.append('run')))
        self.modules={W.PACKAGE+'.contract':self.C,W.PACKAGE+'.admission':self.A,W.PACKAGE+'.entry':self.entry}

    def run_ready(self):
        self.prepared()
        manifest_sha=write(self.out/'M128_ENTRY_MANIFEST.json',self.manifest)
        started=time.monotonic()
        self.context.pop('deadline_ns')
        self.context.update(profile='same-host-m128-run-v1',started=started,work_deadline=started+2424,
            outer_deadline=started+2430,entry_manifest_sha256=manifest_sha,source_manifest_sha256=sha(encoded(self.sources)))
        self.args.mode='run';self.args.context=self.out/'M128_RUN_CONTEXT.json'
        self.args.context_sha256=write(self.args.context,self.context)
        self.identity=projected_identity(self.manifest,self.producer,self.qualified,self.m16,manifest_sha)
        write(self.out/'M128_SEALED.json',W.sealed_value(self.L,self.context,self.sources,manifest_sha,self.identity))

    def patches(self): return mock.patch.multiple(W,import_root=mock.DEFAULT,imported_sources=mock.DEFAULT)

    def context_call(self): return W.context_check(self.api,self.L,self.args,self.origin,self.out)
    def run_call(self): return W.run(self.api,self.L,self.pins,self.args,self.origin,self.out,self.context,self.qualified)

    def test_cold_import_has_no_numerical_dependencies(self):
        self.assertFalse(any(n in sys.modules for n in ('torch','numpy','ctypes','transformers','safetensors')))

    def test_fresh_isolated_worker_import_and_cli_without_unittest_ambient(self):
        code=("import importlib.util,sys\npath=sys.argv[1]\n"
              "spec=importlib.util.spec_from_file_location('standalone_worker',path)\n"
              "module=importlib.util.module_from_spec(spec)\n"
              "exec(compile(open(path,'rb').read(),path,'exec'),module.__dict__)\n"
              "api=module.load_parent(module.HERE.parents[2])\n"
              "if not callable(api.read_context): raise RuntimeError('parent bootstrap')\n"
              "if not hasattr(importlib,'machinery'): raise RuntimeError('missing machinery')\n"
              "if any(n in sys.modules for n in ('unittest','torch','numpy','ctypes','transformers','safetensors')): raise RuntimeError('ambient import')\n"
              "module.main(['--help'])\n")
        for optimize in ([],['-O']):
            with self.subTest(optimize=optimize):
                result=subprocess.run([sys.executable,'-I','-B',*optimize,'-c',code,str(HERE/'worker.py')],capture_output=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr.decode())
                self.assertIn(b'{compose,seal,run}',result.stdout)

    def test_fresh_isolated_namespace_import_without_test_harness(self):
        code=("import hashlib,importlib.util,pathlib,sys,tempfile,types\n"
              "path=sys.argv[1]\n"
              "spec=importlib.util.spec_from_file_location('standalone_worker',path)\n"
              "module=importlib.util.module_from_spec(spec)\n"
              "exec(compile(open(path,'rb').read(),path,'exec'),module.__dict__)\n"
              "with tempfile.TemporaryDirectory() as temp:\n"
              " root=pathlib.Path(temp); (root/'candidates').mkdir(); leaf=root/'candidates/probe.py'\n"
              " raw=b'value = 128\\n'; leaf.write_bytes(raw); sources={'candidates/probe.py':hashlib.sha256(raw).hexdigest()}\n"
              " api=types.SimpleNamespace(import_path_guard=lambda *args:None,sha=lambda b:hashlib.sha256(b).hexdigest(),safe=lambda p,*args:p.read_bytes())\n"
              " module.import_root(api,root,sources)\n"
              " probe=importlib.import_module('candidates.probe')\n"
              " if probe.value != 128: raise RuntimeError('wrong source')\n"
              " module.imported_sources(api,root,sources)\n"
              " if any(n in sys.modules for n in ('unittest','torch','numpy','ctypes','transformers','safetensors')): raise RuntimeError('ambient import')\n"
              " print('PASS_FRESH_ISOLATED_NAMESPACE_IMPORT')\n")
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(HERE/'worker.py')],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(result.stdout,b'PASS_FRESH_ISOLATED_NAMESPACE_IMPORT\n')

    def test_fresh_real_main_rejects_nonprivate_runtime_before_source_import(self):
        code=("import importlib.util,pathlib,sys,tempfile\npath=sys.argv[1]\n"
              "spec=importlib.util.spec_from_file_location('standalone_worker',path)\n"
              "module=importlib.util.module_from_spec(spec)\n"
              "exec(compile(open(path,'rb').read(),path,'exec'),module.__dict__)\n"
              "with tempfile.TemporaryDirectory() as temp:\n"
              " out=pathlib.Path(temp)\n"
              " try:\n"
              "  module.main(['compose','--origin',str(module.HERE.parents[2]),'--out',str(out),'--context',str(out/'absent.json'),'--commit','a'*40,'--context-sha256','b'*64])\n"
              " except ValueError as error:\n"
              "  if 'interpreter' not in str(error) and 'virtual environment' not in str(error): raise\n"
              " else: raise RuntimeError('wrong runtime admitted')\n"
              " if any(n in sys.modules for n in ('unittest','candidates','scripts','torch','numpy','ctypes','transformers','safetensors')): raise RuntimeError('ambient source import')\n"
              " print('PASS_REAL_MAIN_FAILS_CLOSED_BEFORE_SOURCE_IMPORT')\n")
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(HERE/'worker.py')],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(result.stdout,b'PASS_REAL_MAIN_FAILS_CLOSED_BEFORE_SOURCE_IMPORT\n')

    def test_exact_context_acceptance(self):
        self.assertEqual(self.context_call(),(self.context,self.qualified))

    def test_context_rejects_foreign_parent_host_nonce_ci_and_paths(self):
        for change in (dict(parent_pid=1),dict(parent_pid=os.getppid()+1),dict(host={}),dict(attempt_nonce='0'*64),
                       dict(ci=dict(self.ci,commit='0'*40)),dict(origin=str(self.out)),dict(out=str(self.origin))):
            with self.subTest(change=change),mock.patch.object(self.api,'read_context',return_value=dict(self.context,**change)):
                with self.assertRaises((ValueError,KeyError)): self.context_call()

    def test_context_rejects_wrong_mode_path_hash_environment_and_expiry(self):
        for key,value in (('mode','run'),('context',self.out/'elsewhere.json'),('context_sha256','0'*64)):
            with self.subTest(key=key),mock.patch.object(self.args,key,value):
                with self.assertRaises((ValueError,FileNotFoundError)):self.context_call()
        for key,value in (('GITHUB_SHA','0'*40),('GITHUB_RUN_ID','999'),('GITHUB_RUN_ATTEMPT','2')):
            with self.subTest(key=key),mock.patch.dict(os.environ,{key:value}):
                with self.assertRaises(ValueError):self.context_call()
        with mock.patch.object(time,'monotonic_ns',return_value=self.context['deadline_ns']):
            with self.assertRaises(ValueError):self.context_call()

    def test_qualification_semantic_forgeries_rejected_even_with_current_hash(self):
        original=copy.deepcopy(self.qualified)
        changes=(dict(schema=True),dict(status='PASS_FRESH_M16_PRODUCER'),dict(child_pid=True),dict(child_exit_code=False),
            dict(child_exit_code=1),dict(owned_group_cleanup_complete=False),dict(original_array_gate_revalidated=False),
            dict(verifier_receipt_sha256='bad'),dict(runtime_identity_sha256='0'*64),dict(claims={}),
            dict(claims=dict(self.qualified['claims'],full_29_node_acceptance=True)),dict(unexpected=True))
        for change in changes:
            with self.subTest(change=change):
                self.qualified=dict(copy.deepcopy(original),**change);self.rebind()
                with self.assertRaises(ValueError):self.context_call()

    def test_current_producer_context_semantic_forgeries_rejected(self):
        original=copy.deepcopy(self.producer_context)
        for change in (dict(profile='historical'),dict(parent_pid=4243),dict(root='/old'),dict(workspace=str(self.out/'m16/setup/producer')),
                       dict(python='/usr/bin/python'),dict(upstream_workspace='/old'),dict(ci=dict(self.ci,run_attempt='2')),
                       dict(attempt_nonce='0'*64),dict(host={})):
            with self.subTest(change=change):
                self.producer_context=dict(copy.deepcopy(original),**change);self.rebind()
                with self.assertRaises(ValueError):self.context_call()

    def test_m16_prerequisite_semantic_forgeries_rejected(self):
        original=copy.deepcopy(self.m16)
        changes=(dict(schema=True),dict(profile='old'),dict(status='PASS'),dict(parent_pid=4243),dict(m16_root='/old/m16'),
            dict(attempt_nonce='0'*64),dict(host_sha256='0'*64),dict(runtime_identity_sha256='0'*64),
            dict(m128_verdict_inherited=True),dict(old_pass_inherited=True),dict(full_29_node_acceptance=True),
            dict(observed_full=dict(self.m16['observed_full'],observed_exit_code=False)),
            dict(observed_full=dict(self.m16['observed_full'],final_exit_code=1)),
            dict(observed_full=dict(self.m16['observed_full'],owned_group_cleanup_complete=False)))
        for change in changes:
            with self.subTest(change=change):
                self.m16=dict(copy.deepcopy(original),**change);self.rebind()
                with self.assertRaises(ValueError):self.context_call()

    def test_bound_metadata_substitution_is_rejected(self):
        for relative in ('M128_QUALIFICATION.json','M128_CONTEXT.json','M16_PREREQUISITE.json'):
            path=self.out/relative;original=path.read_bytes();path.write_bytes(b'{}\n')
            with self.subTest(relative=relative):
                with self.assertRaises(ValueError):self.context_call()
            path.write_bytes(original)

    def test_bound_metadata_aliases_and_nondict_are_rejected(self):
        path=self.out/'bound.json';write(path,[])
        with self.assertRaises(ValueError):W.read_bound(self.L,path,sha(path.read_bytes()))
        path.write_bytes(b'{}\n');other=self.out/'alias';os.link(path,other)
        with self.assertRaises(ValueError):W.read_bound(self.L,path,sha(path.read_bytes()))

    def test_directory_symlinks_and_relative_paths_rejected(self):
        alias=self.base/'alias';alias.symlink_to(self.source,target_is_directory=True)
        for path in (Path('relative'),self.base/'absent',alias,self.source/'..'/'source128'):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):W.directory(path)

    def overlay(self):
        overlay=self.out/'overlay128';overlay.mkdir()
        for name,raw in self.raws.items():
            path=overlay/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return overlay

    def test_copy_preserves_git_and_other_checkout_files(self):
        overlay=self.overlay();git=(self.source/'.git').read_bytes();(self.source/'untouched').write_bytes(b'untouched')
        W.copy_overlay(self.L,overlay,self.source,self.sources)
        self.assertEqual((self.source/'.git').read_bytes(),git);self.assertEqual((self.source/'untouched').read_bytes(),b'untouched')
        for name,raw in self.raws.items():self.assertEqual((self.source/name).read_bytes(),raw)

    def test_copy_into_genuine_detached_git_worktree_preserves_actual_commit(self):
        repo=self.base/'gitrepo';repo.mkdir()
        def git(*args,cwd=repo):
            return subprocess.run(['git',*map(str,args)],cwd=cwd,check=True,capture_output=True,timeout=10).stdout
        git('init');(repo/'unchanged.txt').write_bytes(b'committed source\n')
        git('add','unchanged.txt');git('-c','user.name=Source Test','-c','user.email=source-test@example.invalid','commit','-m','source fixture')
        commit=git('rev-parse','HEAD').decode().strip();target=self.out/'genuine128'
        git('worktree','add','--detach',target,commit)
        marker=(target/'.git').read_bytes();overlay=self.overlay()
        value=dict(schema=1,profile=W.PROFILE,git_head=commit,sources=self.static,scope='FRESH_M128_ASSIGNED27_ONLY')
        (overlay/W.SOURCE_CONTRACT).write_bytes(encoded(value))
        sources=dict(self.static,**{W.SOURCE_CONTRACT:sha(encoded(value))})
        W.copy_overlay(self.L,overlay,target,sources)
        self.assertEqual((target/'.git').read_bytes(),marker)
        self.assertEqual(git('rev-parse','HEAD',cwd=target).decode().strip(),commit)
        self.assertEqual(git('show','HEAD:unchanged.txt',cwd=target),b'committed source\n')
        self.assertEqual(R.validate_composition(self.L,self.pins,target,commit),sources)
        with self.assertRaises(ValueError):R.validate_composition(self.L,self.pins,target,'0'*40)

    def test_copy_rejects_extra_missing_mutated_source(self):
        overlay=self.overlay();extra=overlay/'extra.py';extra.write_bytes(b'x')
        with self.assertRaises(ValueError):W.copy_overlay(self.L,overlay,self.source,self.sources)
        extra.unlink();sample=overlay/'candidates/example.py';sample.write_bytes(b'mutated')
        with self.assertRaises(ValueError):W.copy_overlay(self.L,overlay,self.source,self.sources)
        sample.unlink()
        with self.assertRaises(ValueError):W.copy_overlay(self.L,overlay,self.source,self.sources)

    def test_copy_rejects_aliases_symlinks_and_fake_git(self):
        overlay=self.overlay();sample=self.source/'candidates/example.py';other=self.out/'alias';os.link(sample,other)
        with self.assertRaises(ValueError):W.copy_overlay(self.L,overlay,self.source,self.sources)
        other.unlink();sample.unlink();sample.symlink_to(overlay/'candidates/example.py')
        with self.assertRaises(ValueError):W.copy_overlay(self.L,overlay,self.source,self.sources)
        sample.unlink();sample.write_bytes(self.raws['candidates/example.py']);(self.source/'.git').write_bytes(b'fake')
        with self.assertRaises(ValueError):W.copy_overlay(self.L,overlay,self.source,self.sources)

    def test_composition_commit_specific_and_nonaccepting(self):
        result=W.composition_value(self.L,self.sources,self.commit)
        self.assertEqual(len(result),7);self.assertFalse(result['actual_chain_executed']);self.assertFalse(result['full_public_admission'])
        self.assertEqual(result['source_contract_sha256'],self.sources[W.SOURCE_CONTRACT])
        R.validate_composition(self.L,self.pins,self.source,self.commit)
        with self.assertRaises(ValueError):R.validate_composition(self.L,self.pins,self.source,'0'*40)
        write(self.out/'M128_COMPOSED.json',dict(result,actual_chain_executed=True))
        with self.assertRaises(ValueError):W.read_composition(self.api,self.L,self.pins,self.out,self.commit)

    def test_preexisting_namespace_or_source_root_rejected(self):
        for name in ('candidates','scripts','candidates.foreign','scripts.foreign'):
            with self.subTest(name=name),mock.patch.dict(sys.modules,{name:types.ModuleType(name)}):
                with self.assertRaises(ValueError):W.import_root(self.L,self.origin,{})
        with mock.patch.object(sys,'path',[str(self.origin)]):
            with self.assertRaises(ValueError):W.import_root(self.L,self.origin,{})

    def test_foreign_imported_namespace_or_unpinned_source_rejected(self):
        module=types.ModuleType('candidates.foreign');module.__file__=str(self.origin/'foreign.py')
        with mock.patch.dict(sys.modules,{'candidates.foreign':module}):
            with self.assertRaises(ValueError):W.imported_sources(self.L,self.source,self.sources)
            module.__file__=str(self.source/'unpinned.py')
            with self.assertRaises(ValueError):W.imported_sources(self.L,self.source,self.sources)
            del module.__file__;module.__path__=[str(self.origin)]
            with self.assertRaises(ValueError):W.imported_sources(self.L,self.source,self.sources)

    def test_compose_original_root_dynamic_commit_both_producer_packages(self):
        def prepare(destination,**kwargs):
            self.assertEqual(destination,self.out/'overlay128')
            self.assertEqual(kwargs,dict(git_head=self.commit,producer_package=self.origin/W.PRODUCER,
                                         producer_m128_package=self.origin/W.PRODUCER_M128))
            self.overlay();return W.composition_value(self.L,self.sources,self.commit)
        module=types.SimpleNamespace(ROOT=self.origin,compose=mock.Mock(side_effect=prepare))
        with self.patches() as patches,mock.patch.object(W.importlib,'import_module',return_value=module):
            W.compose(self.api,self.L,self.pins,self.args,self.origin,self.out,self.context,self.qualified)
            patches['import_root'].assert_called_once_with(self.L,self.origin,self.pins['inputs'])
        self.assertEqual(json.loads((self.out/'M128_COMPOSED.json').read_bytes()),W.composition_value(self.L,self.sources,self.commit))

    def test_seal_exact_current_job_arguments_and_admitted_identity(self):
        self.prepared();self.args.mode='seal'
        def seal(path,**kwargs):
            self.seal_kwargs=kwargs;manifest_sha=write(path,self.manifest)
            return path,manifest_sha,dict(terminal_identity=projected_identity(self.manifest,self.producer,self.qualified,self.m16,manifest_sha))
        self.A.seal_manifest=mock.Mock(side_effect=seal)
        with self.patches() as patches,mock.patch.object(W.importlib,'import_module',side_effect=self.modules.__getitem__):
            W.seal(self.api,self.L,self.pins,self.args,self.origin,self.out,self.context,self.qualified)
            patches['import_root'].assert_called_once_with(self.L,self.source,self.sources)
        self.assertEqual(self.seal_kwargs,dict(producer_origin=self.origin,producer_workspace=self.out/'producer128',
            producer_manifest_sha256=self.qualified['producer_manifest_sha256'],producer_receipt=self.out/'M128_QUALIFICATION.json',
            producer_receipt_sha256=self.context['producer_receipt_sha256'],producer_context=self.out/'M128_CONTEXT.json',
            producer_context_sha256=self.context['producer_context_sha256'],m16_prerequisite=self.out/'M16_PREREQUISITE.json',
            m16_prerequisite_sha256=self.context['m16_prerequisite_sha256']))
        sealed=json.loads((self.out/'M128_SEALED.json').read_bytes())
        self.assertEqual(sealed['terminal_identity_sha256'],sha(encoded(sealed['terminal_identity'])))
        self.assertEqual(sealed['m16_prerequisite_sha256'],self.context['m16_prerequisite_sha256'])

    def test_run_configures_once_then_exact_single_full128_entry(self):
        self.run_ready()
        with self.patches() as patches,mock.patch.object(W.importlib,'import_module',side_effect=self.modules.__getitem__):
            self.run_call();patches['import_root'].assert_called_once_with(self.L,self.source,self.sources)
        self.assertEqual(self.order,['configure','run']);self.entry.configure_backend.assert_called_once_with();self.entry.run.assert_called_once()
        args,kwargs=self.entry.run.call_args
        self.assertEqual(args,(self.out/'full_m128',));self.assertEqual(kwargs['manifest'],self.out/'M128_ENTRY_MANIFEST.json')
        self.assertEqual(kwargs['manifest_sha256'],self.context['entry_manifest_sha256'])
        self.assertEqual(kwargs['run_context'],dict(profile=W.PROFILE,attempt=1,pid=os.getpid(),parent_pid=os.getppid(),
            started=self.context['started'],work_deadline=self.context['started']+2424,outer_deadline=self.context['started']+2430,
            source_manifest_sha256=self.context['source_manifest_sha256'],producer_receipt_sha256=self.context['producer_receipt_sha256'],
            attempt_nonce=self.context['attempt_nonce'],m16_prerequisite_sha256=self.context['m16_prerequisite_sha256']))

    def test_manifest_or_seal_substitution_before_import_rejected(self):
        self.run_ready()
        for relative in ('M128_ENTRY_MANIFEST.json','M128_SEALED.json'):
            path=self.out/relative;raw=path.read_bytes();path.write_bytes(b'{}\n')
            with self.subTest(relative=relative),self.patches() as patches:
                with self.assertRaises(ValueError):self.run_call()
                patches['import_root'].assert_not_called()
            path.write_bytes(raw)

    def test_coherent_forged_terminal_identity_rejected_before_backend(self):
        self.run_ready();forged=copy.deepcopy(self.identity);forged['native_result_sha256']='0'*64
        write(self.out/'M128_SEALED.json',W.sealed_value(self.L,self.context,self.sources,self.context['entry_manifest_sha256'],forged),replace=True)
        with self.patches(),mock.patch.object(W.importlib,'import_module',side_effect=self.modules.__getitem__):
            with self.assertRaises(ValueError):self.run_call()
        self.entry.configure_backend.assert_not_called();self.entry.run.assert_not_called()

    def test_relabelled_m16_or_past_assets_rejected_before_identity(self):
        self.prepared()
        for key,value in (('rows',16),('rows',True),('past_tokens',1),('past_tokens',False)):
            with self.subTest(key=key,value=value):
                producer=dict(self.producer,**{key:value})
                psha=write(self.out/'producer128/PRODUCER_M128.json',producer,replace=True)
                qualified=dict(self.qualified,producer_manifest_sha256=psha)
                with self.assertRaises(ValueError):W.terminal_identity(self.L,self.A,self.out,self.context,qualified,self.manifest,'a'*64)

    def test_manifest_foreign_origin_old_pointer_or_changed_elf_rejected(self):
        self.run_ready();original=copy.deepcopy(self.manifest)
        changes=(dict(producer_origin='/old'),dict(producer_workspace='/old/producer128'),
            dict(producer_context=dict(path='/old/M128_CONTEXT.json',sha256=self.context['producer_context_sha256'])),
            dict(m16_prerequisite=dict(path='/old/M16_PREREQUISITE.json',sha256=self.context['m16_prerequisite_sha256'])),
            dict(library=dict(self.library,binary=dict(self.library['binary'],sha256='0'*64))))
        for change in changes:
            self.manifest.clear();self.manifest.update(copy.deepcopy(original));self.manifest.update(change)
            with self.subTest(change=change),self.patches(),mock.patch.object(W.importlib,'import_module',side_effect=self.modules.__getitem__):
                with self.assertRaises(ValueError):self.run_call()
        self.entry.configure_backend.assert_not_called();self.entry.run.assert_not_called()

    def test_unmodified_2424_2430_envelope_required(self):
        self.run_ready();self.context['work_deadline']+=1
        with self.patches(),mock.patch.object(W.importlib,'import_module',side_effect=self.modules.__getitem__):
            with self.assertRaises(ValueError):self.run_call()
        self.entry.configure_backend.assert_not_called();self.entry.run.assert_not_called()

    def test_backend_failure_propagates_without_numerical_retry(self):
        self.run_ready();self.entry.configure_backend.side_effect=ValueError('backend refused')
        with self.patches(),mock.patch.object(W.importlib,'import_module',side_effect=self.modules.__getitem__):
            with self.assertRaisesRegex(ValueError,'backend refused'):self.run_call()
        self.entry.run.assert_not_called()

    def test_entry_failure_propagates_without_retry(self):
        self.run_ready();self.entry.run.side_effect=ValueError('numeric failure')
        with self.patches(),mock.patch.object(W.importlib,'import_module',side_effect=self.modules.__getitem__):
            with self.assertRaisesRegex(ValueError,'numeric failure'):self.run_call()
        self.entry.run.assert_called_once()

    def test_postflight_source_or_context_drift_rejected(self):
        self.run_ready();self.C.snapshot.side_effect=[self.sources,{}]
        with self.patches(),mock.patch.object(W.importlib,'import_module',side_effect=self.modules.__getitem__):
            with self.assertRaises(ValueError):self.run_call()
        self.entry.run.assert_called_once()

    def test_runtime_exact_version_flags_and_same_m16_private_venv(self):
        good_flags=types.SimpleNamespace(isolated=1,optimize=0)
        with mock.patch.multiple(sys,version_info=(3,12,15),flags=good_flags,dont_write_bytecode=True,pycache_prefix=None,
                executable=str(self.out/'m16/setup/venv/bin/python'),prefix=str(self.out/'m16/setup/venv'),base_prefix='/base'):
            W.runtime(self.out)
            for key,value in (('version_info',(3,12,14)),('executable',str(self.out/'setup/venv/bin/python')),
                ('prefix',str(self.out/'other/venv')),('dont_write_bytecode',False),('pycache_prefix','/cache'),
                ('flags',types.SimpleNamespace(isolated=1,optimize=1)),('flags',types.SimpleNamespace(isolated=0,optimize=0))):
                with self.subTest(key=key,value=value),mock.patch.object(sys,key,value):
                    with self.assertRaises(ValueError):W.runtime(self.out)


if __name__ == '__main__': unittest.main(verbosity=2)
