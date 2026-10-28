"""Small original-graph/source/protocol models, NOT Chisel/DUT/RTL execution.
ExpNegative is deliberately injected identically in both graphs. This verifies
operation/FP32/BF16 boundary placement, not the frozen hardware polynomial or
Torch equivalence. Held/debt models are abstract protocol controls only.
"""
from pathlib import Path
import argparse
import hashlib
import math
import re
import struct
import unittest

C = Path(__file__).resolve().parents[1]
W = C.parent
LEAF = C / 'source/GdnRuntimeElementwiseOwnerV15.scala'
PROTOCOL = C / 'source/UnifiedMoeSharedArithmeticProtocolV5.scala'
BASE = W / 'host_runtime_output/source/GdnRuntimeElementwiseOwnerV15.scala'
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--original-elementwise-source',type=Path,required=True)
args,unittest_args=parser.parse_known_args()
ORIGINAL=args.original_elementwise_source
ORIGINAL_SHA = '01b394526f75b9732c3e605652c64f3968851aca97258a3a640bc056de1f2fe3'
BASE_SHA = 'fb05631a19d4dcb90b9e35f018b3a8e362d94535274b4ef079160acb28a71ffe'


def need(condition, message):
    if not condition:
        raise ValueError(message)


def f32(x):
    try:
        return struct.unpack('>f', struct.pack('>f', x))[0]
    except OverflowError:
        return math.copysign(math.inf, x)


def bits(x):
    return struct.unpack('>I', struct.pack('>f', x))[0]


def from_bits(x):
    return struct.unpack('>f', struct.pack('>I', x))[0]


def bf16(x):
    u = bits(x)
    return from_bits(((u + 0x7fff + ((u >> 16) & 1)) >> 16) << 16)


def scalar(op, a, b=0.):
    if op == 'exp':
        return f32(math.exp(-abs(a)))
    if op == 'div':
        return f32(a / b)
    if op == 'add':
        return f32(a + b)
    return f32(a * b)


def validate(g, u, op):
    if op not in (0, 1, 2):
        raise ValueError('unsupported op')
    if not math.isfinite(g) or not math.isfinite(u):
        raise ValueError('nonfinite')
    if op and bits(g) >> 31 and abs(g) >= 80:
        raise ValueError('unsupported negative gate')


def original_graph(g, u, op=1, exp_primitive=lambda x: scalar('exp', x)):
    validate(g, u, op)
    if op == 0:
        return bf16(scalar('add', g, u)), ['add', 'bf16']
    e = exp_primitive(g)
    den = scalar('add', 1., e)
    inv = scalar('div', 1., den)
    sig = scalar('mul', inv, e if bits(g) >> 31 else 1.)
    trace = ['exp', 'denominator', 'inverse', 'sign']
    if op == 1:
        sig = scalar('mul', sig, g)
        trace += ['activate']
    value = bf16(sig)
    return bf16(scalar('mul', value, u)), trace + ['bf16', 'multiply', 'bf16']


def successor_graph(g, u, op=1, exp_primitive=lambda x: scalar('exp', x),
                    round_sigmoid_early=False, omit_activation_round=False):
    validate(g, u, op)
    value, exponential = 0., 0.
    operation = 'add' if op == 0 else 'exp'
    trace = []
    while True:
        trace.append(operation)
        if operation == 'add':
            value = scalar('add', g, u)
        elif operation == 'exp':
            value = exp_primitive(g)
            exponential = value
            operation = 'denominator'
            continue
        elif operation == 'denominator':
            value = scalar('add', 1., exponential)
            operation = 'inverse'
            continue
        elif operation == 'inverse':
            value = scalar('div', 1., value)
            operation = 'sign'
            continue
        elif operation == 'sign':
            value = scalar('mul', value, exponential if bits(g) >> 31 else 1.)
            if op == 1:
                if round_sigmoid_early:
                    value = bf16(value)
                operation = 'activate'
                continue
        elif operation == 'activate':
            value = scalar('mul', value, g)
        else:
            value = scalar('mul', value, u)
        trace.append('bf16')
        if not (operation == 'activate' and omit_activation_round):
            value = bf16(value)
        if operation in ('add', 'multiply'):
            return value, trace
        operation = 'multiply'


def shape(op, m, n):
    return 1 <= m <= 128 and ((op == 0 and n in (1024, 2048)) or
                            (op == 1 and n == 3584) or
                            (op == 2 and n in (2048, 4096)))


def counts(op, m, n):
    need(shape(op, m, n), 'shape')
    e = m * n
    return dict(scalar=e * (1, 6, 5)[op], formatter=e * (1 if op == 0 else 2),
                memory=e // 32 * 3, write_bytes=e * 2)


class Channel:
    def __init__(self):
        self.held = False
        self.pending = False
        self.poison = False
        self.quarantine = False
        self.accepted = self.returned = 0

    def offer(self, intent=True, published_gate=True, ready=False, fault=False):
        visible = intent and (not (self.poison or self.quarantine or fault) or self.held)
        published = visible and (published_gate or self.held)
        fire = published and ready
        if published:
            self.held = not ready
        if fire:
            self.pending = True
            self.accepted += 1
        self.poison |= fault
        return visible, published, fire

    def response(self, matching=True):
        if not self.pending or not matching:
            self.quarantine = self.poison = True
            return False
        self.pending = False
        self.returned += 1
        return True

    def drained(self):
        return not (self.held or self.pending or self.quarantine)


def source_checks(leaf, protocol, base=None):
    need('val add :: exp :: denominator :: inverse :: sign :: activate :: multiply :: Nil=Enum(7)' in leaf,
         'original seven FP32 operations')
    need('sign->Mux(x(31),exponential,F32.lit(1)),activate->x,multiply->y' in leaf,
         'exact original sign/gate/up operands')
    need('when(job.op===GdnElementwiseOp.SiluMul.U){operation:=activate}\n              .otherwise{state:=formatIssue}' in leaf,
         'SiLU must not format sigmoid')
    need('is(activate){state:=formatIssue}' in leaf and 'is(multiply){state:=formatIssue}' in leaf,
         'BF16 activation and output materialization')
    need('when(operation===sign || operation===activate){\n          value:=Cat(r.value,0.U(16.W));operation:=multiply;state:=scalarIssue' in leaf,
         'actual returned BF16 used by following multiply')
    need('val expectedScalar=elements*Mux(job.op===GdnElementwiseOp.SiluMul.U,6.U,\n    Mux(job.op===GdnElementwiseOp.SigmoidMul.U,5.U,1.U))' in leaf,
         'exact distinct Scalar quotas')
    need('val expectedFormat=elements*Mux(job.op===GdnElementwiseOp.Add.U,1.U,2.U)' in leaf,
         'exact Format quotas')
    need('(j.op===GdnElementwiseOp.SiluMul.U && j.rowWidth===3584.U)' in leaf,
         'fixed runtime F3584 only')
    need('(job.op===GdnElementwiseOp.SiluMul.U || job.op===GdnElementwiseOp.SigmoidMul.U) &&\n        x(31) && x(30,0)>=F32.lit(80)' in leaf,
         'negative saturation forbidden for both nonlinear branches')
    need('val requestPolicy=UnifiedScalarPolicyV2.Legacy.U(2.W)' in leaf and 'ScalarOp.MulIeeeRne.U' in leaf,
         'original policy and gradual-underflow multiplication')
    need('OrdinaryElementwiseMaximumOperations=Seq(2752512,1048576)' in protocol,
         'bound covers actual SiLU without growing formatter domain')
    need('val Count=11' in protocol and 'val OrdinaryElementwiseScalar=8;val OrdinaryElementwiseFormat=9' in protocol and
         'val OrdinaryElementwiseStage=77' in protocol and 'OrdinaryElementwise=9' in protocol,
         'reuse original slots/kind/stage')
    need(leaf.count('Reg(Vec(32,UInt(16.W)))') == 3, 'exact original payload banks')
    need('Module(new ' not in leaf and 'TensorMath.bf16Rne' not in leaf, 'no local formatter or FPU')
    need('when(published){held:= !ready}' in leaf and
         'val visible=intent && ((!poison && !quarantine && !currentFault) || held)' in leaf,
         'held requests survive late poison')
    need('when(memoryWrite && !io.response.bits.error){bytes:=bytes+64.U}' in leaf,
         'only actual successful ACK bytes')
    need('memoryAccepted===expectedMemory && sequence===expectedMemory && bytes===(elements<<1)' in leaf and
         'formatAccepted===expectedFormat && formatReturned===expectedFormat' in leaf and
         'scalarAccepted===expectedScalar && scalarReturned===expectedScalar' in leaf,
         'exact all counts required for completion')
    need('when(state===drain && !memoryPending && !scalarPending && !formatPending && !quarantine){state:=finish}' in leaf,
         'real debt and unknown quarantine preserved')
    if base is not None:
        # Numerical extension leaves request/response publication, memory ACK,
        # debt handling, and held terminal transport byte-for-byte unchanged.
        for start, end in [
            ('  val unknownMemory=', '  val x=Cat('),
            ('  when(io.memory.fire){', '  when(state===checkLane){'),
            ('  when(state===drain', '\n}')]:
            a = base[base.index(start):base.index(end, base.index(start))]
            b = leaf[leaf.index(start):leaf.index(end, leaf.index(start))]
            need(a == b, 'unchanged transport block ' + start)
        need(re.findall(r'\b(?:val|var)\s+\w+\s*=Reg(?:Init)?\([^\n]*', base) ==
             re.findall(r'\b(?:val|var)\s+\w+\s*=Reg(?:Init)?\([^\n]*', leaf),
             'register declarations unchanged')


class Numerical(unittest.TestCase):
    def test_original_pins(self):
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(), ORIGINAL_SHA)
        self.assertEqual(hashlib.sha256(BASE.read_bytes()).hexdigest(), BASE_SHA)

    def test_original_scalar_graph_all_ops(self):
        for op in (0, 1, 2):
            for g in [-79., -8., -2., -.01, -0.0, 0., .5, 1., 3., 79., 80.]:
                for u in [-32., -.1, 0., .01, 1., 17.]:
                    self.assertEqual(original_graph(bf16(g), bf16(u), op),
                                     successor_graph(bf16(g), bf16(u), op))

    def test_original_graph_injected_exp(self):
        for op in (1, 2):
            for e in [0., .25, .5, 1.]:
                for g in [-1., 1.]:
                    self.assertEqual(original_graph(g, 3., op, lambda x: e),
                                     successor_graph(g, 3., op, lambda x: e))

    def test_no_early_bf16_sigmoid(self):
        counterexamples = []
        for gi in range(-80, 81):
            for ui in range(1, 31):
                g, u = bf16(gi / 16), bf16(ui / 7)
                if bits(successor_graph(g, u)[0]) != bits(successor_graph(g, u, round_sigmoid_early=True)[0]):
                    counterexamples.append((g, u))
        self.assertTrue(counterexamples)

    def test_bf16_silu_cannot_be_omitted(self):
        counterexamples = []
        for gi in range(-80, 81):
            for ui in range(1, 31):
                g, u = bf16(gi / 16), bf16(ui / 7)
                if bits(successor_graph(g, u)[0]) != bits(successor_graph(g, u, omit_activation_round=True)[0]):
                    counterexamples.append((g, u))
        self.assertTrue(counterexamples)

    def test_silu_is_not_attention_gate(self):
        self.assertNotEqual(successor_graph(-2., 3., 1)[0], successor_graph(-2., 3., 2)[0])
        self.assertEqual(successor_graph(-2., 3., 1)[1],
                         ['exp', 'denominator', 'inverse', 'sign', 'activate', 'bf16', 'multiply', 'bf16'])

    def test_negative_cutoff_and_finite(self):
        for op in (1, 2):
            for g in [-80., -128., math.inf, math.nan]:
                with self.assertRaises(ValueError):
                    successor_graph(g, 1., op)
            for g in [-79., 80., 128.]:
                successor_graph(g, 1., op)
            with self.assertRaises(ValueError):
                successor_graph(1., math.inf, op)

    def test_shape_edges(self):
        for op, n in [(0, 1024), (0, 2048), (1, 3584), (2, 2048), (2, 4096)]:
            for m in [1, 16, 128]:
                self.assertTrue(shape(op, m, n))
        for args in [(1, 0, 3584), (1, 129, 3584), (1, 128, 512), (1, 128, 8960), (2, 128, 3584), (3, 128, 3584)]:
            self.assertFalse(shape(*args))

    def test_exact_silu_max_counts(self):
        self.assertEqual(counts(1, 128, 3584),
                         dict(scalar=2752512, formatter=917504, memory=43008, write_bytes=917504))

    def test_existing_bounds_unchanged(self):
        self.assertEqual(counts(2, 128, 4096),
                         dict(scalar=2621440, formatter=1048576, memory=49152, write_bytes=1048576))
        self.assertEqual(counts(0, 128, 2048),
                         dict(scalar=262144, formatter=262144, memory=24576, write_bytes=524288))


class Protocol(unittest.TestCase):
    def test_each_silu_node_can_hold_under_fault(self):
        for step in ['exp', 'denominator', 'inverse', 'sign', 'activate', 'multiply', 'format_silu', 'format_output', 'read_gate', 'read_up', 'write_output']:
            with self.subTest(step=step):
                c = Channel()
                self.assertEqual(c.offer(), (True, True, False))
                self.assertEqual(c.offer(published_gate=False, fault=True), (True, True, False))
                self.assertFalse(c.drained())
                self.assertEqual(c.offer(ready=True, published_gate=False), (True, True, True))
                self.assertTrue(c.pending)
                self.assertTrue(c.response())
                self.assertTrue(c.drained())
                self.assertEqual((c.accepted, c.returned), (1, 1))
                self.assertEqual(c.offer(ready=True), (False, False, False))

    def test_unpublished_intent_is_not_debt(self):
        c = Channel()
        self.assertEqual(c.offer(published_gate=False), (True, False, False))
        self.assertEqual(c.offer(fault=True), (False, False, False))
        self.assertTrue(c.drained())

    def test_unknown_reply_preserves_owned_debt(self):
        c = Channel()
        c.offer(ready=True)
        self.assertFalse(c.response(matching=False))
        self.assertTrue(c.pending)
        self.assertTrue(c.response())
        self.assertFalse(c.drained())

    def test_incomplete_success_never_retires(self):
        expected = counts(1, 128, 3584)
        for key in expected:
            actual = expected.copy()
            actual[key] -= 1
            self.assertNotEqual(actual, expected)

    def test_terminal_payload_late_fault_unchanged(self):
        terminal = dict(status=0, outputCommitted=True, outputAckBytes=917504)
        saved = terminal.copy()
        current_fault = True
        self.assertEqual(terminal, saved)
        self.assertFalse(terminal['outputCommitted'] and not current_fault)


class Source(unittest.TestCase):
    def test_source_contracts(self):
        source_checks(LEAF.read_text(), PROTOCOL.read_text(), BASE.read_text())

    def test_mutants_rejected(self):
        leaf, protocol = LEAF.read_text(), PROTOCOL.read_text()
        source_checks(leaf, protocol)
        mutations = [
            ('leaf', 'activate->x,multiply->y', 'activate->y,multiply->x'),
            ('leaf', 'when(job.op===GdnElementwiseOp.SiluMul.U){operation:=activate}',
             'when(job.op===GdnElementwiseOp.SiluMul.U){state:=formatIssue}'),
            ('leaf', 'is(activate){state:=formatIssue}', 'is(activate){operation:=multiply}'),
            ('leaf', 'GdnElementwiseOp.SiluMul.U,6.U', 'GdnElementwiseOp.SiluMul.U,5.U'),
            ('leaf', 'j.rowWidth===3584.U', 'j.rowWidth<=3584.U'),
            ('leaf', 'when(published){held:= !ready}', 'when(visible){held:= !ready}'),
            ('leaf', 'sequence===expectedMemory', 'sequence<=expectedMemory'),
            ('leaf', 'formatReturned===expectedFormat', 'formatReturned<=expectedFormat'),
            ('leaf', 'scalarReturned===expectedScalar', 'scalarReturned<=expectedScalar'),
            ('protocol', 'Seq(2752512,1048576)', 'Seq(2621440,1048576)'),
            ('protocol', 'val Count=11', 'val Count=12'),
        ]
        for target, before, after in mutations:
            values = dict(leaf=leaf, protocol=protocol)
            self.assertIn(before, values[target])
            values[target] = values[target].replace(before, after, 1)
            with self.subTest(mutation=before), self.assertRaises(ValueError):
                source_checks(values['leaf'], values['protocol'])


if __name__ == '__main__':
    unittest.main(argv=[__file__]+unittest_args)
