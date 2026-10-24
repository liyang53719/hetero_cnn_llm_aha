"""Source-only construction of the admitted fullblock observation context.

No DUT, codec, admission, or native module is imported at module import time.
The callable is for the already admitted actual process, AFTER dependencies and
existing ELF load and BEFORE the runner constructs/binds its fresh objects.
It grants no authority, supplies no budget, and performs no arithmetic/reset.
"""
from __future__ import annotations

import ast
from abc import ABCMeta
import builtins
from collections.abc import Sequence
from dataclasses import fields, is_dataclass
import dis
import hashlib
import importlib
import importlib.util
import importlib.machinery
import inspect
import json
import os
from pathlib import Path
import struct
import sys
import types

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'source'
CONTRACT = 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'
CODEC_FIELDS = frozenset(('contexts', 'bank_bytes', 'max_chunk', 'max_metadata',
                         'max_record', 'max_records', 'max_output', 'max_raw'))
TRACE_FIELDS = frozenset(('codec', 'max_trace_call_bytes', 'max_semantic_bytes',
    'max_listener_count', 'max_loaded_codes', 'max_trace_objects', 'max_exception_frames'))
_FACTORY_USED = False


class RuntimeBindingError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise RuntimeBindingError(message)


def checked(path, expected=None):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and path.is_file() and
         not any(p.is_symlink() for p in (path, *path.parents)), 'missing/aliased source: ' + str(path))
    raw = path.read_bytes()
    identity = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if expected is not None:
        need(identity == expected, 'exact file identity differs: ' + str(path))
    return raw, identity


def child(code, name):
    found = [v for v in code.co_consts if type(v) is types.CodeType and v.co_name == name]
    need(len(found) == 1, 'ambiguous source code child: ' + name)
    return found[0]


def global_reads(code):
    """Actual global loads, including nested code, never attribute-name indices.

    co_names also contains LOAD_ATTR names. Treating those as module globals
    creates false bindings such as type(value).__name__. Nested class LOAD_NAME
    resolution is not part of this admitted function set and fails closed.
    """
    need(type(code) is types.CodeType, 'source code object required')
    names = set()
    pending = [code]
    while pending:
        current = pending.pop()
        for instruction in dis.get_instructions(current, adaptive=False):
            need(instruction.opname != 'LOAD_NAME',
                 'nested LOAD_NAME scope is not admitted')
            if instruction.opname == 'LOAD_GLOBAL':
                need(type(instruction.argval) is str, 'exact global-load name required')
                names.add(instruction.argval)
        pending.extend(value for value in current.co_consts
                       if type(value) is types.CodeType)
    return tuple(sorted(names))


def same_code(actual, expected):
    return (type(actual) is types.CodeType and type(expected) is types.CodeType and
        actual == expected and actual.co_filename == expected.co_filename and
        actual.co_firstlineno == expected.co_firstlineno and
        actual.co_linetable == expected.co_linetable and actual.co_exceptiontable == expected.co_exceptiontable and
        all(same_code(a, b) for a, b in zip(actual.co_consts, expected.co_consts)
            if type(a) is types.CodeType))


def module_path(module, path):
    need(type(module) is types.ModuleType and Path(module.__file__).resolve() == path and
         module.__dict__.get('__name__') == module.__name__, 'wrong source-bound loaded module: ' + str(path))
    return module


class LoadedClosure:
    """Inspect source-selected objects without evaluating source expressions.

    Only the listed literal/path/alias forms are interpreted. A new unsupported
    default or global binding is an explicit rejection, never eval/exec fallback.
    Source functions are compiled for comparison, never executed. Dataclass
    generated methods remain the parent-pinned stdlib's responsibility.
    """
    def __init__(self, sources):
        self.sources = dict(sources)
        self.cache = {}
        self.checked_functions = {}
        self.checked_classes = {}

    def source(self, module):
        path = Path(module.__file__).resolve()
        module_path(module, path)
        need(str(path) in self.sources, 'loaded source outside declared closure: ' + str(path))
        raw, ident = checked(path)
        need(ident['sha256'] == self.sources[str(path)], 'loaded source drift: ' + str(path))
        if path not in self.cache:
            self.cache[path] = (ast.parse(raw), compile(raw, str(path), 'exec', dont_inherit=True, optimize=0))
        return path, *self.cache[path]

    def reference(self, node, module, trail=()):
        path, tree, _ = self.source(module)
        if isinstance(node, ast.Name):
            name = node.id
            if name == '__file__':
                return str(path)
            if name in vars(builtins) and name not in vars(module):
                return vars(builtins)[name]
            need(name in vars(module) and name not in trail, 'missing/cyclic source global: ' + name)
            for statement in tree.body:
                if isinstance(statement, ast.Import):
                    for alias in statement.names:
                        key = alias.asname or alias.name.split('.')[0]
                        if key == name:
                            dependency = sys.modules.get(alias.name if alias.asname else key)
                            need(dependency is not None and vars(module)[name] is dependency,
                                 'source import alias changed: ' + name)
                            return dependency
                elif isinstance(statement, ast.ImportFrom):
                    package = module.__package__ or ''
                    target = importlib.util.resolve_name('.' * statement.level + (statement.module or ''), package) if statement.level else statement.module
                    dependency = sys.modules.get(target)
                    for alias in statement.names:
                        if (alias.asname or alias.name) == name:
                            need(dependency is not None and alias.name != '*', 'missing explicit imported module')
                            expected = vars(dependency).get(alias.name)
                            need(expected is not None and vars(module)[name] is expected, 'source from-import alias changed: ' + name)
                            return expected
                elif isinstance(statement, (ast.FunctionDef, ast.ClassDef)) and statement.name == name:
                    return vars(module)[name]
                elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                    for target in targets:
                        names = [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]
                        if name in names:
                            expected = self.reference(statement.value, module, (*trail, name))
                            if isinstance(target, (ast.Tuple, ast.List)):
                                need(all(isinstance(n, ast.Name) for n in target.elts), 'nested assignment not admitted')
                                expected = expected[[n.id for n in target.elts].index(name)]
                            need(equal_value(vars(module)[name], expected), 'source global binding changed: ' + name)
                            return vars(module)[name]
            raise RuntimeBindingError('unresolved source global: ' + module.__name__ + '.' + name)
        if isinstance(node, ast.Attribute):
            value = self.reference(node.value, module, trail)
            if isinstance(value, Path) and node.attr in ('parent', 'parents', 'name'):
                return getattr(value, node.attr)
            need(type(value) is types.ModuleType or isinstance(value, type), 'nonstatic source attribute')
            return inspect.getattr_static(value, node.attr)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            items = [self.reference(v, module, trail) for v in node.elts]
            return tuple(items) if isinstance(node, ast.Tuple) else list(items) if isinstance(node, ast.List) else set(items)
        if isinstance(node, ast.Dict):
            return {self.reference(k, module, trail): self.reference(v, module, trail) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Subscript):
            value = self.reference(node.value, module, trail)
            key = self.reference(node.slice, module, trail)
            need(isinstance(value, (tuple, list, dict, str, bytes, type(path.parents))), 'nonliteral subscript')
            return value[key]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Invert)):
            value = self.reference(node.operand, module, trail)
            need(type(value) is int, 'noninteger unary constant')
            return -value if isinstance(node.op, ast.USub) else +value if isinstance(node.op, ast.UAdd) else ~value
        if isinstance(node, ast.BinOp):
            a, b = self.reference(node.left, module, trail), self.reference(node.right, module, trail)
            if isinstance(node.op, ast.Div) and isinstance(a, Path) and type(b) is str:
                return a / b
            if isinstance(node.op, ast.Add) and type(a) is type(b) and type(a) in (int, str, tuple, bytes):
                return a + b
            if isinstance(node.op, (ast.LShift, ast.Sub)) and type(a) is type(b) is int:
                return a << b if isinstance(node.op, ast.LShift) else a - b
        if isinstance(node, ast.Call):
            label = ast.unparse(node.func)
            args = [self.reference(v, module, trail) for v in node.args]
            kwargs = {v.arg: self.reference(v.value, module, trail) for v in node.keywords}
            need(None not in kwargs, 'expanded source call not admitted')
            if label == 'Path' and len(args) == 1 and not kwargs and type(args[0]) is str:
                need(self.reference(node.func, module, trail) is Path, 'Path import replaced')
                return Path(args[0])
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'resolve' and not args and not kwargs:
                value = self.reference(node.func.value, module, trail)
                need(isinstance(value, Path), 'only source Path.resolve is allowed')
                return value.resolve()
            if label == 'importlib.util.spec_from_file_location' and len(args) == 2 and not kwargs:
                need(self.reference(node.func, module, trail) is importlib.util.spec_from_file_location and
                     type(args[0]) is str and isinstance(args[1], Path), 'source module spec expression')
                return ('__source_module_spec__', args[0], args[1].resolve())
            if label == 'importlib.util.module_from_spec' and len(args) == 1 and not kwargs:
                need(self.reference(node.func, module, trail) is importlib.util.module_from_spec and
                     type(args[0]) is importlib.machinery.ModuleSpec, 'source module-from-spec expression')
                value = module_path(sys.modules.get(args[0].name), Path(args[0].origin).resolve())
                need(value.__spec__ is args[0], 'loaded original module spec object differs')
                return value
            if label == '_pinned_module' and len(args) == 3 and not kwargs:
                need(type(args[0]) is str and isinstance(args[1], Path) and
                     self.sources.get(str(args[1].resolve())) == args[2], 'original pinned-module source mismatch')
                return module_path(sys.modules.get(args[0]), args[1].resolve())
            if label == 'load_module' and len(args) == 2 and not kwargs:
                value = sys.modules.get(args[0])
                need(type(args[0]) is str and isinstance(args[1], Path), 'dynamic source alias shape')
                return module_path(value, args[1].resolve())
            if label in ('MappingProxyType', 'dict'):
                expected = types.MappingProxyType if label == 'MappingProxyType' else dict
                need(self.reference(node.func, module, trail) is expected, 'constant constructor alias replaced')
                return expected(*args, **kwargs)
            if label == 'ReductionProfile' and not kwargs:
                return ('__source_profile__', tuple(args))
            if label == 'struct.pack':
                need(self.reference(node.func, module, trail) is struct.pack and len(args) == 2 and
                     args[0] == '<I' and type(args[1]) is int and not kwargs, 'unsupported packed source constant')
                return struct.pack(*args)
            if ast.unparse(node) == 'hashlib.sha256(Path(__file__).read_bytes()).hexdigest()':
                return self.sources[str(path)]
        raise RuntimeBindingError('unsupported source constant (no execution fallback): ' + ast.unparse(node))

    def function(self, module, qualname):
        path, tree, code = self.source(module)
        parts = qualname.split('.')
        node, obj, cls = tree, module, None
        for name in parts:
            if name == 'fget':
                need(isinstance(obj, property), 'fget descriptor missing')
                obj = obj.fget
                continue
            nodes = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
            need(len(nodes) == 1, 'source definition missing/ambiguous: ' + qualname)
            node = nodes[0]
            code = child(code, name)
            obj = inspect.getattr_static(obj, name)
            if isinstance(node, ast.ClassDef):
                cls = obj
        need(isinstance(node, ast.FunctionDef), 'function descriptor is not a function')
        if isinstance(obj, (classmethod, staticmethod)):
            obj = obj.__func__
        elif isinstance(obj, property):
            need(obj.fset is None and obj.fdel is None, 'mutating property not admitted')
            obj = obj.fget
        need(type(obj) is types.FunctionType and same_code(obj.__code__, code) and
             obj.__globals__ is vars(module) and obj.__builtins__ is vars(builtins), 'loaded function code/globals differs: ' + qualname)
        defaults = tuple(self.reference(n, module) for n in node.args.defaults) or None
        keywords = {a.arg: self.reference(v, module) for a, v in zip(node.args.kwonlyargs, node.args.kw_defaults) if v is not None} or None
        need(equal_value(obj.__defaults__, defaults) and equal_value(obj.__kwdefaults__, keywords), 'loaded defaults differ: ' + qualname)
        if code.co_freevars:
            need(code.co_freevars == ('__class__',) and cls is not None and len(obj.__closure__ or ()) == 1 and
                 obj.__closure__[0].cell_contents is cls, 'unexpected function closure: ' + qualname)
        else:
            need(obj.__closure__ is None, 'unexpected closure cells: ' + qualname)
        # Referenced module globals are checked against their source declarations;
        # imported object identity is not inferred from a matching display name.
        for name in global_reads(code):
            self.reference(ast.Name(id=name, ctx=ast.Load()), module)
        descriptor = dict(function=obj, code=obj.__code__, path=str(path), sha256=self.sources[str(path)],
                          qualname=obj.__code__.co_qualname, firstlineno=obj.__code__.co_firstlineno)
        self.checked_functions[(id(module), qualname)] = descriptor
        return descriptor

    def cls(self, cls):
        need(isinstance(cls, type), 'exact class missing')
        if cls is object or cls in (Exception, ValueError, RuntimeError):
            return
        if id(cls) in self.checked_classes:
            return
        module = sys.modules.get(cls.__module__)
        path = Path(getattr(module, '__file__', '')).resolve()
        if str(path) not in self.sources:
            # Only parent-pinned standard-library abstract bases are permitted.
            need(cls.__module__ in ('collections.abc', '_collections_abc'), 'class base outside source closure: ' + str(cls))
            return
        path, tree, _ = self.source(module)
        nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls.__name__]
        need(len(nodes) == 1 and vars(module).get(cls.__name__) is cls, 'source class binding differs')
        node = nodes[0]
        bases = tuple(self.reference(v, module) for v in node.bases) or (object,)
        need(cls.__bases__ == bases, 'source-selected class bases changed: ' + cls.__qualname__)
        # The two immutable Matrix views inherit the exact stdlib Sequence
        # ABC. No other ABC/custom metaclass or alternate base is admitted.
        sequence_view = (path == SOURCE/'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py'
                         and cls.__name__ in ('MatrixValue', '_MatrixRow'))
        if sequence_view:
            need(not node.keywords and bases == (Sequence,) and
                 type(cls) is ABCMeta and type(Sequence) is ABCMeta and
                 cls.__mro__ == (cls, *Sequence.__mro__) and
                 cls.__abstractmethods__ == frozenset(),
                 'source-selected Matrix Sequence metaclass/bases/MRO differ')
        else:
            need(type(cls) is type, 'custom class metaclass not admitted')

        self.checked_classes[id(cls)] = cls
        for base in bases:
            self.cls(base)
        for method in node.body:
            if isinstance(method, ast.FunctionDef):
                self.function(module, cls.__name__ + '.' + method.name)
            elif isinstance(method, ast.Assign):
                expected = self.reference(method.value, module)
                for target in method.targets:
                    need(isinstance(target, ast.Name) and equal_value(vars(cls).get(target.id), expected),
                         'source class constant changed: ' + cls.__name__)

    def revalidate(self):
        entries = list(self.checked_functions.items())
        for _, d in entries:
            fn = d['function']
            module = next((m for m in sys.modules.values() if type(m) is types.ModuleType and vars(m) is fn.__globals__), None)
            need(module is not None, 'loaded function module was detached')
            again = self.function(module, d['qualname'])
            need(again['function'] is fn and again['code'] is d['code'], 'loaded function object replaced')


def equal_value(actual, expected):
    if type(expected) is tuple and len(expected) == 3 and expected[0] == '__source_module_spec__':
        return (type(actual) is importlib.machinery.ModuleSpec and actual.name == expected[1] and
                Path(actual.origin).resolve() == expected[2] and
                type(actual.loader) is importlib.machinery.SourceFileLoader and
                actual.loader.name == expected[1] and Path(actual.loader.path).resolve() == expected[2])
    if type(expected) is tuple and len(expected) == 2 and expected[0] == '__source_profile__':
        return is_dataclass(actual) and tuple(getattr(actual, f.name) for f in fields(actual)) == expected[1]
    if type(expected) in (types.FunctionType, types.ModuleType, type) or callable(expected):
        return actual is expected
    if isinstance(expected, types.MappingProxyType):
        return type(actual) is types.MappingProxyType and dict(actual) == dict(expected)
    return type(actual) is type(expected) and actual == expected


def _check_observation_helpers(declaration):
    """Check already loaded read-only guard helpers, not merely their disk bytes."""
    for relative in ('observation/source_guard.py', 'observation/event_stream.py'):
        path = HERE / relative
        module = module_path(sys.modules.get(relative[:-3].replace('/', '.')), path)
        raw, _ = checked(path, declaration['files'][relative])
        tree, compiled = ast.parse(raw), compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
        if relative == 'observation/event_stream.py':
            expected_names = {'EXP_ENVELOPE_SCHEMA', 'EXP_METADATA_SCHEMA', 'EXP_LAYOUT',
                              'EXP_METADATA_MAX', 'EVENT_METADATA_MAX'}
            assigned = {}
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in expected_names:
                            need(len(node.targets) == 1 and target.id not in assigned,
                                 'ambiguous observation envelope constant assignment')
                            assigned[target.id] = ast.literal_eval(node.value)
            need(set(assigned) == expected_names, 'observation envelope constant inventory differs')
            for name, expected in assigned.items():
                actual = vars(module).get(name)
                need(type(expected) in (str, int) and type(actual) is type(expected) and
                     actual == expected, 'loaded observation envelope constant changed: ' + name)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                fn = vars(module).get(node.name)
                need(type(fn) is types.FunctionType and same_code(fn.__code__, child(compiled, node.name)) and
                     fn.__globals__ is vars(module) and fn.__builtins__ is vars(builtins) and
                     not node.args.defaults and not any(v is not None for v in node.args.kw_defaults) and
                     fn.__defaults__ is None and fn.__kwdefaults__ is None and fn.__closure__ is None,
                     'observation guard helper code/defaults changed: ' + node.name)
    return sys.modules['observation.source_guard']


def _check_token_helpers(declaration):
    """Bind the finite byte representation, not a transitive stdlib proof."""
    inventories = {
        'capture/fixed_token_table.py': {
            'TOKEN_COUNT', 'TOKEN_TABLE_SHA256', 'SOURCE_TABLE_SHA256', 'TOKEN_WORDS'},
        'capture/token_encoder.py': {
            'SCHEMA', 'ORIGINAL_METADATA_MAX', 'ORIGINAL_RAW_MAX',
            'OUTER_METADATA_MAX', 'WIRE_MAX_CHUNK', 'ENVELOPE_MAX', '_DOMAINS'}}
    modules = {}
    for relative, expected_names in inventories.items():
        path = HERE / relative
        module = module_path(sys.modules.get(relative[:-3].replace('/', '.')), path)
        raw, _ = checked(path, declaration['files'][relative])
        tree = ast.parse(raw)
        compiled = compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
        assigned = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in expected_names:
                        need(len(node.targets) == 1 and target.id not in assigned,
                             'ambiguous token constant assignment')
                        if target.id == 'ENVELOPE_MAX':
                            need(ast.dump(node.value) == ast.dump(ast.parse(
                                '4 + ORIGINAL_METADATA_MAX + ORIGINAL_RAW_MAX',
                                mode='eval').body), 'token envelope bound expression changed')
                            expected = 4 + assigned['ORIGINAL_METADATA_MAX'] + assigned['ORIGINAL_RAW_MAX']
                        elif target.id == '_DOMAINS':
                            need(isinstance(node.value, ast.Call) and
                                 isinstance(node.value.func, ast.Name) and
                                 node.value.func.id == 'frozenset' and
                                 len(node.value.args) == 1 and not node.value.keywords,
                                 'token domain literal constructor changed')
                            expected = frozenset(ast.literal_eval(node.value.args[0]))
                        else:
                            expected = ast.literal_eval(node.value)
                        assigned[target.id] = expected
        need(set(assigned) == expected_names, 'token constant inventory differs')
        for name, expected in assigned.items():
            actual = vars(module).get(name)
            need(type(expected) in (str, int, tuple, frozenset) and
                 type(actual) is type(expected) and actual == expected,
                 'loaded token constant changed: ' + name)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                fn = vars(module).get(node.name)
                need(type(fn) is types.FunctionType and
                     same_code(fn.__code__, child(compiled, node.name)) and
                     fn.__globals__ is vars(module) and fn.__builtins__ is vars(builtins) and
                     not node.args.defaults and not any(v is not None for v in node.args.kw_defaults) and
                     fn.__defaults__ is None and fn.__kwdefaults__ is None and fn.__closure__ is None,
                     'token helper code/defaults changed: ' + node.name)
        modules[relative] = module
    table = modules['capture/fixed_token_table.py']
    encoder = modules['capture/token_encoder.py']
    need(table.hashlib is sys.modules['hashlib'] and table.struct is sys.modules['struct'],
         'token table imported modules changed')
    need(encoder.verify_runtime_bindings(table.TOKEN_TABLE_SHA256) is True,
         'token derived runtime binding check failed')


def _authority():
    raw, identity = checked(HERE / 'ADMISSION.json')
    need(identity['sha256'] == os.environ.get('QWEN2_FIXED93_ADMISSION_SHA256'), 'new externally bound actual admission absent')
    declaration = json.loads(raw)
    need(type(declaration) is dict and declaration.get('startup_only') is True and
         declaration.get('fullblock_authorized') is False and declaration.get('M128_authorized') is False and
         declaration.get('entrypoint') == 'integration/startup_probe.py' and
         declaration.get('stop_before') == 'first_x.advance_to_request',
         'root authority must be startup-only with the exact stop boundary')
    need(declaration.get('schema') == 'fixed93-startup-probe-admission-v1' and
         declaration.get('status') == 'REVIEWED_FIXED93_STARTUP_PROBE_ACTUAL' and
         declaration.get('actual_execution_authorized') is True and declaration.get('source_only') is False and
         declaration.get('automatic_retry') is False and declaration.get('evidence_contract') == CONTRACT,
         'source-only or wrong-contract admission cannot construct actual observation')
    pins = declaration.get('files')
    required = {'admission.py', 'fullblock_runtime.py', 'SOURCE_MANIFEST.json', 'BUDGET_PROPOSAL.json',
                'native_reuse.py', 'NATIVE_REUSE_PINS.json', 'RUNTIME_PINS.json',
                'capture/anchors.json', 'capture/CODEC_PINS.json', 'observation/TRACE_CODES.json'}
    required.update(str(p.relative_to(HERE)) for base in ('capture', 'observation') for p in (HERE / base).rglob('*.py'))
    need(type(pins) is dict and required <= pins.keys(), 'factory/observation/codec/anchor exact pins missing')
    for name in required:
        checked(HERE / name, pins[name])
    bridge = module_path(sys.modules.get('admission'), HERE / 'admission.py')
    # Parent's function has no dependency on DUT instances; source code and
    # defaults are checked, while its private one-use state is its authority.
    tree = ast.parse((HERE / 'admission.py').read_bytes())
    node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'require_actual_runtime'), None)
    fn = vars(bridge).get('require_actual_runtime')
    code = child(compile((HERE / 'admission.py').read_bytes(), str(HERE / 'admission.py'), 'exec', dont_inherit=True, optimize=0), 'require_actual_runtime')
    need(node is not None and type(fn) is types.FunctionType and same_code(fn.__code__, code) and
         fn.__globals__ is vars(bridge) and fn.__defaults__ is None and fn.__kwdefaults__ is None,
         'canonical actual-runtime authority code/defaults missing')
    actual = fn('wholeblock_observation_factory')
    need(type(actual) is dict, 'independent live actual authority missing')
    return declaration, actual


def _sources(declaration, actual, source_context):
    raw, ident = checked(HERE / 'SOURCE_MANIFEST.json', declaration['files']['SOURCE_MANIFEST.json'])
    manifest = json.loads(raw)
    need(actual.get('source_manifest') == manifest and type(source_context) is dict and
         set(source_context) == {'source_root', 'source_manifest', 'source_sha256'} and
         Path(source_context['source_root']).resolve() == SOURCE and
         Path(source_context['source_manifest']).resolve() == HERE / 'SOURCE_MANIFEST.json' and
         source_context['source_sha256'] == manifest['source_sha256'], 'actual/source_context final manifest mismatch')
    hashes, sizes = manifest['source_sha256'], manifest['source_bytes']
    need(type(hashes) is dict and type(sizes) is dict and hashes.keys() == sizes.keys() and len(hashes) == 306,
         'exact frozen306 source closure required')
    result = {}
    for relative, digest in hashes.items():
        need(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'source path escape')
        path = SOURCE / relative
        checked(path, dict(bytes=sizes[relative], sha256=digest))
        result[str(path)] = digest
    return manifest, ident['sha256'], result


def _budget(declaration, actual, manifest_sha):
    raw, ident = checked(HERE / 'BUDGET_PROPOSAL.json', declaration['files']['BUDGET_PROPOSAL.json'])
    budget = json.loads(raw)
    need(declaration.get('budget_reviewed') is True and actual.get('budget_sha256') == ident['sha256'] and
         budget.get('status') == 'REVIEWED_FIXED93_STARTUP_PROBE_BUDGET' and actual.get('limits') == budget and
         budget.get('automatic_retry') is False, 'new reviewed complete wholeblock budget missing')
    need(budget.get('schema') == 'fixed93-startup-probe-resource-v1' and
         budget.get('startup_only_scope_required') is True and budget.get('wholeblock_scope_required') is False and
         budget.get('inner_wall_seconds') == 30 and budget.get('outer_wall_seconds') == 45 and
         budget.get('rss_bytes') == 2147483648 and budget.get('one_cpu') is True and
         budget.get('output_bytes') == 16777216 and budget.get('file_bytes') == 8388608 and
         budget.get('sample_rows') == 46 and budget.get('automatic_retry') is False,
         'exact startup-only bounded resource scope required')
    whole, attention_template = budget.get('wholeblock_trace_limits'), budget.get('attention_trace_limits')
    need(type(attention_template) is dict and
         attention_template.get('source_manifest_sha256') == 'DERIVE_FROM_REVIEWED_SOURCE_MANIFEST',
         'noncircular Attention manifest binding marker required')
    attention = dict(attention_template, source_manifest_sha256=manifest_sha)
    need(type(whole) is dict and set(whole) == TRACE_FIELDS and
         type(whole['codec']) is dict and set(whole['codec']) == CODEC_FIELDS and
         actual.get('wholeblock_trace_limits') == whole and actual.get('attention_trace_limits') == attention,
         'exact explicit trace budget handoff missing')
    for key in ('inner_wall_seconds', 'outer_wall_seconds', 'rss_bytes', 'output_bytes', 'file_bytes', 'log_bytes'):
        need(type(budget.get(key)) is int and budget[key] > 0, 'positive complete-run budget missing: ' + key)
    need(type(attention) is dict and attention.get('source_manifest_sha256') == manifest_sha and
         attention.get('max_m') == 128 and type(attention.get('codec_limits')) is dict and
         set(attention['codec_limits']) == CODEC_FIELDS, 'final M128 Attention budget binding missing')
    for domain in (whole['codec'], attention['codec_limits']):
        need(all(type(v) is int and v > 0 for v in domain.values()), 'positive explicit codec limits required')
        worst = 52 + domain['max_raw'] + domain['max_records'] * (88 + domain['max_metadata']) + 146
        need(worst <= domain['max_output'] <= budget['file_bytes'], 'no-compression codec reservation exceeds admitted file limit')
    need(whole['codec']['max_output'] + attention['codec_limits']['max_output'] <= budget['output_bytes'],
         'two stream reservations exceed whole-run output limit')
    # Algorithm files and logs/free-space margin remain the independent parent's
    # complete resource derivation, not guessed by this construction adapter.
    return whole, attention


def _modules(runtime_context):
    required = {'r','dense','native','helper','original','fixtures','public','prefix','scalar',
                'owner_module','binding','profiles','execution','suffix','observation','built','reuse'}
    need(type(runtime_context) is dict and set(runtime_context) == required, 'exact runner runtime_context required')
    result = {}
    paths = dict(r='dense_block_reduce/check_public_numeric', dense='official_bf16/dense_silu',
        helper='ffn_public/check_numeric', original='ffn_public/execute_numeric', fixtures='ffn_public/fixture',
        public='ffn_public/model', prefix='ffn_public/prefix_execution', scalar='ffn_public/prefix_arithmetic',
        owner_module='dense_block_reduce/dense_drain', binding='dense_block_reduce/matrix_binding',
        profiles='dense_block_reduce/profile', execution='dense_block_reduce/public_execution',
        suffix='ffn_public/fullgraph_execution', observation='dense_block_reduce/observation')
    paths = {name: 'candidates/qwen2_resident_matrix/' + value + '.py' for name, value in paths.items()}
    paths['native'] = 'scripts/qwen2_layer0_model_gate.py'
    for name, relative in paths.items():
        module = module_path(runtime_context[name], SOURCE / relative)
        need(sys.modules.get(relative[:-3].replace('/', '.')) is module,
             'runtime_context canonical module alias differs: ' + name)
    original = runtime_context['original']
    explicit = (original, original.numeric, original.numeric.drain_check, original.down_driver)
    for module in explicit:
        path = Path(module.__file__).resolve()
        need(path.is_relative_to(SOURCE), 'original dynamic module outside frozen source')
        result[str(path.relative_to(SOURCE))] = module
    return result


def _resolve(relative, explicit):
    path = SOURCE / relative
    module = explicit.get(relative)
    if module is None:
        module = sys.modules.get(relative[:-3].replace('/', '.'))
    return module_path(module, path)


def _native(declaration, actual, library, context, attention):
    adapter = module_path(sys.modules.get('_fixed93_parent_native_reuse'), HERE / 'native_reuse.py')
    # Reuse the exact parent's map/address verifier. This performs no CDLL load,
    # reset, entrypoint invocation, or numerical work. Read-only ctypes.cast only.
    verifier = LoadedClosure({str(HERE / 'native_reuse.py'): declaration['files']['native_reuse.py']['sha256']})
    for name in ('pins', '_maps', '_loaded_receipt', 'checked', 'need'):
        verifier.function(adapter, name)
    need(adapter._LOADED is library, 'not the one actual admitted loaded ELF object')
    value, built = adapter.pins()
    runtime_raw, _ = checked(HERE / 'RUNTIME_PINS.json', declaration['files']['RUNTIME_PINS.json'])
    runtime = json.loads(runtime_raw)
    need(actual.get('runtime_pins') == runtime and context['built'] == built, 'native build/runtime receipt differs')
    ctypes_module = sys.modules.get('ctypes')
    need(type(ctypes_module) is types.ModuleType and context['dense'].C is ctypes_module, 'exact loaded ctypes alias missing')
    fresh = adapter._loaded_receipt(library, value, runtime, ctypes_module)
    need(fresh == context['reuse'] and fresh['compilation_performed'] is False and
         fresh['old_numeric_state_reused'] is False and fresh['reset_performed_by_loader'] is False,
         'actual native load receipt/map/symbol identity differs')
    need(attention['native_library_path'] == value['files']['elf']['path'] and
         attention['native_library_sha256'] == value['files']['elf']['sha256'], 'Attention native budget pins differ')
    return fresh, ctypes_module.CDLL


def accumulator_mapping(address, library_path):
    """Read-only coverage proof for all existing 81920 bank bytes, not a getter.

    The anonymous zero-fill tail is legal only within the exact loaded ELF's
    writable PT_LOAD interval. No memory is read and no native symbol is called.
    """
    extent = 5 * 16 * 256 * 4
    need(type(address) is int and 0 < address <= (1 << 64) - extent and address % 4 == 0,
         'saved accumulator pointer invalid or interval overflows UInt64')
    raw, identity = checked(Path(library_path))
    need(raw[:6] == b'\x7fELF\x02\x01' and len(raw) >= 64, 'existing little-endian ELF64 required')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    need(header[1] == 3 and header[2] == 62 and header[9] == 56 and 0 < header[10] <= 64,
         'exact x86_64 ET_DYN program headers required')
    offset, stride, count = header[5], header[9], header[10]
    need(offset + stride * count <= len(raw), 'ELF program header range')
    segments = [struct.unpack_from('<IIQQQQQQ', raw, offset + i * stride) for i in range(count)]
    loads = [p for p in segments if p[0] == 1]
    need(loads and all(p[5] <= p[6] and p[2] + p[5] <= len(raw) and
                       p[3] + p[6] <= 1 << 64 for p in loads),
         'ELF load file/virtual interval overflow or invalid extent')
    zero = [p for p in loads if p[2] == 0]
    need(len(zero) == 1 and zero[0][3] % 4096 == 0, 'unambiguous ELF load-bias segment required')
    rows = []
    for line in Path('/proc/self/maps').read_text().splitlines():
        parts = line.split(maxsplit=5)
        need(len(parts) in (5, 6), 'mapped row format')
        lo, hi = (int(v, 16) for v in parts[0].split('-'))
        need(0 <= lo < hi <= 1 << 64 and len(parts[1]) == 4, 'mapped row UInt64 range')
        rows.append(dict(lo=lo, hi=hi, permissions=parts[1], offset=int(parts[2], 16),
                         device=parts[3], inode=int(parts[4]), path=parts[5] if len(parts) == 6 else '', raw=line))
    origins = [r for r in rows if r['path'] == library_path and r['offset'] == 0]
    need(len(origins) == 1, 'one existing ELF base mapping required')
    bias = origins[0]['lo'] - zero[0][3]
    need(bias >= 0 and all(bias + p[3] + p[6] <= 1 << 64 for p in loads),
         'loaded ELF interval overflows UInt64')
    enclosing = [p for p in loads if p[1] & 2 and not p[1] & 1 and
                 bias + p[3] <= address and address + extent <= bias + p[3] + p[6]]
    need(len(enclosing) == 1, 'full accumulator interval outside exact ELF writable data/BSS segment')
    segment = enclosing[0]
    relevant = [r for r in rows if r['lo'] < address + extent and r['hi'] > address]
    cursor = address
    stat = Path(library_path).stat()
    for row in relevant:
        need(row['lo'] <= cursor < row['hi'] and 'r' in row['permissions'] and
             'w' in row['permissions'] and 'x' not in row['permissions'] and row['permissions'][-1] == 'p',
             'accumulator mapping gap or wrong protection')
        if row['path'] == library_path:
            need(row['inode'] == stat.st_ino and tuple(int(v, 16) for v in row['device'].split(':')) ==
                 (os.major(stat.st_dev), os.minor(stat.st_dev)), 'bank ELF mapping file identity changed')
        else:
            need(row['path'] == '' and row['inode'] == 0 and
                 cursor >= bias + segment[3] + segment[5], 'bank outside exact ELF anonymous BSS tail')
        cursor = min(address + extent, row['hi'])
    need(cursor == address + extent, 'full accumulator mapping coverage missing')
    return dict(address=address, bytes=extent, library=library_path, library_sha256=identity['sha256'],
                load_bias=bias, writable_segment_start=bias + segment[3],
                writable_segment_end=bias + segment[3] + segment[6],
                mappings=[r['raw'] for r in relevant], native_getter_called=False, bank_values_read=False)


class BoundWholeblock:
    """Bind-time exact-object checks, then an unchanged capture delegate."""
    def __init__(self, capture, closure, modules, native_check, source_guard, declaration):
        self.capture, self.closure, self.modules = capture, closure, modules
        self.native_check, self.source_guard = native_check, source_guard
        self.declaration = declaration
        self.public_trace, self.trace_dispatcher = capture.public_trace, capture.trace_dispatcher
        self.objects = None
        self.bank_identity = None
        self.bank_latest = None

    def _verify(self):
        self.closure.revalidate()
        if self.objects is None:
            return
        x = self.objects['x']
        m = self.modules
        need(type(x.owner) is m['dense_owner'].DenseReductionOwner and
             type(x.prefix_owner) is m['official_owners'].OfficialPrefixOwner and
             type(x.attention_owner) is m['fixed_owner'].Fixed93AttentionOwner and
             type(x.matrix_service) is m['profiled'].ProfiledMatrixService and
             type(x.prefix_owner.scalar) is m['scalar'].ScalarService and
             x.prefix_owner.scalar is x.attention_owner.scalar and x.matrix_service is x.attention_owner.matrix,
             'exact shared owner/service types changed')
        need(_check_observation_helpers(self.declaration) is self.source_guard, 'observation guard module replaced')
        _check_token_helpers(self.declaration)
        self.source_guard.verify_loaded(x.attention_owner, SOURCE)
        self.native_check()
        bank = accumulator_mapping(x.matrix_service.resource_address, self.objects['library']._name)
        if self.bank_identity is None:
            self.bank_identity = bank
        stable = ('address', 'bytes', 'library', 'library_sha256', 'load_bias',
                  'writable_segment_start', 'writable_segment_end')
        need(all(bank[k] == self.bank_identity[k] for k in stable),
             'whole original accumulator interval identity changed')
        # An unrelated adjacent anonymous allocation may split/merge a maps row.
        # Re-prove full interval coverage every time; do not equate row text with
        # the identity of bytes outside this exact ELF segment.
        self.bank_latest = bank

    def bind(self, x, physical, memory, silu, library):
        need(self.objects is None, 'one fresh binding only')
        self.objects = dict(x=x, physical=physical, memory=memory, silu=silu, library=library)
        self._verify()
        self.capture.bind(**self.objects)
        return self

    def __enter__(self):
        need(self.objects is not None, 'bind before context entry')
        self._verify()
        self.capture.__enter__()
        return self

    def __exit__(self, kind, value, traceback):
        return self.capture.__exit__(kind, value, traceback)

    def check(self):
        return self.capture.check()

    def seal(self, report):
        self._verify()
        report['wholeblock_runtime_binding'] = dict(
            actual_loaded_functions=len(self.closure.checked_functions),
            actual_loaded_classes=len(self.closure.checked_classes),
            accumulator_mapping_initial=self.bank_identity, accumulator_mapping_terminal=self.bank_latest,
            complete_hermetic_runtime_proof=False,
            selected_loaded_code_defaults_aliases_and_mro_checked=True,
            arbitrary_transitive_stdlib_closure_reproved=False)
        return self.capture.seal(report)

    def close(self):
        return self.capture.close()


def wholeblock_observation(*, out, library, source_context, runtime_context):
    """Exact runner factory API. Not a preflight, constructor probe or launch."""
    global _FACTORY_USED
    need(not _FACTORY_USED, 'wholeblock observation factory is single-use')
    declaration, actual = _authority()
    _FACTORY_USED = True  # Failure after independent admission cannot be retried.
    need(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12) and
         not sys.flags.optimize, 'pinned CPython3.12 unoptimized source-code verification required')
    out = Path(out)
    need(out.is_absolute() and out.resolve() == out and out.is_dir() and
         out.is_relative_to(HERE / 'work/fixed93_fullblock') and not out.is_symlink(), 'fresh runner output namespace required')
    manifest, manifest_sha, sources = _sources(declaration, actual, source_context)
    whole_limits, attention_limits = _budget(declaration, actual, manifest_sha)
    explicit = _modules(runtime_context)
    native_identity, library_type = _native(declaration, actual, library, runtime_context, attention_limits)
    closure = LoadedClosure(sources)
    anchors = json.loads((HERE / 'capture/anchors.json').read_bytes())
    need(len(anchors) == 50, 'reviewed sparse capture anchor inventory changed')
    descriptors = {}
    for key, expected in anchors.items():
        module = _resolve(expected['relative_path'], explicit)
        d = closure.function(module, expected['qualname'])
        need(d['sha256'] == expected['sha256'] and d['firstlineno'] == expected['firstlineno'], 'capture anchor source differs: ' + key)
        descriptors[key] = d
    trace_codes = json.loads((HERE / 'observation/TRACE_CODES.json').read_bytes())['loaded_code_descriptors']
    need(len(trace_codes) == 24, 'reviewed Attention code inventory changed')
    for i, (name, cls, member) in enumerate(trace_codes):
        module = _resolve(name.replace('.', '/') + '.py', explicit)
        descriptors['attention_' + str(i)] = closure.function(module, (cls + '.' if cls else '') + member)
    names = dict(fixed_binding='candidates.qwen2_fixed93_attention.binding',
        fixed_owner='candidates.qwen2_fixed93_attention.owner',
        dense_owner='candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain',
        official_owners='candidates.qwen2_resident_matrix.official_bf16.owners',
        profiled='candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding',
        scalar='candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic',
        physical='candidates.qwen2_resident_matrix.ffn_public.prefix_execution',
        memory='candidates.qwen2_resident_matrix.ffn_public.fullgraph_memory',
        silu='candidates.qwen2_resident_matrix.official_bf16.execution')
    modules = {key: _resolve(name.replace('.', '/') + '.py', explicit) for key, name in names.items()}
    selected_classes = [(modules['fixed_binding'], 'Fixed93PublicExecution'), (modules['fixed_binding'], 'Fixed93ReductionDriver'),
        (modules['fixed_owner'], 'Fixed93AttentionOwner'), (modules['dense_owner'], 'DenseReductionOwner'),
        (modules['official_owners'], 'OfficialPrefixOwner'), (modules['profiled'], 'ProfiledMatrixService'),
        (modules['scalar'], 'ScalarService'), (modules['physical'], 'PhysicalMemory'),
        (modules['memory'], 'FullGraphMemory'), (modules['memory'], 'SharedWorkspace'),
        (modules['silu'], 'ObservedSiluLibrary')]
    for module, name in selected_classes:
        closure.cls(vars(module)[name])
    matrix_globals = descriptors['matrix_accept_step']['function'].__globals__
    ordinary_globals = descriptors['public_ordinary_edge']['function'].__globals__
    matrix_payload_types = dict(
        normal_result=matrix_globals['MatrixResult'],
        matrix_value=matrix_globals['MatrixValue'],
        dense_result=ordinary_globals['numeric'].model.MatrixResult)
    need(matrix_payload_types['dense_result'] is
         descriptors['silu_execute']['function'].__globals__['model'].MatrixResult and
         matrix_payload_types['dense_result'] is
         descriptors['reduce_tick']['function'].__globals__['MatrixResult'],
         'one source-selected Dense result class across driver families')
    for cls in matrix_payload_types.values():
        closure.cls(cls)
    closure.cls(matrix_globals['_MatrixRow'])
    attention_globals = descriptors['owner_attention']['function'].__globals__
    reduction_globals = descriptors['reduce_tick']['function'].__globals__
    operand_payload_types = dict(
        dense_step=ordinary_globals['numeric'].model.Step,
        window_step=reduction_globals['DenseReductionOwner']._operand_response.__globals__['KWindowStep'],
        normal_step=matrix_globals['NormalStep'],
        legacy_request=attention_globals['LegacyRequest'],
        packed_request=attention_globals['PackedQkRequest'])
    for cls in operand_payload_types.values():
        closure.cls(cls)
    # These observation modules were hash-pinned before their actual import.
    from observation import source_guard
    from observation.event_stream import load_codec
    from capture.wholeblock import WholeblockObservation
    from capture import token_encoder
    need(_check_observation_helpers(declaration) is source_guard, 'observation guard module identity differs')
    _check_token_helpers(declaration)
    codec_root = Path(attention_limits['codec_root'])
    need(codec_root.is_absolute() and codec_root.resolve() == codec_root and codec_root.is_dir(), 'exact reviewed codec root required')
    codec_pins = json.loads((HERE / 'capture/CODEC_PINS.json').read_bytes())
    for name, digest in codec_pins.items():
        _, identity = checked(codec_root / name)
        need(identity['sha256'] == digest, 'r3 codec source differs')
    fmt, writer = load_codec(codec_root)
    need(writer.Writer.__module__ == 'writer' and fmt.Limits.__module__ == 'format', 'codec real type identity required')
    codec = dict(Writer=writer.Writer, Limits=fmt.Limits,
                 source_sha256={str(codec_root / name): digest for name, digest in codec_pins.items()})
    identity_types = dict(x=modules['fixed_binding'].Fixed93PublicExecution,
        physical=modules['physical'].PhysicalMemory, memory=modules['memory'].FullGraphMemory,
        silu=modules['silu'].ObservedSiluLibrary, library=library_type)
    admission = dict(source_roots=[str(SOURCE)], sources=sources, loaded_codes=descriptors,
        identity_types=identity_types, source_verified=True, native_verified=True,
        native_identity=native_identity, jsonable=descriptors['jsonable']['function'], codec=codec,
        matrix_payload_types=matrix_payload_types, operand_payload_types=operand_payload_types)
    # The booleans above summarize the preceding checks, not an input authority.
    capture = WholeblockObservation(out, admission=admission, trace_limits=whole_limits)
    return BoundWholeblock(capture, closure, modules,
        lambda: _native(declaration, actual, library, runtime_context, attention_limits), source_guard, declaration)
