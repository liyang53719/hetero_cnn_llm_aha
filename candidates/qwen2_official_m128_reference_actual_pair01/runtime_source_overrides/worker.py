"""Future exact-GO worker. This file is prepared, not authorized or executed."""
from __future__ import annotations
import argparse
import ctypes
import importlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import time
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (CLASS_FILES, GATE_FILES, LIMITS, actual_class_identity,
                         collect_modules, file_id, need, parse_maps, process_stat,
                         read_checked, selected_bindings, verify_observed_files, write_new)
from network_policy import network_guard, probe_terminal
from validate_outputs import validate_capture
from run_gate import validate_review

_CLAIM_TOKEN = object()


def claim(capability_fd, config, config_sha, out):
    need(stat.S_ISFIFO(os.fstat(capability_fd).st_mode), 'live inherited FIFO capability required')
    with os.fdopen(capability_fd, 'rb') as stream:
        raw = stream.read(16385)
    need(len(raw) <= 16384, 'oversized capability')
    cap = json.loads(raw)
    parent = os.getppid()
    need(cap['go'] == 'GO' and cap['parent_pid'] == parent, 'GO/parent mismatch')
    identity = process_stat(parent)
    need(identity and identity['start_ticks'] == cap['parent_start_ticks'], 'parent identity mismatch')
    need(cap['config_sha256'] == config_sha and cap['output'] == str(out), 'capability config/output mismatch')
    need(os.getpgrp() == os.getpid(), 'worker must lead its own process group')
    need(Path('/proc/%d/exe' % parent).resolve() == Path(config['interpreter']), 'parent interpreter mismatch')
    argv = [os.fsdecode(x) for x in Path('/proc/%d/cmdline' % parent).read_bytes().split(b'\0') if x]
    need(argv == cap['parent_argv'], 'parent argv changed')
    cwd = Path(os.readlink('/proc/%d/cwd' % parent))
    script = Path(argv[4]) if len(argv) > 4 else Path('/missing-script')
    script = script if script.is_absolute() else cwd / script
    need(argv[1:4] == ['-I', '-S', '-B'] and script.resolve() == Path(config['gate_directory']) / 'run_gate.py', 'not exact reviewed launcher')
    need('--go' in argv and argv[argv.index('--go') + 1] == 'GO', 'parent lacks explicit GO')
    need(config['status'] == 'PREPARED_NOT_EXECUTED_NOT_APPROVED' and config['execution_started'] is False, 'wrong proposal state')
    need(config['action'] == 'single_official_m128_full_layer_reference_pair', 'wrong reference action')
    need(Path(cap['review_path']) == out / 'REVIEW.json' and Path(cap['approval_path']) == out / 'APPROVAL.json', 'wrong review/approval archive')
    review = read_checked(cap['review_path'], cap['review_sha256'], maximum=1048576)
    approval = read_checked(cap['approval_path'], cap['approval_sha256'], maximum=16384)
    validate_review(review, config_sha, cap['review_sha256'], approval, config)
    need(approval['run_id'] == cap['run_id'] == out.name, 'run ID mismatch')
    claim_path = Path(config['gate_directory']) / 'FULL_REFERENCE_CLAIM.json'
    need(cap['claim_path'] == str(claim_path), 'wrong one-use claim path')
    ledger = json.loads(claim_path.read_text())
    for key in ('config_sha256', 'review_sha256', 'approval_sha256', 'run_id', 'output', 'go'):
        need(ledger[key] == cap[key], 'claim ledger mismatch: ' + key)
    need(ledger['pid'] == parent and ledger['process']['start_ticks'] == identity['start_ticks'] and ledger['maximum_invocations'] == 1, 'claim ownership mismatch')
    for name in GATE_FILES:
        path = Path(config['gate_directory']) / name
        need(file_id(path) == config['file_manifest'][str(path)], 'gate source drift: ' + name)
    for path, expected in config['capture_sources'].items():
        need(file_id(path) == expected, 'frozen capture drift')
    need(not (out / 'WORKER_RESULT.json').exists() and not (out / 'capture').exists(), 'worker already used')
    write_new(out / 'WORKER_CLAIM.json', {'pid': os.getpid(), 'identity': process_stat(os.getpid()),
              'capability': cap, 'parent_verified': identity, 'parent_argv_verified': argv})
    libc = ctypes.CDLL(None, use_errno=True)
    need(libc.prctl(1, signal.SIGKILL, 0, 0, 0) == 0, 'PR_SET_PDEATHSIG failed')
    need(os.getppid() == parent, 'parent exited during claim')
    return cap, _CLAIM_TOKEN


def install_guards(config):
    capture_network, profile_network, network_state = network_guard(config)
    state = {'phase': 'import', 'model_calls': [], 'denied_model_calls': [],
             'denied_imports': [], 'denied_process_events': [], 'denied_payload_opens': []}
    model_files = {str(Path(config['target']) / x) for x in CLASS_FILES.values()}
    allowed_init = {'Qwen2Config.__init__', 'Qwen2DecoderLayer.__init__', 'Qwen2RMSNorm.__init__',
                    'Qwen2Attention.__init__', 'Qwen2RotaryEmbedding.__init__', 'Qwen2MLP.__init__'}
    allowed_forward = {'Qwen2DecoderLayer.forward', 'Qwen2RMSNorm.forward', 'Qwen2Attention.forward',
                       'Qwen2RotaryEmbedding.forward', 'Qwen2MLP.forward'}
    # Exact canonical raw paths, never arbitrary providers or previous outputs.
    raw_inputs = {str(Path(path).resolve()) for path in config['raw_input_manifest']}
    # Do not resolve the capture child itself: an attacker-created symlink at
    # that name must not redefine the authorized output subtree.
    capture_root = Path(config['_output']).resolve() / 'capture'
    def profile(frame, event, arg):
        profile_network(frame, event, arg)
        if event == 'call' and frame.f_code.co_filename in model_files and frame.f_code.co_name in ('__init__', 'forward'):
            name = frame.f_code.co_qualname
            record = {'name': name, 'filename': frame.f_code.co_filename,
                      'firstlineno': frame.f_code.co_firstlineno, 'phase': state['phase']}
            state['model_calls'].append(record)
            if state['phase'] != 'capture' or name not in allowed_init | allowed_forward:
                state['denied_model_calls'].append(record)
                raise RuntimeError('model construction/forward outside exact authorized paired one-layer phase')
            if name in ('Qwen2DecoderLayer.__init__', 'Qwen2DecoderLayer.forward'):
                maximum = 1 if name.endswith('__init__') else 2
                need(sum(r['name'] == name for r in state['model_calls']) <= maximum, 'too many official decoder calls for exact pair profile')
    def audit(event, args):
        if event in ('subprocess.Popen', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.exec', 'os.system'):
            state['denied_process_events'].append({'event': event})
            raise RuntimeError('worker child process/program execution forbidden')
        if event == 'import' and args and type(args[0]) is str and any(args[0] == p or args[0].startswith(p + '.') for p in config['excluded_module_prefixes']):
            state['denied_imports'].append(args[0])
            raise RuntimeError('excluded GUI import')
        if event.startswith('socket.'):
            capture_network(event, args, sys._getframe(1), 'audit')
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            lexical = Path(os.fsdecode(args[0])).absolute()
            canonical = lexical.resolve()
            # Narrow tensor-payload boundary, not a general filesystem sandbox.
            suffixes = ('.bin', '.safetensors', '.pt', '.pth', '.f32le')
            if lexical.suffix.lower() in suffixes or canonical.suffix.lower() in suffixes:
                mode = args[1] if len(args) > 1 else None
                flags = args[2] if len(args) > 2 else 0
                writing = ((type(mode) is str and any(c in mode for c in 'wax+')) or
                           (type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))))
                original_raw_read = str(canonical) in raw_inputs and not writing
                fresh_capture = canonical.is_relative_to(capture_root)
                allowed = original_raw_read or fresh_capture
                if not allowed:
                    state['denied_payload_opens'].append({'requested': str(lexical), 'canonical': str(canonical), 'writing': bool(writing)})
                    raise RuntimeError('tensor payload outside read-only original raw13 or canonical fresh capture')
    sys.addaudithook(audit)
    sys.setprofile(profile)
    return state, network_state, profile


def snapshot(config, out, prefix):
    """Persist FULL raw observations before attempting closure checks."""
    modules = collect_modules(sys.modules)
    maps_text = Path('/proc/self/maps').read_text()
    maps = parse_maps(maps_text)
    write_new(out / (prefix + '_MODULES.json'), {'modules': modules, 'count': len(modules), 'truncated': False})
    with (out / (prefix + '_MAPS.txt')).open('x') as stream:
        stream.write(maps_text)
        stream.flush()
        os.fsync(stream.fileno())
    write_new(out / (prefix + '_MAPS.json'), {'maps': maps, 'count': len(maps), 'truncated': False})
    closure = verify_observed_files(modules, maps, config['file_manifest'], mapped_manifest=config['mapped_file_manifest'])
    write_new(out / (prefix + '_FILE_CLOSURE.json'), closure)
    return closure


def import_and_validate(config, out):
    imported, versions, error = {}, {}, None
    try:
        import torch
        import numpy
        import transformers
        from transformers.models.qwen2.configuration_qwen2 import Qwen2Config
        from transformers.models.qwen2.modeling_qwen2 import Qwen2DecoderLayer, Qwen2Attention, Qwen2MLP
        imported = {'Qwen2Config': Qwen2Config, 'Qwen2DecoderLayer': Qwen2DecoderLayer,
                    'Qwen2Attention': Qwen2Attention, 'Qwen2MLP': Qwen2MLP}
        versions = {'torch': torch.__version__, 'numpy': numpy.__version__, 'transformers': transformers.__version__}
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    closure = snapshot(config, out, 'IMPORT')
    classes, class_errors = {}, {}
    for name, cls in imported.items():
        try:
            module = sys.modules[type.__getattribute__(cls, '__dict__')['__module__']]
            classes[name] = actual_class_identity(cls, config['selected_classes'][name], module)
        except BaseException as exc:
            class_errors[name] = {'type': type(exc).__name__, 'message': str(exc)}
    bindings = selected_bindings(imported, sys.modules) if imported else {'passed': False}
    result = {'error': error, 'versions': versions, 'closure_passed': closure['passed'],
              'classes': classes, 'class_errors': class_errors, 'bindings': bindings}
    write_new(out / 'IMPORT_VALIDATION.json', result)
    need(error is None and versions == config['expected_versions'], 'official normal import failed/version drift')
    need(closure['passed'] and not class_errors and set(classes) == set(CLASS_FILES) and bindings['passed'], 'import closure/class bindings failed')
    need(all(all(c[k] for k in ('own_method_code_exact', 'module_file_exact', 'class_name_exact', 'class_module_exact')) for c in classes.values()), 'selected class identity drift')
    return torch


def run(config, out, cap, token):
    need(token is _CLAIM_TOKEN and cap.get('go') == 'GO', 'worker was not capability-claimed')
    need(config['limits'] == LIMITS, 'exact resource proposal not reviewed')
    need(list(sys.version_info[:2]) == config['python_major_minor'] == [3, 12], 'Python version mismatch')
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and sys.flags.optimize == 0, 'exact -I -S -B required')
    need(sorted(os.sched_getaffinity(0)) == cap['affinity'] and len(cap['affinity']) == 4, 'exact four-CPU affinity required')
    need(resource.getrlimit(resource.RLIMIT_CPU) == (120, 120), '120 CPU-second hard worker limit required')
    need(resource.getrlimit(resource.RLIMIT_AS) == tuple(cap['rlimit_as_unchanged']), 'RLIMIT_AS changed')
    sys.path[:] = [config['target'], config['runtime'], config['stdlib'], str(Path(config['stdlib']) / 'lib-dynload'), config['gate_directory']]
    config['_output'] = str(out)
    write_new(out / 'WORKER_BEFORE.json', {'pid': os.getpid(), 'ppid': os.getppid(), 'affinity': cap['affinity'],
              'rlimit_cpu': resource.getrlimit(resource.RLIMIT_CPU), 'rlimit_as': resource.getrlimit(resource.RLIMIT_AS),
              'sys_path': sys.path, 'environment': dict(sorted(os.environ.items())), 'scope': config['scope']})
    state, network, profile = install_guards(config)
    started = time.monotonic()
    error, report, checks, closure, runtime_profile = None, None, None, None, None
    try:
        torch = import_and_validate(config, out)
        need(probe_terminal(config, network)['passed'], 'exact loopback probe did not terminate correctly')
        need(sys.getprofile() is profile, 'network/model profile displaced during import')
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        from gate_common import sha
        runtime_profile = {'cpu_capability': torch.backends.cpu.get_cpu_capability(),
                           'torch_build_sha256': sha(torch.__config__.show().encode()),
                           'torch_git_version': torch.version.git_version,
                           'intraop_threads': torch.get_num_threads(), 'interop_threads': torch.get_num_interop_threads(),
                           'deterministic_algorithms': torch.are_deterministic_algorithms_enabled(),
                           'python_major_minor': list(sys.version_info[:2])}
        runtime_record = {'actual': runtime_profile, 'expected': config['reviewed_runtime_profile'],
                          'build_configuration': torch.__config__.show(), 'affinity': sorted(os.sched_getaffinity(0)),
                          'rlimit_as': resource.getrlimit(resource.RLIMIT_AS), 'limits': LIMITS}
        runtime_receipt = out / 'RUNTIME_IDENTITY.json'
        write_new(runtime_receipt, runtime_record)
        need(runtime_profile == config['reviewed_runtime_profile'], 'live build/capability/thread/deterministic profile drift')
        need(sys.gettrace() is None and sys.getprofile() is profile, 'observation controls displaced before capture')
        capture_path = Path(config['capture_directory']) / 'capture_pair.py'
        need(file_id(capture_path) == config['capture_sources'][str(capture_path)], 'frozen capture changed before private call')
        spec = importlib.util.spec_from_file_location('frozen_official_m128_capture_pair', capture_path)
        capture = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = capture
        spec.loader.exec_module(capture)
        context = {'run_id': cap['run_id'], 'numerical_runtime_root': config['runtime'],
                   'transformers_root': config['target'], 'config_path': config['input_config']['path'],
                   'runtime_receipt_path': str(runtime_receipt), 'runtime_receipt_sha256': file_id(runtime_receipt)['sha256'],
                   'softmax_source_sha256': capture.load_pins()['torch_functional_source_sha256'],
                   'launch_authorization': {'go': 'GO', 'config_sha256': cap['config_sha256'],
                       'review_sha256': cap['review_sha256'], 'approval_sha256': cap['approval_sha256'], 'one_use_claim': cap['claim_path']},
                   'resource_controls': dict(LIMITS, affinity=cap['affinity']),
                   'reviewed_runtime_profile': runtime_profile, 'capture_profile': config['capture_profile']}
        state['phase'] = 'capture'
        # Exactly one paired private call (one layer, two forwards), after live authority gates.
        # Public run_capture remains unconditionally disabled and unmodified.
        report = capture._capture_pair_impl(config['raw_root'], out / 'capture', context)
        state['phase'] = 'closed'
        need(sys.gettrace() is None and sys.getprofile() is profile, 'capture displaced audit controls')
        checks = validate_capture(config, out / 'capture', report)
        write_new(out / 'ALL29_VALIDATION.json', checks)
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    finally:
        state['phase'] = 'closed'
        intact = sys.getprofile() is profile
        # Keep network protection active through terminal observations/validation.
        try:
            closure = snapshot(config, out, 'FINAL')
        except BaseException as exc:
            error = error or {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
        terminal_probe = probe_terminal(config, network)
        write_new(out / 'NETWORK_EVENTS.json', network)
        write_new(out / 'LOOPBACK_PROBE_TERMINAL.json', terminal_probe)
        write_new(out / 'MODEL_AND_PAYLOAD_GUARDS.json', state)
        sys.setprofile(None)
    calls = [x['name'] for x in state['model_calls']]
    counts = {n: calls.count(n) for n in set(calls)}
    expected_forwards = {'Qwen2DecoderLayer.forward': 2, 'Qwen2Attention.forward': 2,
                         'Qwen2MLP.forward': 2, 'Qwen2RMSNorm.forward': 4, 'Qwen2RotaryEmbedding.forward': 2}
    passed = bool(error is None and checks and checks['passed'] and closure and closure['passed']
                  and intact and terminal_probe['passed'] and runtime_profile == config['reviewed_runtime_profile']
                  and counts.get('Qwen2DecoderLayer.__init__') == 1
                  and all(counts.get(n) == c for n, c in expected_forwards.items())
                  and not any(state[x] for x in ('denied_model_calls', 'denied_imports', 'denied_process_events', 'denied_payload_opens')))
    result = {'status': 'REFERENCE_PAIR_WORKER_COMPLETE_NOT_DUT_PASS' if passed else 'FAIL_REFERENCE_WORKER',
              'passed': passed, 'error': error, 'model_call_counts': counts, 'profile_intact': intact,
              'model_instance_created': bool(counts.get('Qwen2DecoderLayer.__init__')),
              'forward_executed': bool(counts.get('Qwen2DecoderLayer.forward')),
              'forward_call_count': counts.get('Qwen2DecoderLayer.forward', 0),
              'capture_profile': config['capture_profile'],
              'pair_y_prob_exact': bool(report and report.get('pair_output_comparison', {}).get('passed')),
              'pair_boundary_state_unchanged': bool(report and report.get('baseline_state_unchanged', {}).get('passed') and report.get('observed_state_unchanged', {}).get('passed')),
              'capture_completed': bool(report), 'all29_self_checks_passed': bool(checks and checks['passed']),
              'final_file_closure_passed': bool(closure and closure['passed']),
              'runtime_profile': runtime_profile, 'loopback_probe_terminal': terminal_probe,
              'numeric_acceptance': 'NOT_RUN', 'dut_comparison': 'NOT_RUN', 'legacy_results_inherited': False,
              'expected_output_hashes': None, 'scope': config['scope'], 'elapsed_seconds': time.monotonic() - started,
              'limitations': ['Module/maps snapshots are not a lifetime trace or all-code identity proof.',
                              'Python audit/profile guards are not kernel isolation or native/unprofiled-thread bypass proof.',
                              'Sampled tree RSS is not a hard memory cap; RLIMIT_CPU is per process including threads.',
                              'Two-arm evidence concerns only actual y/prob native bytes and original input/parameter/buffer boundary state; all29 baseline intermediate noninterference is not claimed.',
                              'Internal capture/SEAL.json is not wrapper completion; only parent terminal COMPLETION_SEAL.json qualifies.']}
    write_new(out / 'WORKER_RESULT.json', result)
    return 0 if passed else 2


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--config-sha256', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--capability-fd', type=int, required=True)
    a = p.parse_args()
    config = read_checked(a.config, a.config_sha256)
    out = Path(a.output).resolve(strict=True)
    cap, token = claim(a.capability_fd, config, a.config_sha256, out)
    try:
        return run(config, out, cap, token)
    except BaseException as exc:
        write_new(out / 'WORKER_FAILURE.json', {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
        return 3

if __name__ == '__main__':
    raise SystemExit(main())
