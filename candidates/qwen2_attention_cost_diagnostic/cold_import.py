"""Cold, normally loaded source closure only. Never a numerical admission.

This entry point performs no DUT construction, arithmetic, reset, job, tensor
read, Matrix CDLL load, subprocess, or network action. Pinned Python/NumPy
initialization and NumPy's own import-time self-checks remain ordinary imports.
It must be launched in a fresh interpreter, not used to retry a native attempt.
"""
import argparse
import ast
import hashlib
import importlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
COLD_NAMESPACE_NAMES = (
    'candidates',
    'candidates.qwen2_resident_matrix',
    'candidates.qwen2_resident_matrix.ffn_attention',
    'candidates.qwen2_resident_matrix.ffn_public',
    'candidates.qwen2_resident_matrix.official_bf16',
    'candidates.qwen2_resident_matrix.production_qk16_model',
    'candidates.qwen2_resident_matrix.attention_packed_owner',
    'scripts',
)
DUT_MODULE_NAMES = (
    'candidates.qwen2_resident_matrix.ffn_attention.attention_owner',
    'candidates.qwen2_resident_matrix.production_qk16_model.schedule',
    'candidates.qwen2_resident_matrix.production_qk16_model.ordered_work',
    'candidates.qwen2_resident_matrix.attention_packed_owner.client',
    'candidates.qwen2_resident_matrix.official_bf16.owners',
    'candidates.qwen2_resident_matrix.production_qk16_model.entry',
)
LOCAL_MODULE_NAMES = ('harness', 'runtime_observer', 'reference_capture')
RECIPE_MODULE = 'scripts.qwen2_block_recipe_model'
PAYLOAD_SUFFIXES = frozenset(('.f32le', '.bf16le', '.u32le', '.npz', '.npy',
                              '.bin', '.safetensors', '.pt', '.pth'))
PINNED_RUNTIME_RESOURCES = frozenset((
    '/usr/lib/locale/C.utf8/LC_CTYPE',
    '/usr/lib/x86_64-linux-gnu/gconv/gconv-modules.cache',
))
PROCESS_EVENTS = frozenset(('subprocess.Popen', 'os.system', 'os.fork',
    'os.forkpty', 'os.posix_spawn', 'os.posix_spawnp', 'os.exec', 'os.spawn',
    'pty.spawn'))
FORBIDDEN_TASK_NAMES = frozenset(('__init__', '__new__', 'configure_library',
    'td_reset', 'reset', 'run', 'op', '_op', 'tick', '_matrix_step', 'run_owner',
    'load_exact', 'load_library', 'extract_sources', 'run_recipe', 'main',
    'install', 'capture_reference', 'bindings', 'load_observer'))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def write_text(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def cold_namespaces(source_root):
    """Fixed, reviewed project namespaces; never infer permission from a load."""
    root = Path(source_root).resolve()
    return {name: {'paths': [str(root.joinpath(*name.split('.')))]}
            for name in COLD_NAMESPACE_NAMES}


def create_observer_namespace(root):
    """The only no-file carrier, checked by source/code identity in inventory."""
    package = types.ModuleType('_qualified_runtime_observer')
    package.__path__ = [str(Path(root).resolve())]
    sys.modules[package.__name__] = package
    return package


def observer_registration(package, root):
    return {'_qualified_runtime_observer': {
        'kind': 'namespace_package', 'module': package,
        'paths': [str(Path(root).resolve())],
        'allowed_children': ['monitor', 'capture'],
        'creator_source': str(Path(__file__).resolve()),
        'creator_function': create_observer_namespace,
    }}


def select_cold_files(config):
    """Select only source/runtime bytes. Payloads and the DUT ELF are excluded."""
    files = config['files']
    need(type(files) is dict, 'files must be an exact-path pin dictionary')
    excluded = {str(Path(value['path']).resolve())
                for value in config.get('inputs', {}).values()}
    excluded.add(str(Path(config['elf']).resolve()))
    runtime = set(config.get('runtime_graph', {}).get('files', {}))
    admitted = {}
    for name, pin in files.items():
        path = Path(name)
        if name in excluded or path.suffix in PAYLOAD_SUFFIXES:
            continue
        if (path.suffix == '.py' or name in runtime or '.so' in path.name
                or name in PINNED_RUNTIME_RESOURCES
                or path == Path(config['observer_root']) / 'SOURCE_PINS.json'):
            need(path.is_absolute() and str(path.resolve()) == name,
                 'noncanonical cold pin: ' + name)
            need(type(pin) is dict and type(pin.get('bytes')) is int
                 and pin['bytes'] >= 0 and type(pin.get('sha256')) is str
                 and len(pin['sha256']) == 64
                 and all(c in '0123456789abcdef' for c in pin['sha256']),
                 'malformed cold pin: ' + name)
            admitted[name] = pin
    return admitted, excluded


def pin_record(path, pin):
    """Record drift without stopping collection of the other pins."""
    row = {'path': str(path), 'expected': pin}
    try:
        path = Path(path)
        stat = path.stat()
        row.update(bytes=stat.st_size, sha256=digest(path),
                   realpath=str(path.resolve()), device=stat.st_dev,
                   inode=stat.st_ino)
        row['match'] = (row['realpath'] == str(path)
                        and row['bytes'] == pin['bytes']
                        and row['sha256'] == pin['sha256'])
    except Exception as error:
        row.update(match=False, error=type(error).__name__ + ': ' + str(error))
    return row


class ColdGuard:
    """Exact-path read admission and task-call prohibition, not a general sandbox."""
    def __init__(self, config, files, output):
        self.config = config
        self.files = files
        self.output = Path(output).resolve()
        self.verified = {}
        self.checking = set()
        self.events = []
        self.blocked = []
        self.dependency_code_cache = {}
        self.codegen_events = []
        self.source = Path(config['source_root']).resolve()
        self.observer = Path(config['observer_root']).resolve()
        self.buffer = Path(config['buffer_source']).resolve()
        self.source_prefix = str(self.source) + os.sep
        self.observer_prefix = str(self.observer) + os.sep
        self.local_task_files = {str(HERE / (name + '.py'))
                                 for name in LOCAL_MODULE_NAMES}

    def reject(self, kind, detail, error=PermissionError):
        self.blocked.append({'kind': kind, 'detail': str(detail)})
        raise error(kind + ': ' + str(detail))

    def verify(self, path):
        key = str(path)
        if key in self.checking:
            return
        if key not in self.files:
            self.reject('unapproved_read', key)
        self.checking.add(key)
        try:
            pin = self.files[key]
            stat = path.stat()
            actual = digest(path)
            if stat.st_size != pin['bytes'] or actual != pin['sha256']:
                self.reject('pinned_file_drift', key)
            self.verified[key] = actual
        finally:
            self.checking.remove(key)

    def audit(self, event, args):
        if event in PROCESS_EVENTS or event.startswith(('os.exec', 'os.spawn')):
            self.reject('process_execution_forbidden', event)
        if event.startswith('socket.'):
            self.reject('network_forbidden', event)
        if event == 'ctypes.dlopen':
            if args[0] is not None:
                self.reject('explicit_library_load_forbidden', args[0])
            self.events.append('ctypes.dlopen(None): pinned dependency initialization')
        if event == 'import' and args:
            if str(args[0]).split('.')[0] in ('torch', 'transformers'):
                self.reject('oracle_import_forbidden', args[0])
            if len(args) > 1 and args[1]:
                self.verify(Path(args[1]).resolve())
        if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
            raw_name = os.fsdecode(args[0])
            path = Path(raw_name).resolve()
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            mode = args[1] if len(args) > 1 else ''
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            writing = writing or (isinstance(mode, str) and any(x in mode for x in 'wax+'))
            if writing:
                if not path.is_relative_to(self.output):
                    self.reject('write_outside_new_output', path)
                return
            if raw_name == '/proc/self/maps' or path.is_relative_to(self.output):
                return
            if path.suffix == '.pyc':
                self.reject('bytecode_cache_not_admitted', path)
            if str(path) in self.checking:
                return
            self.verify(path)

    def task_frame(self, frame):
        for raw in (frame.f_code.co_filename, frame.f_globals.get('__file__')):
            if not isinstance(raw, str) or raw.startswith('<'):
                continue
            # Import filenames have already passed the canonical-path read gate.
            # Avoid filesystem operations for every Python dependency call.
            if (raw.startswith(self.source_prefix) or raw.startswith(self.observer_prefix)
                    or raw == str(self.buffer) or raw in self.local_task_files):
                return True
        return False

    def dataclass_definition_factory(self, frame):
        """Permit only the pinned stdlib's method-definition factory, not a method.

        Normal dataclass decoration executes a generated __create_fn__ with the
        decorated module's globals. Its caller/source/text/object identities are
        bound here. The generated __init__/__setattr__/task methods remain denied.
        """
        code = frame.f_code
        if code.co_filename != '<string>' or code.co_name != '__create_fn__':
            return False
        caller = frame.f_back
        module = sys.modules.get('dataclasses')
        if caller is None or type(module) is not types.ModuleType:
            return False
        values = vars(module)
        function = values.get('_create_fn')
        raw_path = values.get('__file__')
        if (type(function) is not types.FunctionType or type(raw_path) is not str
                or function.__code__ is not caller.f_code
                or function.__globals__ is not values or caller.f_globals is not values):
            return False
        path = Path(raw_path)
        pin = self.files.get(raw_path)
        if (pin is None or not path.is_absolute() or path.resolve() != path
                or path.name != 'dataclasses.py'
                or not path.is_relative_to(Path(sys.base_prefix).resolve())):
            return False
        key = (raw_path, pin['sha256'])
        expected_caller = self.dependency_code_cache.get(key)
        if expected_caller is None:
            raw = path.read_bytes()
            if len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']:
                return False
            complete = compile(raw, raw_path, 'exec', dont_inherit=True, optimize=sys.flags.optimize)
            found = [item for item in complete.co_consts
                     if type(item) is types.CodeType and item.co_name == '_create_fn']
            if len(found) != 1:
                return False
            expected_caller = found[0]
            self.dependency_code_cache[key] = expected_caller
        if not same_code(caller.f_code, expected_caller):
            return False
        local = caller.f_locals
        txt, namespace, arguments = (local.get(name) for name in ('txt', 'ns', 'locals'))
        if (type(txt) is not str or type(namespace) is not dict or type(arguments) is not dict
                or local.get('globals') is not frame.f_globals):
            return False
        factory = namespace.get('__create_fn__')
        if (type(factory) is not types.FunctionType or factory.__code__ is not code
                or factory.__globals__ is not frame.f_globals
                or set(frame.f_locals) != set(arguments)
                or any(frame.f_locals[name] is not value for name, value in arguments.items())):
            return False
        if not definition_factory_text(txt):
            return False
        compiled = compile(txt, '<string>', 'exec', dont_inherit=True, optimize=sys.flags.optimize)
        factories = [item for item in compiled.co_consts
                     if type(item) is types.CodeType and item.co_name == '__create_fn__']
        if len(factories) != 1 or not same_code(code, factories[0]):
            return False
        self.codegen_events.append({'kind': 'pinned_dataclass_method_definition',
                                    'caller_source': raw_path,
                                    'caller_source_sha256': pin['sha256'],
                                    'factory_text_sha256': hashlib.sha256(txt.encode()).hexdigest(),
                                    'method': local.get('name')})
        return True

    def profile(self, frame, event, arg):
        if event != 'call' or not self.task_frame(frame):
            return
        code = frame.f_code
        if self.dataclass_definition_factory(frame):
            return
        # Class definition frames have no CO_NEWLOCALS. Decorator work executes
        # in the pinned Python dependency, not in DUT arithmetic functions.
        definition_body = not code.co_flags & 0x02
        literal_comprehension = code.co_name in ('<listcomp>', '<dictcomp>',
                                                 '<setcomp>', '<genexpr>')
        if (code.co_name in FORBIDDEN_TASK_NAMES
                or not (definition_body or literal_comprehension)):
            self.reject('task_execution_forbidden',
                        str(code.co_filename) + ':' + code.co_qualname)


def same_code(actual, expected):
    if (type(actual) is not types.CodeType or type(expected) is not types.CodeType
            or actual != expected or actual.co_filename != expected.co_filename
            or actual.co_firstlineno != expected.co_firstlineno
            or actual.co_linetable != expected.co_linetable
            or actual.co_exceptiontable != expected.co_exceptiontable):
        return False
    return all(same_code(left, right) for left, right in zip(actual.co_consts, expected.co_consts)
               if type(left) is types.CodeType or type(right) is types.CodeType)


def definition_factory_text(txt):
    """The factory may define one method and return it; no eager expression calls."""
    try:
        tree = ast.parse(txt, filename='<string>', mode='exec')
    except (SyntaxError, ValueError):
        return False
    if len(tree.body) != 1 or type(tree.body[0]) is not ast.FunctionDef:
        return False
    factory = tree.body[0]
    if (factory.name != '__create_fn__' or factory.decorator_list or factory.returns is not None
            or factory.type_params or len(factory.body) != 2
            or type(factory.body[0]) is not ast.FunctionDef
            or type(factory.body[1]) is not ast.Return):
        return False
    args = factory.args
    if (args.posonlyargs or args.vararg or args.kwarg or args.kwonlyargs
            or args.defaults or any(arg.annotation is not None for arg in args.args)):
        return False
    method, returned = factory.body
    if (method.decorator_list or method.type_params or type(returned.value) is not ast.Name
            or returned.value.id != method.name):
        return False
    # Dataclasses uses local-name placeholders for all annotations/defaults.
    # The method body is compiled but never run by this factory.
    eager = [method.returns, *method.args.defaults, *method.args.kw_defaults]
    eager.extend(arg.annotation for arg in [*method.args.posonlyargs, *method.args.args,
                                            *method.args.kwonlyargs])
    eager.extend(arg.annotation for arg in (method.args.vararg, method.args.kwarg) if arg)
    return all(item is None or type(item) in (ast.Name, ast.Constant) for item in eager)


def raw_scalar(value):
    """Represent unexpected metadata by type only, without user hooks/repr."""
    if type(value) in (str, int, bool, type(None)):
        return value
    return {'non_scalar_type': type(value).__name__}


def raw_package_paths(value):
    if type(value) in (list, tuple):
        return [raw_scalar(item) for item in value]
    namespace_type = importlib._bootstrap_external._NamespacePath
    if type(value) is namespace_type:
        # Do not iterate _NamespacePath: iteration may invoke path recalculation.
        return [raw_scalar(item) for item in vars(value).get('_path', ())]
    return raw_scalar(value)


def raw_modules(modules):
    """JSON-safe per-entry evidence, without getattr, user repr, reads, or hashes."""
    rows = []
    entries = list(modules.items())
    entries.sort(key=lambda item: item[0] if type(item[0]) is str else
                 '<non-string-key:' + type(item[0]).__name__ + '>')
    for index, (name, module) in enumerate(entries):
        row = {'module': raw_scalar(name), 'entry_index': index,
               'object_type': type(module).__name__}
        try:
            if type(module) is types.ModuleType:
                values = vars(module)
                spec = values.get('__spec__')
                row.update(file=raw_scalar(values.get('__file__')),
                           package=raw_scalar(values.get('__package__')),
                           loader_type=type(values.get('__loader__')).__name__,
                           spec_type=type(spec).__name__)
                if type(spec) is importlib.machinery.ModuleSpec:
                    row['spec_origin'] = raw_scalar(vars(spec).get('origin'))
                if '__path__' in values:
                    row['package_paths'] = raw_package_paths(values['__path__'])
        except Exception as error:
            row['metadata_error_type'] = type(error).__name__
        rows.append(row)
    return {'module_count': len(rows), 'modules': rows}


def collect_maps(raw, files, forbidden_elf, mapping_allowlist=None):
    """Inspect every map and every difference; never read an unknown mapping."""
    rows = []
    allowed = set(files) if mapping_allowlist is None else set(mapping_allowlist) - {forbidden_elf}
    for line in raw.splitlines():
        parts = line.split(None, 5)
        if len(parts) != 6 or not parts[5].startswith('/'):
            continue
        name = parts[5]
        path = Path(name)
        row = {'raw': line, 'path': name, 'mapped_device': parts[3],
               'mapped_inode': parts[4], 'reasons': []}
        pin = files.get(name) if name in allowed else None
        if name == forbidden_elf or name.removesuffix(' (deleted)') == forbidden_elf:
            row['reasons'].append('matrix_elf_loaded')
        if name not in allowed:
            row['reasons'].append('mapping_outside_allowlist_not_read')
        if pin is None:
            row['reasons'].append('unbound_mapping_not_read')
        try:
            stat = path.stat()
            row.update(realpath=str(path.resolve()), bytes=stat.st_size,
                       device=stat.st_dev, inode=stat.st_ino)
            if row['realpath'] == forbidden_elf and 'matrix_elf_loaded' not in row['reasons']:
                row['reasons'].append('matrix_elf_loaded')
            major, minor = (int(value, 16) for value in parts[3].split(':'))
            if (os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino) != (
                    major, minor, int(parts[4])):
                row['reasons'].append('mapped_inode_or_device_differs')
            if str(path.resolve()) != name:
                row['reasons'].append('mapped_path_not_canonical')
            if pin is not None:
                row['sha256'] = digest(path)
                if stat.st_size != pin['bytes'] or row['sha256'] != pin['sha256']:
                    row['reasons'].append('mapped_file_pin_differs')
        except Exception as error:
            row['reasons'].append(type(error).__name__ + ': ' + str(error))
        row['match'] = not row['reasons']
        rows.append(row)
    failures = [row for row in rows if not row['match']]
    return {'status': 'FAIL' if failures else 'PASS_PINNED_COLD_MAPPINGS',
            'mappings': rows, 'failures': failures,
            'matrix_elf_loaded': any('matrix_elf_loaded' in r['reasons'] for r in rows)}


def snapshot_stage(out, stage, inventory, files, config, synthetic):
    """Save BOTH complete snapshots, then collect BOTH reports, then validate."""
    target = Path(out) / stage
    target.mkdir()
    modules = dict(sys.modules)
    errors = []
    try:
        module_raw = raw_modules(modules)
    except Exception as error:
        module_raw = {'status': 'FAIL_RAW_COLLECTOR', 'module_count': len(modules),
                      'error_type': type(error).__name__}
        errors.append({'stage': stage, 'gate': 'raw_modules',
                       'error_type': type(error).__name__})
    write_json(target / 'MODULES_RAW.json', module_raw)
    maps = Path('/proc/self/maps').read_text()
    write_text(target / 'MAPS.txt', maps)
    try:
        module_report = inventory.collect_modules(
            modules, files, namespaces=cold_namespaces(config['source_root']),
            synthetic=synthetic,
            registered_objects=config.get('registered_module_objects', {}))
    except Exception as error:
        module_report = {'status': 'FAIL_COLLECTOR', 'errors': [
            type(error).__name__ + ': ' + str(error)]}
    write_json(target / 'MODULE_AUDIT.json', module_report)
    map_report = collect_maps(maps, files, str(Path(config['elf']).resolve()),
                              config.get('mapping_allowlist'))
    write_json(target / 'MAP_AUDIT.json', map_report)
    # A module failure cannot prevent collection/persistence of all maps.
    try:
        inventory.validate_modules(module_report)
    except Exception as error:
        errors.append({'stage': stage, 'gate': 'modules',
                       'error': type(error).__name__ + ': ' + str(error)})
    if map_report['failures']:
        errors.append({'stage': stage, 'gate': 'maps',
                       'failures': map_report['failures']})
    write_json(target / 'VALIDATION.json', {'status': 'FAIL' if errors else 'PASS',
                                          'errors': errors})
    return errors


def import_targets(config):
    imported = []
    for name in (*DUT_MODULE_NAMES, RECIPE_MODULE, *LOCAL_MODULE_NAMES):
        module = importlib.import_module(name)
        expected = (HERE / (name + '.py') if name in LOCAL_MODULE_NAMES else
                    Path(config['source_root']).joinpath(*name.split('.')).with_suffix('.py'))
        need(Path(module.__file__).resolve() == expected, 'target origin drift: ' + name)
        imported.append(name)
    buffer = Path(config['buffer_source']).resolve()
    spec = importlib.util.spec_from_file_location('_qualified_runtime_fields', buffer)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    imported.append(spec.name)
    package = create_observer_namespace(config['observer_root'])
    monitor = importlib.import_module(package.__name__ + '.monitor')
    need(Path(monitor.__file__).resolve() == Path(config['observer_root']) / 'monitor.py',
         'monitor origin drift')
    imported.extend((package.__name__, package.__name__ + '.monitor',
                     package.__name__ + '.capture'))
    return imported, package


def stop_task_profile(guard, callback):
    """Fail closed if an importer swallowed a callback exception or replaced it."""
    current = sys.getprofile()
    sys.setprofile(None)
    errors = []
    if current is not callback:
        errors.append({'stage': 'cold_import', 'gate': 'task_profile',
                       'error': 'profile callback was removed or replaced'})
    violations = [event for event in guard.blocked
                  if event['kind'] == 'task_execution_forbidden']
    if violations:
        errors.append({'stage': 'cold_import', 'gate': 'task_profile',
                       'violations': violations})
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--config-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    config = None
    guard = None
    inventory = None
    files = {}
    imported = []
    synthetic = {}
    errors = []
    try:
        raw = args.config.read_bytes()
        need(hashlib.sha256(raw).hexdigest() == args.config_sha, 'exact config SHA256 differs')
        config = json.loads(raw)
        files, excluded = select_cold_files(config)
        need(type(config.get('mapping_allowlist')) is list
             and all(type(name) is str and Path(name).is_absolute()
                     and str(Path(name).resolve()) == name
                     for name in config['mapping_allowlist']),
             'explicit canonical mapping allowlist required')
        need(set(config['mapping_allowlist']) - {config['elf']} <= set(files),
             'mapping allowlist missing cold runtime pins')
        required = {str(Path(__file__).resolve()), str(HERE / 'module_inventory.py'),
                    str(Path(sys.executable).resolve()), str(Path(config['buffer_source']).resolve()),
                    str(Path(config['observer_root']) / 'SOURCE_PINS.json')}
        required.update(str(HERE / (name + '.py')) for name in LOCAL_MODULE_NAMES)
        required.update(str(Path(config['source_root']).joinpath(*name.split('.')).with_suffix('.py'))
                        for name in (*DUT_MODULE_NAMES, RECIPE_MODULE))
        need(required <= set(files), 'missing required cold source/runtime pins: '
             + ', '.join(sorted(required - set(files))))
        need(not any(name in sys.modules for name in (*DUT_MODULE_NAMES, RECIPE_MODULE,
                                                      *LOCAL_MODULE_NAMES, 'numpy')),
             'fresh cold interpreter required; task/dependency modules already loaded')
        need(not any(key.startswith('LD_') for key in os.environ), 'loader override forbidden')
        sys.dont_write_bytecode = True
        guard = ColdGuard(config, files, out)
        sys.addaudithook(guard.audit)
        pin_rows = [pin_record(Path(name), pin) for name, pin in sorted(files.items())]
        write_json(out / 'COLD_PIN_AUDIT.json', {'files': pin_rows,
            'failures': [row for row in pin_rows if not row['match']],
            'excluded_without_read': sorted(excluded), 'task_payloads_hashed': False})
        failures = [row for row in pin_rows if not row['match']]
        # Inventory code is admitted independently, never imported from unverified bytes.
        guard.verify(HERE / 'module_inventory.py')
        sys.path[:0] = [str(HERE), config['source_root'], config['numpy_root']]
        inventory = importlib.import_module('module_inventory')
        need(Path(inventory.__file__).resolve() == HERE / 'module_inventory.py',
             'inventory helper origin differs')
        errors.extend(snapshot_stage(out, '00_before_import', inventory, files, config, synthetic))
        if failures:
            errors.append({'stage': 'preflight', 'gate': 'source_pins', 'failures': failures})
        if not errors:
            callback = guard.profile
            sys.setprofile(callback)
            try:
                imported, package = import_targets(config)
                synthetic = observer_registration(package, config['observer_root'])
            finally:
                # CPython automatically removes a callback that raises.
                errors.extend(stop_task_profile(guard, callback))
    except BaseException as error:
        sys.setprofile(None)
        errors.append({'stage': 'cold_import', 'error_type': type(error).__name__,
                       'error': str(error)})
    finally:
        sys.setprofile(None)
        # An interrupted observer import may have installed its carrier already.
        package = sys.modules.get('_qualified_runtime_observer')
        if package is not None and config is not None:
            synthetic = observer_registration(package, config['observer_root'])
        if inventory is not None and config is not None:
            errors.extend(snapshot_stage(out, '01_after_import_or_failure', inventory,
                                         files, config, synthetic))
        else:
            write_json(out / 'MODULES_RAW_ON_FAILURE.json', raw_modules(dict(sys.modules)))
            write_text(out / 'MAPS_ON_FAILURE.txt', Path('/proc/self/maps').read_text())
        report = {'status': 'FAIL_COLD_IMPORT' if errors else 'PASS_COLD_IMPORT_ONLY',
            'errors': errors, 'config_sha256': args.config_sha, 'imported_targets': imported,
            'verified_reads': guard.verified if guard else {},
            'dependency_initialization_events': guard.events if guard else [],
            'definition_codegen_events': guard.codegen_events if guard else [],
            'rejected_operations': guard.blocked if guard else [],
            'allowed_dependency_self_tests': ['pinned NumPy import initialization and self-tests'],
            'task_construction_permitted': False, 'observation_construction_permitted': False,
            'task_execution_permitted': False, 'task_tensor_reads_permitted': False,
            'task_payloads_hashed': False,
            'task_profile_violations': sum(event['kind'] == 'task_execution_forbidden'
                                           for event in (guard.blocked if guard else [])),
            'explicit_cdll_permitted': False, 'matrix_elf_loading_permitted': False,
            'native_retry': False, 'numerical_qualification': False,
            'observer_nonintrusion_qualification': False, 'rtl': False}
        write_json(out / 'RESULT.json', report)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
