"""Stdlib-only adversarial worker tests; never import models or native code."""
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


W = load('cold_same_host_worker', HERE / 'worker.py')
R = load('cold_same_host_parent', HERE / 'run.py')


def safe(path, limit=2*1024*1024):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('symlink')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError('type/alias/size')
    return path.read_bytes()


def write(path, value):
    raw = R.encoded(value)
    with Path(path).open('xb') as stream:
        stream.write(raw)
    return R.sha(raw)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        parent = mock.patch.object(os, 'getppid', return_value=4242)
        parent.start()
        self.addCleanup(parent.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.origin = self.base / 'origin'
        self.out = self.base / 'out'
        self.origin.mkdir()
        self.out.mkdir()
        self.source = self.out / 'source'
        self.source.mkdir()
        (self.source / '.git').write_bytes(b'gitdir: /fake/repo/.git/worktrees/source\n')
        (self.out / 'setup').mkdir()
        self.commit = 'a'*40
        self.host = dict(host_sha256='b'*64, boot_sha256='c'*64, machine='x86_64', system='Linux')
        self.L = types.SimpleNamespace(sha=R.sha, encoded=R.encoded, digest=R.digest,
            strict=lambda raw, limit=2*1024*1024: json.loads(raw), safe=safe,
            host=lambda: self.host, write_new=write, import_path_guard=mock.Mock())
        self.static = {'candidates/example.py': R.sha(b'# exact source\n')}
        contract = dict(schema=1, profile=W.PROFILE, git_head=self.commit,
            sources=self.static, scope='FRESH_M16_ASSIGNED27_ONLY')
        self.raws = {'candidates/example.py': b'# exact source\n', W.SOURCE_CONTRACT: R.encoded(contract)}
        self.sources = {name: R.sha(raw) for name, raw in self.raws.items()}
        for name, raw in self.raws.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.pins = dict(inputs={}, composed_sources=self.static)
        self.api = types.SimpleNamespace(read_context=R.read_context,
            validate_composition=lambda L, pins, source, commit: R.validate_composition(L, pins, source, commit),
            load_pins=mock.Mock(return_value=self.pins))
        self.qualified = dict(schema=1, profile='qwen2-fresh-same-host-m16-producer-qualified-v1',
            status='PASS_FRESH_M16_PRODUCER', attempt_nonce='d'*64,
            producer_manifest_sha256='e'*64, ci=dict(commit=self.commit, run_id='123', run_attempt='1'),
            host_sha256=R.sha(R.encoded(self.host)), child_exit_code=0,
            owned_group_cleanup_complete=True, producer_native_gate_validated=True,
            fresh_tiny_result_sha256='f'*64)
        qsha = write(self.out / 'setup/QUALIFICATION.json', self.qualified)
        self.context = dict(schema=1, profile='same-host-m16-prepare-v1', parent_pid=os.getppid(),
            origin=str(self.origin), out=str(self.out), ci=self.qualified['ci'], host=self.host,
            attempt_nonce=self.qualified['attempt_nonce'], producer_receipt_sha256=qsha,
            deadline_ns=time.monotonic_ns()+60_000_000_000)
        self.args = types.SimpleNamespace(mode='compose', commit=self.commit,
            context=self.out / 'PREPARE_CONTEXT.json', context_sha256=write(self.out / 'PREPARE_CONTEXT.json', self.context))
        self.env = mock.patch.dict(os.environ, GITHUB_SHA=self.commit, GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')
        self.env.start()
        self.addCleanup(self.env.stop)

    def prepared(self):
        write(self.out / 'COMPOSED.json', W.composition_value(self.L, self.sources, self.commit))
        tiny_contract = self.origin / W.TINY / 'input-contract.json'
        tiny_contract.parent.mkdir(parents=True)
        tiny_contract.write_bytes(b'{}\n')
        self.manifest = dict(source_sha256=self.sources, source_manifest_sha256=R.sha(R.encoded(self.sources)),
            producer_workspace=str(self.out / 'setup/producer'),
            producer_manifest=dict(path=str(self.out / 'setup/producer/PRODUCER_M16.json'), sha256='e'*64),
            producer_receipt=dict(path=str(self.out / 'setup/QUALIFICATION.json'), sha256=self.context['producer_receipt_sha256']),
            tiny=dict(workspace=str(self.out / 'setup/tiny'),
                result=dict(path=str(self.out / 'setup/tiny/result.json'), sha256='f'*64),
                input_contract=dict(path=str(tiny_contract), sha256=R.sha(tiny_contract.read_bytes()))),
            library=dict(origin_root=str(self.out / 'setup/tiny/source'),
                receipt=dict(path=str(self.out / 'setup/tiny/build/official_bf16_compile.json'), sha256='1'*64),
                binary=dict(path=str(self.out / 'setup/tiny/build/official_bf16_matrix_silu.so'))))
        self.C = types.SimpleNamespace(ROOT=self.source, snapshot=mock.Mock(return_value=self.sources),
            git_context=mock.Mock(return_value=dict(commit=self.commit)), authorize_run=mock.Mock())
        self.A = types.SimpleNamespace(read_manifest=mock.Mock(return_value=self.manifest))
        self.order = []
        self.entry = types.SimpleNamespace(configure_backend=mock.Mock(side_effect=lambda: self.order.append('configure')),
            run=mock.Mock(side_effect=lambda *args, **kwargs: self.order.append('run')))
        self.modules = {W.PACKAGE+'.contract': self.C, W.PACKAGE+'.admission': self.A,
            W.PACKAGE+'.entry': self.entry}

    def run_ready(self):
        self.prepared()
        manifest_sha = write(self.out / 'ENTRY_MANIFEST.json', self.manifest)
        started = time.monotonic()
        self.context = {k: v for k, v in self.context.items() if k != 'deadline_ns'}
        self.context.update(profile='same-host-m16-run-v1', started=started, work_deadline=started+924,
            outer_deadline=started+930, entry_manifest_sha256=manifest_sha,
            source_manifest_sha256=R.sha(R.encoded(self.sources)))
        self.args.mode = 'run'
        self.args.context = self.out / 'RUN_CONTEXT.json'
        self.args.context_sha256 = write(self.args.context, self.context)
        write(self.out / 'SEALED.json', W.sealed_value(self.L, self.context, self.sources, manifest_sha))

    def patches(self):
        return mock.patch.multiple(W, import_root=mock.DEFAULT, imported_sources=mock.DEFAULT)

    def test_cold_import_has_no_numerical_dependencies(self):
        self.assertFalse(any(name in sys.modules for name in ('torch', 'numpy', 'ctypes', 'transformers', 'safetensors')))

    def test_fresh_cold_worker_import_supplies_machinery_without_test_harness(self):
        code = ("import importlib.util,sys\n"
                "path=sys.argv[1]\n"
                "spec=importlib.util.spec_from_file_location('standalone_worker',path)\n"
                "module=importlib.util.module_from_spec(spec)\n"
                "exec(compile(open(path,'rb').read(),path,'exec'),module.__dict__)\n"
                "if not hasattr(importlib,'machinery'): raise RuntimeError('missing machinery')\n"
                "if any(n in sys.modules for n in ('torch','numpy','ctypes','transformers','safetensors')): raise RuntimeError('numeric import')\n")
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(HERE/'worker.py')],
            capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_exact_context_acceptance(self):
        value, qualified = W.context_check(self.api, self.L, self.args, self.origin, self.out)
        self.assertEqual(value, self.context)
        self.assertEqual(qualified, self.qualified)

    def test_context_rejects_foreign_parent_host_nonce_ci_and_paths(self):
        changes = [dict(parent_pid=os.getppid()+1), dict(host={}), dict(attempt_nonce='0'*64),
            dict(ci=dict(commit='0'*40, run_id='123', run_attempt='1')), dict(origin=str(self.out))]
        for change in changes:
            with self.subTest(change=change):
                value = dict(self.context, **change)
                with mock.patch.object(self.api, 'read_context', return_value=value):
                    with self.assertRaises((ValueError, KeyError)):
                        W.context_check(self.api, self.L, self.args, self.origin, self.out)

    def test_context_rejects_wrong_mode_path_hash_environment_and_expiry(self):
        for name, changed in [('mode', 'run'), ('context', self.out/'elsewhere.json'), ('context_sha256', '0'*64)]:
            with self.subTest(name=name), mock.patch.object(self.args, name, changed):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    W.context_check(self.api, self.L, self.args, self.origin, self.out)
        with mock.patch.dict(os.environ, GITHUB_RUN_ID='999'):
            with self.assertRaises(ValueError):
                W.context_check(self.api, self.L, self.args, self.origin, self.out)
        with mock.patch.object(R.time, 'monotonic_ns', return_value=self.context['deadline_ns']):
            with self.assertRaises(ValueError):
                W.context_check(self.api, self.L, self.args, self.origin, self.out)

    def test_qualification_substitution_is_rejected(self):
        (self.out/'setup/QUALIFICATION.json').write_bytes(b'{}\n')
        with self.assertRaises(ValueError):
            W.context_check(self.api, self.L, self.args, self.origin, self.out)

    def test_directory_symlinks_and_relative_paths_are_rejected(self):
        for path in (Path('relative'), self.base/'absent'):
            with self.assertRaises(ValueError):
                W.directory(path)
        alias = self.base/'alias'
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            W.directory(alias)

    def overlay(self):
        overlay = self.out/'overlay'
        overlay.mkdir()
        for name, raw in self.raws.items():
            path = overlay/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        return overlay

    def test_copy_preserves_git_and_other_checkout_files(self):
        overlay = self.overlay()
        git = (self.source/'.git').read_bytes()
        (self.source/'untouched').write_bytes(b'untouched')
        W.copy_overlay(self.L, overlay, self.source, self.sources)
        self.assertEqual((self.source/'.git').read_bytes(), git)
        self.assertEqual((self.source/'untouched').read_bytes(), b'untouched')
        for name, raw in self.raws.items():
            self.assertEqual((self.source/name).read_bytes(), raw)

    def test_copy_rejects_extra_missing_and_mutated_source(self):
        overlay = self.overlay()
        extra = overlay/'extra.py'
        extra.write_bytes(b'x')
        with self.assertRaises(ValueError): W.copy_overlay(self.L, overlay, self.source, self.sources)
        extra.unlink()
        sample = overlay/'candidates/example.py'
        sample.write_bytes(b'mutated')
        with self.assertRaises(ValueError): W.copy_overlay(self.L, overlay, self.source, self.sources)
        sample.unlink()
        with self.assertRaises(ValueError): W.copy_overlay(self.L, overlay, self.source, self.sources)

    def test_copy_rejects_aliases_and_symlinks(self):
        overlay = self.overlay()
        sample = self.source/'candidates/example.py'
        other = self.out/'alias'
        os.link(sample, other)
        with self.assertRaises(ValueError): W.copy_overlay(self.L, overlay, self.source, self.sources)
        other.unlink()
        sample.unlink()
        sample.symlink_to(overlay/'candidates/example.py')
        with self.assertRaises(ValueError): W.copy_overlay(self.L, overlay, self.source, self.sources)

    def test_copy_rejects_fake_worktree_before_mutation(self):
        overlay = self.overlay()
        (self.source/'.git').write_bytes(b'not a linked worktree')
        with self.assertRaises(ValueError): W.copy_overlay(self.L, overlay, self.source, self.sources)

    def test_composition_is_commit_specific_and_acyclic(self):
        result = W.composition_value(self.L, self.sources, self.commit)
        self.assertEqual(len(result), 7)
        self.assertFalse(result['actual_chain_executed'])
        self.assertFalse(result['full_public_admission'])
        self.assertEqual(result['source_contract_sha256'], self.sources[W.SOURCE_CONTRACT])
        R.validate_composition(self.L, self.pins, self.source, self.commit)
        with self.assertRaises(ValueError): R.validate_composition(self.L, self.pins, self.source, '0'*40)

    def test_receipt_mismatch_is_rejected(self):
        write(self.out/'COMPOSED.json', dict(W.composition_value(self.L, self.sources, self.commit), actual_chain_executed=True))
        with self.assertRaises(ValueError): W.read_composition(self.api, self.L, self.pins, self.out, self.commit)

    def test_preexisting_namespace_or_source_root_is_rejected(self):
        with mock.patch.dict(sys.modules, {'candidates.foreign': types.ModuleType('foreign')}):
            with self.assertRaises(ValueError): W.import_root(self.L, self.origin, {})
        with mock.patch.object(sys, 'path', [str(self.origin)]):
            with self.assertRaises(ValueError): W.import_root(self.L, self.origin, {})

    def test_foreign_imported_namespace_is_rejected(self):
        module = types.ModuleType('candidates.foreign')
        module.__file__ = str(self.origin/'foreign.py')
        with mock.patch.dict(sys.modules, {'candidates.foreign': module}):
            with self.assertRaises(ValueError): W.imported_sources(self.L, self.source, self.sources)
        del module.__file__
        module.__path__ = [str(self.origin)]
        with mock.patch.dict(sys.modules, {'candidates.foreign': module}):
            with self.assertRaises(ValueError): W.imported_sources(self.L, self.source, self.sources)

    def test_compose_uses_original_root_and_dynamic_commit(self):
        def prepare(destination, **kwargs):
            self.assertEqual(destination, self.out/'overlay')
            self.assertEqual(kwargs, dict(git_head=self.commit, producer_package=self.origin/W.PRODUCER))
            self.overlay()
            return W.composition_value(self.L, self.sources, self.commit)
        module = types.SimpleNamespace(ROOT=self.origin, compose=mock.Mock(side_effect=prepare))
        with self.patches() as patches, mock.patch.object(W.importlib, 'import_module', return_value=module):
            W.compose(self.api, self.L, self.pins, self.args, self.origin, self.out, self.context, self.qualified)
            patches['import_root'].assert_called_once_with(self.L, self.origin, self.pins['inputs'])
        self.assertEqual(json.loads((self.out/'COMPOSED.json').read_bytes()), W.composition_value(self.L, self.sources, self.commit))

    def test_seal_uses_current_composed_root_and_exact_tiny_artifacts(self):
        self.prepared()
        self.args.mode = 'seal'
        def seal(path, **kwargs):
            self.seal_kwargs = kwargs
            return path, write(path, self.manifest), {}
        self.A.seal_manifest = mock.Mock(side_effect=seal)
        with self.patches() as patches, mock.patch.object(W.importlib, 'import_module', side_effect=self.modules.__getitem__):
            W.seal(self.api, self.L, self.pins, self.args, self.origin, self.out, self.context, self.qualified)
            patches['import_root'].assert_called_once_with(self.L, self.source, self.sources)
        self.assertEqual(self.seal_kwargs, dict(producer_workspace=self.out/'setup/producer',
            producer_manifest_sha256='e'*64, producer_receipt=self.out/'setup/QUALIFICATION.json',
            producer_receipt_sha256=self.context['producer_receipt_sha256'],
            compile_receipt=self.out/'setup/tiny/build/official_bf16_compile.json',
            compile_origin=self.out/'setup/tiny/source', tiny_workspace=self.out/'setup/tiny',
            tiny_input_contract=self.origin/W.TINY/'input-contract.json'))
        sealed = json.loads((self.out/'SEALED.json').read_bytes())
        self.assertEqual(sealed, W.sealed_value(self.L, self.context, self.sources, R.sha(safe(self.out/'ENTRY_MANIFEST.json'))))

    def test_run_configures_once_then_exact_original_entry(self):
        self.run_ready()
        with self.patches() as patches, mock.patch.object(W.importlib, 'import_module', side_effect=self.modules.__getitem__):
            W.run(self.api, self.L, self.pins, self.args, self.origin, self.out, self.context, self.qualified)
            patches['import_root'].assert_called_once_with(self.L, self.source, self.sources)
        self.assertEqual(self.order, ['configure', 'run'])
        self.entry.configure_backend.assert_called_once_with()
        self.entry.run.assert_called_once()
        args, kwargs = self.entry.run.call_args
        self.assertEqual(args, (self.out/'full_m16',))
        self.assertEqual(kwargs['manifest'], self.out/'ENTRY_MANIFEST.json')
        self.assertEqual(kwargs['manifest_sha256'], self.context['entry_manifest_sha256'])
        self.assertEqual(kwargs['run_context'], dict(profile=W.PROFILE, attempt=1, pid=os.getpid(),
            parent_pid=os.getppid(), started=self.context['started'], work_deadline=self.context['started']+924,
            outer_deadline=self.context['started']+930, source_manifest_sha256=self.context['source_manifest_sha256'],
            producer_receipt_sha256=self.context['producer_receipt_sha256'], attempt_nonce=self.context['attempt_nonce']))

    def test_run_rejects_manifest_or_seal_substitution_before_import(self):
        self.run_ready()
        path = self.out/'ENTRY_MANIFEST.json'
        original = path.read_bytes()
        path.write_bytes(b'{}\n')
        with self.patches() as patches:
            with self.assertRaises(ValueError): W.run(self.api, self.L, self.pins, self.args, self.origin, self.out, self.context, self.qualified)
            patches['import_root'].assert_not_called()
        path.write_bytes(original)
        (self.out/'SEALED.json').write_bytes(b'{}\n')
        with self.patches() as patches:
            with self.assertRaises(ValueError): W.run(self.api, self.L, self.pins, self.args, self.origin, self.out, self.context, self.qualified)
            patches['import_root'].assert_not_called()

    def test_backend_failure_never_runs_and_failure_propagates(self):
        self.run_ready()
        self.entry.configure_backend.side_effect = ValueError('backend refused')
        with self.patches(), mock.patch.object(W.importlib, 'import_module', side_effect=self.modules.__getitem__):
            with self.assertRaisesRegex(ValueError, 'backend refused'):
                W.run(self.api, self.L, self.pins, self.args, self.origin, self.out, self.context, self.qualified)
        self.entry.run.assert_not_called()

    def test_manifest_foreign_or_old_pointer_is_rejected(self):
        self.run_ready()
        self.manifest['producer_workspace'] = '/old/history/producer'
        with self.patches(), mock.patch.object(W.importlib, 'import_module', side_effect=self.modules.__getitem__):
            with self.assertRaises(ValueError): W.run(self.api, self.L, self.pins, self.args, self.origin, self.out, self.context, self.qualified)
        self.entry.configure_backend.assert_not_called()
        self.entry.run.assert_not_called()

    def test_runtime_rejects_wrong_version_flags_or_venv(self):
        with self.assertRaises(ValueError): W.runtime(self.out)
        good_flags = types.SimpleNamespace(isolated=1, optimize=0)
        with mock.patch.multiple(sys, version_info=(3,12,15), flags=good_flags, dont_write_bytecode=True,
                pycache_prefix=None, executable=str(self.out/'setup/venv/bin/python'),
                prefix=str(self.out/'setup/venv'), base_prefix='/base'):
            W.runtime(self.out)
            with mock.patch.object(sys, 'executable', '/other/python'):
                with self.assertRaises(ValueError): W.runtime(self.out)
            with mock.patch.object(sys, 'dont_write_bytecode', False):
                with self.assertRaises(ValueError): W.runtime(self.out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
