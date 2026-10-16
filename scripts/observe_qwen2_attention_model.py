"""Read-only, source-pinned observations of the existing software Attention owner.

Use around an existing driver: ``with AttentionObservation(owner) as capture:``.
No owner is replaced, patched, or given a reference tensor. CPython tracing reads
already-computed words and the actual accepted terminal edge. Generator yields
are NOT completion. Future scores are not computed and remain absent. This is
software observation, not Chisel/RTL instrumentation or native model acceptance.
"""
from __future__ import annotations

from array import array
import ast
from dataclasses import asdict
import hashlib
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import threading
import types

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py'
SOURCE_VERSION = 'qwen2-existing-attention-observation-v4'
# Current edited sources have no published commit yet; do not mislabel them as f16.
SOURCE_COMMIT = None
SOURCE_BASE_COMMIT = 'f16df50adfb0f1f4bc668c517a2e29accffe6753'
PINS = {
    OWNER: '65d823ebebdb50cae98c0ff8c9c1c5631ebc298595cc5c28c71ba7a22890f6d8',
    'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py': '5391f807b8164511d6e3e5af156f1fb3dd5f298bb0dca66504c6b818d135f880',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py': 'b3a3b61a0414ab72d67d6de192b79de332fddc64b459c55a6f7f5ff149abaa27',
    'candidates/qwen2_resident_matrix/ffn_attention/scalar_recipe.py': 'a58c7e32d509a368a5127a87165f0a9c8a4f0df6a58a0c78f031d4e337ef580d',
}
SENTINEL = 0xa5963cc3
RECEIPT = 'candidates/qwen2_resident_matrix/ffn_public/fullgraph_numerical_receipt.json'
RECEIPT_SHA = '3d0f449d3e2a62f87ea915d89930dc5788f0ea835b11ce265a169c1fc4e5570e'
RECEIPT_COMMIT = '37b7de74431ed79b7e9f3d52d308ed7f46727b7a'
# V4 retains the exact historical 75-source inventory and 69 unchanged hashes.
# The sixth replacement is AttentionOwner.tick memory-debt control only;
# Attention arithmetic and historical numeric acceptance are not rebound.
# The two V2 Matrix replacements remain explicit; the active Matrix/Prefix
# guards and two f16 Scala files bind only the default-disabled borrower/loan
# profile. No historical receipt/result is rebound or inherited.
EXECUTION_SOURCE_REPLACEMENTS = {
    OWNER: (
        '8f954329ef7a4ae472b8247e6e34456affee2e946f1fcfb439b19d89d2b786ec',
        '65d823ebebdb50cae98c0ff8c9c1c5631ebc298595cc5c28c71ba7a22890f6d8'),
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py': (
        'f8e4c274a5b304b589b7c725d45588c1fd6367efa5987cc004f07e7d4b400345',
        'b3a3b61a0414ab72d67d6de192b79de332fddc64b459c55a6f7f5ff149abaa27'),
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp': (
        'f5e8767890aeb06a9b6b07e0c7602e38d8aa0af76e72ae9f7b22b61e03100ddd',
        '7702e5975ff04393deb4969835eb5ffcfbb99258329ee6ac27fd75b289356e14'),
    'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py': (
        '3a57df5e1ea438663dcd9fb490366317356662994c77cb567d62b94876854369',
        '5391f807b8164511d6e3e5af156f1fb3dd5f298bb0dca66504c6b818d135f880'),
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala': (
        '1152cb11e145c27f271b0170913194bd66ce2930008a75e3a580d5660e410a43',
        '9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4'),
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala': (
        'c8d6cfd95901bc9f2cae3f248d542cb532b1b66aec1be98942a9a7533d3ca542',
        '7f2b4a623b61b6e68478b2310d441ed04ccde1cd5490cb22205113f907b7974d'),
}


def execute_public_attention_observed(execution, physical, job, *,
                                      final_ack_stall=5, observation=None):
    """Observe the original public driver; return its report without publication.

    The caller still owns all three public completion handshakes, physical
    publication and final launch-result acceptance. An optional unused capture
    lets the caller inspect a failed driver without replacing its exception.
    This helper never advances those public gates or changes driver readiness.
    """
    from candidates.qwen2_resident_matrix.ffn_public import fullgraph_execution as driver
    path = ROOT / 'candidates/qwen2_resident_matrix/ffn_public/fullgraph_execution.py'
    sources = verify_execution_sources()
    require(sha(path.read_bytes()) == sources[str(path.relative_to(ROOT))],
            'public Attention driver source drift')
    function = driver.execute_attention_owner
    expected = _code(compile(path.read_text(), str(path), 'exec',
                             dont_inherit=True, optimize=0), 'execute_attention_owner')
    require(isinstance(function, types.FunctionType) and
            _same_code(function.__code__, expected) and function.__defaults__ is None and
            function.__kwdefaults__ == {'final_ack_stall': 5} and
            function.__globals__ is driver.__dict__, 'loaded public Attention driver changed')
    capture = (AttentionObservation(execution.attention_owner) if observation is None
               else observation)
    require(type(capture) is AttentionObservation and capture.owner is execution.attention_owner,
            'public observer must belong to this actual Attention owner')
    with capture:
        report = function(execution, physical, job, final_ack_stall=final_ack_stall)
    return report, capture


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_sources(root=ROOT):
    root = Path(root).resolve()
    for relative, expected in PINS.items():
        require(sha((root / relative).read_bytes()) == expected,
                'observation source drift: ' + relative)
    return dict(PINS)


def verify_execution_sources(root=ROOT, *, enable_h2048_rms_borrower=False,
                             external_elementwise_loan=False):
    if enable_h2048_rms_borrower is not False or external_elementwise_loan is not False:
        raise ValueError('execution inventory requires the original default-disabled borrower/loan profile')
    root = Path(root).resolve()
    raw = (root / RECEIPT).read_bytes()
    require(sha(raw) == RECEIPT_SHA, 'frozen execution-source inventory changed')
    sources = json.loads(raw)['source_sha256']
    require(len(sources) == 75, 'frozen execution-source inventory is incomplete')
    require(set(EXECUTION_SOURCE_REPLACEMENTS) == {
        OWNER,
        'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py',
        'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
        'candidates/qwen2_resident_matrix/ffn_public/prefix_arithmetic.py',
        'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala',
        'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QwenOwnerProtocol.scala',
    }, 'v4 execution-source replacement closure changed')
    for relative, (previous, current) in EXECUTION_SOURCE_REPLACEMENTS.items():
        require(sources.get(relative) == previous and previous != current,
                'v4 execution-source replacement origin changed: ' + relative)
        require(relative not in PINS or PINS[relative] == current,
                'v4 observation/execution source identity mismatch: ' + relative)
        sources[relative] = current
    for relative, expected in sources.items():
        require(sha((root / relative).read_bytes()) == expected,
                'v4 execution source drift: ' + relative)
    return sources


def _code(module, name):
    candidates = [c for c in module.co_consts if isinstance(c, types.CodeType) and c.co_name == name]
    require(len(candidates) == 1, 'ambiguous compiled observation code: ' + name)
    return candidates[0]


def _same_code(actual, fresh):
    return (actual == fresh and actual.co_filename == fresh.co_filename and
            actual.co_firstlineno == fresh.co_firstlineno and
            actual.co_linetable == fresh.co_linetable and
            actual.co_exceptiontable == fresh.co_exceptiontable)


def verify_loaded_dependencies(owner):
    """Bind the participating Python functions and imports, not just trace points.

    This is not a security sandbox or a binary-build attestation. The caller's
    Matrix-library/source receipt and independent arithmetic checks remain needed.
    """
    def literal(node):
        if isinstance(node, ast.Name) and node.id == 'ROOT':
            return ROOT
        if isinstance(node, ast.Tuple):
            return tuple(literal(x) for x in node.elts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.LShift,ast.Sub)):
            left,right=literal(node.left),literal(node.right)
            return left << right if isinstance(node.op,ast.LShift) else left-right
        return ast.literal_eval(node)

    def defaults(function, node, namespace):
        args = tuple(literal(x) for x in node.args.defaults) or None
        keywords = {a.arg: literal(d) for a,d in zip(node.args.kwonlyargs,node.args.kw_defaults)
                    if d is not None} or None
        require(function.__defaults__ == args and function.__kwdefaults__ == keywords and
                function.__globals__ is namespace, 'loaded function defaults/globals changed: ' + node.name)

    packages = (
        'candidates.qwen2_resident_matrix.ffn_attention.attention_owner',
        'candidates.qwen2_resident_matrix.ffn_attention.scalar_recipe',
        'candidates.qwen2_resident_matrix.ffn_attention.matrix_service',
        'candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic',
        'candidates.qwen2_resident_matrix.ffn_public.prefix_owners',
    )
    checked = 0
    for name in packages:
        module = sys.modules[name]
        path = Path(module.__file__).resolve()
        require(path == ROOT / (name.replace('.', '/') + '.py'), 'loaded dependency path changed')
        raw = path.read_text()
        tree = ast.parse(raw)
        expected = compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                actual = getattr(module, node.name)
                require(isinstance(actual, types.FunctionType) and
                        _same_code(actual.__code__, _code(expected, node.name)),
                        'loaded dependency function changed: ' + name + '.' + node.name)
                defaults(actual,node,module.__dict__)
                checked += 1
            elif isinstance(node, ast.ClassDef):
                cls = getattr(module, node.name)
                class_code = _code(expected, node.name)
                for method in node.body:
                    if isinstance(method, ast.FunctionDef):
                        actual = vars(cls).get(method.name)
                        if isinstance(actual, (staticmethod, classmethod)):
                            actual = actual.__func__
                        elif isinstance(actual, property):
                            actual = actual.fget
                        require(isinstance(actual, types.FunctionType) and
                                _same_code(actual.__code__, _code(class_code, method.name)),
                                'loaded dependency method changed: ' + name + '.' + node.name + '.' + method.name)
                        defaults(actual,method,module.__dict__)
                        checked += 1
            elif isinstance(node, ast.Assign):
                expected_value = ROOT if any(isinstance(t,ast.Name) and t.id=='ROOT'
                                            for t in node.targets) else literal(node.value)
                for target in node.targets:
                    pairs = (zip(target.elts,expected_value) if isinstance(target,ast.Tuple)
                             else [(target,expected_value)])
                    for variable,value in pairs:
                        require(isinstance(variable,ast.Name) and getattr(module,variable.id)==value,
                                'loaded source constant changed: ' + name + '.' + ast.unparse(variable))
            elif isinstance(node, ast.ImportFrom) and node.level:
                source = importlib.import_module(importlib.util.resolve_name(
                    '.'*node.level + (node.module or ''), module.__package__))
                for alias in node.names:
                    require(getattr(module, alias.asname or alias.name) is getattr(source, alias.name),
                            'loaded dependency import changed: ' + name + '.' + alias.name)
    # Reject instance-method replacements, including inherited owner helpers.
    for instance in (owner, owner.scalar, owner.matrix):
        names = {n for cls in type(instance).__mro__ for n in vars(cls)}
        for name in names:
            method = inspect.getattr_static(type(instance), name)
            if isinstance(method, types.FunctionType):
                bound = getattr(instance, name)
                require(isinstance(bound, types.MethodType) and bound.__func__ is method,
                        'patched dependency instance method: ' + name)
            elif isinstance(method, staticmethod):
                require(getattr(instance, name) is method.__func__, 'patched static dependency: ' + name)
    return checked


class AttentionObservation:
    """One cold M1..M128 owner transaction, sealed only at accepted success.

    Buffers belong to the external observer; they are never owner SRAM or input.
    Probability repeats across the eight PV groups are checked bit-for-bit.
    The trace turns itself off at the first accepted owner terminal, so later
    FFN work in the same driver is not traced. It does not publish a block result.
    """
    def __init__(self, owner):
        from candidates.qwen2_resident_matrix.ffn_attention.attention_owner import AttentionOwner
        from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService
        from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService
        require(type(owner) is AttentionOwner, 'exact existing AttentionOwner required')
        require(type(owner.matrix) is MatrixService and type(owner.scalar) is ScalarService,
                'exact existing MatrixService and ScalarService required')
        require(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12)
                and not sys.flags.optimize, 'reviewed CPython 3.12 without -O required')
        self.owner, self.sources = owner, verify_sources()
        self.execution_sources = verify_execution_sources()
        self.loaded_functions_checked = verify_loaded_dependencies(owner)
        self.instrumentation_sha256 = sha(Path(__file__).read_bytes())
        self.services = owner.matrix, owner.scalar
        raw = (ROOT / OWNER).read_text()
        expected = _code(compile(raw, str(ROOT / OWNER), 'exec', dont_inherit=True, optimize=0),
                         'AttentionOwner')
        self.codes = {}
        for name in ('_attention', '_matrix_step', 'tick'):
            method = getattr(owner, name)
            require(method.__func__ is getattr(AttentionOwner, name), 'patched observer target')
            code = method.__func__.__code__
            fresh = _code(expected, name)
            # marshal encodes interpreter string-interning/reference choices;
            # compare executable code plus its precise source/line metadata.
            require(_same_code(code, fresh),
                    'loaded owner code differs from pinned source: ' + name)
            self.codes[name] = code
        tree = ast.parse(raw)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AttentionOwner')
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}

        def point(method, statement):
            expected_node = ast.dump(ast.parse(statement).body[0], include_attributes=False)
            found = [n.lineno for n in ast.walk(methods[method]) if isinstance(n, ast.stmt)
                     and ast.dump(n, include_attributes=False) == expected_node]
            require(len(found) == 1, 'ambiguous observation statement: ' + statement)
            return found[0]

        self.points = {
            'score': point('_attention', 'scores.append(score)'),
            'exp': point('_attention', 'probabilities.append(probability)'),
            'matrix': point('_matrix_step', 'return lanes'),
        }
        self.thread = threading.get_ident()
        self.active = self.closed = self.disarmed = False
        self.started = 0
        self.job = self.terminal = None
        self.retirement = None
        self.error = None
        self.fields = {}
        self._callback = self._trace

    def __enter__(self):
        require(threading.get_ident() == self.thread, 'observation thread changed')
        require(not self.active and not self.closed and self.started == 0, 'observer is single-use')
        require(sys.gettrace() is None, 'existing tracer must not be replaced')
        require(self.owner.state == 'idle' and not self.owner.poison and
                self.owner.matrix.owner is None and not self.owner.matrix.reset_required and
                self.owner.scalar.client is None, 'observe before an idle owner launch')
        verify_sources()
        verify_execution_sources()
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
            verify_sources()
            require(verify_execution_sources() == self.execution_sources, 'execution inventory drift')
            require(sha(Path(__file__).read_bytes()) == self.instrumentation_sha256,
                    'observer implementation changed during capture')
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
            'dot_parts': (12, m, m, 16), 'dot_sum': (12, m, m),
            'scores': (12, m, m), 'softmax_exp': (12, m, m),
            'softmax_fp32': (12, m, m), 'prob': (12, m, m),
            'normalizer': (12, m, 3),
            'pv': (12, m, 128),
        }.items():
            count = 1
            for dimension in shape:
                count *= dimension
            self.fields[name] = dict(shape=shape, words=array('I', [SENTINEL])*count,
                                     observed=bytearray(count), frequency=array('H', [0])*count,
                                     writes=0, repeats=0)

    def _put(self, name, coordinates, values):
        field = self.fields[name]
        shape, offset = field['shape'], 0
        require(len(coordinates) == len(shape), 'observation rank')
        for index, dimension in zip(coordinates, shape):
            require(type(index) is int and 0 <= index < dimension, 'observation coordinate')
            offset = offset * dimension + index
        require(offset + len(values) <= len(field['words']), 'observation vector bound')
        for i, value in enumerate(values, offset):
            require(type(value) is int and 0 <= value < 1 << 32, 'observation is not a uint32 word')
            if field['observed'][i]:
                require(field['words'][i] == value, 'inconsistent repeated actual observation: ' + name)
                field['repeats'] += 1
            else:
                field['words'][i], field['observed'][i] = value, 1
            field['writes'] += 1
            field['frequency'][i] += 1

    def _line(self, frame):
        local = frame.f_locals
        if frame.f_code is self.codes['_attention']:
            if frame.f_lineno == self.points['score']:
                coordinates = local['head'], local['token'], local['key']
                self._put('dot_sum', coordinates, (local['total'],))
                self._put('scores', coordinates, (local['score'],))
            elif frame.f_lineno == self.points['exp']:
                coordinates = local['head'], local['token'], len(local['probabilities'])
                self._put('softmax_exp', coordinates, (local['probability'],))
        elif frame.f_lineno == self.points['matrix']:
            # This point follows a real Matrix result fire and finite/protocol
            # checks. On a generator yield/exception no values are recorded.
            outer = frame.f_back
            require(outer is not None and outer.f_code is self.codes['_attention']
                    and outer.f_locals.get('self') is self.owner, 'Matrix observation caller mismatch')
            context = outer.f_locals
            h, t, k = context['head'], context['token'], context['key']
            if local['opcode'] == 0x23 and local['last']:
                self._put('dot_parts', (h, t, k, 0), tuple(local['lanes']))
            elif local['opcode'] == 0x24:
                self._put('softmax_fp32', (h, t, k), (context['probability'],))
                self._put('prob', (h, t, k), (local['a'][0] << 16,))
                self._put('normalizer', (h, t, 0),
                          (context['maximum'], context['total'], context['inverse']))
                if local['last']:
                    self._put('pv', (h, t, context['col']), tuple(local['lanes']))

    def _trace(self, frame, event, arg):
        if frame.f_code not in self.codes.values() or frame.f_locals.get('self') is not self.owner:
            return None
        if self.error is None:
            try:
                if event == 'line' and frame.f_code is not self.codes['tick']:
                    self._line(frame)
                elif event == 'return' and frame.f_code is self.codes['tick'] and isinstance(arg, dict):
                    if arg['job_fire']:
                        self._start(arg)
                    if arg['response_fire']:
                        require(self.terminal is None and self.started == 1, 'duplicate/unowned terminal')
                        self.terminal = asdict(arg['response'])
                        self.retirement = dict(state=self.owner.state, poison=self.owner.poison,
                            same_services=(self.owner.matrix is self.services[0] and self.owner.scalar is self.services[1]),
                            same_job=asdict(self.owner.job) == self.job,
                            matrix_released=self.owner.matrix.owner is None,
                            matrix_reset_required=self.owner.matrix.reset_required,
                            client_retired=self.owner.matrix_client is None,
                            memory_pending=self.owner.memory_pending,
                            scalar_released=self.owner.scalar.client is None)
                        self.disarmed = True
                        sys.settrace(None)
            except Exception as error:
                # Diagnostics must not change the owner transition or swallow
                # its error. Preserve the first observer error and reject seal.
                self.error = str(error)
        return self._callback

    def _bytes(self, name, kind='words'):
        values = array('I' if kind == 'words' else 'H', self.fields[name][kind])
        if sys.byteorder != 'little':
            values.byteswap()
        return values.tobytes()

    def _coverage(self):
        m = self.job['m']
        for name, field in self.fields.items():
            for h in range(12):
                for t in range(m):
                    if name in ('normalizer', 'pv'):
                        width = 3 if name == 'normalizer' else 128
                        count = 8*(t+1) if name == 'normalizer' else 1
                        start = (h*m+t)*width
                        targets = ((start+i,count) for i in range(width))
                    else:
                        width = 16 if name == 'dot_parts' else 1
                        count = 8 if name in ('softmax_fp32','prob') else 1
                        targets = (((h*m*m+t*m+k)*width+i,count if k<=t else 0)
                                   for k in range(m) for i in range(width))
                    for index, expected in targets:
                        if (field['frequency'][index] != expected or
                                field['observed'][index] != bool(expected) or
                                (not expected and field['words'][index] != SENTINEL)):
                            return False
        return True

    def report(self):
        require(self.closed and not self.active, 'close the observer before inspecting acceptance')
        complete = self.error is None and self.started == 1 and self.terminal is not None
        if complete:
            m = self.job['m']
            causal = 12*m*(m+1)//2
            counts = dict(dot_parts=16*causal, dot_sum=causal, scores=causal,
                          softmax_exp=causal, softmax_fp32=causal, prob=causal,
                          normalizer=12*m*3, pv=12*m*128)
            writes = dict(counts, softmax_fp32=8*causal, prob=8*causal, normalizer=24*causal)
            retired = self.retirement
            complete = (self.terminal['status'] is None and self.terminal['tag'] == self.job['tag']
                and self.terminal['write_bytes'] == self.job['write_bytes'] == m*1536*4
                and retired['same_services'] and retired['same_job'] and retired['state'] == 'idle'
                and not retired['poison'] and retired['matrix_released']
                and not retired['matrix_reset_required'] and retired['client_retired']
                and not retired['memory_pending'] and retired['scalar_released']
                and self._coverage()
                and all(sum(self.fields[n]['observed']) == count and self.fields[n]['writes'] == writes[n]
                        for n, count in counts.items()))
        return dict(schema='qwen2-existing-attention-observation-v4',
            status='COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED' if complete else 'INCOMPLETE',
            source_version=SOURCE_VERSION, execution_source_commit=SOURCE_COMMIT,
            execution_source_base_commit=SOURCE_BASE_COMMIT,
            execution_source_profile='original Qwen2; borrower=false; elementwise loan=false',
            prior_observation_results_inherited=False,
            historical_fullgraph=dict(commit=RECEIPT_COMMIT, path=RECEIPT,
                sha256=RECEIPT_SHA, results_inherited=False),
            source_sha256=self.sources, execution_source_sha256=self.execution_sources,
            instrumentation_sha256=self.instrumentation_sha256, python=sys.version,
            loaded_python_functions_checked=self.loaded_functions_checked,
            matrix_binary_provenance_verified_by_observer=False,
            trace_api='CPython sys.settrace source-bound read-only local snapshots',
            job=self.job, terminal=self.terminal, accepted_retirement=self.retirement, observer_error=self.error,
            fields={name: dict(shape=f['shape'], words=len(f['words']), observed_words=sum(f['observed']),
                raw_sha256=sha(self._bytes(name)), presence_sha256=sha(bytes(f['observed'])),
                frequency_sha256=sha(self._bytes(name,'frequency')),
                writes=f['writes'], identical_repeats=f['repeats']) for name, f in self.fields.items()},
            future_scores_observed=False, full_29_node_gate=False, whole_block_terminal_observed=False,
            hardware_simulation=False, numerical_policy='unchanged-v0', native_acceptance='UNCHANGED_FAIL_POLICY_PENDING')

    def save(self, out):
        """Optional bounded actual activation pack, never weights or Git input."""
        report = self.report()
        out = Path(out)
        out.mkdir(parents=True, exist_ok=False)
        for name, field in self.fields.items():
            (out / (name + '.u32le')).write_bytes(self._bytes(name))
            (out / (name + '.presence')).write_bytes(bytes(field['observed']))
            (out / (name + '.count.u16le')).write_bytes(self._bytes(name,'frequency'))
        (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
        return report
