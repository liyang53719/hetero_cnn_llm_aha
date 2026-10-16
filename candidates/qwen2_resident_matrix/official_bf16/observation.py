"""Read-only causal observations of the versioned official-BF16 software owner.

Wrap the unchanged public suffix driver in ``OfficialAttentionObservation``.
Only actual owner locals are copied. No reference tensor, service arithmetic,
scheduling decision or public completion/publication edge is changed. Missing
future-key entries remain missing. Raw PV and BF16 store words are distinct;
only an accepted successful owner terminal seals the latter as acknowledged.

The caller supplies a frozen source_sha256 mapping containing the exact v4
75-source execution inventory and all four observer/helper modules below.
V4 retains the historical inventory's names and 69 unchanged identities; only
the helper's six explicit default-profile replacements are admitted. Historical receipts
remain unchanged and confer no acceptance on this version. Loaded bytecode is
also checked. This is software evidence, not native or RTL acceptance.
"""
from __future__ import annotations

from array import array
import ast
from dataclasses import asdict
import importlib
from pathlib import Path
import sys
import threading
import types

from scripts import observe_qwen2_attention_model as base

ROOT = Path(__file__).resolve().parents[3]
HELPER = 'scripts/observe_qwen2_attention_model.py'
SOURCE_VERSION = 'qwen2-official-bf16-attention-observation-v4'
HELPER_SOURCE_VERSION = 'qwen2-existing-attention-observation-v4'
HELPER_SHA256 = '18446e01900f81c6bbf9cf211c1df6b9a86b06013e6d7ef8ae8609eea2309a45'
OWNER = 'candidates/qwen2_resident_matrix/official_bf16/owners.py'
SERVICE = 'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py'
OBSERVER = 'candidates/qwen2_resident_matrix/official_bf16/observation.py'
REQUIRED_SOURCES = (HELPER, OWNER, SERVICE, OBSERVER)
SENTINEL = 0xa5963cc3


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _code(module, name):
    matches = [value for value in module.co_consts
               if isinstance(value, types.CodeType) and value.co_name == name]
    require(len(matches) == 1, 'ambiguous compiled observation code: ' + name)
    return matches[0]


def _same_code(actual, fresh):
    # Bootstrap the loaded-helper check independently of that helper's aliases.
    return (actual == fresh and actual.co_filename == fresh.co_filename and
            actual.co_firstlineno == fresh.co_firstlineno and
            actual.co_linetable == fresh.co_linetable and
            actual.co_exceptiontable == fresh.co_exceptiontable)


def _literal(node, namespace):
    """Evaluate only source literals and names; never call a candidate helper."""
    if isinstance(node, ast.Name):
        return namespace[node.id]
    if isinstance(node, ast.Attribute):
        return getattr(_literal(node.value, namespace), node.attr)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'MappingProxyType' and len(node.args) == 1 and not node.keywords:
        return types.MappingProxyType(_literal(node.args[0], namespace))
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values = [_literal(value, namespace) for value in node.elts]
        return tuple(values) if isinstance(node, ast.Tuple) else set(values) if isinstance(node, ast.Set) else values
    if isinstance(node, ast.Dict):
        return {_literal(k, namespace): _literal(v, namespace) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.LShift, ast.Sub, ast.Add)):
        left, right = _literal(node.left, namespace), _literal(node.right, namespace)
        return left << right if isinstance(node.op, ast.LShift) else left + right if isinstance(node.op, ast.Add) else left - right
    return ast.literal_eval(node)


def _verify_module(module, relative):
    """Bind source functions, defaults, class bases and imported aliases."""
    path = ROOT / relative
    require(Path(module.__file__).resolve() == path, 'loaded dependency path changed: ' + relative)
    raw = path.read_text()
    tree = ast.parse(raw)
    fresh = compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
    checked = 0

    def function(actual, node, code):
        nonlocal checked
        descriptors = {d.id for d in node.decorator_list if isinstance(d, ast.Name)}
        descriptor = staticmethod if 'staticmethod' in descriptors else classmethod if 'classmethod' in descriptors else property if 'property' in descriptors else types.FunctionType
        require(type(actual) is descriptor, 'loaded method descriptor changed: ' + node.name)
        if isinstance(actual, (staticmethod, classmethod)):
            actual = actual.__func__
        elif isinstance(actual, property):
            actual = actual.fget
        require(isinstance(actual, types.FunctionType) and _same_code(actual.__code__, code),
                'loaded dependency function changed: ' + relative + ':' + node.name)
        args = tuple(_literal(value, module.__dict__) for value in node.args.defaults) or None
        keywords = {a.arg: _literal(d, module.__dict__)
                    for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults) if d is not None} or None
        require(actual.__defaults__ == args and actual.__kwdefaults__ == keywords and
                actual.__globals__ is module.__dict__, 'loaded defaults/globals changed: ' + node.name)
        checked += 1

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            function(getattr(module, node.name), node, _code(fresh, node.name))
        elif isinstance(node, ast.ClassDef):
            cls = getattr(module, node.name)
            expected_bases = tuple(_literal(value, module.__dict__) for value in node.bases) or (object,)
            require(isinstance(cls, type) and cls.__bases__ == expected_bases,
                    'loaded class bases changed: ' + node.name)
            code = _code(fresh, node.name)
            methods = {n.name: n for n in node.body if isinstance(n, ast.FunctionDef)}
            actual_methods = {name for name, value in vars(cls).items()
                              if isinstance(value, (types.FunctionType, staticmethod, classmethod, property))}
            generated = set()
            if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == 'dataclass' for d in node.decorator_list):
                generated = {'__init__', '__repr__', '__eq__', '__setattr__', '__delattr__', '__hash__'}
                require(cls.__dataclass_params__.frozen, 'loaded dataclass mutability changed: ' + node.name)
                fields = {n.target.id for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
                require(set(cls.__dataclass_fields__) == fields, 'loaded dataclass fields changed: ' + node.name)
                # Recreate only this trusted class declaration to verify the
                # standard decorator's generated frozen/init/equality methods.
                namespace = dict(module.__dict__)
                declaration = ast.Module(body=[node], type_ignores=[])
                exec(compile(declaration, str(path), 'exec', dont_inherit=True, optimize=0), namespace)
                fresh_cls = namespace[node.name]
                for method in generated:
                    actual_fn, fresh_fn = vars(cls).get(method), vars(fresh_cls).get(method)
                    require(isinstance(actual_fn, types.FunctionType) and
                            _same_code(actual_fn.__code__, fresh_fn.__code__) and
                            actual_fn.__defaults__ == fresh_fn.__defaults__ and
                            actual_fn.__kwdefaults__ == fresh_fn.__kwdefaults__,
                            'loaded generated dataclass method changed: ' + node.name + '.' + method)
                    checked += 1
            require(actual_methods - generated == set(methods), 'loaded class method inventory changed: ' + node.name)
            for name, method in methods.items():
                function(vars(cls).get(name), method, _code(code, name))
        elif isinstance(node, ast.ImportFrom) and node.module != '__future__':
            name = importlib.util.resolve_name('.' * node.level + (node.module or ''), module.__package__) if node.level else node.module
            source = importlib.import_module(name)
            for alias in node.names:
                require(getattr(module, alias.asname or alias.name) is getattr(source, alias.name),
                        'loaded dependency import changed: ' + relative + ':' + alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name if alias.asname else alias.name.split('.')[0]
                require(getattr(module, alias.asname or name) is importlib.import_module(name),
                        'loaded dependency module changed: ' + relative + ':' + name)
        elif isinstance(node, ast.Assign):
            try:
                value = ROOT if any(isinstance(t, ast.Name) and t.id == 'ROOT' for t in node.targets) else path.parent if any(isinstance(t, ast.Name) and t.id == 'HERE' for t in node.targets) else _literal(node.value, module.__dict__)
            except (ValueError, TypeError, KeyError):
                # Function-valued aliases are checked by imports/method code;
                # no candidate code is executed merely to validate a default.
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    require(getattr(module, target.id) == value,
                            'loaded constant changed: ' + relative + ':' + target.id)
    return checked


def verify_source_snapshot(source_sha256):
    """Verify exact v4 execution identities and every caller-frozen extra source."""
    require(isinstance(source_sha256, dict), 'frozen source_sha256 mapping required')
    require(base.sha((ROOT / HELPER).read_bytes()) == HELPER_SHA256,
            'read-only observer helper source drift')
    require(base.SOURCE_VERSION == HELPER_SOURCE_VERSION,
            'loaded observer helper source version changed')
    execution = base.verify_execution_sources()
    require(len(execution) == 75 and
            all(source_sha256.get(name) == digest for name, digest in execution.items()),
            'snapshot must retain the exact v4 75-source execution inventory')
    require(all(name in source_sha256 for name in REQUIRED_SOURCES),
            'snapshot must include all official-BF16 observer dependencies')
    for relative, digest in source_sha256.items():
        require(isinstance(relative, str) and not Path(relative).is_absolute() and
                '..' not in Path(relative).parts and isinstance(digest, str) and len(digest) == 64,
                'invalid frozen source entry')
        require(base.sha((ROOT / relative).read_bytes()) == digest,
                'official-BF16 observation source drift: ' + relative)
    return execution


def verify_loaded_dependencies(owner):
    # The old verifier still binds every unchanged arithmetic/service method,
    # relative import, source constant and participating instance method.
    count = _verify_module(base, HELPER)
    count += base.verify_loaded_dependencies(owner)
    for relative in (OWNER, SERVICE, OBSERVER):
        module = importlib.import_module(relative[:-3].replace('/', '.'))
        count += _verify_module(module, relative)
    # Public driver functions are verified without invoking or wrapping them.
    driver = importlib.import_module('candidates.qwen2_resident_matrix.ffn_public.fullgraph_execution')
    count += _verify_module(driver, 'candidates/qwen2_resident_matrix/ffn_public/fullgraph_execution.py')
    return count


class OfficialAttentionObservation(base.AttentionObservation):
    """One cold M1..M128 capture; enter while idle, including before suffix pc10."""

    def __init__(self, owner, *, source_sha256):
        from .owners import OfficialAttentionOwner
        from .dense_silu import OfficialMatrixService
        from ..ffn_public.prefix_arithmetic import ScalarService
        require(type(owner) is OfficialAttentionOwner, 'exact OfficialAttentionOwner required')
        require(type(owner.matrix) is OfficialMatrixService and type(owner.scalar) is ScalarService,
                'exact OfficialMatrixService and ScalarService required')
        require(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12)
                and not sys.flags.optimize, 'reviewed CPython 3.12 without -O required')
        self.owner, self.sources = owner, dict(source_sha256)
        self.execution_sources = verify_source_snapshot(self.sources)
        self.loaded_functions_checked = verify_loaded_dependencies(owner)
        self.instrumentation_sha256 = base.sha(Path(__file__).read_bytes())
        self.services = owner.matrix, owner.scalar
        self.codes, methods = {}, {}
        for name in ('_attention', '_matrix_step', 'tick'):
            method = getattr(owner, name)
            path = ROOT / (OWNER if name == '_attention' else base.OWNER)
            cls_name = 'OfficialAttentionOwner' if name == '_attention' else 'AttentionOwner'
            raw = path.read_text()
            code = _code(_code(compile(raw, str(path), 'exec', dont_inherit=True, optimize=0), cls_name), name)
            require(isinstance(method, types.MethodType) and _same_code(method.__func__.__code__, code),
                    'loaded observation target changed: ' + name)
            self.codes[name] = method.__func__.__code__
            cls = next(n for n in ast.parse(raw).body if isinstance(n, ast.ClassDef) and n.name == cls_name)
            methods[name] = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)

        def point(method, statement):
            expected = ast.dump(ast.parse(statement).body[0], include_attributes=False)
            found = [n.lineno for n in ast.walk(methods[method]) if isinstance(n, ast.stmt)
                     and ast.dump(n, include_attributes=False) == expected]
            require(len(found) == 1, 'ambiguous observation statement: ' + statement)
            return found[0]

        self.points = dict(score=point('_attention', 'scores.append(score)'),
            exp=point('_attention', 'probabilities.append(probability)'),
            matrix=point('_matrix_step', 'return lanes'),
            store=point('_attention', 'yield from self._write(j.dst + (token * 1536 + head * 128 + col) * 4, output)'))
        self.thread = threading.get_ident()
        self.active = self.closed = self.disarmed = False
        self.started = 0
        self.job = self.terminal = self.retirement = self.error = None
        self.fields = {}
        self._callback = self._trace

    def __enter__(self):
        require(threading.get_ident() == self.thread, 'observation thread changed')
        require(not self.active and not self.closed and self.started == 0, 'observer is single-use')
        require(sys.gettrace() is None, 'existing tracer must not be replaced')
        require(self.owner.state == 'idle' and not self.owner.poison and
                self.owner.matrix.owner is None and not self.owner.matrix.reset_required and
                self.owner.scalar.client is None, 'observe before an idle owner launch')
        verify_source_snapshot(self.sources)
        require(verify_loaded_dependencies(self.owner) == self.loaded_functions_checked,
                'loaded dependencies changed before entry')
        self.active = True
        sys.settrace(self._callback)
        return self

    def __exit__(self, kind, error, traceback):
        require(threading.get_ident() == self.thread, 'observation thread changed')
        installed = sys.gettrace()
        intact = installed is self._callback or (self.disarmed and installed is None)
        if installed is self._callback:
            sys.settrace(None)
        self.active, self.closed = False, True
        if not intact:
            self.error = self.error or 'observer trace was replaced'
        if kind is not None:
            self.error = self.error or 'driver exited with an exception'
        try:
            require(verify_source_snapshot(self.sources) == self.execution_sources, 'execution inventory drift')
            require(verify_loaded_dependencies(self.owner) == self.loaded_functions_checked,
                    'loaded dependency inventory changed')
        except Exception as failure:
            self.error = self.error or str(failure)
            raise
        return False

    def _start(self, edge):
        require(self.started == 0 and self.owner.job is not None, 'more than one observed launch')
        job = self.owner.job
        require(1 <= job.m <= 128, 'observer geometry restricted to cold M1..M128')
        self.started, self.job = 1, asdict(job)
        m = job.m
        for name, shape in {
            'dot_parts': (12, m, m, 16), 'unrounded_dot_sum': (12, m, m),
            'dot_bf16': (12, m, m), 'scores_bf16': (12, m, m),
            'softmax_exp': (12, m, m), 'softmax_fp32': (12, m, m),
            'prob_bf16': (12, m, m), 'normalizer': (12, m, 3),
            'pv_raw': (12, m, 128), 'pv_bf16': (12, m, 128),
        }.items():
            count = 1
            for dimension in shape:
                count *= dimension
            self.fields[name] = dict(shape=shape, words=array('I', [SENTINEL]) * count,
                observed=bytearray(count), frequency=array('H', [0]) * count, writes=0, repeats=0)

    def _line(self, frame):
        local = frame.f_locals
        if frame.f_code is self.codes['_attention']:
            if frame.f_lineno == self.points['score']:
                coordinates = local['head'], local['token'], local['key']
                self._put('unrounded_dot_sum', coordinates, (local['total'],))
                self._put('dot_bf16', coordinates, (local['dot'],))
                self._put('scores_bf16', coordinates, (local['score'],))
            elif frame.f_lineno == self.points['exp']:
                self._put('softmax_exp', (local['head'], local['token'], len(local['probabilities'])),
                          (local['probability'],))
            elif frame.f_lineno == self.points['store']:
                self._put('pv_bf16', (local['head'], local['token'], local['col']), tuple(local['output']))
        elif frame.f_lineno == self.points['matrix']:
            outer = frame.f_back
            require(outer is not None and outer.f_code is self.codes['_attention']
                    and outer.f_locals.get('self') is self.owner, 'Matrix observation caller mismatch')
            context = outer.f_locals
            h, t, k = context['head'], context['token'], context['key']
            if local['opcode'] == 0x23 and local['last']:
                self._put('dot_parts', (h, t, k, 0), tuple(local['lanes']))
            elif local['opcode'] == 0x24:
                self._put('softmax_fp32', (h, t, k), (context['probability'],))
                self._put('prob_bf16', (h, t, k), (local['a'][0] << 16,))
                self._put('normalizer', (h, t, 0), (context['maximum'], context['total'], context['inverse']))
                if local['last']:
                    self._put('pv_raw', (h, t, context['col']), tuple(local['lanes']))

    def _coverage(self):
        m = self.job['m']
        for name, field in self.fields.items():
            for h in range(12):
                for t in range(m):
                    if name in ('normalizer', 'pv_raw', 'pv_bf16'):
                        width = 3 if name == 'normalizer' else 128
                        count = 8 * (t + 1) if name == 'normalizer' else 1
                        start = (h * m + t) * width
                        targets = ((start + i, count) for i in range(width))
                    else:
                        width = 16 if name == 'dot_parts' else 1
                        count = 8 if name in ('softmax_fp32', 'prob_bf16') else 1
                        targets = (((h * m * m + t * m + k) * width + i, count if k <= t else 0)
                                   for k in range(m) for i in range(width))
                    for index, expected in targets:
                        if (field['frequency'][index] != expected or field['observed'][index] != bool(expected)
                                or (not expected and field['words'][index] != SENTINEL)):
                            return False
        return True

    def report(self):
        require(self.closed and not self.active, 'close the observer before inspecting acceptance')
        complete = self.error is None and self.started == 1 and self.terminal is not None
        if complete:
            m = self.job['m']
            causal = 12 * m * (m + 1) // 2
            counts = dict(dot_parts=16 * causal, unrounded_dot_sum=causal, dot_bf16=causal,
                scores_bf16=causal, softmax_exp=causal, softmax_fp32=causal, prob_bf16=causal,
                normalizer=12 * m * 3, pv_raw=12 * m * 128, pv_bf16=12 * m * 128)
            writes = dict(counts, softmax_fp32=8 * causal, prob_bf16=8 * causal, normalizer=24 * causal)
            retired = self.retirement
            complete = (self.terminal['status'] is None and self.terminal['tag'] == self.job['tag']
                and self.terminal['write_bytes'] == self.job['write_bytes'] == m * 1536 * 4
                and retired['same_services'] and retired['same_job'] and retired['state'] == 'idle'
                and not retired['poison'] and retired['matrix_released']
                and not retired['matrix_reset_required'] and retired['client_retired']
                and not retired['memory_pending'] and retired['scalar_released'] and self._coverage()
                and all(sum(self.fields[n]['observed']) == count and self.fields[n]['writes'] == writes[n]
                        for n, count in counts.items()))
        return dict(schema=SOURCE_VERSION, source_version=SOURCE_VERSION,
            status='COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED' if complete else 'INCOMPLETE',
            source_sha256=self.sources, execution_source_sha256=self.execution_sources,
            helper_source_sha256={HELPER: HELPER_SHA256}, instrumentation_sha256=self.instrumentation_sha256,
            helper_source_version=HELPER_SOURCE_VERSION, prior_observation_results_inherited=False,
            execution_source_commit=base.SOURCE_COMMIT, execution_source_base_commit=base.SOURCE_BASE_COMMIT,
            execution_source_profile='original Qwen2; borrower=false; elementwise loan=false',
            historical_fullgraph=dict(commit=base.RECEIPT_COMMIT, path=base.RECEIPT,
                sha256=base.RECEIPT_SHA, results_inherited=False),
            python=sys.version, loaded_python_functions_checked=self.loaded_functions_checked,
            matrix_binary_provenance_verified_by_observer=False,
            trace_api='CPython sys.settrace source-bound read-only local snapshots',
            job=self.job, terminal=self.terminal, accepted_retirement=self.retirement, observer_error=self.error,
            fields={name: dict(shape=f['shape'], words=len(f['words']), observed_words=sum(f['observed']),
                raw_sha256=base.sha(self._bytes(name)), presence_sha256=base.sha(bytes(f['observed'])),
                frequency_sha256=base.sha(self._bytes(name, 'frequency')), writes=f['writes'],
                identical_repeats=f['repeats']) for name, f in self.fields.items()},
            future_scores_observed=False, full_29_node_gate=False, whole_block_terminal_observed=False,
            physical_publication_observed=False, hardware_simulation=False,
            pv_bf16_boundary='actual store words; ACK coverage requires accepted successful owner terminal',
            numerical_policy='official-bf16-v1', native_acceptance='NOT_EVALUATED_BY_OBSERVER')
