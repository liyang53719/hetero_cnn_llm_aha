"""M1/2/4/8/16 admission variant, with bounded observer-only trace sinks.

Only the pinned bank Controller.run validator constant is transformed. Compute,
retirement, scratch placement, Banks and arithmetic remain inherited unchanged.
This is behavioral calibration infrastructure, not native or RTL evidence.
"""
import ast
import copy
import hashlib
from pathlib import Path
import struct

from ..attention_bank_scratch import controller as frozen

SOURCE_SHA256 = 'f9242181603ff779c9074eff40d67395beb45a5573a6f7382ee5df8823bbbdc5'
SOURCE_PATH = Path(frozen.__file__)
ADMITTED_SHAPES = (1, 2, 4, 8, 16)
SCHEMA = 'attention-bank-multirow-observer-v1'


def admit(tokens):
    if type(tokens) is not int or tokens not in ADMITTED_SHAPES:
        raise ValueError('multirow admitted shapes are 1,2,4,8,16')


def transform_run(source):
    """Fail closed on byte drift, then alter exactly one AST Constant: 2 ->16."""
    if type(source) is not bytes or hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('frozen bank controller source SHA256 mismatch')
    tree = ast.parse(source, filename=str(SOURCE_PATH))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Controller']
    if len(classes) != 1:
        raise ValueError('unique frozen Controller required')
    runs = [n for n in classes[0].body if isinstance(n, ast.FunctionDef) and n.name == 'run']
    if len(runs) != 1:
        raise ValueError('unique frozen run required')
    original = runs[0]
    changed = copy.deepcopy(original)
    calls = [n for n in ast.walk(changed) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == 'integer']
    expected = ast.parse('integer(tokens, 1, 2)', mode='eval').body
    if len(calls) != 1 or ast.dump(calls[0]) != ast.dump(expected):
        raise ValueError('unique exact token bound required')
    calls[0].args[2].value = 16
    # Independently reverse just that constant and require the whole run AST.
    restored = copy.deepcopy(changed)
    candidates = [n for n in ast.walk(restored) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name) and n.func.id == 'integer']
    candidates[0].args[2].value = 2
    if ast.dump(restored) != ast.dump(original):
        raise ValueError('non-admission run AST changed')
    return changed


def build_run(source):
    namespace = dict(vars(frozen))
    module = ast.Module(body=[transform_run(source)], type_ignores=[])
    exec(compile(module, str(SOURCE_PATH) + ':M16-admission-only', 'exec'), namespace)
    return namespace['run']


_RUN = build_run(SOURCE_PATH.read_bytes())


def _uint(value):
    if type(value) is not int or not 0 <= value < 2**64:
        raise ValueError('observer uint64')
    return value


def _bool(value):
    if type(value) is not bool:
        raise ValueError('observer bool')
    return value


def _tuple(value, size):
    if type(value) is not tuple or len(value) != size:
        raise ValueError('observer tuple schema')
    return value


def _banks(value):
    if type(value) is not tuple or len(value) > 16:
        raise ValueError('observer bank schema')
    result, previous = [], -1
    for pair in value:
        bank, word = _tuple(pair, 2)
        _uint(bank); _uint(word)
        if not previous < bank < 16:
            raise ValueError('observer bank order')
        previous = bank
        result.append(struct.pack('>BQ', bank, word))
    return bytes([len(value)]) + b''.join(result) + bytes(9*(16-len(value)))


class EventSink:
    """Append-only fixed-schema SHA256/count; stores no events or references.

    Hash input starts with schema/kind domain separation, followed by fixed-size
    big-endian records in append order. views records contain only group uint64.
    Sink state is constant-size apart from its bounded uint64 append counter.
    """
    __slots__ = ('kind', 'count', '_hash')
    KINDS = ('read_events', 'ack_events', 'views', 'scratch.events')

    def __init__(self, kind):
        if kind not in self.KINDS:
            raise ValueError('observer kind')
        self.kind, self.count = kind, 0
        self._hash = hashlib.sha256((SCHEMA + '\0' + kind + '\0').encode('ascii'))

    def append(self, event):
        if self.kind == 'views':
            data = struct.pack('>Q', _uint(event.group))
        elif self.kind == 'read_events':
            data = struct.pack('>QQQ', *map(_uint, _tuple(event, 3)))
        elif self.kind == 'ack_events':
            edge, group, poison = _tuple(event, 3)
            data = struct.pack('>QQ?', _uint(edge), _uint(group), _bool(poison))
        else:
            edge, reads, writes, accepted, acked = _tuple(event, 5)
            data = (struct.pack('>Q', _uint(edge)) + _banks(reads) + _banks(writes)
                    + struct.pack('>??', _bool(accepted), _bool(acked)))
        if self.count == 2**64-1:
            raise ValueError('observer count overflow')
        self._hash.update(data)
        self.count += 1

    def __len__(self):
        return self.count

    def hexdigest(self):
        return self._hash.hexdigest()

    def summary(self):
        return dict(schema=SCHEMA, kind=self.kind, count=self.count, sha256=self.hexdigest(), retained_events=0)


class Controller(frozen.Controller):
    def __init__(self, *args, **kwargs):
        # Recheck on construction as well as import, including under python -O.
        if hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest() != SOURCE_SHA256:
            raise ValueError('frozen bank controller source SHA256 mismatch')
        super().__init__(*args, **kwargs)
        self.read_events = EventSink('read_events')
        self.ack_events = EventSink('ack_events')
        self.views = EventSink('views')
        if self.scratch is not None:
            self.scratch.events = EventSink('scratch.events')

    def run(self, tokens, q, k, v):
        admit(tokens)
        return _RUN(self, tokens, q, k, v)

    def observation_summary(self):
        sinks = (self.read_events, self.ack_events, self.views)
        if self.scratch is not None:
            sinks += (self.scratch.events,)
        return {sink.kind: sink.summary() for sink in sinks}
