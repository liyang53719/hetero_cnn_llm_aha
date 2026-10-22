"""Explicit pure-Python services for bounded owner tests, NOT native or RTL.

Execute real candidate/baseline owner and shared clients. Arithmetic is an
independent rational-to-binary32 RNE surrogate; Matrix computes only selected
QK stripes and PV lanes. No weight fixture, CDLL, fullblock, or M128 execution.
"""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import types
import ctypes

from pv_reuse_test_config import WORK_ROOT as ROOT, SOURCE_ROOT as SOURCE

def forbid_native_library(*args, **kwargs):
    raise AssertionError('native library loading forbidden in bounded synthetic tests')
ctypes.CDLL = forbid_native_library

def word(x): return struct.unpack('<I', struct.pack('<f', x))[0]
def value(x): return struct.unpack('<f', struct.pack('<I', x))[0]
def finite(x): return x & 0x7f800000 != 0x7f800000
class ArithmeticFault(Exception): pass

@lru_cache(maxsize=65536)
def rational(w):
    if not finite(w): raise ArithmeticFault('nonfinite input')
    e = (w >> 23) & 255
    n = (w & 0x7fffff) | (0x800000 if e else 0)
    shift = (e - 127 - 23) if e else -149
    return Fraction((-n if w >> 31 else n) << max(0, shift), 1 << max(0, -shift))

def rne(q, zero_sign=0):
    if not q: return zero_sign << 31
    sign = int(q < 0); q = abs(q); n, d = q.numerator, q.denominator
    e = n.bit_length() - d.bit_length()
    if (n < (d << e)) if e >= 0 else ((n << -e) < d): e -= 1
    shift = max(e, -126) - 23
    nn, dd = (n, d << shift) if shift >= 0 else (n << -shift, d)
    m, r = divmod(nn, dd)
    if r * 2 > dd or (r * 2 == dd and m & 1): m += 1
    if m == 1 << 24: m >>= 1; e += 1
    if e > 127: return (sign << 31) | 0x7f800000
    bits = m if m < 1 << 23 else ((max(e, -126) + 127) << 23) | (m & 0x7fffff)
    return (sign << 31) | bits

@lru_cache(maxsize=131072)
def binary(op, a, b=0):
    if op == 'bf':
        if not finite(a): raise ArithmeticFault('nonfinite BF16 input')
        return ((a + 0x7fff + ((a >> 16) & 1)) & 0xffffffff) & 0xffff0000
    x, y = rational(a), rational(b)
    if op == 'add': q, sign = x + y, int(a == b == 0x80000000)
    elif op == 'mul': q, sign = x * y, (a ^ b) >> 31
    elif op == 'div':
        if not y: raise ArithmeticFault('division by zero')
        q, sign = x / y, (a ^ b) >> 31
    else: raise AssertionError(op)
    return rne(q, sign)

@lru_cache(maxsize=131072)
def fma_bf16(a, b, c):
    # A/B are BF16 halfwords; preserve the exact per-key FP32 FMA graph.
    product = rational(a << 16) * rational(b << 16)
    negative_zero = int(not product and bool((a ^ b) & 0x8000) and c == 0x80000000)
    return rne(product + rational(c), negative_zero)

class ScalarDouble:
    def __init__(self, fault=None):
        self.client = None; self.calls = Counter(); self.trace = []; self.normalizations = []; self.fault = fault
    def acquire(self, c):
        assert self.client is None; self.client = c; return True
    def release(self, c): assert self.client is c; self.client = None
    def op(self, c, op, a, b=0, *, policy='legacy_scalar'):
        assert self.client is c
        self.calls[op] += 1
        frame = c.program.gi_frame if c.program else None
        normalization = bool(frame and frame.f_lineno == c.normalization_line)
        loc = frame.f_locals if frame else {}
        identity = tuple(loc.get(k) for k in ('token', 'head', 'key', 'col'))
        if normalization and self.fault == ('normalize', identity):
            self.normalizations.append((identity, a, b, 'FAULT'))
            self.fault_probability_storage = loc['probabilities']
            raise ArithmeticFault('injected first-column normalization fault')
        out = binary(op, a, b)
        if not finite(out): raise ArithmeticFault('nonfinite scalar output')
        if op != 'bf' and policy == 'legacy_scalar' and out & 0x7fffffff < 0x800000:
            exact = rational(a) + rational(b) if op == 'add' else rational(a) * rational(b) if op == 'mul' else rational(a) / rational(b)
            if rational(out) != exact: raise ArithmeticFault('inexact underflow')
        self.trace.append((normalization, op, a, b, policy, out))
        if normalization: self.normalizations.append((identity, a, b, out))
        return out

fake = types.ModuleType('candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic')
for n, v in dict(ArithmeticFault=ArithmeticFault, NATIVE_ACCEPTANCE='SYNTHETIC_RATIONAL_RNE_ONLY',
                 ScalarService=ScalarDouble, finite=finite, word=word, value=value).items(): setattr(fake, n, v)
sys.modules[fake.__name__] = fake
# These imports define the actual shared protocol classes but never construct a
# native MatrixService or call configure_library/source-guard/build entrypoints.
from candidates.qwen2_resident_matrix.ffn_public.prefix_owners import Job, MemoryResponse
from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import MatrixResult, MatrixDone


def owner_class(variant):
    path = ROOT / ('baseline/owner.py' if variant == 'baseline' else 'delta/candidates/qwen2_fixed93_attention/owner.py')
    name = 'candidates.qwen2_fixed93_attention.test_' + variant
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    normalize_line = next(i for i, line in enumerate(path.read_text().splitlines(), 1)
                          if "probability = self._op('mul', probability, inverse)" in line)
    class ObservedOwner(module.Fixed93AttentionOwner):
        normalization_line = normalize_line
        def _matrix_step(self, opcode, a, b, **kw):
            loc = self.program.gi_frame.f_locals
            ident = tuple(loc[k] for k in ('token', 'head', 'key', 'col'))
            self.pv_inputs.append((ident, a[0], binary('bf', a[0])))
            lanes = yield from super()._matrix_step(opcode, a, b, **kw)
            self.pv_intermediates.append((ident, lanes))
            return lanes
    return ObservedOwner

class SparseRow:
    def __init__(self, data, row): self.data, self.row = data, row
    def __getitem__(self, col): return self.data.get((self.row, col), 0)
class SparseResult:
    def __init__(self, data): self.data = dict(data)
    def __getitem__(self, row): return SparseRow(self.data, row)

class MatrixDouble:
    def __init__(self, fault=None):
        self.epoch = 0; self.owner = None; self.reset_required = False; self.group = self.result = None
        self.lib = self; self.counts = Counter(); self.legacy_reply = self.last = False
        self.resource_address = 0; self.n = 0; self.trace = []; self.fault = fault; self.pv_steps = 0
    def matrix_normal_fmas(self): return self.n
    def matrix_state(self): return (4 if self.group else 0) | (8 if self.result else 0) | (64 if self.legacy_reply else 0)
    def acquire(self, owner, mode, tag): assert self.owner is None; self.owner = owner; return True
    def _check_owner(self, owner, mode='normal'): assert owner is self.owner and mode == 'normal'
    def _check_event(self, ticket=None, epoch=None): assert epoch is None or epoch == self.epoch
    def accept_group(self, owner, group):
        assert self.group is None and not self.legacy_reply
        self.group = group; self.index = 0; self.last = False; self.acc = {}; self.counts['normal_groups'] += 1
        self.trace.append(('group', group.profile, group.steps, group.slice_mask)); return True
    def accept_step(self, owner, step):
        assert self.group is not None and self.result is None and not self.legacy_reply
        assert step.index == self.index and step.clear == (self.index == 0)
        self.index += 1; self.last = step.last
        self.trace.append(('step', step.index, step.clear, step.last, step.emit,
                           hashlib.sha256(struct.pack('<' + 'H' * (len(step.a) + len(step.b)), *step.a, *step.b)).hexdigest()))
        if self.group.profile == 2:
            assert self.group.slice_mask == 255 and self.group.steps == 8 and step.emit == step.last
            for row in range(16):
                for selected in range(16):
                    col = selected * 16 + row
                    self.acc[row, col] = fma_bf16(step.a[row], step.b[col], self.acc.get((row, col), 0))
        else:
            assert self.group.profile == 0 and self.group.slice_mask == 1 and step.emit and self.group.opcode == 0x24
            for col in range(16): self.acc[0, col] = fma_bf16(step.a[0], step.b[col], self.acc.get((0, col), 0))
            self.pv_steps += 1
            if self.fault == ('nonfinite_pv', self.pv_steps): self.acc[0, 7] = 0x7f800000
        self.n += 4096 if self.group.profile == 2 else 512
        self.counts['normal_steps'] += 1
        if step.emit: self.result = MatrixResult(0, SparseResult(self.acc), step.last, False, 1, self.epoch)
        self.legacy_reply = self.group.profile == 0
        return True
    @property
    def done(self):
        if self.group and self.last and self.result is None: return MatrixDone(self.group.tag, False, 1, self.epoch)
    def retire_result(self, owner, result): assert result is self.result; self.result = None; self.counts['normal_results'] += 1
    def retire_done(self, owner, done): assert done == self.done; self.group = None; self.counts['normal_done'] += 1
    def retire_legacy_reply(self, owner, ticket, epoch): assert self.legacy_reply; self.legacy_reply = False
    def retire_owner_response(self, owner): assert self.matrix_state() == 0
    def release(self, owner): assert self.owner is owner; self.owner = None
    def abort(self, owner):
        self.reset_required = True
        # Fault cases below occur after any returned Matrix step is retired.
        # No asynchronous Matrix debt is fabricated or silently discarded.


def memory_words(address, job, seed=0):
    if job.a <= address < job.a + job.m * 1536 * 4:
        offset = (address - job.a) // 4; kind = 1
    elif job.b <= address < job.b + job.m * 256 * 4:
        offset = (address - job.b) // 4; kind = 2
    elif job.c <= address < job.c + job.m * 256 * 4:
        offset = (address - job.c) // 4; kind = 3
    else: raise AssertionError(('unexpected/causally unallocated read', hex(address)))
    return tuple(word((((offset + i) * (kind * 2 + 1) + seed * 7 + offset // 128 * 3) % 29 - 14) / (16 if kind < 3 else 4)) for i in range(16))


def run_owner(variant, m, *, fault=None, seed=0, shared=None):
    assert m in (1, 2, 16), 'bounded synthetic jobs only; no M128 run'
    matrix, scalar = shared if shared is not None else (MatrixDouble(fault), ScalarDouble(fault))
    owner = owner_class(variant)(matrix, scalar); owner.pv_inputs = []; owner.pv_intermediates = []
    job = Job('Attention', 0x1000a, 0x100000, 0x200000, 0x400000, m, 1536, 128, m * 1536 * 4, c=0x300000)
    assert owner.tick(job=job)['job_fire']
    pending = None; writes = []; requests = []; response_hold = 3; final_ack_hold = 4; injected = False; stable = None
    for tick in range(600000):
        ports = owner.ports(); response = None
        if ports['memory'] is not None and stable is not None: assert ports['memory'] == stable
        stable = ports['memory'] if ports['memory'] is not None and tick % 5 == 0 else None
        if pending is not None:
            if pending.write and owner.ack_bytes + 64 == job.write_bytes and final_ack_hold:
                final_ack_hold -= 1; assert ports['response'] is None
            else:
                target_read = not pending.write and job.c <= pending.address < job.c + m * 256 * 4
                target_write = pending.write
                error = bool(not injected and fault in ('vread', 'write') and
                             (target_read if fault == 'vread' else target_write))
                injected |= error
                response = MemoryResponse(pending.tag, None if pending.write else memory_words(pending.address, job, seed), error=error)
        ready = True
        if ports['response'] is not None and response_hold:
            response_hold -= 1; ready = False
        event = owner.tick(memory_ready=tick % 5 != 0, memory_response=response, response_ready=ready,
                           matrix_request_ready=tick % 7 != 0, matrix_result_ready=tick % 11 != 0,
                           service_result_ready=tick % 13 != 0, service_done_ready=tick % 17 != 0)
        if event['memory_response_fire']:
            if pending.write and not response.error: writes.append((pending.address, pending.data))
            pending = None
        if event['memory_fire']:
            assert pending is None; pending = event['memory']; requests.append((pending.address, pending.write, pending.data))
            loc = owner.program.gi_frame.f_locals if owner.program else {}
            if not pending.write and (job.b <= pending.address < job.b + m * 256 * 4 or job.c <= pending.address < job.c + m * 256 * 4):
                base = job.b if pending.address < job.c else job.c
                assert (pending.address - base) // (256 * 4) <= loc['token'], 'future key read'
        if event['response_fire']:
            terminal = event['response']; break
    else: raise AssertionError(('owner stuck', owner.state, owner.detail, matrix.matrix_state()))
    assert pending is None and matrix.owner is None and scalar.client is None
    assert owner.counts['owner_results'] == owner.counts['job_fire'] == 1 and response_hold == 0
    if fault is None:
        assert terminal.status is None and owner.state == 'idle' and final_ack_hold == 0
        assert len(writes) == len(set(address for address, _ in writes)) == m * 12 * 8
    else:
        assert terminal.status in ('Numerical', 'Memory') and owner.state == 'locked' and owner.poison
        assert not owner.ports()['job_ready']
    return dict(owner=owner, matrix=matrix, scalar=scalar, terminal=terminal,
                requests=requests, writes=writes, ticks=tick + 1)
