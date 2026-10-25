"""Capability-bound normal import probe. Only the reviewed launcher may start it."""
from __future__ import annotations
import argparse
import ctypes
import importlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import _socket
import types
import stat
import sys
import time
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (CLASS_FILES, GATE_FILES, LIMITS, actual_class_identity,
                         collect_modules, file_id, need, parse_maps, process_stat,
                         read_checked, selected_bindings, verify_observed_files, write_new,
                         code_inventory, complete_probe_code_identity, module_dict, value_record)


def claim(capability_fd, config, config_sha, out):
    need(stat.S_ISFIFO(os.fstat(capability_fd).st_mode), 'live inherited FIFO capability required')
    with os.fdopen(capability_fd, 'rb') as f:
        raw = f.read(16385)
    need(len(raw) <= 16384, 'oversized capability')
    cap = json.loads(raw)
    parent = os.getppid()
    need(cap['parent_pid'] == parent, 'capability parent PID mismatch')
    ps = process_stat(parent)
    need(ps and ps['start_ticks'] == cap['parent_start_ticks'], 'capability parent identity mismatch')
    need(cap['config_sha256'] == config_sha and cap['output'] == str(out), 'capability config/output mismatch')
    need(os.getpgrp() == os.getpid(), 'worker must lead its own process group')
    need(Path('/proc/%d/exe' % parent).resolve() == Path(config['interpreter']), 'parent Python executable mismatch')
    argv = [os.fsdecode(x) for x in Path('/proc/%d/cmdline' % parent).read_bytes().split(b'\0') if x]
    need(argv == cap['parent_argv'], 'parent argv changed')
    parent_cwd = Path(os.readlink('/proc/%d/cwd' % parent))
    parent_script = Path(argv[4]) if len(argv) > 4 else Path('/missing-script')
    parent_script = parent_script if parent_script.is_absolute() else parent_cwd / parent_script
    need(argv[1:4] == ['-I', '-S', '-B'] and parent_script.resolve() == Path(config['gate_directory']) / 'run_gate.py',
         'parent is not exact isolated reviewed launcher')
    for name in GATE_FILES:
        path = Path(config['gate_directory']) / name
        need(file_id(path) == config['file_manifest'][str(path)], 'gate source changed: ' + name)
    need(not (out / 'WORKER_RESULT.json').exists(), 'worker already used')
    write_new(out / 'WORKER_CLAIM.json', {'pid': os.getpid(), 'start': process_stat(os.getpid()),
              'capability': cap, 'parent_verified': ps, 'parent_argv_verified': argv})
    # A killed wrapper must not leave a worker behind. This does not alter system settings.
    libc = ctypes.CDLL(None, use_errno=True)
    need(libc.prctl(1, signal.SIGKILL, 0, 0, 0) == 0, 'PR_SET_PDEATHSIG failed')
    need(os.getppid() == parent, 'parent exited during capability claim')
    return cap


# Exact trusted stdlib type/descriptor handles, captured before target imports.
_SOCKET_CLASS = socket.socket
_SOCKET_NATIVE = _socket.socket
_SOCKET_FIELDS = {name: _SOCKET_NATIVE.__dict__[name] for name in ('family', 'type', 'proto')}
_SOCKET_FILENO = _SOCKET_NATIVE.__dict__['fileno']
# CPython 3.12 has no audit event for these native socket calls. A Python
# c_call profile guard covers calls observed on this profiled worker thread;
# it is not kernel isolation and cannot attest native or unprofiled bypasses.
_UNAUDITED_SOCKET_CALLS = frozenset(('listen', 'send', 'sendall', 'sendmsg',
                                    'sendfile', '_accept', 'accept', 'recv',
                                    'recv_into', 'recvfrom', 'recvfrom_into',
                                    'recvmsg', 'recvmsg_into'))


def network_value(value, depth=0):
    record = value_record(value)
    if type(value) is int:
        record['scalar'] = value
    elif type(value) is tuple and depth < 3:
        record['tuple_items'] = [network_value(x, depth + 1) for x in value]
    return record


def socket_record(sock):
    record = {'object': value_record(sock), 'exact_socket_type': type(sock) is _SOCKET_CLASS}
    if type(sock) is _SOCKET_CLASS:
        for name, descriptor in _SOCKET_FIELDS.items():
            value = descriptor.__get__(sock, _SOCKET_NATIVE)
            record[name] = value if type(value) is int else None
        fd = _SOCKET_FILENO(sock)
        record['fileno'] = fd if type(fd) is int else None
        if type(fd) is int and fd >= 0:
            st = os.fstat(fd)
            record['fd_identity'] = {'device': st.st_dev, 'inode': st.st_ino,
                                     'is_socket': stat.S_ISSOCK(st.st_mode)}
    return record


def probe_caller(frame, policy):
    record = {'frame': value_record(frame), 'evidence_complete': False}
    if type(frame) is not types.FrameType or type(policy) is not dict:
        return record, False
    expected = policy['function']
    code = frame.f_code
    globals_dict = frame.f_globals
    module = sys.modules.get(policy['module'])
    md = module_dict(module) if type(module) is types.ModuleType else None
    fn = md.get(expected['name']) if type(md) is dict else None
    record.update({'code': complete_probe_code_identity(code), 'globals_object_id': hex(id(globals_dict)),
                   'module_object': value_record(module), 'module_dict_is_frame_globals': md is globals_dict,
                   'module_name': network_value(md.get('__name__')) if type(md) is dict else None,
                   'module_file': network_value(md.get('__file__')) if type(md) is dict else None,
                   'bound_function': value_record(fn),
                   'bound_function_code_is_frame_code': type(fn) is types.FunctionType and fn.__code__ is code,
                   'bound_function_globals_is_frame_globals': type(fn) is types.FunctionType and fn.__globals__ is globals_dict})
    record['code_exact'] = record['code'] == expected['code']
    record['filename_exact'] = code.co_filename == expected['filename']
    record['source_expected'] = {'bytes': expected['file_bytes'], 'sha256': expected['file_sha256']}
    # Only the sealed source path is read. Unknown frame metadata never selects a path.
    record['source_actual'] = file_id(expected['filename'])
    record['source_exact'] = record['source_actual'] == record['source_expected']
    record['module_metadata_exact'] = (type(md) is dict and type(md.get('__name__')) is str
        and md['__name__'] == policy['module'] and type(md.get('__file__')) is str
        and md['__file__'] == expected['filename'])
    matched = all(record[k] for k in ('code_exact', 'filename_exact', 'source_exact',
        'module_dict_is_frame_globals', 'bound_function_code_is_frame_code',
        'bound_function_globals_is_frame_globals', 'module_metadata_exact'))
    record['evidence_complete'] = True
    return record, matched


def network_guard(config):
    policy = config.get('loopback_probe')
    state = {'events': [], 'allowed_bind_events': [], 'denied_events': [],
             'probe_returns': [], 'collection_errors': [],
             'audit_allowance_is_not_syscall_success': True,
             'coverage': 'Python socket audit events and observed native socket c_call operations on this profiled thread; not OS isolation or native/unprofiled-thread bypass proof'}
    probe = {'socket': None, 'frame': None}

    def capture(event, args, frame, origin):
        record = {'event': event, 'origin': origin, 'decision': 'pending',
                  'arguments': network_value(args), 'caller': None, 'socket': None,
                  'address': None, 'address_evidence': 'unavailable; inspect exact captured audit arguments when present',
                  'audit_event_is_pre_operation': origin == 'audit'}
        state['events'].append(record)
        try:
            record['caller'], caller_exact = probe_caller(frame, policy)
            sock = args[0] if type(args) is tuple and args else None
            address = args[1] if type(args) is tuple and len(args) > 1 else None
            record['socket'] = socket_record(sock)
            if event in ('socket.bind', 'socket.connect', 'socket.connect_ex', 'socket.sendto') and type(args) is tuple and len(args) > 1:
                record['address'] = network_value(address)
                record['address_evidence'] = 'audit argument 1; no guessed address for c_call-only events'
            allowed = False
            if event == 'socket.__new__' and origin == 'audit':
                # Construction creates no bound/listening/connected endpoint.
                allowed = True
                record['reason'] = 'socket construction only; no network operation permitted by this event'
            elif event == 'socket.bind' and origin == 'audit':
                exact_address = (type(args) is tuple and len(args) == 2 and type(address) is tuple
                    and len(address) == 2 and type(address[0]) is str and address[0] == '::1'
                    and type(address[1]) is int and address[1] == 0)
                sr = record['socket']
                exact_socket = (sr['exact_socket_type'] and sr.get('family') == _socket.AF_INET6
                    and sr.get('type') == _socket.SOCK_STREAM and sr.get('proto') == 0
                    and type(sr.get('fileno')) is int and sr['fileno'] >= 0
                    and sr.get('fd_identity', {}).get('is_socket') is True)
                record['checks'] = {'caller_exact': caller_exact, 'exact_address': exact_address,
                                    'exact_socket': exact_socket,
                                    'unused_allowance': len(state['allowed_bind_events']) == 0}
                allowed = all(record['checks'].values())
                if allowed:
                    probe['socket'], probe['frame'] = sock, frame
                    state['allowed_bind_events'].append(record)
                    record['reason'] = 'single exact sealed dependency loopback capability probe'
            record['decision'] = 'allowed' if allowed else 'denied'
        except BaseException as exc:
            record['decision'] = 'denied'
            record['collection_error'] = value_record(exc)
            state['collection_errors'].append(record)
        if record['decision'] != 'allowed':
            state['denied_events'].append(record)
            raise RuntimeError('network operation outside the exact single loopback probe')

    def profile(frame, event, arg):
        if event == 'c_call' and type(arg) is types.BuiltinMethodType:
            # Exact built-in method metadata has no arbitrary Python descriptors.
            name = arg.__name__
            owner = arg.__self__
            if name in _UNAUDITED_SOCKET_CALLS and type(owner) in (_SOCKET_CLASS, _SOCKET_NATIVE):
                capture('socket.' + name, (owner,), frame, 'profile_c_call_no_audit_event')
        if event == 'return' and frame is probe['frame']:
            row = {'return_value': network_value(arg), 'exact_bool_return': type(arg) is bool,
                   'same_bound_socket': False, 'socket': None, 'caller': None, 'passed': False}
            state['probe_returns'].append(row)
            try:
                row['caller'], exact = probe_caller(frame, policy)
                sock = frame.f_locals.get('sock')
                row['same_bound_socket'] = sock is probe['socket']
                row['socket'] = socket_record(sock)
                row['closed_fd_at_return'] = row['socket'].get('fileno') == -1
                row['passed'] = bool(exact and row['exact_bool_return'] and row['same_bound_socket']
                    and row['socket']['exact_socket_type'] and row['closed_fd_at_return'])
            except BaseException as exc:
                row['collection_error'] = value_record(exc)
                state['collection_errors'].append(row)
            # Do not replace the dependency return value or force its outcome.
    return capture, profile, state


def probe_terminal(config, state):
    policy = config.get('loopback_probe')
    module = sys.modules.get(policy['module']) if type(policy) is dict else None
    md = module_dict(module) if type(module) is types.ModuleType else None
    value = md.get('HAS_IPV6') if type(md) is dict else None
    returns = state['probe_returns']
    bool_value = value if type(value) is bool else None
    fn = md.get('_has_ipv6') if type(md) is dict else None
    allowed = state['allowed_bind_events']
    module_identity_exact = (len(allowed) == 1 and type(md) is dict
        and value_record(module)['object_id'] == allowed[0]['caller']['module_object']['object_id']
        and type(fn) is types.FunctionType and fn.__globals__ is md
        and complete_probe_code_identity(fn.__code__) == policy['function']['code']
        and type(md.get('__file__')) is str and md['__file__'] == policy['function']['filename']
        and type(md.get('__name__')) is str and md['__name__'] == policy['module'])
    result = {'module': value_record(module), 'HAS_IPV6': bool_value,
              'HAS_IPV6_exact_bool': type(value) is bool, 'module_identity_exact': module_identity_exact,
              'allowed_bind_count': len(state['allowed_bind_events']),
              'denied_event_count': len(state['denied_events']),
              'probe_return_count': len(returns),
              'audit_allowance_is_not_syscall_success': True,
              'interpretation': 'The original function return and original module HAS_IPV6 are observed, not patched or recomputed; audit alone does not establish bind success.'}
    result['passed'] = (len(state['allowed_bind_events']) == 1 and not state['denied_events']
        and not state['collection_errors'] and len(returns) == 1 and returns[0]['passed']
        and module_identity_exact and type(value) is bool and returns[0]['return_value'].get('scalar') is value)
    return result


def install_guards(config):
    forbidden_calls = []
    capture_network, profile_network, network_state = network_guard(config)
    denied_network = network_state['denied_events']
    denied_profile_imports = []
    denied_process_events = []
    model_files = {str(Path(config['target']) / value) for value in CLASS_FILES.values()}
    def profile(frame, event, arg):
        profile_network(frame, event, arg)
        if event == 'call' and frame.f_code.co_filename in model_files and frame.f_code.co_name in ('__init__', 'forward'):
            record = {'filename': frame.f_code.co_filename, 'name': frame.f_code.co_qualname,
                      'firstlineno': frame.f_code.co_firstlineno}
            forbidden_calls.append(record)
            raise RuntimeError('model/config construction or forward is forbidden in this import-only gate')
    def audit(event, args):
        if event in ('subprocess.Popen', 'os.fork', 'os.forkpty', 'os.posix_spawn', 'os.exec', 'os.system'):
            denied_process_events.append({'event': event})
            raise RuntimeError('child process creation and program execution forbidden in import-only gate')
        if event == 'import' and args and type(args[0]) is str and any(args[0] == p or args[0].startswith(p + '.') for p in config.get('excluded_module_prefixes', [])):
            denied_profile_imports.append({'module': args[0]})
            raise RuntimeError('GUI module outside this import-only profile')
        if event.startswith('socket.'):
            capture_network(event, args, sys._getframe(1), 'audit')
    sys.addaudithook(audit)
    sys.setprofile(profile)
    return forbidden_calls, denied_network, denied_profile_imports, denied_process_events, network_state


def run(config, out):
    need(config['limits'] == LIMITS, 'fixed import-only limits mismatch')
    need(list(sys.version_info[:2]) == config['python_major_minor'] == [3, 12], 'Python version mismatch')
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'isolated -I -S -B required')
    need(sys.flags.optimize == config['python_optimization'] == 0, 'nonoptimized worker required for code identities')
    need(len(os.sched_getaffinity(0)) == 1, 'exactly one affinity CPU required')
    need(resource.getrlimit(resource.RLIMIT_CPU) == (30, 30), '30 CPU-second hard limit required')
    need(resource.getrlimit(resource.RLIMIT_AS) == tuple(config['_launch_rlimit_as']), 'RLIMIT_AS was changed')
    sys.path[:] = [config['target'], config['runtime'], config['stdlib'], str(Path(config['stdlib']) / 'lib-dynload'), config['gate_directory']]
    write_new(out / 'WORKER_BEFORE.json', {
        'pid': os.getpid(), 'ppid': os.getppid(), 'process': process_stat(os.getpid()),
        'affinity': sorted(os.sched_getaffinity(0)), 'sys_path': sys.path,
        'rlimit_cpu': resource.getrlimit(resource.RLIMIT_CPU),
        'rlimit_as': resource.getrlimit(resource.RLIMIT_AS), 'rlimit_as_changed': False,
        'environment': dict(sorted(os.environ.items())),
        'scope': config['scope'], 'pyc_note': '-B prevents writes, not reads; existing cache file paths are separately pinned and verified',
    })
    forbidden, network, denied_profile, denied_process, network_state = install_guards(config)
    installed_profile = sys.getprofile()
    imported = {}
    error = None
    started = time.monotonic()
    try:
        # These are real upstream package/module imports. Never AST exec, mocks,
        # from_pretrained, a config/model instance, tensor work, or forward calls.
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
        versions = {}
    finally:
        profile_intact = sys.getprofile() is installed_profile
        sys.setprofile(None)
    # Persist all raw module and map observations BEFORE any closure validation.
    modules = collect_modules(sys.modules)
    maps_text = Path('/proc/self/maps').read_text()
    maps = parse_maps(maps_text)
    write_new(out / 'MODULES.json', {'modules': modules, 'count': len(modules),
                                   'truncated': False, 'snapshot_phase': 'after_normal_import_attempt_before_validation'})
    with (out / 'MAPS.txt').open('x') as f:
        f.write(maps_text)
        f.flush()
        os.fsync(f.fileno())
    write_new(out / 'MAPS.json', {'maps': maps, 'count': len(maps), 'truncated': False})
    write_new(out / 'IMPORT_ATTEMPT.json', {'import_error': error, 'versions': versions,
               'elapsed_before_validation_seconds': time.monotonic() - started,
               'forbidden_model_calls': forbidden, 'denied_network_events': network, 'denied_profile_imports': denied_profile, 'denied_process_events': denied_process})
    terminal_probe = probe_terminal(config, network_state)
    write_new(out / 'NETWORK_EVENTS.json', network_state)
    write_new(out / 'LOOPBACK_PROBE_TERMINAL.json', terminal_probe)
    closure = verify_observed_files(modules, maps, config['file_manifest'], mapped_manifest=config['mapped_file_manifest'])
    write_new(out / 'FILE_CLOSURE.json', closure)
    classes = {}
    class_errors = {}
    for name, cls in imported.items():
        try:
            need(type(cls) is type, 'selected binding must have exact built-in type metaclass')
            class_module = type.__getattribute__(cls, '__dict__').get('__module__')
            need(type(class_module) is str, 'selected class module must be an exact string')
            module = sys.modules[class_module]
            classes[name] = actual_class_identity(cls, config['selected_classes'][name], module)
        except BaseException as exc:
            class_errors[name] = {'type': type(exc).__name__, 'message': str(exc)}
    write_new(out / 'CLASS_IDENTITIES.json', {'classes': classes, 'errors': class_errors,
                                             'requested': list(CLASS_FILES), 'truncated': False})
    try:
        bindings = selected_bindings(imported, sys.modules) if imported else {'passed': False, 'not_reached': True}
    except Exception as exc:
        bindings = {'passed': False, 'error': {'type': type(exc).__name__, 'message': str(exc)}}
    write_new(out / 'BINDINGS.json', bindings)
    source_check = {rel: {'actual': file_id(Path(config['target']) / rel), 'expected': pin}
                    for rel, pin in config['upstream'].items()}
    write_new(out / 'UPSTREAM_IDENTITIES.json', source_check)
    dynamic = [m['name'] for m in modules if m['kind'] not in ('file_backed', 'built-in', 'frozen', 'none_sentinel')]
    passed = (error is None and versions == config['expected_versions'] and closure['passed'] and not class_errors
              and set(classes) == set(CLASS_FILES) and bindings['passed']
              and all(c['own_method_code_exact'] and c['module_file_exact'] and c['class_name_exact'] and c['class_module_exact'] for c in classes.values())
              and all(c['actual'] == c['expected'] for c in source_check.values()) and not forbidden and not network and not denied_profile and not denied_process and terminal_probe['passed'] and profile_intact)
    result = {
        'status': 'PASS_IMPORT_FILES_AND_SELECTED_CLASSES_WITH_DIAGNOSTIC_LIMITS' if passed else 'FAIL_IMPORT_GATE',
        'passed': passed, 'normal_import_succeeded': error is None,
        'versions': versions, 'file_closure_passed': closure['passed'], 'selected_bindings_passed': bindings['passed'],
        'selected_classes_exact': bool(classes) and not class_errors and all(c['own_method_code_exact'] for c in classes.values()),
        'dynamic_no_file_modules': dynamic, 'dynamic_code_origin_proven': False,
        'all_live_code_objects_identity_proven': False,
        'diagnostic_limits': [
            'Every sys.modules entry and every process-map line at this snapshot is retained; this is not a lifetime trace of transient modules or mappings.',
            'All observed file origins are individually checked against the presealed file manifest. File provenance is not proof of every live code object.',
            'No-file dynamic modules retain all dictionary-member names/types and directly reachable Python function/class-method code trees. Transitive object graphs and native-generated code origins are not proven.',
            'Built-in/frozen module labels are recorded under the pinned interpreter. Anonymous/native dynamic executable mappings are not attested as source code.',
            'Selected upstream classes verify complete own source and own recursive method code trees; inherited methods rely on file provenance, not complete code-object identity.',
            'Only one source/code/module/socket/address-bound loopback bind may be allowed. All other socket audit operations except construction are denied. Profile c_call guards cover observed native listen/send/accept/receive calls on this thread where CPython has no audit event. These are not OS isolation or proof about native/unprofiled-thread bypasses.',
            'RLIMIT_CPU is per worker process including its threads, not an aggregate process-tree CPU quota; guarded Python child creation is denied.',
        ],
        'import_error': error, 'forbidden_model_calls': forbidden, 'denied_network_events': network, 'denied_profile_imports': denied_profile, 'denied_process_events': denied_process,
        'profile_remained_installed_until_import_end': profile_intact,
        'loopback_probe_terminal': terminal_probe, 'network_policy': network_state['coverage'],
        'scope': config['scope'], 'user_model_execution': False, 'numerical_pass': False,
        'rusage_self': {'user_cpu_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime,
                        'system_cpu_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_stime,
                        'ru_maxrss_bytes_linux': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024},
        'process': process_stat(os.getpid()), 'elapsed_seconds': time.monotonic() - started,
    }
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
    cap = claim(a.capability_fd, config, a.config_sha256, out)
    config['_launch_rlimit_as'] = cap['rlimit_as_unchanged']
    try:
        return run(config, out)
    except BaseException as exc:
        write_new(out / 'WORKER_FAILURE.json', {'type': type(exc).__name__, 'message': str(exc),
                  'traceback': traceback.format_exc(), 'process': process_stat(os.getpid())})
        return 3

if __name__ == '__main__':
    raise SystemExit(main())
