#!/usr/bin/env python3
"""Read-only bounded stdlib controls, NOT execution of Scala/Chisel/RTL.

Separately admitted root-only command: Python 3.12 -I -S -B tests.py --base
BASE --contract CONTRACT --phase1 PHASE1. Outer limits: <=10 s, 1 CPU, 256 MiB.
Possession of this file is NOT permission to run any test. No repository import,
NumPy, compiler, JVM, native model or hardware simulator is invoked. Exact integer
binary32 Add/Mul and separately rounded P7 nodes are SIMULATED response services,
not independent HardFloat validation. Literal vectors check these helpers only.
The independent sequence generator is a transcription of pinned original order,
not execution of the original software candidate. Every event/data item of two
full traces is compared online, retaining only bounded hashes and summaries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import types
import unittest
from dataclasses import fields, replace
from functools import lru_cache

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
OWNER_SOURCE = 'source/GdnChunkDerivedAndPairOwner.scala'
PHASE1_SOURCE = 'source/GdnChunkLoadPrepOwner.scala'
ORIGINAL = 'candidates/qwen35_gdn_prefill/chunk/model.py'
CONV_SCALAR = 'candidates/qwen35_gdn_prefill/conv/scalar.py'
MODEL = PINS = None
FULL_CASES = []


def require(condition, message):
    if not condition:
        raise ValueError(message)


def readonly_audit(event, args):
    denied = ('ctypes.dlopen', 'subprocess.Popen', 'os.system', 'os.posix_spawn',
              'os.fork', 'os.exec', 'os.remove', 'os.rename', 'os.rmdir', 'os.mkdir',
              'os.unlink', 'os.symlink', 'os.link', 'os.truncate', 'os.chmod',
              'os.chown', 'os.utime', 'os.setxattr', 'os.removexattr')
    if event in denied or event.startswith('socket.'):
        raise RuntimeError('read-only controls forbid this operation')
    if event == 'open':
        mode, flags = args[1], args[2]
        if ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise RuntimeError('read-only controls forbid file writes')


def safe_path(root, relative):
    require(isinstance(relative, str) and relative, 'missing pin path')
    rel = Path(relative)
    require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe pin path')
    path = root / rel
    require(path.is_file() and not path.is_symlink(), 'pin must be regular file')
    require(path.resolve().is_relative_to(root.resolve()), 'pin escapes root')
    return path


def read_small(path, expected=None):
    before = path.stat()
    require(before.st_size <= 2 * 1024 * 1024, 'small-control file bound')
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after), 'file changed during read')
    digest = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if expected is not None:
        require(digest == dict(bytes=expected['bytes'], sha256=expected['sha256']), f'pin mismatch: {path.name}')
    return raw, digest


class PinSet:
    def __init__(self, base, contract, phase1):
        roots = dict(base=base.resolve(), contract=contract.resolve(), phase1=phase1.resolve())
        pin_raw, pin_digest = read_small(HERE / 'INPUT_PINS.json')
        manifest_raw, manifest_digest = read_small(HERE / 'SOURCE_MANIFEST.json')
        external, manifest = json.loads(pin_raw), json.loads(manifest_raw)
        require(isinstance(external.get('files'), dict) and external['files'], 'missing input pins')
        require(isinstance(manifest.get('files'), dict) and manifest['files'], 'missing own pins')
        own = manifest['files']
        require({'derived_model.py', 'tests.py', OWNER_SOURCE, 'README.md', 'SCOPE.json',
                 'INPUT_PINS.json', 'TEST_COMMAND.json', 'INTERFACE_CONTRACT.md'} <= set(own), 'omitted own required file')
        require('SOURCE_MANIFEST.json' not in own, 'self-referential manifest')
        self.entries, self.cache = [], {}
        self.descriptors = [(HERE / 'INPUT_PINS.json', pin_digest), (HERE / 'SOURCE_MANIFEST.json', manifest_digest)]
        for label, spec in external['files'].items():
            require(spec.get('role') in roots, f'unknown role: {label}')
            key = (spec['role'], spec['path'])
            require(key not in self.cache, 'duplicate external pin')
            path = safe_path(roots[spec['role']], spec['path'])
            raw, digest = read_small(path, spec)
            self.cache[key] = raw
            self.entries.append((path, digest))
        for relative, spec in own.items():
            path = safe_path(HERE, relative)
            raw, digest = read_small(path, spec)
            self.cache[('own', relative)] = raw
            self.entries.append((path, digest))
        require(sum(d['bytes'] for _, d in self.entries) <= 20 * 1024 * 1024, 'total pin bound')
        required = {('base', PREFIX + n) for n in ('Protocol.scala', 'BlockFloat.scala',
                    'GdnOwnerProtocol.scala', 'ElementwiseRegisterLoan.scala')}
        required |= {('base', ORIGINAL), ('base', CONV_SCALAR), ('phase1', PHASE1_SOURCE),
                     ('contract', 'source/GdnChunkProtocol.scala'), ('contract', 'source/GdnChunkAddressPlan.scala')}
        require(required <= set(self.cache), 'missing correspondence input')

    def text(self, role, path):
        return self.cache[(role, path)].decode('utf-8')

    def verify_after(self):
        for path, digest in self.descriptors + self.entries:
            read_small(path, digest)


def compact(source):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S))


def pack(words):
    return sum(word << (32 * i) for i, word in enumerate(words))


def unpack(value):
    return tuple((value >> (32 * i)) & 0xFFFFFFFF for i in range(16))


def decode(word):
    """Finite binary32 magnitude as integer multiples of 2**-149."""
    exponent, fraction = (word >> 23) & 255, word & 0x7FFFFF
    if exponent == 255:
        raise ValueError('simulated primitive expects finite operands')
    return fraction if exponent == 0 else (fraction | 0x800000) << (exponent - 1)


def round_scaled(sign, magnitude, power):
    """Round exact nonnegative integer * 2**power, RNE, tininess AFTER rounding.

    Flags use HardFloat layout NV,DZ,OF,UF,NX but are only simulated flags.
    Exact subnormal results do not raise UF. Normal rounding of a tiny exact
    value to min-normal sets NX alone under after-rounding tininess detection.
    """
    if magnitude == 0:
        return sign, 0
    exponent = magnitude.bit_length() - 1 + power
    quantum = max(-149, exponent - 23)
    shift = quantum - power
    if shift > 0:
        rounded, remainder = divmod(magnitude, 1 << shift)
        half = 1 << (shift - 1)
        rounded += int(remainder > half or (remainder == half and rounded & 1))
        inexact = remainder != 0
    else:
        rounded, inexact = magnitude << -shift, False
    if rounded == 0:
        return sign, 3 if inexact else 0
    exponent = rounded.bit_length() - 1 + quantum
    if exponent >= 128:
        return sign | 0x7F800000, 5
    if exponent < -126:
        bits = rounded << (quantum + 149)
        return sign | bits, 3 if inexact else 0
    significand = rounded << (24 - rounded.bit_length()) if rounded.bit_length() <= 24 else rounded >> (rounded.bit_length() - 24)
    return sign | ((exponent + 127) << 23) | (significand & 0x7FFFFF), int(inexact)


def simulated_add(a, b):
    x, y = decode(a), decode(b)
    total = (-x if a >> 31 else x) + (-y if b >> 31 else y)
    if total == 0:
        return (0x80000000 if a == b == 0x80000000 else 0), 0
    return round_scaled(0x80000000 if total < 0 else 0, abs(total), -149)


def simulated_mul(a, b):
    return round_scaled((a ^ b) & 0x80000000, decode(a) * decode(b), -298)


EXP_COEFFICIENTS = (0x3F800000, 0xBF317218, 0x3E75FDF0, 0xBD635847,
                    0x3C1D955B, 0xBAAEC3FF, 0x39218489, 0xB77FE5FE)


@lru_cache(maxsize=256)
def simulated_exp(a):
    """Original ExpNegative4 recipe, including ignored internal primitive flags.

    Service accepts either sign (exp(-abs(a))). Owner separately gates +x from
    Exp valid. abs>=80 saturates +0, and scale node executes before saturation.
    """
    magnitude = a & 0x7FFFFFFF
    decode(a)
    scaled = simulated_mul(magnitude, 0x3FB8AA3B)[0]
    if magnitude >= 0x42A00000:
        return 0
    integral = decode(scaled) >> 149
    integer_word = round_scaled(0, integral, 0)[0]
    fraction = simulated_add(scaled, integer_word ^ 0x80000000)[0]
    accumulator = EXP_COEFFICIENTS[-1]
    for coefficient in reversed(EXP_COEFFICIENTS[:-1]):
        product = simulated_mul(accumulator, fraction)[0]
        accumulator = simulated_add(product, coefficient)[0]
    return simulated_mul(accumulator, (127 - integral) << 23)[0]


def simulated_loan(request):
    fn = simulated_add if request.op == 1 else simulated_mul
    require(request.op in (1, 2), 'unsupported simulated loan')
    results = tuple(fn(a, b) for a, b in zip(unpack(request.a), unpack(request.b)))
    bad = any(flags & 30 or not MODEL.finite(value) for value, flags in results)
    return MODEL.LoanResult(request.tag, 8 if bad else 0,
                            0 if bad else pack(value for value, _ in results))


def make_job(tokens=16, head=3, chunk=0, cold=False):
    m = MODEL
    c = m.Context(0x87654321, tokens, cold, 0 if cold else 7, 0,
                  0x100000, 0x800000, 0xA00000, 0xC00000, 0x1000000)
    p = m.Receipt(c.tag, c.expected_generation, head, chunk, 1, 0, 102400, 0, 0, True)
    r = m.Phase1Result(p, 25600 if tokens == 16 else 102400, 64, 64, 987, True)
    return m.Job(c, head, chunk, c, r), m.Committed(not cold, c.expected_generation, 0 if cold else c.state_in)


def repack(job, **changes):
    c = replace(job.context, **changes)
    r = replace(job.phase1_ready, receipt=replace(job.phase1_ready.receipt,
                tag=c.tag, expected_generation=c.expected_generation),
                read_bytes=102400 if c.tokens == 128 else 25600)
    return replace(job, context=c, phase1_context=c, phase1_ready=r)


def gate_words(job, row):
    effective = min(row + 1, 16) if job.context.tokens == 16 else row + 1
    cumulative = round_scaled(0x80000000, effective, -6)[0]
    beta = (0x3F000000, 0x3F800000, 0, 0x80000000)[row % 4]
    if job.context.tokens == 16 and row >= 16:
        beta = 0
    return cumulative, beta


def input_payload(job, name, row, beat=0):
    if name == 'gates':
        return pack(gate_words(job, row))
    if job.context.tokens == 16 and row >= 16:
        return 0
    role = {'q': 0, 'k': 1, 'v': 2}[name]
    words = [0, 0x80000000]
    for lane in range(2, 16):
        fraction = (row * 1009 + role * 103 + beat * 17 + lane + job.head * 4099 + job.chunk * 65537) & 0x7FFFFF
        words.append(0x3F000000 | fraction | ((lane & 1) << 31))
    return pack(words)


def base_address(job):
    return job.context.scratch + job.head * (1679360 if job.context.tokens == 128 else 872448) + 65536 + job.chunk * 806912


def original_sequence(job):
    """Independent loop generator: never reads Owner state/steps/payload/offsets.

    It includes the one explicit final cumulative reload needed by the new
    separate owner. The original monolithic software already retained it.
    All tuple products are computed before the first tuple write is yielded.
    """
    base = base_address(job)
    offsets = dict(gates=0, q=4096, k=36864, v=69632, kb=102400,
                   vb=135168, kbg=167936, qg=200704, ke=233472, pair=331776)
    def read(name, row, beat=0):
        address = base + offsets[name] + row * (64 if name == 'gates' else 512) + beat * 64
        value = input_payload(job, name, row, beat)
        yield ('read', address, value)
        return value
    def exp(word):
        yield ('exp', 4, word, 0)
        return simulated_exp(word)
    def add(a, b):
        yield ('loan', 1, a, b, 0)
        value, flags = simulated_add(a, b)
        require(flags & 30 == 0, 'reference Add failure')
        return value
    def mul(value, factor):
        b = pack([factor] * 16)
        yield ('loan', 2, value, b, 0)
        results = tuple(simulated_mul(word, factor) for word in unpack(value))
        require(not any(flags & 30 for _, flags in results), 'reference Mul failure')
        return pack(word for word, _ in results)
    final = (yield from read('gates', 63)) & 0xFFFFFFFF
    decay = yield from exp(final)
    for row in range(64):
        gate = yield from read('gates', row)
        cumulative, beta = gate & 0xFFFFFFFF, (gate >> 32) & 0xFFFFFFFF
        exp_g = yield from exp(cumulative)
        remaining = yield from add(final, cumulative ^ 0x80000000)
        exp_remaining = yield from exp(remaining)
        for beat in range(8):
            k = yield from read('k', row, beat)
            q = yield from read('q', row, beat)
            kb = yield from mul(k, beta)
            kbg = yield from mul(kb, exp_g)
            qg = yield from mul(q, exp_g)
            ke = yield from mul(k, exp_remaining)
            for name, value in (('kb', kb), ('kbg', kbg), ('qg', qg), ('ke', ke)):
                yield ('write', base + offsets[name] + row * 512 + beat * 64, value)
        for beat in range(8):
            value = yield from read('v', row, beat)
            vb = yield from mul(value, beta)
            yield ('write', base + offsets['vb'] + row * 512 + beat * 64, vb)
        for beat in range(4):
            pair = [0] * 16
            for lane in range(min(16, max(0, row - beat * 16 + 1))):
                earlier = (yield from read('gates', beat * 16 + lane)) & 0xFFFFFFFF
                difference = yield from add(cumulative, earlier ^ 0x80000000)
                pair[lane] = yield from exp(difference)
            yield ('write', base + offsets['pair'] + row * 256 + beat * 64, pack(pair))
    return decay


def drive_one(test, owner, event, *, stalls=False, last=False):
    """One transaction, with responses first offered on the issue edge.

    Pre-edge ready must prevent consuming that response until the next edge.
    Stalls also offer a second job and prove it cannot replace accepted context.
    """
    m = MODEL
    before = owner.peek()
    test.assertFalse(before.loan_abort or before.reset_loan)
    test.assertLessEqual(sum((owner.memory_outstanding, owner.scalar_outstanding, owner.loan_outstanding)), 1)
    kind = event[0]
    if kind in ('read', 'write'):
        req = before.memory_request
        test.assertIsNotNone(req)
        test.assertEqual((req.write, req.address, req.mask), (kind == 'write', event[1], m.FULL_MASK if kind == 'write' else 0))
        test.assertEqual(req.data, event[2] if kind == 'write' else 0)
        response = m.MemoryResponse(req.tag, event[2] if kind == 'read' else 0)
        issue = dict(memory_ready=True, response=response)
        retire = dict(response=response)
        fire, result_fire = 'memory_fire', 'response_fire'
    elif kind == 'exp':
        req = before.scalar_request
        test.assertIsNotNone(req)
        test.assertEqual((req.op, req.a, req.b), event[1:])
        response = m.ScalarResult(simulated_exp(req.a))
        issue, retire = dict(scalar_ready=True, scalar_result=response), dict(scalar_result=response)
        fire, result_fire = 'scalar_fire', 'scalar_result_fire'
    else:
        req = before.loan_request
        test.assertIsNotNone(req)
        test.assertEqual((req.op, req.a, req.b, req.inverse), event[1:])
        test.assertEqual(req.tag, owner.job.context.tag ^ owner.loan_sequence)
        response = simulated_loan(req)
        test.assertEqual(response.status, 0)
        issue, retire = dict(loan_ready=True, loan_result=response), dict(loan_result=response)
        fire, result_fire = 'loan_fire', 'loan_result_fire'
    if stalls:
        held = owner.peek()
        accepted = owner.job
        for _ in range(2):
            e = owner.tick(job=replace(accepted, context=replace(accepted.context, tag=0x12345678)))
            test.assertFalse(e.job_fire)
            test.assertEqual(owner.peek(), held)
            test.assertEqual(owner.job, accepted)
    old_write = owner.write_bytes
    e = owner.tick(**issue)
    test.assertTrue(getattr(e, fire))
    test.assertFalse(getattr(e, result_fire))
    test.assertEqual(owner.write_bytes, old_write)
    test.assertIsNone(owner.peek().done)
    test.assertEqual(sum((owner.memory_outstanding, owner.scalar_outstanding, owner.loan_outstanding)), 1)
    test.assertIsNone(owner.peek().memory_request)
    test.assertIsNone(owner.peek().scalar_request)
    test.assertIsNone(owner.peek().loan_request)
    if stalls or last:
        owner.tick()
        test.assertIsNone(owner.peek().done)
        test.assertEqual(owner.write_bytes, old_write)
    e = owner.tick(**retire)
    test.assertTrue(getattr(e, result_fire))
    test.assertEqual(owner.write_bytes, old_write + (64 if kind == 'write' else 0))
    test.assertEqual(len(owner.payload), 4)
    test.assertTrue(all(0 <= value < 1 << 512 for value in owner.payload))


class SourceCorrespondence(unittest.TestCase):
    def test_abi_states_policy_and_sequence_source(self):
        source = PINS.text('own', OWNER_SOURCE)
        text = compact(source)
        self.assertIn('Enum(11)', text)
        self.assertIn('Enum(23)', text)
        self.assertIn('Seq.fill(4)(0.U(512.W))', text)
        for state in MODEL.STATES:
            self.assertIn(state, source)
        for step in MODEL.STEPS:
            self.assertIn(step, source)
        self.assertNotIn('Module(new', text)
        for piece in ('io.loan.abort:=false.B', 'io.loan.resetLoan:=false.B',
                      'io.scalar.request.valid:=state===issueExp&&expDomain(expArgument)',
                      'io.loan.request.valid:=state===issueLoan&&!io.loan.resetRequired',
                      'valcurrentLoanTag=context.tag^loanSequence',
                      'when(io.done.fire){state:=Mux(status===Status.Ok.U,idle,locked)}',
                      'j.phase1Context.asUInt===c.asUInt', 'r.addRequests===64.U', 'r.addResults===64.U',
                      'p.scratchAckBytes===102400.U', 'r.readBytes===Mux(is128,102400.U,25600.U)',
                      'expRequests===2209.U', 'addRequests===2144.U', 'mulRequests===2560.U',
                      'readBytes===phaseReadBytes.U', 'writeBytes===phaseBytes.U'):
            self.assertIn(piece, text)
        self.assertLess(text.index('when(r.tag=/=Cat(context.tag,memorySequence))'), text.index('.elsewhen(r.error)'))
        self.assertLess(text.index('when(r.tag=/=currentLoanTag)'), text.index('.elsewhen(r.status=/=Status.Ok.U)'))
        self.assertIn('class GdnChunkLoadPrepResult', PINS.text('phase1', PHASE1_SOURCE))
        phase1 = compact(PINS.text('phase1', PHASE1_SOURCE))
        for field in ('valreadBytes=UInt(64.W)', 'valaddRequests=UInt(7.W)', 'valaddResults=UInt(7.W)'):
            self.assertIn(field, phase1)
        memory = compact(PINS.text('base', PREFIX + 'Protocol.scala'))
        self.assertIn('classMemoryResponseextendsBundle{valdata=UInt(512.W);valtag=UInt(64.W);valerror=Bool()}', memory)
        loan = compact(PINS.text('base', PREFIX + 'ElementwiseRegisterLoan.scala'))
        self.assertIn('valAdd=1;valMul=2;', loan)
        self.assertIn('loan.result.valid:=loanState===lReply&&!loan.abort&&!loan.resetLoan', loan)
        scalar = compact(PINS.text('base', PREFIX + 'BlockFloat.scala'))
        self.assertIn('valExpNegative=4', scalar)
        self.assertIn('conv.io.roundingMode:=round_minMag', scalar)
        self.assertIn('when(a(30,0)>=F32.lit(80)){out:=0.U;state:=done}', scalar)
        original = PINS.text('base', ORIGINAL)
        section = original.split("self._phase('chunk_decay_exp')", 1)[1].split("self._phase('transpose_k')", 1)[0]
        required_order = ["chunk_decay = self._exp(cumulative)", "exp_g = self._exp(cum)",
                          "rem = self._op('add'", "exp_rem = self._exp(rem)", "m['k'].address", "m['q'].address",
                          "kb = self._op('mul'", "('kbg', self._op('mul'", "('qg', self._op('mul'", "('ke', self._op('mul'",
                          "yield from self._write(m[name]", "self._phase('prepare_vbeta')", "self._phase('pairwise_decay')"]
        indices = [section.index(piece) for piece in required_order]
        self.assertEqual(indices, sorted(indices))
        self.assertIn('range(min(16, max(0, row - col + 1)))', section)
        recipe = PINS.text('base', CONV_SCALAR).lower()
        for literal in EXP_COEFFICIENTS + (0x3FB8AA3B,):
            self.assertIn(hex(literal), recipe)
        self.assertEqual([f.name for f in fields(MODEL.MemoryResponse)], ['tag', 'data', 'error'])
        self.assertEqual([f.name for f in fields(MODEL.ScalarResult)], ['result', 'error'])
        plan = PINS.text('contract', 'source/GdnChunkAddressPlan.scala')
        shape_body = plan.split('val Shapes: Vector[Shape] = Vector(', 1)[1].split('require(Shapes', 1)[0]
        shape_rows = re.findall(r'Shape\("([a-z_]+)",\s*(\d+),\s*(\d+)\)', shape_body)
        self.assertEqual(len(shape_rows), 24)
        cursor, sizes = 0, {}
        for name, rows, columns in shape_rows:
            if name in MODEL.OFFSETS:
                self.assertEqual(MODEL.OFFSETS[name], cursor)
            sizes[name] = int(rows) * int(columns) * 4
            cursor += sizes[name]
        self.assertEqual(cursor, MODEL.CHUNK_BYTES)
        self.assertEqual(sum(sizes[name] for name in ('kb', 'vb', 'kbg', 'qg', 'ke', 'pair')), 180224)


class SimulatedArithmeticControls(unittest.TestCase):
    def test_literal_add_vectors(self):
        for a, b, result, flags in ((0, 0, 0, 0), (0x80000000, 0x80000000, 0x80000000, 0),
            (0, 0x80000000, 0, 0), (1, 1, 2, 0), (0x00800000, 0x807FFFFF, 1, 0),
            (0x3F800000, 0x33800000, 0x3F800000, 1),
            (0x3F800001, 0x33800000, 0x3F800002, 1),
            (0x7F7FFFFF, 0x7F7FFFFF, 0x7F800000, 5)):
            self.assertEqual(simulated_add(a, b), (result, flags))

    def test_literal_mul_vectors_and_after_rounding_tininess(self):
        for a, b, result, flags in ((0, 0xBF800000, 0x80000000, 0),
            (0x80000000, 0xBF800000, 0, 0), (1, 0x3F800000, 1, 0),
            (0x00800000, 0x3F000000, 0x00400000, 0),
            (1, 0x3F000000, 0, 3), (3, 0x3F000000, 2, 3),
            (0x00800000, 0x3F7FFFFF, 0x00800000, 1),
            (0x7F7FFFFF, 0x40000000, 0x7F800000, 5)):
            self.assertEqual(simulated_mul(a, b), (result, flags))
        # A tiny exact finite Add is NOT an injected underflow fault.
        self.assertEqual(simulated_add(2, 0x80000001), (1, 0))

    def test_exp_literals_domain_distinction_and_internal_flags(self):
        for word, expected in ((0, 0x3F800000), (0x80000000, 0x3F800000),
                               (1, 0x3F800000), (0x80000001, 0x3F800000),
                               (0x42A00000, 0), (0xC2A00000, 0),
                               (0x7F7FFFFF, 0), (0xFF7FFFFF, 0)):
            self.assertEqual(simulated_exp(word), expected)
        self.assertFalse(MODEL.exp_domain(0x42A00000))
        self.assertTrue(MODEL.exp_domain(0xC2A00000))
        self.assertEqual(simulated_mul(1, 0x3FB8AA3B)[1], 3)
        # Exp4 ignores that internal UF/NX; it still returns exactly 1.
        self.assertEqual(simulated_exp(0x80000001), 0x3F800000)
        for word in (0x7F800000, 0xFF800000, 0x7FC00000):
            with self.assertRaises(ValueError):
                simulated_exp(word)


class ModelControls(unittest.TestCase):
    def accepted(self, **kwargs):
        job, root = make_job(**kwargs)
        owner = MODEL.Owner()
        e = owner.tick(job=job, committed=root)
        self.assertTrue(e.job_fire)
        self.assertEqual(owner.state, 'issueRead')
        return owner

    def prepare(self, step, state=None):
        owner = self.accepted()
        sequence = original_sequence(owner.job)
        for _ in range(700):
            if owner.step == step and (state is None or owner.state == state):
                return owner
            drive_one(self, owner, next(sequence))
        self.fail('bounded early-stage preparation exceeded')

    def failure(self, owner, status, *, outstanding=None):
        done = owner.peek().done
        self.assertIsNotNone(done)
        self.assertEqual(done.receipt.status, status)
        self.assertFalse(done.stage_complete or done.decay.valid or done.receipt.drained)
        self.assertEqual(done.decay.value, 0)
        self.assertTrue(owner.peek().reset_required)
        if outstanding is not None:
            self.assertEqual((owner.memory_outstanding, owner.scalar_outstanding, owner.loan_outstanding), outstanding)
        for _ in range(3):
            e = owner.tick(job=owner.job, done_ready=False)
            self.assertFalse(e.job_fire)
            self.assertEqual(owner.peek().done, done)
            self.assertFalse(owner.peek().loan_abort or owner.peek().reset_loan)
        owner.tick(done_ready=True)
        self.assertEqual(owner.state, 'locked')
        self.assertFalse(owner.tick(job=owner.job).job_fire)
        self.assertFalse(owner.peek().job_ready)

    def test_two_complete_online_event_and_payload_traces(self):
        for tokens, head, chunk in ((16, 3, 0), (128, 11, 1)):
            owner = self.accepted(tokens=tokens, head=head, chunk=chunk)
            job = owner.job
            sequence = original_sequence(job)
            counts = dict(read=0, write=0, exp=0, add=0, mul=0)
            trace_hash, write_hash = hashlib.sha256(), hashlib.sha256()
            seen_steps, seen_states = set(), set()
            last_address = base_address(job) + 331776 + 63 * 256 + 3 * 64
            for index in range(13411):
                try:
                    event = next(sequence)
                except StopIteration as terminal:
                    expected_decay = terminal.value
                    break
                seen_steps.add(owner.step)
                seen_states.add(owner.state)
                kind = event[0]
                counts['add' if kind == 'loan' and event[1] == 1 else 'mul' if kind == 'loan' else kind] += 1
                if kind in ('read', 'write'):
                    expected_sequence = counts['read'] + counts['write'] - 1
                    self.assertEqual(owner.peek().memory_request.tag,
                                     (job.context.tag << 32) | expected_sequence)
                elif kind == 'loan':
                    expected_sequence = counts['add'] + counts['mul'] - 1
                    self.assertEqual(owner.peek().loan_request.tag, job.context.tag ^ expected_sequence)
                trace_hash.update(repr(event).encode('ascii'))
                if kind == 'write':
                    write_hash.update(event[1].to_bytes(8, 'little') + event[2].to_bytes(64, 'little'))
                    if base_address(job) + 331776 <= event[1] < base_address(job) + 348160:
                        delta = event[1] - base_address(job) - 331776
                        row, beat = delta // 256, (delta % 256) // 64
                        for lane, word in enumerate(unpack(event[2])):
                            column = beat * 16 + lane
                            if column > row:
                                self.assertEqual(word, 0)
                            elif column == row:
                                self.assertEqual(word, 0x3F800000)
                last = kind == 'write' and event[1] == last_address
                drive_one(self, owner, event, stalls=index % 257 == 0, last=last)
                seen_states.add('waitRead' if kind == 'read' else 'waitWrite' if kind == 'write' else 'waitExp' if kind == 'exp' else 'waitLoan')
                if not last:
                    self.assertIsNone(owner.peek().done)
            else:
                self.fail('full trace exceeded exact bounded transaction budget')
            self.assertEqual(index, 13410)
            self.assertEqual(counts, dict(read=3681, write=2816, exp=2209, add=2144, mul=2560))
            self.assertEqual(seen_steps, set(MODEL.STEPS))
            self.assertEqual(seen_states, set(MODEL.STATES) - {'idle', 'finish', 'locked'})
            result = owner.peek().done
            self.assertTrue(result.stage_complete and result.decay.valid and result.receipt.drained)
            self.assertEqual(result.read_bytes, 235584)
            self.assertEqual(result.receipt.scratch_ack_bytes, 180224)
            self.assertEqual((result.receipt.output_ack_bytes, result.receipt.state_ack_bytes), (0, 0))
            self.assertEqual((result.exp_requests, result.exp_results, result.add_requests, result.add_results,
                              result.mul_requests, result.mul_results), (2209, 2209, 2144, 2144, 2560, 2560))
            self.assertEqual((result.decay.context, result.decay.head, result.decay.chunk, result.decay.value),
                             (job.context, head, chunk, expected_decay))
            self.assertTrue(gate_words(job, 63)[0] & 0x7FFFFFFF)
            self.assertEqual((result.receipt.tag, result.receipt.expected_generation, result.receipt.head,
                              result.receipt.chunk, result.receipt.phase), (job.context.tag, 7, head, chunk, 2))
            for _ in range(4):
                e = owner.tick(job=job, done_ready=False, committed=MODEL.Committed(False, 0, 0))
                self.assertFalse(e.job_fire)
                self.assertEqual(owner.peek().done, result)
            # Held successful done cannot accept a second offer on its retire edge.
            e = owner.tick(job=job, done_ready=True)
            self.assertTrue(e.done_fire)
            self.assertFalse(e.job_fire)
            self.assertTrue(owner.peek().job_ready)
            FULL_CASES.append(dict(tokens=tokens, head=head, chunk=chunk, counts=counts,
                trace_sha256=trace_hash.hexdigest(), writes_sha256=write_hash.hexdigest(),
                decay=f'{expected_decay:08x}', model_cycles=result.cycles))

    def test_admission_qualified_phase1_identity_and_counts(self):
        m = MODEL
        job, root = make_job()
        for field in fields(job.phase1_context):
            old = getattr(job.phase1_context, field.name)
            changed = not old if type(old) is bool else old ^ 1
            bad = replace(job, phase1_context=replace(job.phase1_context, **{field.name: changed}))
            self.assertEqual(m.admission_status(bad, root), m.Status.DEPENDENCY)
        for field, changed in (('stage_complete', False), ('add_requests', 63), ('add_results', 63),
                               ('read_bytes', 102400)):
            bad = replace(job, phase1_ready=replace(job.phase1_ready, **{field: changed}))
            self.assertEqual(m.admission_status(bad, root), m.Status.DEPENDENCY)
        for field, changed in (('tag', 1), ('expected_generation', 6), ('head', 2), ('chunk', 1),
            ('phase', 2), ('status', 3), ('drained', False), ('scratch_ack_bytes', 102336),
            ('output_ack_bytes', 64), ('state_ack_bytes', 64)):
            bad = replace(job, phase1_ready=replace(job.phase1_ready,
                          receipt=replace(job.phase1_ready.receipt, **{field: changed})))
            owner = m.Owner()
            owner.tick(job=bad, committed=root)
            self.assertEqual((owner.read_bytes, owner.write_bytes, owner.exp_requests), (0, 0, 0))
            self.failure(owner, m.Status.DEPENDENCY)
        job128, root128 = make_job(128, 11, 1)
        bad = replace(job128, phase1_ready=replace(job128.phase1_ready, read_bytes=25600))
        self.assertEqual(m.admission_status(bad, root128), m.Status.DEPENDENCY)
        self.assertEqual(m.admission_status(replace(job, phase1_ready=replace(job.phase1_ready, cycles=0)), root), 0)

    def test_admission_root_spans_alias_boundary_and_precedence(self):
        m = MODEL
        job, root = make_job()
        for badroot in (replace(root, generation=6), replace(root, valid=False), replace(root, state=root.state + 64)):
            self.assertEqual(m.admission_status(job, badroot), m.Status.DEPENDENCY)
        cold, coldroot = make_job(cold=True)
        self.assertEqual(m.admission_status(cold, coldroot), 0)
        self.assertEqual(m.admission_status(cold, replace(coldroot, valid=True)), m.Status.DEPENDENCY)
        for tokens in (0, 1, 64, 129):
            self.assertEqual(m.admission_status(repack(job, tokens=tokens), root), m.Status.BOUNDS)
        for bad in (replace(job, head=16), replace(job, head=65535), replace(job, chunk=1)):
            self.assertEqual(m.admission_status(bad, root), m.Status.BOUNDS)
        job128, root128 = make_job(128, 15, 1)
        self.assertEqual(m.admission_status(job128, root128), 0)
        self.assertEqual(m.admission_status(replace(job128, chunk=2), root128), m.Status.BOUNDS)
        last = repack(job, expected_generation=0xFFFFFFFF)
        self.assertEqual(m.admission_status(last, replace(root, generation=0xFFFFFFFF)), m.Status.BOUNDS)
        self.assertEqual(m.admission_status(repack(job, vector_policy=1), root), m.Status.UNSUPPORTED)
        names = ('input', 'state_in', 'state_out', 'output', 'scratch')
        sizes = (16 * 25600, 1048576, 1048576, 16 * 4096, 16 * 872448)
        for name, size in zip(names, sizes):
            for address, expected in ((getattr(job.context, name) + 1, m.Status.BOUNDS),
                                      ((1 << 56) - size, m.Status.OK),
                                      ((1 << 56) - size + 64, m.Status.BOUNDS)):
                candidate = repack(job, **{name: address})
                snapshot = replace(root, state=address) if name == 'state_in' else root
                self.assertEqual(m.admission_status(candidate, snapshot), expected)
        for i, name in enumerate(names):
            for other in names[:i]:
                address = getattr(job.context, other)
                candidate = repack(job, **{name: address})
                snapshot = replace(root, state=candidate.context.state_in)
                self.assertEqual(m.admission_status(candidate, snapshot), m.Status.BOUNDS)
        # Root mismatch outranks bounds/policy/provenance, bounds outranks policy.
        bad = repack(job, tokens=1, vector_policy=1)
        self.assertEqual(m.admission_status(bad, replace(root, generation=0)), m.Status.DEPENDENCY)
        self.assertEqual(m.admission_status(bad, root), m.Status.BOUNDS)

    def test_stale_admission_services_and_committed_sampling(self):
        m = MODEL
        job, root = make_job()
        for kwargs in (dict(response=m.MemoryResponse(0)), dict(scalar_result=m.ScalarResult(0)),
                       dict(loan_result=m.LoanResult(0)), dict(loan_busy=True), dict(loan_reset_required=True)):
            owner = m.Owner()
            owner.tick(job=job, committed=root, **kwargs)
            self.failure(owner, m.Status.PROTOCOL)
        owner = self.accepted()
        owner.tick(committed=m.Committed(False, 99, 0))
        self.assertEqual(owner.state, 'issueRead')
        self.assertEqual(owner.job.context, job.context)

    def test_memory_errors_wrong_tag_priority_and_ack_only_counts(self):
        m = MODEL
        for step in ('finalGate', 'writeKb'):
            for wrong, error, status in ((True, True, m.Status.PROTOCOL), (True, False, m.Status.PROTOCOL),
                                         (False, True, m.Status.MEMORY)):
                owner = self.prepare(step)
                req = owner.peek().memory_request
                before = owner.read_bytes, owner.write_bytes
                owner.tick(memory_ready=True)
                owner.tick(response=m.MemoryResponse(req.tag ^ int(wrong), 0x7FC00000, error))
                self.assertEqual((owner.read_bytes, owner.write_bytes), before)
                self.failure(owner, status, outstanding=(wrong, False, False))
        owner = self.prepare('writeKbg')
        self.assertEqual(owner.write_bytes, 64)
        req = owner.peek().memory_request
        owner.tick(memory_ready=True)
        owner.tick(response=m.MemoryResponse(req.tag, error=True))
        self.assertEqual(owner.write_bytes, 64)
        self.failure(owner, m.Status.MEMORY)

    def test_finite_memory_and_exp_domain_guard_before_valid(self):
        m = MODEL
        for word in (0x7F800000, 0xFF800000, 0x7FC00000):
            owner = self.accepted()
            request = owner.peek().memory_request
            owner.tick(memory_ready=True)
            owner.tick(response=m.MemoryResponse(request.tag, word << (15 * 32)))
            self.assertEqual((owner.read_bytes, owner.exp_requests), (64, 0))
            self.failure(owner, m.Status.NUMERICAL, outstanding=(False, False, False))
        for word in (1, 0x3F800000, 0x42A00000):
            owner = self.accepted()
            request = owner.peek().memory_request
            owner.tick(memory_ready=True)
            owner.tick(response=m.MemoryResponse(request.tag, word))
            self.assertIsNone(owner.peek().scalar_request)
            e = owner.tick(scalar_ready=True)
            self.assertFalse(e.scalar_fire)
            self.assertEqual(owner.exp_requests, 0)
            self.failure(owner, m.Status.NUMERICAL)
        # Positive finite subtraction result is rejected before pair/remaining Exp.
        for step in ('remainingAdd', 'pairAdd'):
            owner = self.prepare(step)
            req = owner.peek().loan_request
            owner.tick(loan_ready=True)
            owner.tick(loan_result=m.LoanResult(req.tag, value=1))
            before = owner.exp_requests
            self.assertIsNone(owner.peek().scalar_request)
            owner.tick(scalar_ready=True)
            self.assertEqual(owner.exp_requests, before)
            self.failure(owner, m.Status.NUMERICAL)
        for word in (0, 0x80000000, 0x80000001, 0xC2A00000):
            owner = self.accepted()
            req = owner.peek().memory_request
            owner.tick(memory_ready=True)
            owner.tick(response=m.MemoryResponse(req.tag, word))
            self.assertEqual(owner.peek().scalar_request.a, word)

    def test_scalar_errors_and_exact_subnormal_response(self):
        m = MODEL
        for result in (m.ScalarResult(1, True), m.ScalarResult(0x7F800000),
                       m.ScalarResult(0xFF800000), m.ScalarResult(0x7FC00000)):
            owner = self.prepare('chunkExp')
            owner.tick(scalar_ready=True)
            owner.tick(scalar_result=result)
            self.assertEqual((owner.exp_requests, owner.exp_results), (1, 0))
            self.failure(owner, m.Status.NUMERICAL, outstanding=(False, False, False))
        owner = self.prepare('chunkExp')
        owner.tick(scalar_ready=True)
        owner.tick(scalar_result=m.ScalarResult(1))
        self.assertEqual((owner.chunk_decay, owner.exp_results), (1, 1))
        self.assertIsNone(owner.peek().done)

    def test_loan_errors_wrong_tag_poison_and_exact_subnormal(self):
        m = MODEL
        for wrong, status, value, expected in ((True, 8, 0x7FC00000, 7), (True, 0, 0, 7),
             (False, 3, 0x7FC00000, 3), (False, 8, 1, 8), (False, 0, 0x7FC00000 << 480, 8)):
            owner = self.prepare('remainingAdd')
            req = owner.peek().loan_request
            owner.tick(loan_ready=True)
            # A held error remains valid despite resetRequired. abort/reset stay LOW.
            self.assertTrue(owner.peek(True).loan_result_ready)
            owner.tick(loan_result=m.LoanResult(req.tag ^ int(wrong), status, value), loan_reset_required=True)
            self.assertEqual((owner.add_requests, owner.add_results), (1, 0))
            self.failure(owner, expected, outstanding=(False, False, wrong))
        owner = self.prepare('remainingAdd')
        self.assertIsNone(owner.peek(True).loan_request)
        e = owner.tick(loan_ready=True, loan_reset_required=True)
        self.assertFalse(e.loan_fire)
        self.assertEqual(owner.add_requests, 0)
        self.failure(owner, m.Status.DEPENDENCY)
        owner = self.prepare('remainingAdd')
        req = owner.peek().loan_request
        self.assertEqual(req.a >> 32, 0)
        self.assertEqual(req.b >> 32, 0)
        owner.tick(loan_ready=True)
        owner.tick(loan_result=m.LoanResult(req.tag, value=0x80000001))
        self.assertEqual(owner.add_results, 1)
        self.assertEqual(owner.peek().scalar_request.a, 0x80000001)

    def test_tuple_failures_never_spill_before_all_four_products(self):
        m = MODEL
        for failed_stage, completed in (('mulKb', 0), ('mulKbg', 1), ('mulQg', 2), ('mulKe', 3)):
            owner = self.prepare(failed_stage)
            self.assertEqual(owner.write_bytes, 0)
            self.assertIsNone(owner.peek().memory_request)
            self.assertEqual(owner.mul_results, completed)
            req = owner.peek().loan_request
            owner.tick(loan_ready=True)
            owner.tick(loan_result=m.LoanResult(req.tag, m.Status.NUMERICAL))
            self.assertEqual((owner.write_bytes, owner.mul_requests, owner.mul_results), (0, completed + 1, completed))
            self.failure(owner, m.Status.NUMERICAL)
        owner = self.prepare('writeKb')
        self.assertEqual((owner.mul_results, owner.write_bytes), (4, 0))

    def test_masked_pairs_no_service_and_diagonal_is_computed(self):
        owner = self.prepare('pairRead')
        self.assertEqual((owner.row, owner.pair_beat, owner.lane), (0, 0, 0))
        before = owner.exp_requests, owner.add_requests, owner.read_bytes
        for _ in range(3):
            # first diagonal: read gate -> Add -> Exp, despite resulting exp(0)=1.
            signals = owner.peek()
            if signals.memory_request:
                event = ('read', signals.memory_request.address, input_payload(owner.job, 'gates', 0))
            elif signals.loan_request:
                r = signals.loan_request
                event = ('loan', r.op, r.a, r.b, r.inverse)
            else:
                r = signals.scalar_request
                event = ('exp', r.op, r.a, r.b)
            drive_one(self, owner, event)
        self.assertEqual((owner.exp_requests, owner.add_requests, owner.read_bytes),
                         (before[0] + 1, before[1] + 1, before[2] + 64))
        self.assertEqual(owner.peek().memory_request.data, 0x3F800000)
        after = owner.exp_requests, owner.add_requests, owner.read_bytes
        for beat in range(4):
            req = owner.peek().memory_request
            self.assertTrue(req.write)
            self.assertEqual(owner.step, 'pairWrite')
            self.assertEqual(req.data, 0x3F800000 if beat == 0 else 0)
            drive_one(self, owner, ('write', req.address, req.data))
        self.assertEqual((owner.exp_requests, owner.add_requests, owner.read_bytes), after)
        self.assertEqual((owner.row, owner.step), (1, 'rowGate'))

    def test_unsigned_abi_rejections(self):
        m = MODEL
        job, _ = make_job()
        for name, value in (('tag', -1), ('tokens', 65536), ('expected_generation', 1 << 32),
            ('vector_policy', 2), ('input', 1 << 64), ('cold', 1)):
            with self.assertRaises(ValueError):
                replace(job.context, **{name: value})
        for factory in (lambda: replace(job, head=65536), lambda: replace(job, chunk=-1),
            lambda: replace(job.phase1_ready, add_requests=128),
            lambda: m.MemoryResponse(1 << 64), lambda: m.MemoryResponse(0, 1 << 512),
            lambda: m.MemoryResponse(0, error=1), lambda: m.ScalarRequest(8, 0),
            lambda: m.ScalarResult(1 << 32), lambda: m.LoanRequest(1 << 32, 1, 0, 0),
            lambda: m.LoanRequest(0, 1, 1 << 512, 0), lambda: m.LoanResult(0, 256),
            lambda: m.Owner().tick(memory_ready=1)):
            with self.assertRaises(ValueError):
                factory()


def main():
    global MODEL, PINS
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'contract', 'phase1'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(sys.version_info[:2] == (3, 12), 'only separately reviewed Python 3.12 admitted')
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'invoke -I -S -B')
    sys.addaudithook(readonly_audit)
    started = time.monotonic()
    try:
        PINS = PinSet(args.base, args.contract, args.phase1)
    except Exception as error:
        print(json.dumps(dict(status='INPUT_PIN_FAILURE', error=str(error))), flush=True)
        return 2
    result, problem, after_ok = None, None, False
    try:
        module = types.ModuleType('pinned_chunk_derived_model')
        module.__file__ = str(HERE / 'derived_model.py')
        sys.modules[module.__name__] = module
        code = compile(PINS.cache[('own', 'derived_model.py')], module.__file__, 'exec')
        exec(code, module.__dict__)
        MODEL = module
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
            for cls in (SourceCorrespondence, SimulatedArithmeticControls, ModelControls))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    except Exception as error:
        problem = str(error)
    finally:
        try:
            PINS.verify_after()
            after_ok = True
        except Exception as error:
            problem = 'AFTER_PIN_FAILURE: ' + str(error)
    success = problem is None and result is not None and result.wasSuccessful()
    print(json.dumps(dict(status='PASS_PYTHON_PROTOCOL_AND_SIMULATED_SERVICES_ONLY' if success else 'FAIL',
        executed_scala=False, executed_chisel=False, executed_rtl=False, executed_native_model=False,
        independent_fp32_dut_validation=False,
        response_service='SIMULATED_EXACT_INTEGER_BINARY32_RNE_ADD_MUL_AND_FROZEN_P7_NODES',
        tests=0 if result is None else result.testsRun, full_cases=FULL_CASES,
        pins_before_and_after=after_ok, pinned_files=len(PINS.entries),
        seconds=round(time.monotonic() - started, 6), error=problem,
        limits='No Scala compilation/elaboration, real service/transport validation, provenance, publication, full chunk/block, hardware timing or utilization proof.'), sort_keys=True), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
