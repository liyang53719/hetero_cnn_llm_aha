"""Stdlib-only evidence utilities. Importing this file never imports ML packages."""
from __future__ import annotations
import ast
import hashlib
import importlib.machinery
import importlib._bootstrap_external
import json
import marshal
import os
from pathlib import Path
import re
import stat
import types

UPSTREAM = {
    'transformers/models/qwen2/modeling_qwen2.py': 'f1c7a117ced20ee632e4c17d09982863304d6e30bb44f0ccdebd4b27dde259ad',
    'transformers/models/qwen2/configuration_qwen2.py': '71aa00c48b4b586e283033afe11ce9df8c3e9bbc51613e11cd0617b103c5582b',
    'transformers/activations.py': '10c37e915ce2b52d539a5b52ecaaf644e2b0c56d282db00778098d74342ebeee',
}
CLASS_FILES = {
    'Qwen2Config': 'transformers/models/qwen2/configuration_qwen2.py',
    'Qwen2DecoderLayer': 'transformers/models/qwen2/modeling_qwen2.py',
    'Qwen2Attention': 'transformers/models/qwen2/modeling_qwen2.py',
    'Qwen2MLP': 'transformers/models/qwen2/modeling_qwen2.py',
}
LIMITS = {
    'affinity_count': 4, 'cpu_seconds_hard': 120, 'wall_seconds': 180,
    'sampled_tree_rss_bytes': 1610612736, 'rss_is_hard_cap': False,
    'poll_seconds': 0.02, 'cleanup_seconds': 2,
    'log_bytes_each': 1048576, 'output_bytes': 83886080,
    'address_space_limit_changed': False, 'threads_env': 4, 'interop_threads': 1,
    'deterministic_algorithms': True,
}
GATE_FILES = ('gate_common.py', 'prepare_gate.py', 'worker.py', 'run_gate.py',
              'network_policy.py', 'validate_outputs.py')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_id(path):
    p = Path(path)
    h = hashlib.sha256()
    count = 0
    with p.open('rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode), 'not a regular file: ' + str(p))
        while data := stream.read(1048576):
            h.update(data)
            count += len(data)
        after = os.fstat(stream.fileno())
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
         'file changed while hashing: ' + str(p))
    need(count == before.st_size, 'short file read: ' + str(p))
    return {'bytes': count, 'sha256': h.hexdigest()}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode()


def write_new(path, value):
    raw = encoded(value)
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'bytes': len(raw), 'sha256': sha(raw)}


def read_checked(path, expected_sha, maximum=33554432):
    raw = Path(path).read_bytes()
    need(len(raw) <= maximum, 'JSON exceeds size boundary')
    need(sha(raw) == expected_sha, 'exact JSON SHA256 mismatch: ' + str(path))
    return json.loads(raw)


def process_stat(pid):
    try:
        raw = Path('/proc/%d/stat' % pid).read_text()
        tail = raw[raw.rfind(')') + 2:].split()
        return {'pid': pid, 'state': tail[0], 'ppid': int(tail[1]),
                'pgrp': int(tail[2]), 'start_ticks': int(tail[19]),
                'rss_bytes': int(tail[21]) * os.sysconf('SC_PAGE_SIZE')}
    except (FileNotFoundError, ProcessLookupError):
        return None


def code_inventory(code):
    """All nested code constants retained. No exec and no bytecode decompilation."""
    return {
        'name': code.co_name, 'qualname': code.co_qualname,
        'filename': code.co_filename, 'firstlineno': code.co_firstlineno,
        'marshal_sha256': sha(marshal.dumps(code)),
        'bytecode_sha256': sha(code.co_code),
        'nested': [code_inventory(c) for c in code.co_consts if isinstance(c, types.CodeType)],
    }


def class_static_identity(raw, name, filename):
    tree = ast.parse(raw, filename=filename)
    matches = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    need(len(matches) == 1, 'exactly one top-level class required: ' + name)
    node = matches[0]
    first = min([node.lineno] + [n.lineno for n in node.decorator_list])
    source = b''.join(raw.splitlines(keepends=True)[first-1:node.end_lineno])
    full_code = compile(raw, filename, 'exec', dont_inherit=True, optimize=0)
    class_codes = [c for c in full_code.co_consts if isinstance(c, types.CodeType) and c.co_name == name]
    need(len(class_codes) == 1, 'exact class code constant required: ' + name)
    methods = {c.co_name: code_inventory(c) for c in class_codes[0].co_consts
               if isinstance(c, types.CodeType)}
    names = [c.co_name for c in class_codes[0].co_consts if isinstance(c, types.CodeType)]
    need(len(names) == len(set(names)), 'duplicate class code names not supported')
    return {'name': name, 'file_sha256': sha(raw), 'filename': filename,
            'lines': [first, node.end_lineno], 'source_sha256': sha(source),
            'ast_sha256': sha(ast.dump(node, include_attributes=False).encode()),
            'methods': methods,
            'scope': 'complete own class source and own method code trees; inherited methods are not selected-class code'}


LOOPBACK_MODULE = 'urllib3.util.connection'
LOOPBACK_RELATIVE = 'urllib3/util/connection.py'
LOOPBACK_SOURCE_SHA256 = 'd28efdfb935b45fa410f2a1e8463cb982039e38b024a25efc74985f71cb7186d'


def complete_probe_code_identity(code):
    """Full code including constants, exceptions, lines, flags and nested code.

    Marshal v2 avoids v3/v4 reference-sharing flags that can change with live
    code/reference counts. This is not a bytecode-only or source-name identity.
    """
    need(type(code) is types.CodeType, 'exact Python code object required')
    return {'name': code.co_name, 'qualname': code.co_qualname,
            'filename': code.co_filename, 'firstlineno': code.co_firstlineno,
            'marshal_version': 2, 'complete_marshal_sha256': sha(marshal.dumps(code, 2)),
            'bytecode_sha256': sha(code.co_code),
            'nested': [complete_probe_code_identity(c) for c in code.co_consts if type(c) is types.CodeType]}


def function_static_identity(raw, name, filename):
    """Compile only; never execute dependency source or call its function."""
    tree = ast.parse(raw, filename=filename)
    matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    need(len(matches) == 1, 'exact top-level probe function required')
    node = matches[0]
    first = min([node.lineno] + [n.lineno for n in node.decorator_list])
    body = b''.join(raw.splitlines(keepends=True)[first - 1:node.end_lineno])
    full = compile(raw, filename, 'exec', dont_inherit=True, optimize=0)
    codes = [c for c in full.co_consts if type(c) is types.CodeType and c.co_name == name]
    need(len(codes) == 1, 'exact probe code constant required')
    return {'name': name, 'filename': filename, 'file_sha256': sha(raw),
            'file_bytes': len(raw), 'source_sha256': sha(body),
            'lines': [first, node.end_lineno], 'code': complete_probe_code_identity(codes[0]),
            'static_diagnostic_marshal_v4_sha256': sha(marshal.dumps(codes[0], 4))}


def loopback_probe_policy(target):
    path = Path(target) / LOOPBACK_RELATIVE
    raw = path.read_bytes()
    need(sha(raw) == LOOPBACK_SOURCE_SHA256, 'unapproved urllib3 probe source')
    return {'module': LOOPBACK_MODULE, 'function': function_static_identity(raw, '_has_ipv6', str(path)),
            'address': ['::1', 0], 'socket_family': 10, 'socket_type': 1, 'socket_proto': 0,
            'maximum_allowed_bind_events': 1, 'required_allowed_bind_events': 1,
            'require_same_module_globals_and_function_code': True,
            'require_normal_boolean_return_and_closed_socket': True,
            'audit_allowance_is_not_syscall_success': True,
            'scope': 'one exact dependency IPv6 loopback port-zero bind; no connect/listen/send/accept permission'}


def actual_class_identity(cls, expected, module):
    """Do not instantiate or invoke descriptors; compare every own Python method."""
    need(type(cls) is type, 'selected class must have exact built-in type metaclass')
    cd = type.__getattribute__(cls, '__dict__')
    md = module_dict(module)
    need(type(md) is dict, 'selected class module must be a real module')
    name = type.__getattribute__(cls, '__name__')
    module_name = cd.get('__module__')
    module_file = md.get('__file__')
    need(type(name) is str and type(module_name) is str and type(module_file) is str,
         'selected class metadata must have exact string types')
    actual = {'name': name, 'module': module_name, 'methods': own_method_codes(cd),
              'module_file': module_file, 'expected': expected}
    actual['own_method_code_exact'] = actual['methods'] == expected['methods']
    actual['module_file_exact'] = actual['module_file'] == expected['filename']
    actual['class_name_exact'] = actual['name'] == expected['name']
    actual['class_module_exact'] = actual['module'] == md.get('__name__')
    return actual


def selected_bindings(imported, modules):
    """Read-only object identity checks. Never invoke ACT2FN.__getitem__."""
    md = module_dict(modules['transformers.models.qwen2.modeling_qwen2'])
    cd = module_dict(modules['transformers.configuration_utils'])
    nd = module_dict(modules['torch.nn'])
    ad = module_dict(modules['transformers.activations'])
    need(all(type(d) is dict for d in (md, cd, nd, ad)), 'binding source must be a real module dictionary')
    config, layer = imported['Qwen2Config'], imported['Qwen2DecoderLayer']
    need(type(config) is type and type(layer) is type, 'binding classes require exact built-in type metaclass')
    config_bases = type.__getattribute__(config, '__bases__')
    layer_bases = type.__getattribute__(layer, '__bases__')
    table = md.get('QWEN2_ATTENTION_CLASSES')
    need(type(table) is dict, 'attention registry must be an exact dictionary')
    checks = {
        'Qwen2Config_base_is_PretrainedConfig': len(config_bases) == 1 and config_bases[0] is cd.get('PretrainedConfig'),
        'Qwen2DecoderLayer_base_is_torch_nn_Module': len(layer_bases) == 1 and layer_bases[0] is nd.get('Module'),
        'attention_registry_exact_keys': set(table) == {'eager', 'flash_attention_2', 'sdpa'},
        'eager_registry_identity': table.get('eager') is imported['Qwen2Attention'],
        'flash_registry_identity': table.get('flash_attention_2') is md.get('Qwen2FlashAttention2'),
        'sdpa_registry_identity': table.get('sdpa') is md.get('Qwen2SdpaAttention'),
        'MLP_global_binding_identity': md.get('Qwen2MLP') is imported['Qwen2MLP'],
    }
    mapping = ad.get('ACT2FN')
    need(type(mapping) is ad.get('ClassInstantier') and issubclass(type(mapping), dict), 'ACT2FN must be actual ClassInstantier dict subclass')
    checks['modeling_ACT2FN_is_activations_mapping'] = md.get('ACT2FN') is mapping
    checks['ACT2FN_raw_silu_class_is_torch_nn_SiLU'] = dict.__getitem__(mapping, 'silu') is nd.get('SiLU')
    return {'checks': checks, 'passed': all(checks.values()),
            'scope': 'listed direct bases and registry identities only; no construction and no complete dynamic globals identity claim'}


def parse_maps(text):
    result = []
    for line in text.splitlines():
        fields = line.split(maxsplit=5)
        need(len(fields) >= 5, 'malformed /proc maps line')
        pathname = fields[5] if len(fields) == 6 else None
        decoded = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), pathname) if pathname else None
        result.append({'raw': line, 'address': fields[0], 'permissions': fields[1],
                       'offset': fields[2], 'device': fields[3], 'inode': int(fields[4]),
                       'pathname': pathname, 'decoded_pathname': decoded,
                       'kind': 'file' if decoded and decoded.startswith('/') else
                               'named_nonfile' if decoded else 'anonymous'})
    return result


KINDS = ((type(None), 'none'), (str, 'str'), (bool, 'bool'), (int, 'int'), (float, 'float'),
         (types.ModuleType, 'module'), (types.FunctionType, 'python_function'),
         (types.BuiltinFunctionType, 'builtin_function'), (type, 'builtin_type'),
         (types.GetSetDescriptorType, 'getset_descriptor'),
         (types.MemberDescriptorType, 'member_descriptor'),
         (types.MethodDescriptorType, 'method_descriptor'),
         (types.WrapperDescriptorType, 'wrapper_descriptor'))


def value_record(value):
    """Never query unknown names, repr, str, equality, iteration, or descriptors."""
    actual = type(value)
    label = next((label for kind, label in KINDS if actual is kind), 'other')
    result = {'object_id': hex(id(value)), 'type_object_id': hex(id(actual)), 'builtin_kind': label}
    if actual is str or actual is bool or value is None:
        result['scalar'] = value
    return result


def module_dict(module):
    # Invoke only the known built-in descriptor, not a ModuleType subclass override.
    if issubclass(type(module), types.ModuleType):
        return types.ModuleType.__dict__['__dict__'].__get__(module, types.ModuleType)
    return None


def own_method_codes(class_dict):
    result = {}
    for key, obj in class_dict.items():
        if type(key) is not str:
            continue
        if type(obj) is types.FunctionType:
            result[key] = code_inventory(obj.__code__)
        elif type(obj) is staticmethod or type(obj) is classmethod:
            if type(obj.__func__) is types.FunctionType:
                result[key] = code_inventory(obj.__func__.__code__)
        elif type(obj) is property:
            for suffix, fn in (('fget', obj.fget), ('fset', obj.fset), ('fdel', obj.fdel)):
                if type(fn) is types.FunctionType:
                    result[key + '.' + suffix] = code_inventory(fn.__code__)
    return result


def nofile_members(d):
    """Every dictionary member retained without evaluating unknown objects.

    Only exact Python functions and exact built-in-type class dictionaries are
    inspected for code. Opaque metatypes remain explicitly unproven metadata.
    """
    records = []
    for name, value in list(d.items()):
        record = {'name': name if type(name) is str else None,
                  'name_metadata': value_record(name), 'value': value_record(value)}
        try:
            if type(value) is types.FunctionType:
                record['code'] = code_inventory(value.__code__)
            elif type(value) is type:
                cd = type.__getattribute__(value, '__dict__')
                cm = cd.get('__module__')
                record['class_module'] = cm if type(cm) is str else None
                record['class_module_metadata'] = value_record(cm)
                record['own_methods'] = own_method_codes(cd)
        except Exception as exc:
            record['collection_error'] = value_record(exc)
        records.append(record)
    return records


def static_path_record(value):
    actual = value
    if type(value) is importlib._bootstrap_external._NamespacePath:
        actual = object.__getattribute__(value, '__dict__').get('_path')
    if type(actual) is list or type(actual) is tuple:
        return {'entries': [x if type(x) is str else None for x in actual],
                'entry_metadata': [value_record(x) for x in actual], 'object': value_record(value)}
    return {'entries': None, 'object': value_record(value)}


def collect_modules(modules):
    result = []
    # Do not sort/equality-compare unknown dictionary keys.
    for name, mod in list(modules.items()):
        record = {'name': name if type(name) is str else None,
                  'name_metadata': value_record(name), 'module': value_record(mod), 'errors': []}
        try:
            if mod is None:
                record['kind'] = 'none_sentinel'
                result.append(record)
                continue
            d = module_dict(mod)
            if type(d) is not dict:
                record['kind'] = 'non_module_entry'
                record['code_origin_proven'] = False
                result.append(record)
                continue
            spec = d.get('__spec__')
            sd = vars(spec) if type(spec) is importlib.machinery.ModuleSpec else {}
            raw_file, raw_origin = d.get('__file__'), sd.get('origin')
            file = raw_file if type(raw_file) is str else None
            origin = raw_origin if type(raw_origin) is str else None
            cached, package = d.get('__cached__'), d.get('__package__')
            record.update({'file': file, 'file_metadata': value_record(raw_file),
                           'cached': cached if type(cached) is str else None,
                           'cached_metadata': value_record(cached), 'spec_origin': origin,
                           'spec_origin_metadata': value_record(raw_origin), 'spec': value_record(spec),
                           'spec_has_location': sd.get('_set_fileattr') if type(sd.get('_set_fileattr')) is bool else None,
                           'spec_has_location_metadata': value_record(sd.get('_set_fileattr')),
                           'spec_loader': value_record(sd.get('loader')),
                           'package': package if type(package) is str else None,
                           'package_metadata': value_record(package),
                           'path': static_path_record(d.get('__path__'))})
            if file:
                record['kind'] = 'file_backed'
            elif origin in ('built-in', 'frozen'):
                record['kind'] = origin
            elif type(spec) is importlib.machinery.ModuleSpec and raw_origin is None and '__path__' in d:
                record['kind'] = 'namespace_or_dynamic'
            else:
                record['kind'] = 'dynamic_no_file_unproven'
            if record['kind'] not in ('file_backed', 'built-in', 'frozen'):
                record['all_dictionary_members'] = nofile_members(d)
                record['code_origin_proven'] = False
            # Metadata of unexpected objects is evidence, never a file identity pass.
            if raw_file is not None and type(raw_file) is not str:
                record['errors'].append({'kind': 'nonstring_file_metadata', 'value': value_record(raw_file)})
            if raw_origin is not None and type(raw_origin) is not str:
                record['errors'].append({'kind': 'nonstring_origin_metadata', 'value': value_record(raw_origin)})
        except Exception as exc:
            record['kind'] = 'collection_error_unproven'
            record['errors'].append({'kind': 'module_collection_error', 'error': value_record(exc)})
        result.append(record)
    return result


def verify_observed_files(modules, maps, manifest, identity=file_id, mapped_manifest=None):
    """No basename/root-only allowlist. Every actual file is individually hashed."""
    references = {}
    issues = []
    nonfile_origins = []
    for item in modules:
        if item.get('errors'):
            issues.append({'module': item.get('name'), 'problem': 'module_metadata_collection_errors', 'errors': item['errors']})
        for field in ('file', 'spec_origin', 'cached'):
            value = item.get(field)
            if not value or value in ('built-in', 'frozen'):
                continue
            if (field == 'spec_origin' and type(value) is str and not Path(value).is_absolute()
                    and item.get('file') is None and item.get('spec_has_location') is False):
                nonfile_origins.append({'module': item.get('name'), 'origin': value,
                                        'has_location': False, 'file': None, 'code_origin_proven': False})
                continue
            if not isinstance(value, str) or not Path(value).is_absolute():
                issues.append({'module': item['name'], 'field': field, 'problem': 'nonabsolute_file_origin', 'value': value})
                continue
            # __cached__ may denote a never-written .pyc; preserve but do not pretend it was loaded.
            if field == 'cached' and not Path(value).exists():
                continue
            references.setdefault(value, []).append('module:' + (item['name'] if type(item.get('name')) is str else '<nonstring-key>') + ':' + field)
    for item in maps:
        if item['kind'] == 'file':
            references.setdefault(item['decoded_pathname'], []).append('map:' + item['address'])
    verified = {}
    for raw_path, refs in sorted(references.items()):
        path = Path(raw_path)
        record = {'references': refs, 'observed_path': raw_path}
        try:
            canonical = str(path.resolve(strict=True))
            record['canonical_path'] = canonical
            actual = identity(path)
            record['actual'] = actual
            record['expected'] = manifest.get(canonical)
            record['exact'] = actual == manifest.get(canonical)
            if mapped_manifest is not None and any(ref.startswith('map:') for ref in refs):
                record['mapping_expected'] = mapped_manifest.get(canonical)
                record['mapping_exact'] = actual == mapped_manifest.get(canonical)
                record['exact'] = record['exact'] and record['mapping_exact']
            if not record['exact']:
                issues.append({'path': raw_path, 'problem': 'unmanifested_or_hash_mismatch'})
        except (OSError, ValueError) as exc:
            record['exact'] = False
            record['error'] = type(exc).__name__ + ': ' + str(exc)
            issues.append({'path': raw_path, 'problem': 'unreadable_file_origin'})
        verified[raw_path] = record
    return {'files': verified, 'issues': issues, 'nonfile_origin_markers': nonfile_origins, 'passed': not issues,
            'scope': 'observed module file/spec/cache paths and file-backed process maps; not all live code objects'}
