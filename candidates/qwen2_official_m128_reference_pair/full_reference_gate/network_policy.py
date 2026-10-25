"""Exact read-only helper copy from frozen r2; see NETWORK_HELPER_PROVENANCE.json."""
import os
import socket
import _socket
import stat
import sys
import types
from gate_common import (value_record, module_dict, code_inventory, file_id, complete_probe_code_identity)

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

