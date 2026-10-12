"""Small FP32 and owner protocol checks; not RTL or full-chain numerical proof."""
from pathlib import Path
import random
import tempfile
import unittest

from . import check_vector_add as source
from . import vector_add_model as m
from ..ffn_public.test_prefix_owners import exact, ref_add


def request(a=0x3f800000, b=0x3f800000, binary_add=True):
    return m.Request((a,) * 16, (b,) * 16, binary_add)


class AddArithmeticTests(unittest.TestCase):
    def test_finite_add_compares_to_independent_rational_fp32(self):
        rng = random.Random(0xadd16)
        pairs = [(0, 0), (0x80000000, 0x80000000), (0, 0x80000000),
                 (1, 1), (0x00800000, 0x807fffff), (0x3f800000, 0x33800000),
                 (0x3f800001, 0x33800000), (0x7f7fffff, 0xff7fffff),
                 (0x3f801234, 0x33012345)]
        pairs += [(rng.randrange(0xff000000), rng.randrange(0xff000000)) for _ in range(512)]
        for a, b in pairs:
            if not m.fp.finite(a) or not m.fp.finite(b):
                continue
            got, want = m.add_lane(a, b), ref_add(a, b)
            self.assertEqual(got.value, want, (hex(a), hex(b)))
            self.assertEqual(got.error, not m.fp.finite(want))

    def test_signed_zero_exact_subnormal_and_cancellation(self):
        for a, b, want in ((0, 0, 0), (0x80000000, 0, 0),
                           (0x80000000, 0x80000000, 0x80000000),
                           (1, 1, 2), (0x80000001, 0x80000001, 0x80000002),
                           (0x00800000, 0x807fffff, 1), (1, 0x80000001, 0)):
            got = m.add_lane(a, b)
            self.assertEqual(got.value, want)
            self.assertFalse(got.error)
            self.assertEqual(got.flags & 2, 0)
            self.assertEqual(exact(want), exact(a) + exact(b))

    def test_finite_overflow_and_nonfinite_are_fatal(self):
        for a, b in ((0x7f7fffff, 0x7f7fffff), (0xff7fffff, 0xff7fffff),
                     (0x7f800000, 0), (0x7fc00001, 0), (0xff800000, 0)):
            self.assertTrue(m.add_lane(a, b).error)
        self.assertEqual(m.add_lane(0x7f7fffff, 0x7f7fffff).flags & 4, 4)

    def test_exception_policy_does_not_mask_underflow_or_invalid(self):
        # A finite binary32 Add has no naturally inexact tiny result. Exercise
        # the real fatal UF contract through an independently injected flag.
        for flag in (2, 4, 8, 16):
            self.assertTrue(m.LaneReply(1, flag).error)
        self.assertFalse(m.LaneReply(1, 1).error)


class LoanProtocolTests(unittest.TestCase):
    def ready_result(self, model, req=None):
        self.assertTrue(model.tick(request=req or request())['request_fire'])
        for _ in range(40):
            if model.ports()['result_valid']:
                return
            model.tick()
        self.fail('bounded software loan never returned')

    def test_holds_result_and_latches_payload_mode(self):
        model = m.VectorLoanModel(official_bf16=True)
        gate, up = [0x3f801234] * 16, [0x33012345] * 16
        self.assertTrue(model.tick(request=m.Request(gate, up))['request_fire'])
        gate[:] = [0x7fc00001] * 16
        up[:] = [0] * 16
        for _ in range(20):
            e = model.tick(request=request(0, 0, False))
            self.assertFalse(e['request_fire'])
            if e['result_valid']:
                break
        want = (ref_add(0x3f801234, 0x33012345),) * 16
        self.assertNotEqual(want[0] & 0xffff, 0)
        held = model.ports()['result']
        self.assertEqual(held.words, want)
        for _ in range(10):
            e = model.tick(request=request(0x7f800000, 0))
            self.assertEqual(e['result'], held)
            self.assertFalse(e['request_fire'] or e['result_fire'] or e['drained'])
        self.assertEqual(len(model.issued), 1)
        self.assertTrue(all(op == 'add' for op, _, _ in model.issued[0]))
        self.assertTrue(model.tick(result_ready=True)['result_fire'])
        self.assertTrue(model.ports()['drained'])
        self.assertFalse(model.ports()['reset_required'])

    def test_lane_readiness_and_out_of_order_returns(self):
        model = m.VectorLoanModel(auto_respond=False)
        model.tick(request=request())
        self.assertIsNone(model.tick(core_ready=[True] * 15 + [False])['issued'])
        self.assertEqual(model.state, 'issue')
        self.assertIsNotNone(model.tick()['issued'])
        for i in reversed(range(15)):
            self.assertFalse(model.tick(lane_returns={i: m.LaneReply(0x40000000)})['result_valid'])
        self.assertEqual(model.state, 'wait')
        model.tick(lane_returns={15: m.LaneReply(0x40000000)})
        self.assertEqual(model.ports()['words'], (0x40000000,) * 16)

    def test_error_reply_zero_payload_hold_retire_and_poison(self):
        for reply in (m.LaneReply(0x7f800000, 5), m.LaneReply(1, 3),
                      m.LaneReply(0x7fc00001), m.LaneReply(0, rejected=True)):
            model = m.VectorLoanModel(auto_respond=False)
            model.tick(request=request()); model.tick()
            replies = {i: m.LaneReply(0x40000000) for i in range(16)}
            replies[11] = reply
            model.tick(lane_returns=replies)
            for _ in range(5):
                e = model.tick()
                self.assertTrue(e['result_valid'] and e['error'])
                self.assertEqual(e['words'], m.ZERO)
                self.assertFalse(e['drained'])
            self.assertTrue(model.tick(result_ready=True)['result_fire'])
            self.assertTrue(model.ports()['drained'] and model.ports()['reset_required'])
            self.assertFalse(model.tick(request=request())['request_fire'])
            self.assertTrue(all(result.error and result.words == m.ZERO for result in model.published))

    def test_abort_on_final_public_result_wins_and_retires(self):
        for ready in (False, True):
            model = m.VectorLoanModel()
            self.ready_result(model)
            e = model.tick(result_ready=ready, abort=True)
            self.assertFalse(e['result_valid'] or e['result_fire'])
            self.assertEqual(model.published, [])
            self.assertTrue(model.ports()['drained'] and model.ports()['reset_required'])
            self.assertFalse(model.tick(request=request())['request_fire'])

    def test_abort_on_final_lane_return_drains_without_borrower_ready(self):
        model = m.VectorLoanModel(auto_respond=False)
        model.tick(request=request()); model.tick()
        model.tick(lane_returns={i: m.LaneReply(0x40000000) for i in range(15)})
        e = model.tick(lane_returns={15: m.LaneReply(0x40000000)}, abort=True)
        self.assertFalse(e['result_valid'] or e['drained'])
        self.assertFalse(model.ports()['drained'])
        model.tick(result_ready=False)
        self.assertTrue(model.ports()['drained'] and model.ports()['reset_required'])
        self.assertEqual(model.published, [])

    def test_abort_during_issue_or_wait_still_drains_and_reset_recovers(self):
        for before_issue in (True, False):
            model = m.VectorLoanModel(lane_latency=4)
            model.tick(request=request())
            if not before_issue:
                model.tick()
            model.tick(abort=True)
            for _ in range(12):
                self.assertFalse(model.tick(request=request())['result_fire'])
            self.assertTrue(model.ports()['drained'] and model.ports()['reset_required'])
            self.assertEqual(model.published, [])
            model.tick(coordinated_reset=True)
            self.ready_result(model)
            self.assertTrue(model.tick(result_ready=True)['result_fire'])

    def test_idle_abort_and_owner_busy_block_admission(self):
        model = m.VectorLoanModel()
        self.assertFalse(model.tick(request=request(), owner_idle=False)['request_fire'])
        self.assertFalse(model.tick(request=request(), abort=True)['request_fire'])
        self.assertTrue(model.ports()['drained'])
        self.assertFalse(model.tick(request=request())['request_fire'])

    def test_registered_poison_and_error_handshake_have_no_abort_feedback(self):
        model = m.VectorLoanModel()
        # Current abort must not enter reset_required combinationally; the
        # borrower can safely feed that registered output back into abort.
        self.assertFalse(model.ports(abort=True)['reset_required'])
        self.ready_result(model, request(0x7f7fffff, 0x7f7fffff))
        ports = model.ports()
        cancel = ports['reset_required']
        arithmetic_error = ports['result_valid'] and ports['error']
        self.assertFalse(cancel)
        self.assertTrue(arithmetic_error)
        e = model.tick(abort=cancel, result_ready=arithmetic_error)
        self.assertTrue(e['result_fire'])
        self.assertEqual(e['words'], m.ZERO)
        self.assertTrue(model.ports()['drained'] and model.ports()['reset_required'])

    def test_false_mode_keeps_six_silu_phases(self):
        model = m.VectorLoanModel(auto_respond=False, official_bf16=True)
        model.tick(request=request(binary_add=False))
        for phase, op in enumerate(('exp_negative', 'add', 'div', 'mul', 'mul', 'mul')):
            e = model.tick(request=request(binary_add=True))
            self.assertEqual(e['issued'][0][0], op)
            model.tick(lane_returns={i: m.LaneReply(0x3f801234) for i in range(16)})
            self.assertEqual(model.value[0], 0x3f800000 if phase in (4, 5) else 0x3f801234)
        self.assertTrue(model.ports()['result_valid'])
        self.assertEqual(len(model.issued), 6)


class SourceScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='vector_add_test_', dir='/tmp')
        cls.paths, cls.report, cls.before, cls.after = source.compose(Path(cls.tmp.name) / 'source')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_patch_composes_and_does_not_allocate_arithmetic_or_storage(self):
        self.assertEqual(self.report['changed_sources'], [source.VECTOR])
        self.assertEqual(self.report['expected_added_state_bits'], 1)
        self.assertFalse(self.report['dense_or_bank_connected'])
        self.assertFalse(self.report['default_ir_equivalence_verified'])

    def test_reject_extra_alu_and_detached_latch_or_drain(self):
        for old, new in (('val cores = Seq.fill(lanes)(Module(new BlockScalarFloat))',
                          'val cores = Seq.fill(lanes)(Module(new BlockScalarFloat))\n val extra=Module(new BlockScalarFloat)'),
                         ('core.io.request.bits.a:=input.gate(i)', 'core.io.request.bits.a:=io.request.bits.gate(i)'),
                         ('p.result.ready || loanPoison || p.abort', 'p.result.ready'),
                         ('!loanPoison && !p.abort', '!loanPoison')):
            after = dict(self.after)
            after[source.VECTOR] = after[source.VECTOR].replace(old, new)
            with self.assertRaises(ValueError):
                source.audit(self.before, after)


class HandshakeDependencyTests(unittest.TestCase):
    FIR = """circuit VectorAddHandshakeHarness :
  module VectorAddHandshakeHarness :
    reg poison : UInt<1>, clock
    node cancel = or(io.abort, owner.io.loan.resetRequired)
    node arithmeticError = and(owner.io.loan.result.valid, owner.io.loan.result.bits.error)
    node bad = or(cancel, arithmeticError)
    connect owner.io.loan.abort, cancel
    connect owner.io.loan.result.ready, or(bad, io.write.ready)
    connect io.write.valid, and(owner.io.loan.result.valid, not(bad))
    connect io.request.ready, owner.io.loan.request.ready
  module VectorSiluOwner :
    reg loanPoison : UInt<1>, clock
    reg loanActive : UInt<1>, clock
    connect io.loan.resetRequired, loanPoison
    connect io.loan.result.valid, and(loanActive, and(vector.io.result.valid, not(io.loan.abort)))
    connect io.loan.result.bits.error, vector.io.result.bits.error
    connect io.loan.request.ready, not(loanPoison)
  module SiluVectorUnit :
    reg state : UInt<2>, clock
    reg error : UInt<1>, clock
    connect io.result.valid, eq(state, UInt<2>(3))
    connect io.result.bits.error, error
"""

    def test_accept_registered_poison_and_direct_error_retirement(self):
        self.assertEqual(source.audit_handshake_dependencies(self.FIR)['status'],
                         'PASS_CONSERVATIVE_LOAN_CONTROL_DEPENDENCIES')

    def test_reject_current_result_error_feedback_into_abort(self):
        fir = self.FIR.replace('connect owner.io.loan.abort, cancel', 'connect owner.io.loan.abort, bad')
        with self.assertRaisesRegex(ValueError, 'combinational handshake cycle'):
            source.audit_handshake_dependencies(fir)

    def test_reject_abort_reset_required_feedback(self):
        fir = self.FIR.replace('connect io.loan.resetRequired, loanPoison',
                               'connect io.loan.resetRequired, or(loanPoison, io.loan.abort)')
        with self.assertRaisesRegex(ValueError, 'combinational handshake cycle'):
            source.audit_handshake_dependencies(fir)

    def test_guard_dependencies_cannot_hide_feedback(self):
        fir = self.FIR.replace('connect owner.io.loan.abort, cancel',
                              'connect owner.io.loan.abort, cancel\n    when arithmeticError :\n      connect owner.io.loan.abort, UInt<1>(1)')
        with self.assertRaisesRegex(ValueError, 'combinational handshake cycle'):
            source.audit_handshake_dependencies(fir)


if __name__ == '__main__':
    unittest.main()
