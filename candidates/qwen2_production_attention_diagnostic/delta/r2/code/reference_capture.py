"""Terminal-only capture of the EXISTING AST-loaded independent recipe.

This module does not import a DUT, NumPy, a native library, or an oracle module.
The caller imports the pinned old oracle only AFTER all DUT terminal ACKs.
No arithmetic is implemented here. The old observer's _line, _put, _bytes and
_coverage definitions are reused without constructing its native-only owner.
This is reference provenance, never NORMAL_LOADED_SOURCE DUT provenance.
"""
import ast
from array import array
import hashlib
from pathlib import Path
import sys
import threading
import types


FIELDS = ('dot_parts', 'unrounded_dot_sum', 'dot_bf16', 'scores_bf16',
          'softmax_exp', 'softmax_fp32', 'prob_bf16', 'normalizer',
          'pv_raw', 'pv_bf16')
ROLES = frozenset(('oracle_harness', 'original_driver', 'original_owner',
                   'original_adapter', 'prefix_owner', 'arithmetic',
                   'exp_recipe', 'observer', 'buffer_helper', 'buffer'))
SENTINEL = 0xa5963cc3
DRIVER_DEFINITIONS = ('finite', 'ref_fma', 'ArithmeticFault', 'PrefixFault', 'ExactScalar',
                      'LegacyRequest', 'SelectedMatrix', 'OriginalSchedule', 'fixture')
ARITHMETIC_DEFINITIONS = ('exact', 'rn', 'ref_add', 'ref_mul', 'ref_div', 'ref_bf')
EXP_DEFINITIONS = ('EXP_COEFFICIENTS', 'LOG2_RECIPROCAL', 'exp_negative')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def _sources(pins):
    need(type(pins) is dict and set(pins) == ROLES, 'exact reference source roles required')
    result = {}
    for role, pin in pins.items():
        need(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'},
             'exact reference pin keys required: ' + role)
        path = Path(pin['path'])
        need(path.is_absolute() and path == path.resolve(strict=True) and path.is_file(),
             'unaliasable reference source required: ' + role)
        raw = path.read_bytes()
        need(type(pin['bytes']) is int and len(raw) == pin['bytes'] and
             hashlib.sha256(raw).hexdigest() == pin['sha256'],
             'reference source drift: ' + role)
        result[role] = (path, raw, ast.parse(raw, filename=str(path)))
    return result


def _child(code, name):
    found = [x for x in code.co_consts if isinstance(x, types.CodeType) and x.co_name == name]
    need(len(found) == 1, 'ambiguous reference code: ' + name)
    return found[0]


def _node(source, classname, name):
    body = source[2].body
    if classname is not None:
        classes = [n for n in body if isinstance(n, ast.ClassDef) and n.name == classname]
        need(len(classes) == 1, 'missing reference class: ' + str(classname))
        body = classes[0].body
    found = [n for n in body if isinstance(n, ast.FunctionDef) and n.name == name]
    need(len(found) == 1, 'missing reference method: ' + name)
    return found[0]


def _expected(source, classname, name, extracted, *, definition_names=None, extracted_names=None):
    # Match the old source_definitions loader exactly: extracted methods lose
    # only their decorators and class nesting, never their function bodies.
    if definition_names is not None:
        need(not extracted and extracted_names is None, 'ambiguous reference compile mode')
        nodes = [node for node in source[2].body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                 and node.name in definition_names]
        need({node.name for node in nodes} == set(definition_names), 'reference definition group changed')
        tree = ast.Module(body=nodes, type_ignores=[])
        code = compile(tree, str(source[0]), 'exec', dont_inherit=True, optimize=0)
        if classname is not None:
            code = _child(code, classname)
    elif extracted:
        names = (name,) if extracted_names is None else extracted_names
        body = source[2].body
        if classname is not None:
            classes = [node for node in body if isinstance(node, ast.ClassDef) and node.name == classname]
            need(len(classes) == 1, 'reference extraction class missing')
            body = classes[0].body
        nodes = []
        for node in body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                node.decorator_list = []
                nodes.append(node)
            elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                                                      target.id in names for target in node.targets):
                nodes.append(node)
        need(len(nodes) == len(names), 'reference extraction group changed')
        code = compile(ast.Module(body=nodes, type_ignores=[]), str(source[0]),
                       'exec', dont_inherit=True, optimize=0)
    else:
        code = compile(source[1], str(source[0]), 'exec', dont_inherit=True, optimize=0)
        if classname is not None:
            code = _child(code, classname)
    return _child(code, name)


def _bind(actual, source, classname, name, *, extracted=False, namespace=None,
          definition_names=None, extracted_names=None):
    actual = getattr(actual, '__func__', actual)
    if hasattr(actual, '__wrapped__'):
        # Only the existing lru_cache(exact) wrapper is expected.
        need(name == 'exact' and type(actual).__module__ == 'functools',
             'unexpected wrapped reference function')
        actual = actual.__wrapped__
    need(type(actual) is types.FunctionType, 'reference target is not a function: ' + name)
    expected = _expected(source, classname, name, extracted,
                         definition_names=definition_names, extracted_names=extracted_names)
    code = actual.__code__
    need(code == expected and code.co_filename == str(source[0]) and
         code.co_firstlineno == expected.co_firstlineno and
         code.co_linetable == expected.co_linetable and
         code.co_exceptiontable == expected.co_exceptiontable,
         'loaded reference code differs: ' + str(classname) + '.' + name)
    node = _node(source, classname, name)
    defaults = tuple(ast.literal_eval(value) for value in node.args.defaults) or None
    kwdefaults = {key.arg: ast.literal_eval(value) for key, value in
                  zip(node.args.kwonlyargs, node.args.kw_defaults) if value is not None} or None
    need(actual.__defaults__ == defaults and actual.__kwdefaults__ == kwdefaults,
         'reference function defaults changed: ' + name)
    if namespace is not None:
        need(actual.__globals__ is namespace, 'reference namespace alias changed: ' + name)
    if '__class__' in code.co_freevars:
        index = code.co_freevars.index('__class__')
        need(namespace is not None and actual.__closure__[index].cell_contents is namespace[classname],
             'reference class closure changed: ' + name)
    return code


def _reuse(source, classname, name):
    node = _node(source, classname, name)
    node.decorator_list = []
    namespace = {'require': need, 'array': array, 'sys': sys, 'SENTINEL': SENTINEL}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source[0]),
                 'exec', dont_inherit=True, optimize=0), namespace)
    return namespace[name]


def _point(source, classname, method, statement):
    target = ast.dump(ast.parse(statement).body[0], include_attributes=False)
    hits = [n.lineno for n in ast.walk(_node(source, classname, method))
            if isinstance(n, ast.stmt) and ast.dump(n, include_attributes=False) == target]
    need(len(hits) == 1, 'missing/ambiguous reference observation point')
    return hits[0]


def _bind_recipe(module, source, base_fields):
    need(type(module) is types.ModuleType and Path(module.__file__).resolve() == source['oracle_harness'][0],
         'wrong existing oracle module origin')
    namespace = module.NS
    # The two original loaders are themselves source/code bound. Isolating the
    # original ClassDef group is NOT interchangeable with full-module compile:
    # CPython can select different LOAD_GLOBAL/LOAD_ATTR flags around imports.
    _bind(module.definitions, source['oracle_harness'], None, 'definitions', namespace=module.__dict__)
    need(module.source_definitions is namespace['source_definitions'], 'reference loader alias changed')
    _bind(module.source_definitions, source['original_driver'], None, 'source_definitions',
          namespace=namespace, definition_names=('source_definitions',))
    calls = [node for node in ast.walk(source['oracle_harness'][2]) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == 'definitions' and len(node.args) >= 2
             and isinstance(node.args[0], ast.Name) and node.args[0].id == 'COLD_SOURCE']
    need(sorted(ast.literal_eval(node.args[1]) for node in calls) ==
         sorted((('source_definitions',), DRIVER_DEFINITIONS)), 'original loader groups changed')
    need(type(namespace) is dict and namespace['OriginalSchedule'] is module.OriginalSchedule and
         namespace['ExactScalar'] is module.ExactScalar and
         module.ObservedOriginal.__bases__ == (module.OriginalSchedule,) and
         module.ObservedScalar.__bases__ == (module.ExactScalar,), 'reference class aliases changed')
    for name in ('run', 'scores', '_attention', '_matrix_step', '_op', '_read', '_write', '_less'):
        need(getattr(module.ObservedOriginal, name) is getattr(module.OriginalSchedule, name),
             'reference subclass shadows original method: ' + name)
    for name in ('__init__', '_op', '_response', 'run', 'scores'):
        _bind(getattr(module.OriginalSchedule, name), source['original_driver'],
              'OriginalSchedule', name, namespace=namespace, definition_names=DRIVER_DEFINITIONS)
    for cls, methods in ((module.ObservedOriginal, ('__init__', '_response')),
                         (module.ObservedScalar, ('__init__', 'op'))):
        for name in methods:
            _bind(getattr(cls, name), source['oracle_harness'], cls.__name__, name,
                  namespace=module.__dict__)
    for name in ('__init__', 'op', '__call__'):
        _bind(getattr(module.ExactScalar, name), source['original_driver'],
              'ExactScalar', name, namespace=namespace, definition_names=DRIVER_DEFINITIONS)
    for name in ('finite', 'ref_fma'):
        _bind(namespace[name], source['original_driver'], None, name, namespace=namespace,
              definition_names=DRIVER_DEFINITIONS)
    for name in ('__init__', '__getitem__'):
        _bind(getattr(namespace['SelectedMatrix'], name), source['original_driver'],
              'SelectedMatrix', name, namespace=namespace, definition_names=DRIVER_DEFINITIONS)
    for name in ('exact', 'rn', 'ref_add', 'ref_mul', 'ref_div', 'ref_bf'):
        _bind(namespace[name], source['arithmetic'], None, name, extracted=True, namespace=namespace,
              extracted_names=ARITHMETIC_DEFINITIONS)
    _bind(namespace['exp_negative'], source['exp_recipe'], None, 'exp_negative',
          extracted=True, namespace=namespace, extracted_names=EXP_DEFINITIONS)
    for name in ('_read', '_write'):
        _bind(getattr(module.OriginalSchedule, name), source['prefix_owner'],
              'PrefixOwner', name, extracted=True, namespace=namespace, extracted_names=('_read', '_write'))
    _bind(module.OriginalSchedule._less, source['original_adapter'], 'AttentionOwner',
          '_less', extracted=True, namespace=namespace, extracted_names=('_matrix_step', '_less'))
    codes = {}
    for name, role, cls in (('_attention', 'original_owner', 'OfficialAttentionOwner'),
                            ('_matrix_step', 'original_adapter', 'AttentionOwner')):
        codes[name] = _bind(getattr(module.OriginalSchedule, name), source[role], cls,
                            name, extracted=True, namespace=namespace,
                            extracted_names=('_matrix_step', '_less') if name == '_matrix_step' else ('_attention',))
    need(base_fields.__name__ == 'PackedFields', 'reference allocation must use original PackedFields')
    for name in ('__init__', '_put', '_bytes', 'field_summary'):
        _bind(getattr(base_fields, name), source['buffer'], 'PackedFields', name)
    return codes


class _Collector:
    def __init__(self, owner, rows, base_fields, source, codes):
        self.owner, self.job, self.codes = owner, {'m': rows}, codes
        self.fields = base_fields(rows).fields
        self._put = types.MethodType(_reuse(source['buffer_helper'], 'AttentionObservation', '_put'), self)
        self._bytes = types.MethodType(_reuse(source['buffer_helper'], 'AttentionObservation', '_bytes'), self)
        self._line = types.MethodType(_reuse(source['observer'], 'OfficialAttentionObservation', '_line'), self)
        self._coverage = types.MethodType(_reuse(source['observer'], 'OfficialAttentionObservation', '_coverage'), self)
        self.points = {
            'score': _point(source['original_owner'], 'OfficialAttentionOwner', '_attention', 'scores.append(score)'),
            'exp': _point(source['original_owner'], 'OfficialAttentionOwner', '_attention', 'probabilities.append(probability)'),
            'store': _point(source['original_owner'], 'OfficialAttentionOwner', '_attention',
                            'yield from self._write(j.dst + (token * 1536 + head * 128 + col) * 4, output)'),
            'matrix': _point(source['original_adapter'], 'AttentionOwner', '_matrix_step', 'return lanes'),
        }
        self.thread, self.error = threading.get_ident(), None
        self.callback = self._trace

    def _trace(self, frame, event, argument):
        if frame.f_code not in self.codes.values() or frame.f_locals.get('self') is not self.owner:
            return None
        try:
            need(threading.get_ident() == self.thread, 'reference observation thread changed')
            if event == 'line' and self.error is None:
                self._line(frame)
        except Exception as error:
            self.error = self.error or type(error).__name__ + ': ' + str(error)
        return self.callback

    def report(self):
        need(self.error is None, 'reference collector failed: ' + str(self.error))
        need(set(self.fields) == set(FIELDS), 'incomplete reference field inventory')
        rows = self.job['m']
        for name, field in self.fields.items():
            shape = ((12, rows, rows, 16) if name == 'dot_parts' else
                     (12, rows, 3) if name == 'normalizer' else
                     (12, rows, 128) if name in ('pv_raw', 'pv_bf16') else (12, rows, rows))
            count = 1
            for dimension in shape:
                count *= dimension
            need(field['shape'] == shape and all(len(field[key]) == count for key in ('words', 'observed', 'frequency')),
                 'reference field shape/extent changed: ' + name)
            need(field['writes'] == sum(field['frequency']) and
                 field['repeats'] == field['writes'] - sum(field['observed']),
                 'reference event accounting changed: ' + name)
        need(self._coverage(), 'reference causal presence/frequency/sentinel coverage incomplete')
        return {name: {'shape': list(field['shape']), 'observed_words': sum(field['observed']),
                       'writes': field['writes'], 'identical_repeats': field['repeats'],
                       'raw_sha256': hashlib.sha256(self._bytes(name)).hexdigest(),
                       'presence_sha256': hashlib.sha256(bytes(field['observed'])).hexdigest(),
                       'frequency_sha256': hashlib.sha256(self._bytes(name, 'frequency')).hexdigest()}
                for name, field in self.fields.items()}


def capture_reference(module, m, inputs, base_fields, source_pins, *, terminal_gate):
    """Run the old recipe once, only after the caller's ALL-DUT terminal gate.

    terminal_gate must be the caller's explicitly computed clean ACK/release
    condition, not an inferred elapsed time or a single arm's completion flag.
    Returned reference fields must NEVER be copied into a DUT capture.
    """
    need(type(terminal_gate) is bool and terminal_gate is True,
         'all DUT clean terminal ACKs must precede any reference work')
    need(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12) and not sys.flags.optimize,
         'reference capture requires reviewed non-optimized CPython 3.12')
    need(type(m) is int and m == 16, 'reference profile restricted to this exact M16 component')
    need(type(inputs) in (tuple, list) and len(inputs) == 3, 'three operator input arrays required')
    inputs = tuple(tuple(values) for values in inputs)
    need(all(len(values) == m * width and all(type(word) is int and 0 <= word < 1 << 32 for word in values)
             for values, width in zip(inputs, (1536, 256, 256))), 'reference input word geometry')
    need(sys.gettrace() is None, 'reference must not replace an existing tracer')
    source = _sources(source_pins)
    codes = _bind_recipe(module, source, base_fields)
    reference = module.ObservedOriginal(m, *inputs)
    need(type(reference) is module.ObservedOriginal and type(reference.scalar) is module.ObservedScalar and
         reference.inject_score_nonfinite is False and reference.scalar.owner is reference and
         reference.scalar.client is reference and 'op' not in reference.scalar.__dict__,
         'reference instance or injection state changed')
    need(not any(name in reference.__dict__ for name in ('run', 'scores', '_attention', '_matrix_step', '_op', '_read', '_write', '_response')),
         'reference instance method shadowing')
    capture = _Collector(reference, m, base_fields, source, codes)
    sys.settrace(capture.callback)
    intact = False
    try:
        output = reference.run()
    finally:
        intact = sys.gettrace() is capture.callback
        if intact:
            sys.settrace(None)
    need(intact, 'reference tracer was replaced')
    fields = capture.report()
    _sources(source_pins)
    _bind_recipe(module, source, base_fields)
    scores = reference.scores()[1]
    need(len(output) == m * 1536 and len(scores) == 12 * m * (m + 1) // 2,
         'incomplete original reference output/scores')
    return {'output': tuple(output), 'scores': tuple(scores), 'fields': capture.fields,
            'report': {'status': 'COMPLETE_EXISTING_REFERENCE_RECIPE_CAPTURE',
                       'execution_provenance': 'EXISTING_AST_INDEPENDENT_REFERENCE_RECIPE',
                       'normal_loaded_dut_provenance': False, 'all_dut_terminals_before_reference': True,
                       'arithmetic_or_control_replaced': False, 'dut_values_consumed': False,
                       'source_pins': {role: dict(pin) for role, pin in source_pins.items()}, 'fields': fields,
                       'reference_normalizer_frequency': '8*(token+1) actual PV packets',
                       'reference_probability_frequency': 8,
                       'hardware_acceptance': False}}
