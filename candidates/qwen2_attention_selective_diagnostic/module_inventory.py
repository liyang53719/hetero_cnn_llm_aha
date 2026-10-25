"""Complete, fail-closed module identity inventory; no task/native imports.

Collection never raises for an individual bad module and never reads an unpinned
file. Unknown paths retain stat metadata and an explicit unavailable-hash reason.
Every sys.modules key is retained, including aliases and None sentinels. This is
an identity audit, not proof that arbitrary already-executed code was unmodified.

collect_modules(...): JSON-safe report, including ALL failures, no validation raise.
persist_and_validate(...): exclusive durable JSON first, then aggregate rejection.
validate_modules(...): for callers that already persisted this and related ledgers.

An ordinary namespace needs explicit {name: {'paths': [canonical directories]}}.
A synthetic namespace needs exact object/path/children and a source/code-bound
creator; it is never classified as normal loaded source. Synthetic AST modules
need explicit source and exact top-level definition bindings, without executing
that source. No generic no-file allowlist or name-prefix exemption exists.
"""
import _imp
import ast
import hashlib
import importlib.machinery as machinery
import json
import marshal
import os
from pathlib import Path
import stat
import sys
import types


class ModuleInventoryError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__('runtime module inventory failed: %d differences; full evidence retained' % len(report['failures']))


def _typename(value):
    cls = value if isinstance(value, type) else type(value)
    return type.__getattribute__(cls, '__module__') + '.' + type.__getattribute__(cls, '__qualname__')


def _scalar(value):
    return value if value is None or type(value) in (str, int, bool) else {'type': _typename(value)}


def _error(errors, code, detail):
    errors.append({'code': code, 'detail': str(detail)})


def _file_identity(value, files, cache):
    row = {'path': _scalar(value), 'realpath': None, 'bytes': None, 'sha256': None,
           'pinned': False, 'pin': None, 'match': False, 'hash_status': 'not_read', 'errors': []}
    errors = row['errors']
    if type(value) is not str or not value or not os.path.isabs(value):
        _error(errors, 'invalid_absolute_path', _scalar(value)); return row
    try:
        real = os.path.realpath(value, strict=True)
        row['realpath'] = real
        if value != real:
            _error(errors, 'noncanonical_path', value + ' -> ' + real)
        if real in cache:
            cached = dict(cache[real], path=value)
            cached['errors'] = list(cache[real]['errors']) + errors
            cached['match'] = not cached['errors']
            return cached
        before = os.stat(real, follow_symlinks=False)
        row.update(bytes=before.st_size, device=before.st_dev, inode=before.st_ino)
        if not stat.S_ISREG(before.st_mode):
            _error(errors, 'not_regular_file', real); return row
        pin = files.get(real)
        row['pinned'] = pin is not None
        if pin is None:
            row['hash_status'] = 'unbound_path_not_read'
            _error(errors, 'unknown_path', real)
        elif (type(pin) is not dict or type(pin.get('bytes')) is not int or pin['bytes'] < 0 or
              type(pin.get('sha256')) is not str or len(pin['sha256']) != 64 or
              any(c not in '0123456789abcdef' for c in pin['sha256'])):
            row['hash_status'] = 'invalid_pin_not_read'
            _error(errors, 'invalid_pin', real)
        else:
            row['pin'] = {k: pin[k] for k in ('bytes', 'sha256')}
            digest = hashlib.sha256()
            fd = os.open(real, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode):
                    raise ValueError('opened file is not regular')
                while chunk := stream.read(1 << 20):
                    digest.update(chunk)
                after = os.fstat(stream.fileno())
            row.update(sha256=digest.hexdigest(), hash_status='computed')
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if stamp(before) != stamp(opened) or stamp(opened) != stamp(after):
                _error(errors, 'file_changed_during_read', real)
            if before.st_size != pin['bytes']:
                _error(errors, 'bytes_mismatch', real)
            if row['sha256'] != pin['sha256']:
                _error(errors, 'sha256_mismatch', real)
        row['match'] = not errors
        if value == real:
            cache[real] = row
    except (OSError, ValueError, TypeError) as error:
        _error(errors, 'file_identity_error', type(error).__name__ + ': ' + str(error))
    return row


def _paths(value, errors, label):
    # Do not trigger lazy namespace recalculation or arbitrary __iter__ hooks.
    namespace_type = vars(sys.modules['_frozen_importlib_external'])['_NamespacePath']
    if type(value) is namespace_type:
        value = vars(value).get('_path')
    if type(value) not in (list, tuple):
        _error(errors, label + '_invalid', 'static list/tuple or exact CPython namespace path required'); return None
    paths = list(value)
    if paths is None or any(type(p) is not str for p in paths):
        _error(errors, label + '_invalid', 'expected path string sequence'); return None
    return paths


def _namespace_dirs(actual, declared, files, errors):
    result = []
    if type(declared) is not list or not declared or any(type(p) is not str for p in declared):
        _error(errors, 'namespace_registration_invalid', 'nonempty exact path list required'); return result
    if len(set(declared)) != len(declared) or actual != declared:
        _error(errors, 'namespace_path_mismatch', 'actual path differs from registered ordered path list')
    for path in declared:
        item = {'path': path, 'realpath': None, 'entries': [], 'pinned_descendants': []}
        try:
            item['realpath'] = os.path.realpath(path, strict=True)
            if not os.path.isabs(path) or path != item['realpath'] or not os.path.isdir(path):
                _error(errors, 'namespace_noncanonical_directory', path)
            prefix = path + os.sep
            item['pinned_descendants'] = sorted(p for p in files if type(p) is str and p.startswith(prefix) and Path(p).suffix in ('.py', '.so'))
            if not item['pinned_descendants']:
                _error(errors, 'namespace_without_pinned_descendant', path)
            with os.scandir(path) as entries:
                for entry in entries:
                    item['entries'].append({'name': entry.name,
                        'kind': 'symlink' if entry.is_symlink() else 'directory' if entry.is_dir(follow_symlinks=False) else 'file',
                        'pinned': entry.path in files})
            item['entries'].sort(key=lambda x: x['name'])
        except (OSError, ValueError) as error:
            _error(errors, 'namespace_directory_error', path + ': ' + str(error))
        result.append(item)
    return result


def _code_identity(code):
    return {'name': code.co_name, 'qualname': code.co_qualname, 'filename': code.co_filename,
            'firstlineno': code.co_firstlineno, 'marshal_sha256': hashlib.sha256(marshal.dumps(code)).hexdigest()}


def _same_code(actual, expected):
    return (actual == expected and actual.co_filename == expected.co_filename and
            actual.co_firstlineno == expected.co_firstlineno and actual.co_linetable == expected.co_linetable and
            actual.co_exceptiontable == expected.co_exceptiontable)


def _pinned_source_bytes(identity):
    raw = Path(identity['realpath']).read_bytes()
    if len(raw) != identity['pin']['bytes'] or hashlib.sha256(raw).hexdigest() != identity['pin']['sha256']:
        raise ValueError('source drift between identity collection and code binding')
    return raw


def _source_function(source, function, files, cache, errors):
    identity = _file_identity(source, files, cache)
    result = {'source': identity, 'actual_code': None, 'expected_code': None, 'match': False}
    for error in identity['errors']:
        _error(errors, 'creator_source.' + error['code'], error['detail'])
    if type(function) is not types.FunctionType:
        _error(errors, 'creator_function_invalid', 'plain top-level source function required'); return result
    result['actual_code'] = _code_identity(function.__code__)
    if not identity['match']:
        return result
    try:
        # Compile only, never execute. Full-module compile preserves symbol flags.
        code = compile(_pinned_source_bytes(identity), identity['realpath'], 'exec', dont_inherit=True,
                       optimize=sys.flags.optimize)
        found = [c for c in code.co_consts if type(c) is types.CodeType and c.co_name == function.__name__]
        if len(found) != 1:
            raise ValueError('creator is not a unique top-level function')
        result['expected_code'] = _code_identity(found[0])
        result['match'] = _same_code(function.__code__, found[0])
        if not result['match']:
            _error(errors, 'creator_code_mismatch', function.__name__)
    except (OSError, ValueError, TypeError, SyntaxError) as error:
        _error(errors, 'creator_code_error', str(error))
    return result


def _synthetic(row, module, data, registration, snapshot, files, cache):
    errors = row['errors']
    kind = registration.get('kind') if type(registration) is dict else None
    if snapshot.get(data.get('__name__')) is not module:
        _error(errors, 'synthetic_canonical_object_mismatch', data.get('__name__'))
    if type(registration) is not dict or registration.get('module') is not module:
        _error(errors, 'synthetic_object_mismatch', 'exact live module object required'); return
    if data.get('__file__') is not None or data.get('__spec__') is not None or data.get('__loader__') is not None:
        _error(errors, 'synthetic_normal_identity_conflict', 'synthetic module cannot claim a normal loader/file/spec')
    if kind == 'namespace_package':
        row['kind'] = 'synthetic_namespace_package'
        expected = {'kind', 'module', 'paths', 'allowed_children', 'creator_source', 'creator_function'}
        if set(registration) != expected:
            _error(errors, 'synthetic_registration_shape', 'exact namespace registration keys required')
        children = registration.get('allowed_children')
        if type(children) is not list or any(type(c) is not str or not c or '.' in c for c in children):
            _error(errors, 'synthetic_children_invalid', 'direct child names required'); children = []
        allowed = {'__name__', '__doc__', '__package__', '__loader__', '__spec__', '__path__', *children}
        if set(data) - allowed:
            _error(errors, 'synthetic_namespace_extra_attributes', ','.join(sorted(set(data) - allowed)))
        if data.get('__package__') not in (None, data.get('__name__')) or data.get('__doc__') is not None:
            _error(errors, 'synthetic_namespace_metadata_changed', 'unexpected package/doc metadata')
        for child in children:
            full = data.get('__name__', '') + '.' + child
            if child in data and (full not in snapshot or snapshot[full] is not data[child] or type(data[child]) is not types.ModuleType):
                _error(errors, 'synthetic_child_unregistered', full)
        row['namespace_directories'] = _namespace_dirs(_paths(data.get('__path__'), errors, 'module_path'),
                                                       registration.get('paths'), files, errors)
        row['creator'] = _source_function(registration.get('creator_source'), registration.get('creator_function'),
                                          files, cache, errors)
    elif kind == 'ast_module':
        row['kind'] = 'synthetic_ast_module'
        expected = {'kind', 'module', 'source', 'definitions'}
        if set(registration) != expected:
            _error(errors, 'synthetic_registration_shape', 'exact AST registration keys required')
        definitions = registration.get('definitions')
        if type(definitions) is not list or not definitions or any(type(n) is not str for n in definitions):
            _error(errors, 'synthetic_definitions_invalid', 'nonempty function-name list required'); return
        allowed = {'__name__', '__doc__', '__package__', '__loader__', '__spec__', '__builtins__', *definitions}
        if set(data) - allowed:
            _error(errors, 'synthetic_ast_extra_attributes', ','.join(sorted(set(data) - allowed)))
        identity = _file_identity(registration.get('source'), files, cache)
        row['synthetic_source'] = identity
        row['synthetic_code'] = []
        for error in identity['errors']:
            _error(errors, 'synthetic_source.' + error['code'], error['detail'])
        if not identity['match']:
            return
        try:
            tree = ast.parse(_pinned_source_bytes(identity), filename=identity['realpath'])
            nodes = [n for n in tree.body if type(n) is ast.FunctionDef and n.name in definitions]
            if len(nodes) != len(definitions) or {n.name for n in nodes} != set(definitions):
                raise ValueError('exact unique top-level function definitions required')
            expected_module = compile(ast.Module(body=nodes, type_ignores=[]), identity['realpath'], 'exec',
                                      dont_inherit=True, optimize=sys.flags.optimize)
            for name in definitions:
                function = data.get(name)
                expected_code = next(c for c in expected_module.co_consts if type(c) is types.CodeType and c.co_name == name)
                actual_code = function.__code__ if type(function) is types.FunctionType else None
                match = actual_code is not None and function.__globals__ is data and _same_code(actual_code, expected_code)
                row['synthetic_code'].append({'binding': name, 'actual': _code_identity(actual_code) if actual_code else None,
                                               'expected': _code_identity(expected_code), 'match': match})
                if not match:
                    _error(errors, 'synthetic_code_mismatch', name)
            unregistered = [name for name, value in data.items() if type(value) in (types.FunctionType, type) and name not in definitions]
            if unregistered:
                _error(errors, 'synthetic_unregistered_code', ','.join(sorted(unregistered)))
        except (OSError, ValueError, TypeError, SyntaxError, StopIteration) as error:
            _error(errors, 'synthetic_code_error', str(error))
    else:
        _error(errors, 'synthetic_kind_unknown', kind)


def _registered_typing_namespace(row, value, registration, snapshot, files, cache):
    """Narrow CPython typing.io/re class namespaces, never a generic class allowlist."""
    errors = row['errors']
    if (type(registration) is not dict or set(registration) != {'kind', 'owner', 'attribute'} or
        registration.get('kind') != 'typing_compat_namespace' or registration.get('owner') != 'typing' or
        registration.get('attribute') not in ('io', 're')):
        _error(errors, 'registered_object_policy_invalid', row['name']); return
    attribute = registration['attribute']
    if row['name'] != 'typing.' + attribute or snapshot.get(row['name']) is not value:
        _error(errors, 'registered_object_name_mismatch', row['name']); return
    owner = snapshot.get('typing')
    if type(owner) is not types.ModuleType or owner is not sys.modules.get('typing'):
        _error(errors, 'registered_object_owner_invalid', 'exact live typing module required'); return
    owner_data = vars(owner)
    metaclass = owner_data.get('_DeprecatedType')
    if owner_data.get(attribute) is not value or type(value) is not metaclass or type(metaclass) is not type:
        _error(errors, 'registered_object_identity_mismatch', row['name']); return
    row['kind'] = 'registered_typing_compat_namespace'
    row['module_name'] = type.__getattribute__(value, '__name__')
    row['owner_module'] = 'typing'
    identity = _file_identity(owner_data.get('__file__'), files, cache)
    row['owner_source'] = identity
    for error in identity['errors']:
        _error(errors, 'registered_owner_source.' + error['code'], error['detail'])
    if not identity['match']:
        return
    try:
        raw = _pinned_source_bytes(identity)
        tree = ast.parse(raw, filename=identity['realpath'])
        classes = {node.name: node for node in tree.body if type(node) is ast.ClassDef}
        node = classes[attribute]
        if node.bases or len(node.keywords) != 1 or node.keywords[0].arg != 'metaclass' or not isinstance(node.keywords[0].value, ast.Name) or node.keywords[0].value.id != '_DeprecatedType':
            raise ValueError('typing namespace class structure changed')
        assignments = [n for n in node.body if type(n) is ast.Assign]
        if len(assignments) != len(node.body) - 1 or type(node.body[0]) is not ast.Expr:
            raise ValueError('unexpected executable namespace class statements')
        exported = ast.literal_eval(assignments[0].value)
        if (len(assignments[0].targets) != 1 or type(assignments[0].targets[0]) is not ast.Name or
            assignments[0].targets[0].id != '__all__' or type(exported) is not list or
            any(type(n) is not str for n in exported) or len(assignments) != len(exported) + 1):
            raise ValueError('typing namespace exports changed')
        references = {}
        for assignment in assignments[1:]:
            if len(assignment.targets) != 1 or type(assignment.targets[0]) is not ast.Name or type(assignment.value) is not ast.Name:
                raise ValueError('typing namespace contains a non-alias definition')
            references[assignment.targets[0].id] = assignment.value.id
        if set(references) != set(exported):
            raise ValueError('typing namespace exports/aliases differ')
        data = dict(type.__getattribute__(value, '__dict__'))
        expected_keys = {'__module__', '__doc__', '__all__', '__dict__', '__weakref__', *exported}
        if set(data) != expected_keys:
            raise ValueError('typing namespace attribute set changed')
        if (row['module_name'] != row['name'] or type.__getattribute__(value, '__qualname__') != attribute or
            type.__getattribute__(value, '__bases__') != (object,) or data['__module__'] != 'typing' or
            data['__doc__'] != ast.get_docstring(node) or data['__all__'] != exported):
            raise ValueError('typing namespace class metadata changed')
        for attr, owner_attr in references.items():
            if data[attr] is not owner_data.get(owner_attr):
                raise ValueError('typing namespace exported alias changed: ' + attr)
        for attr in ('__dict__', '__weakref__'):
            if type(data[attr]) is not types.GetSetDescriptorType or data[attr].__objclass__ is not value:
                raise ValueError('typing namespace descriptor changed')
        meta_data = dict(type.__getattribute__(metaclass, '__dict__'))
        if (set(meta_data) != {'__module__', '__doc__', '__getattribute__'} or
            meta_data['__module__'] != 'typing' or type.__getattribute__(metaclass, '__bases__') != (type,)):
            raise ValueError('typing namespace metaclass changed')
        function = meta_data['__getattribute__']
        if type(function) is not types.FunctionType or function.__globals__ is not owner_data:
            raise ValueError('typing metaclass method identity changed')
        compiled = compile(raw, identity['realpath'], 'exec', dont_inherit=True, optimize=sys.flags.optimize)
        meta_code = next(c for c in compiled.co_consts if type(c) is types.CodeType and c.co_name == '_DeprecatedType')
        expected = next(c for c in meta_code.co_consts if type(c) is types.CodeType and c.co_name == '__getattribute__')
        row['metaclass_code'] = {'actual': _code_identity(function.__code__), 'expected': _code_identity(expected)}
        if (not _same_code(function.__code__, expected) or function.__defaults__ is not None or
            function.__kwdefaults__ is not None or function.__code__.co_freevars != ('__class__',) or
            type(function.__closure__) is not tuple or len(function.__closure__) != 1 or
            function.__closure__[0].cell_contents is not metaclass):
            raise ValueError('typing metaclass source/code/closure mismatch')
        row['exported_aliases'] = references
    except (OSError, ValueError, TypeError, SyntaxError, StopIteration, KeyError) as error:
        _error(errors, 'registered_object_binding_error', str(error))


def collect_modules(modules, files, *, namespaces=None, synthetic=None, registered_objects=None):
    """Collect every mapping entry and every difference without fail-fast loss."""
    if type(modules) is not dict or type(files) is not dict:
        raise TypeError('modules snapshot and files manifest must be dictionaries')
    namespaces = {} if namespaces is None else namespaces
    synthetic = {} if synthetic is None else synthetic
    registered_objects = {} if registered_objects is None else registered_objects
    if type(namespaces) is not dict or type(synthetic) is not dict or type(registered_objects) is not dict:
        raise TypeError('explicit namespace and synthetic registrations must be dictionaries')
    snapshot = dict(modules)
    cache, groups = {}, {}
    for name, module in snapshot.items():
        groups.setdefault(id(module), []).append(_scalar(name))
    runtime = _file_identity(os.path.realpath(sys.executable), files, cache)
    rows = []
    for name, module in snapshot.items():
        row = {'name': _scalar(name), 'module_name': None, 'object_type': _typename(module),
               'object_id': hex(id(module)), 'aliases': groups[id(module)], 'kind': 'unclassified',
               '__file__': None, 'spec_origin': None, 'spec_name': None, 'loader': None,
               'spec_loader': None, 'file_identity': None, 'origin_identity': None, 'errors': []}
        rows.append(row)
        errors = row['errors']
        try:
            if type(name) is not str or not name:
                _error(errors, 'module_key_invalid', _scalar(name))
            if type(module) is not types.ModuleType:
                if name in registered_objects:
                    _registered_typing_namespace(row, module, registered_objects[name], snapshot, files, cache)
                else:
                    _error(errors, 'module_object_invalid', _typename(module))
                continue
            data = vars(module)
            row['module_name'] = _scalar(data.get('__name__'))
            row['__file__'] = _scalar(data.get('__file__'))
            loader, spec = data.get('__loader__'), data.get('__spec__')
            row['loader'] = _typename(loader) if loader is not None else None
            if type(data.get('__name__')) is not str or not data['__name__']:
                _error(errors, 'module_name_invalid', row['module_name'])
            if spec is not None and type(spec) is not machinery.ModuleSpec:
                _error(errors, 'module_spec_invalid', _typename(spec)); spec = None
            spec_data = {} if spec is None else vars(spec)
            spec_origin, spec_name, spec_loader = (spec_data.get(k) for k in ('origin', 'name', 'loader'))
            if spec is not None:
                row.update(spec_origin=_scalar(spec_origin), spec_name=_scalar(spec_name),
                           spec_loader=_typename(spec_loader) if spec_loader is not None else None)
                if loader is not spec_loader:
                    _error(errors, 'loader_spec_conflict', 'module loader differs from spec loader')
            for field, value in (('file_identity', data.get('__file__')),
                                 ('origin_identity', spec_origin)):
                if value is not None and value not in ('built-in', 'frozen'):
                    identity = _file_identity(value, files, cache)
                    row[field] = identity
                    for error in identity['errors']:
                        _error(errors, field + '.' + error['code'], error['detail'])
            origin = spec_origin
            if origin in ('built-in', 'frozen'):
                row['kind'] = origin
                expected_loader = machinery.BuiltinImporter if origin == 'built-in' else machinery.FrozenImporter
                known = (_imp.is_builtin(spec_name) if origin == 'built-in' else _imp.is_frozen(spec_name)) if type(spec_name) is str else False
                if loader is not expected_loader or spec_loader is not expected_loader or not known:
                    _error(errors, 'unverified_builtin_or_frozen', row['spec_name'])
                # __name__ is diagnostic, not a runtime identity: built-ins such
                # as _decimal legitimately report a different display name.
                if (type(spec_name) is not str or snapshot.get(spec_name) is not module or
                    sys.modules.get(spec_name) is not module):
                    _error(errors, 'builtin_or_frozen_object_alias_mismatch', row['spec_name'])
                if origin == 'built-in' and data.get('__file__') is not None:
                    _error(errors, 'builtin_has_file', row['__file__'])
                if not runtime['match']:
                    _error(errors, 'runtime_interpreter_not_pinned', runtime['realpath'])
                row['runtime_pin_match'] = runtime['match']
            elif data.get('__file__') is not None:
                row['kind'] = 'normal_file_module'
                if spec is None:
                    if name != '__main__' or data.get('__name__') != '__main__':
                        _error(errors, 'missing_file_module_spec', name)
                    else:
                        row['kind'] = 'normal_main_script'
                elif snapshot.get(spec_name) is not module:
                    _error(errors, 'file_module_canonical_object_mismatch', spec_name)
                elif data.get('__name__') != spec_name:
                    _error(errors, 'file_module_spec_name_conflict', str(row['module_name']) + ' != ' + str(spec_name))
                if spec is not None and origin is None:
                    _error(errors, 'file_spec_origin_missing', name)
                elif (row['file_identity'] and row['origin_identity'] and
                      row['file_identity']['realpath'] != row['origin_identity']['realpath']):
                    _error(errors, 'file_spec_origin_conflict', name)
                if type(loader) not in (machinery.SourceFileLoader, machinery.ExtensionFileLoader, machinery.SourcelessFileLoader):
                    _error(errors, 'unrecognized_file_loader', row['loader'])
                else:
                    loader_data = vars(loader)
                    if os.path.realpath(loader_data.get('path')) != (row['file_identity'] or {}).get('realpath'):
                        _error(errors, 'loader_file_conflict', loader_data.get('path'))
                    if loader_data.get('name') != (spec_name if spec is not None else '__main__'):
                        _error(errors, 'loader_spec_name_conflict', loader_data.get('name'))
                if type(loader) is machinery.SourcelessFileLoader:
                    _error(errors, 'bytecode_only_module_forbidden', name)
            elif name in synthetic or data.get('__name__') in synthetic:
                _synthetic(row, module, data, synthetic.get(name, synthetic.get(data.get('__name__'))), snapshot, files, cache)
            elif spec is not None and origin is None and type(loader) is machinery.NamespaceLoader:
                row['kind'] = 'normal_namespace_package'
                if snapshot.get(spec_name) is not module:
                    _error(errors, 'namespace_canonical_object_mismatch', spec_name)
                registration = namespaces.get(spec_name)
                if type(registration) is not dict or set(registration) != {'paths'}:
                    _error(errors, 'unregistered_namespace_package', spec_name)
                else:
                    actual = _paths(data.get('__path__'), errors, 'module_path')
                    locations = _paths(spec_data.get('submodule_search_locations'), errors, 'spec_search_locations')
                    row['namespace_paths'], row['spec_search_locations'] = actual, locations
                    if actual != locations:
                        _error(errors, 'namespace_spec_path_conflict', spec_name)
                    row['namespace_directories'] = _namespace_dirs(actual, registration['paths'], files, errors)
                    loader_paths = _paths(vars(loader).get('_path'), errors, 'namespace_loader_path')
                    row['namespace_loader_paths'] = loader_paths
                    if loader_paths != actual:
                        _error(errors, 'namespace_loader_path_conflict', spec_name)
                    if data.get('__name__') != spec_name or data.get('__package__') != spec_name:
                        _error(errors, 'namespace_name_conflict', spec_name)
                    if data.get('__doc__') is not None:
                        _error(errors, 'namespace_metadata_changed', '__doc__ must be None for an unexecuted namespace')
                    allowed = {'__name__', '__doc__', '__package__', '__loader__', '__spec__', '__path__', '__file__'}
                    for key, value in data.items():
                        if key not in allowed and (type(key) is not str or type(value) is not types.ModuleType or
                                                  snapshot.get(spec_name + '.' + key) is not value):
                            _error(errors, 'namespace_extra_attribute', _scalar(key))
                    for directory in registration['paths']:
                        if os.path.lexists(os.path.join(directory, '__init__.py')):
                            _error(errors, 'namespace_has_init_file', directory)
            else:
                row['kind'] = 'unverified_no_file'
                _error(errors, 'unregistered_no_file_module', name)
        except Exception as error:
            _error(errors, 'module_collection_error', type(error).__name__ + ': ' + str(error))
        finally:
            row['match'] = not errors
    failures = [{'name': row['name'], **error} for row in rows for error in row['errors']]
    report = {'schema': 1, 'status': 'FAIL_MODULE_IDENTITY' if failures else 'PASS_MODULE_IDENTITY',
              'entry_count': len(snapshot), 'unique_object_count': len(groups),
              'runtime_interpreter': runtime, 'modules': rows, 'failures': failures,
              'limitations': 'Module/file identity only; no execution or arithmetic qualification. Unknown files are not read. Synthetic registration binds current object/namespace and source-code identity, not a historical creation event. Interpreter binding is mandatory for built-in/frozen rows.'}
    return report


def validate_modules(report):
    """Call only after saving full inventory and any other required ledgers."""
    if type(report) is not dict or report.get('schema') != 1 or type(report.get('modules')) is not list:
        raise ValueError('invalid module inventory report')
    expected = [{'name': row['name'], **error} for row in report['modules'] for error in row['errors']]
    if report.get('entry_count') != len(report['modules']) or report.get('failures') != expected:
        raise ValueError('inconsistent module inventory report')
    if expected:
        raise ModuleInventoryError(report)
    if report.get('status') != 'PASS_MODULE_IDENTITY' or any(not row.get('match') for row in report['modules']):
        raise ValueError('inconsistent module inventory pass status')
    return report


def persist_and_validate(report, path):
    """Exclusive create: preserve prior evidence, fsync complete JSON, then reject."""
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    return validate_modules(report)
