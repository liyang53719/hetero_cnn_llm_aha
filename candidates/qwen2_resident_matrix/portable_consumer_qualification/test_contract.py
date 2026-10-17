"""Cold source/metadata negatives only. Never import the arithmetic worker."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import contract as c

HERE = Path(__file__).resolve().parent
COLD_SIGNAL_CHILD = (
    "import json, os, signal, sys, time\n"
    "mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())\n"
    "with open(sys.argv[1] + '.pending', 'w') as stream:\n"
    "    json.dump(dict(pid=os.getpid(), group=os.getpgrp(), mask=sorted(int(x) for x in mask)), stream)\n"
    "os.replace(sys.argv[1] + '.pending', sys.argv[1])\n"
    "time.sleep(30)\n")

def forbid_native(event, args):
    if event == 'import' and (args[0].split('.')[0] in ('ctypes', 'numpy', 'torch') or args[0].startswith('candidates.')):
        raise RuntimeError('cold preparation forbids arithmetic/native imports')
    if event == 'subprocess.Popen':
        allowed = [[sys.executable, '-I', '-B', str(HERE / n), '--cold-import-check']
                   for n in ('worker.py', 'run_ci.py')]
        command = args[1]
        controller = sys.modules.get('run_ci')
        dummy = (controller is not None and len(command) == 10 and
                 command[:5] == [sys.executable, '-I', '-B', '-c', controller.CHILD_BOOTSTRAP] and
                 command[5:9] == ['-I', '-B', '-c', COLD_SIGNAL_CHILD] and
                 Path(command[9]).name.startswith('child-mask-'))
        if command not in allowed and not dummy:
            raise RuntimeError('cold preparation permits only isolated cold-import children')
    if event in ('ctypes.dlopen', 'os.system', 'socket.connect'):
        raise RuntimeError('cold preparation forbids execution and network')

sys.addaudithook(forbid_native)

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.value = c.read(HERE / 'input-contract.json')

    def test_contract_is_exact_proposal(self):
        c.shape(self.value)

    def test_missing_extra_and_relabelled_sources_fail(self):
        for kind in ('missing', 'extra', 'relabel'):
            value = copy.deepcopy(self.value)
            source = value['source_sha256']
            key = next(iter(source))
            if kind == 'missing':
                del source[key]
            elif kind == 'extra':
                source['invented.py'] = '0' * 64
            else:
                source['../escape.py'] = source.pop(key)
            with self.assertRaises(ValueError):
                c.shape(value)

    def test_wrong_generation_and_payload_inventories_fail(self):
        for key in ('generated_sha256', 'payload_sha256'):
            value = copy.deepcopy(self.value)
            value[key].pop(next(iter(value[key])))
            with self.assertRaises(ValueError):
                c.shape(value)

    def test_current_bytes_and_generation_must_match_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = copy.deepcopy(self.value)
            for name in value['source_sha256']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('cold metadata fixture ' + name)
            pins = root / (c.PREFIX + 'attention_packed_native/pins.json')
            pins.write_text(json.dumps({'generated': value['generated_sha256']}))
            value['source_sha256'] = {name: c.sha(root / name) for name in value['source_sha256']}
            for name in value['payload_sha256']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                source = HERE.parents[2] / name
                path.write_bytes(source.read_bytes())
            here = root / c.OWN
            (here / 'input-contract.json').write_text(json.dumps(value))
            c.validate(root, here)
            target = root / c.GENERATED[0]
            original = target.read_bytes()
            target.write_bytes(original + b'changed')
            with self.assertRaises(ValueError):
                c.validate(root, here)
            target.write_bytes(original)
            value['generated_sha256'][c.GENERATED[0]] = '0' * 64
            (here / 'input-contract.json').write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                c.validate(root, here)

    def test_scope_budget_runtime_and_historical_pass_fail(self):
        mutations = [('status', 'PASS'), ('profile', 'original-avx512'), ('schema', True),
                     ('budgets', {'worker_seconds': 3600}), ('runtime', {'python': '3.11'}),
                     ('claims', {'full_m128': True}), ('workflow', 'other.yml')]
        for key, replacement in mutations:
            value = copy.deepcopy(self.value)
            value[key] = replacement
            with self.assertRaises(ValueError):
                c.shape(value)
        for key in self.value['budgets']:
            value = copy.deepcopy(self.value)
            value['budgets'][key] = float(value['budgets'][key])
            with self.assertRaises(ValueError):
                c.shape(value)

    def test_native_observation_scalar_types_are_exact(self):
        cases = [dict(case='qk', profile=2, steps=8, fmas=32768, output_sha256='1' * 64),
                 dict(case='pv', profile=2, steps=3, fmas=6144, output_sha256='2' * 64),
                 dict(case='pv128_boundary', profile=2, steps=128, fmas=262144),
                 dict(case='pv', profile=1, steps=3, fmas=12288, output_sha256='3' * 64),
                 dict(case='legacy_default', steps=8, fmas=4096),
                 dict(case='nonselected_nonfinite', protocol_error=False, selected_fault_timing_qualified=False),
                 dict(case='selected_nonfinite', protocol_error=False, selected_fault_timing_qualified=False)]
        observed = dict(profile2_cases=cases, silu_phase_sha256=['4' * 64, '5' * 64])
        c.observations(observed)
        for index, key, replacement in ((3, 'profile', True), (0, 'steps', 8.0), (0, 'fmas', 32768.0),
                                        (5, 'protocol_error', 0), (6, 'selected_fault_timing_qualified', 0.0)):
            value = copy.deepcopy(observed)
            value['profile2_cases'][index][key] = replacement
            with self.assertRaises(ValueError):
                c.observations(value)

    def test_invalid_sha_and_unknown_keys_fail(self):
        for replacement in (None, True, '', 'g' * 64, '0' * 63):
            value = copy.deepcopy(self.value)
            value['source_sha256'][next(iter(value['source_sha256']))] = replacement
            with self.assertRaises(ValueError):
                c.shape(value)
        self.value['inherited_pass'] = True
        with self.assertRaises(ValueError):
            c.shape(self.value)

    def test_duplicate_and_nonfinite_json_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.json'
            for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    c.read(path)

    def test_atomic_bounded_evidence_preserves_previous_on_invalid_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'summary.json'
            c.atomic(path, {'status': 'previous'})
            original = path.read_bytes()
            for value in ({'value': float('nan')}, {'value': 'x' * 262145}):
                with self.assertRaises(ValueError):
                    c.atomic(path, value)
                self.assertEqual(path.read_bytes(), original)
            self.assertFalse(path.with_name(path.name + '.tmp').exists())
            c.atomic(path, {'status': 'next'})
            self.assertEqual(c.read(path), {'status': 'next'})

    def test_path_escape_and_symlink_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'file').write_text('source')
            (root / 'link').symlink_to(root / 'file')
            for name in ('../file', '/file', 'link', 'bad\\name'):
                with self.assertRaises(ValueError):
                    c.safe(root, name)

    def test_own_payload_bytes_are_sealed(self):
        for name in c.FILES:
            self.assertEqual(c.sha(HERE / name), self.value['payload_sha256'][c.OWN + name])

    def test_runtime_worker_is_not_imported(self):
        self.assertFalse(any(x == 'numpy' or x == 'ctypes' or x.startswith('candidates.') for x in sys.modules))
        for name in c.FILES:
            ast.parse((HERE / name).read_text())

    def test_exact_original_helpers_and_no_substitute_backend(self):
        tree = ast.parse((HERE / 'worker.py').read_text())
        text = (HERE / 'worker.py').read_text()
        for call in ('d.build_library(', 'd.verify_library(', 'check_native.run(', 'a.ScalarService()',
                     'test_every_primitive_matches_independent_exact_rounding', 'reference_exp(gate)'):
            self.assertIn(call, text)
        self.assertNotIn('ExactScalar(', text)
        self.assertNotIn('source_identity =', text)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))

    def test_no_producer_or_payload_or_native_flags(self):
        text = (HERE / 'worker.py').read_text() + (HERE / 'run_ci.py').read_text()
        for forbidden in ('huggingface', 'safetensors', 'torch.', 'mmap(', 'download', '-march', '-mavx',
                          'run_m128_ci', 'producer.main', 'git push', 'curl '):
            self.assertNotIn(forbidden, text)

    def test_no_manual_launch_retry_or_wildcard_upload(self):
        payload = HERE.parents[2]
        path = payload / c.WORKFLOW
        self.assertTrue(path.is_file(), 'workflow must be placed at the exact launch path')
        text = path.read_text()
        self.assertEqual(c.sha(path), self.value['payload_sha256'][c.WORKFLOW])
        self.assertIn("paths:\n      - '" + c.WORKFLOW + "'", text)
        self.assertIn("github.event_name == 'push' && github.run_attempt == 1", text)
        for forbidden in ('workflow_dispatch', 'pull_request:', 'schedule:', 'retry:', '**', '-march', 'continue-on-error'):
            self.assertNotIn(forbidden, text)
        self.assertIn('--retries 0', text)
        self.assertIn('timeout --signal=TERM --kill-after=10s 150s python -I -B candidates/qwen2_resident_matrix/portable_consumer_qualification/run_ci.py', text)
        for filename in ('summary.json', 'identities.json', 'source_hashes.json'):
            self.assertIn('/evidence/' + filename, text)

    def test_fabricated_and_partial_success_fail(self):
        for value in ({}, {'status': 'PASS_FIXED_ACTUAL_CASES'}, {'status': 'PASS_TINY_PACKED_NATIVE_MODEL'},
                      {'profile': c.PROFILE, 'status': 'PASS_FIXED_ACTUAL_CASES', 'library_sha256': '0' * 64,
                       'identities': {}, 'checks': {}}):
            with self.assertRaises(ValueError):
                c.result(value, '0' * 40)

    def test_real_isolated_script_bootstrap(self):
        for name in ('run_ci.py', 'worker.py'):
            result = subprocess.run([sys.executable, '-I', '-B', str(HERE / name), '--cold-import-check'],
                                    check=True, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.stdout, 'PASS_COLD_ISOLATED_IMPORT\n')

    def test_duplicate_attempt_preserves_previous_evidence(self):
        env = dict(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='push', GITHUB_RUN_ATTEMPT='1', GITHUB_SHA='a' * 40)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'previous'
            out.mkdir()
            receipt = out / 'summary.json'
            receipt.write_bytes(b'unchanged previous evidence\n')
            for attempt in ('1', '2', '01', ''):
                with self.assertRaises(ValueError):
                    c.admit({**env, 'GITHUB_RUN_ATTEMPT': attempt}, out)
                self.assertEqual(receipt.read_bytes(), b'unchanged previous evidence\n')
            self.assertEqual(c.admit(env, Path(directory) / 'fresh'), 'a' * 40)
            self.assertFalse((Path(directory) / 'fresh').exists())

    def test_exact_hosted_loader_directory_and_clean_environment(self):
        import run_ci
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'toolcache'
            location = cache / 'Python/3.12.15/x64'
            (location / 'bin').mkdir(parents=True)
            (location / 'lib').mkdir()
            binary = location / 'bin/python3.12'
            binary.write_text('metadata fixture only; never executed')
            env = dict(RUNNER_TOOL_CACHE=str(cache), pythonLocation=str(location),
                       LD_LIBRARY_PATH=str(location / 'lib'))
            admitted = c.loader(env, binary)
            self.assertEqual(admitted['toolcache_relative'], 'Python/3.12.15/x64')
            other = root / 'other'
            other.mkdir()
            bad_binary = other / 'python3.12'
            bad_binary.write_text('not the selected interpreter')
            for replacement in ('', str(other), str(location / 'lib') + ':', ':' + str(location / 'lib'),
                                str(location / 'lib') + ':' + str(other)):
                with self.assertRaises(ValueError):
                    c.loader({**env, 'LD_LIBRARY_PATH': replacement}, binary)
            with self.assertRaises(ValueError):
                c.loader({**env, 'RUNNER_TOOL_CACHE': str(other)}, binary)
            with self.assertRaises(ValueError):
                c.loader(env, bad_binary)
            (location / 'lib').rmdir()
            (location / 'lib').symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):
                c.loader(env, binary)
            with patch.dict(os.environ, {'SECRET_TOKEN': 'not-forwarded', 'LD_PRELOAD': '/other.so',
                                         'PYTHONPATH': '/other', 'LD_LIBRARY_PATH': '/other'}):
                clean = run_ci.clean_environment(root, admitted)
            self.assertEqual(clean['LD_LIBRARY_PATH'], env['LD_LIBRARY_PATH'])
            self.assertEqual(clean['PATH'], '/usr/bin:/bin')
            for name in ('SECRET_TOKEN', 'LD_PRELOAD', 'PYTHONPATH'):
                self.assertNotIn(name, clean)

    def test_leader_ownership_is_retained_until_group_cleanup(self):
        import run_ci
        from types import SimpleNamespace
        events = []
        process = SimpleNamespace(pid=12345, wait=lambda timeout: events.append(('reap', timeout)))
        identity = dict(pid=12345, ppid=os.getpid(), group=12345, start=9)
        owner = dict(process=process, identity=identity)
        def observed(*args):
            events.append(('observe', args[2]))
            return SimpleNamespace(si_code=run_ci.os.CLD_EXITED, si_status=0)
        with patch.object(run_ci.os, 'waitid', side_effect=observed), \
             patch.object(run_ci, 'process_identity', return_value=identity), \
             patch.object(run_ci.os, 'killpg', side_effect=lambda pid, sig: events.append(('signal', pid))):
            self.assertEqual(run_ci.observe_exit(process.pid, 0), 0)
            self.assertEqual([x[0] for x in events], ['observe'])
            self.assertTrue(events[0][1] & run_ci.os.WNOWAIT)
            run_ci.cleanup_owned(owner, time.monotonic() + 5)
            self.assertEqual([x[0] for x in events], ['observe', 'observe', 'signal', 'reap'])
        events.clear()
        with patch.object(run_ci.os, 'waitid', side_effect=ChildProcessError('already reaped')), \
             patch.object(run_ci.os, 'killpg', side_effect=lambda *args: events.append('bad_signal')):
            with self.assertRaises(ChildProcessError):
                run_ci.cleanup_owned(owner, time.monotonic() + 5)
        self.assertEqual(events, [])

    def test_real_signal_at_spawn_transfer_child_unblock_and_cleanup(self):
        import run_ci
        real_popen = subprocess.Popen
        previous = {sig: signal.getsignal(sig) for sig in run_ci.CONTROL_SIGNALS}
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        def interrupted(signum, frame):
            raise TimeoutError('injected transfer interruption')
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for signum in sorted(run_ci.CONTROL_SIGNALS):
                    marker = root / ('child-mask-' + str(int(signum)) + '.json')
                    owner = dict(process=None, identity=None)
                    emergency = {}
                    for sig in run_ci.CONTROL_SIGNALS:
                        signal.signal(sig, interrupted)
                    def inject(*args, **kwargs):
                        child = real_popen(*args, **kwargs)
                        emergency['process'] = child
                        stop = time.monotonic() + 2
                        while not marker.exists() and time.monotonic() < stop:
                            time.sleep(0.005)
                        if not marker.exists():
                            raise TimeoutError('dummy child startup')
                        # This is after OS child creation and before the Popen
                        # result is assigned into the caller-owned holder.
                        os.kill(os.getpid(), signum)
                        return child
                    try:
                        with patch.object(run_ci.subprocess, 'Popen', side_effect=inject):
                            with self.assertRaisesRegex(TimeoutError, 'injected transfer'):
                                run_ci.spawn_owned(owner, ['-I', '-B', '-c', COLD_SIGNAL_CHILD, str(marker)],
                                                   cwd=root, stdout=subprocess.DEVNULL, env=run_ci.clean_environment(root))
                        self.assertIs(owner['process'], emergency['process'])
                        observed = json.loads(marker.read_text())
                        self.assertEqual(observed['pid'], owner['process'].pid)
                        self.assertEqual(observed['group'], owner['process'].pid)
                        self.assertFalse(set(observed['mask']) & {int(x) for x in run_ci.CONTROL_SIGNALS})
                        signal.pthread_sigmask(signal.SIG_BLOCK, run_ci.CONTROL_SIGNALS)
                        for pending in run_ci.CONTROL_SIGNALS:
                            os.kill(os.getpid(), pending)
                        run_ci.protect_cleanup()
                        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                        run_ci.cleanup_owned(owner, time.monotonic() + 2)
                        with self.assertRaises(ChildProcessError):
                            os.waitid(os.P_PID, owner['process'].pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                        with self.assertRaises(ProcessLookupError):
                            os.killpg(owner['process'].pid, 0)
                    finally:
                        run_ci.protect_cleanup()
                        if owner['process'] is None and emergency:
                            owner['process'] = emergency['process']
                        if owner['process'] is not None and owner['process'].returncode is None:
                            run_ci.cleanup_owned(owner, time.monotonic() + 2)
        finally:
            run_ci.protect_cleanup()
            signal.pthread_sigmask(signal.SIG_BLOCK, run_ci.CONTROL_SIGNALS)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)

if __name__ == '__main__':
    unittest.main()
