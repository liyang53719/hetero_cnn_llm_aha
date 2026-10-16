"""Bounded cold tests: exact source recipe, allValid, debt and backpressure."""
from collections import Counter
from dataclasses import replace
from fractions import Fraction
import random
import unittest

from candidates.qwen2_resident_matrix.sfu_silu_cycle_candidate.arithmetic import (ROOT, Primitive, check_sources, definitions, exact, finite,
                         primitive, ref_add, ref_bf, ref_div, ref_mul, rn)
from candidates.qwen2_resident_matrix.sfu_silu_cycle_candidate.model import Configuration, Request, SiluCycleModel


class Fault(ValueError):
    pass


_source = definitions(ROOT / 'candidates/qwen2_resident_matrix/ffn_attention/scalar_recipe.py',
    ('EXP_COEFFICIENTS', 'LOG2_RECIPROCAL', 'exp_negative'),
    dict(ArithmeticFault=Fault, finite=finite, value=exact,
         word=lambda x: rn(Fraction(x))))


class OriginalScalar:
    """Execute unchanged exp AST on the existing independent rational helpers."""
    def __init__(self):
        self.client = self
        self.trace = []

    def op(self, client, operation, a, b=0, *, policy):
        if client is not self or policy != 'vector':
            raise ValueError('original exp ownership/policy')
        result = {'add': ref_add, 'mul': ref_mul}[operation](a, b)
        self.trace.append((operation, a, b, result))
        return result


def reference(request, profile):
    values, probability = [0] * 16, [0] * 16
    phases, exp_trace = [], []
    for phase in range(6):
        raw, bad = [], False
        for i in range(16):
            gate, up = request.gate[i], request.up[i]
            if phase == 0:
                scalar = OriginalScalar()
                try:
                    result = _source['exp_negative'](scalar, scalar, gate)
                except Fault:
                    result, bad = 0, True
                probability[i] = result
                exp_trace.append(scalar.trace)
            else:
                a, b = ((0x3f800000, values[i]) if phase in (1, 2) else
                        (values[i], (probability[i] if gate >> 31 else 0x3f800000)
                         if phase == 3 else gate if phase == 4 else up))
                op = 'add' if phase == 1 else 'div' if phase == 2 else 'mul'
                if not finite(a) or not finite(b):
                    result, bad = 0, True
                else:
                    # Bits are independently selected from the original phase
                    # expression; callback flags supply the shared IEEE policy.
                    result = {'add': ref_add, 'div': ref_div, 'mul': ref_mul}[op](a, b)
                    bad |= bool(primitive(op, a, b).flags & 30) or not finite(result)
            raw.append(result)
        values = [ref_bf(x) for x in raw] if profile == 'Qwen2OfficialBf16V2' and phase in (4, 5) else raw[:]
        bad |= any(not finite(x) for x in values)
        phases.append(dict(phase=phase, raw=tuple(raw), value=tuple(values), error=bad))
        if bad:
            break
    return phases, exp_trace


def run(request, configuration=Configuration(), *, stall=0, arithmetic=primitive):
    model = SiluCycleModel(configuration, arithmetic=arithmetic)
    first = model.tick(request=request)
    if not first['accepted']:
        raise AssertionError('initial request refused')
    for _ in range(128):
        if model.response is not None:
            break
        model.tick()
    else:
        raise AssertionError('bounded candidate timeout')
    visible = model.edge
    response = model.response
    for _ in range(stall):
        event = model.tick(request=replace(request, tag=request.tag + 1))
        if event['accepted'] or event['response'] != response or event['debt'] != 1:
            raise AssertionError('held response overwritten')
    event = model.tick(response_ready=True)
    if not event['retired'] or event['debt'] or model.divider_debt:
        raise AssertionError('debt not retired')
    return model, response, visible


class SiluTests(unittest.TestCase):
    def test_named_defaults_and_source_identity(self):
        self.assertEqual(Configuration(), Configuration('legacy_wrapper', 0, 'LegacyV0'))
        self.assertGreater(len(check_sources()['sources']), 10)
        for args in [('microsequence', True), ('microsequence', 1), ('legacy_wrapper', 16),
                     ('microsequence', 0, 'arbitrary_precision')]:
            with self.assertRaises(ValueError):
                Configuration(*args)

    def test_every_intermediate_against_original_recipe_finite_bf16(self):
        rng = random.Random(161021)
        directed = [0, 0x80000000, 0x00010000, 0x80010000, 0x007f0000, 0x00800000,
                    0x3f000000, 0xbf000000, 0x3f800000, 0xbf800000, 0x429f0000,
                    0x42a00000, 0xc2a00000, 0x7f7f0000, 0xff7f0000, 0x40000000]
        vectors = [tuple(directed)]
        for _ in range(12):
            vectors.append(tuple(rng.randrange(0x7f80) << 16 | (rng.randrange(2) << 31)
                                 for _ in range(16)))
        for profile in ('LegacyV0', 'Qwen2OfficialBf16V2'):
            for gates in vectors:
                request = Request(7, gates, tuple(ref_bf(rn(Fraction(rng.randint(-8, 8), 4))) for _ in range(16)))
                expected, exp_trace = reference(request, profile)
                for schedule, option in [('legacy_wrapper', 0), ('microsequence', 0), ('microsequence', 16)]:
                    model, response, _ = run(request, Configuration(schedule, option, profile))
                    self.assertEqual([{k: v for k, v in p.items() if k != 'edge'}
                                      for p in model.phase_trace], expected)
                    self.assertEqual(response.value, expected[-1]['value'])
                    self.assertEqual(response.error, expected[-1]['error'])
                    for lane in range(16):
                        actual = [(x['operation'], x['a'], x['b'], x['bits'])
                                  for x in model.trace if x['phase'] == 0 and x['lane'] == lane]
                        self.assertEqual(actual, exp_trace[lane])

    def test_all_intermediate_nodes_identical_between_schedules(self):
        request = Request(8, tuple(rn(Fraction(i - 8, 3)) for i in range(16)), (0x3fc00000,) * 16)
        models = [run(request, Configuration(mode, option))[0] for mode, option in
                  [('legacy_wrapper', 0), ('microsequence', 0), ('microsequence', 16)]]
        for lane in range(16):
            traces = [[{k: v for k, v in t.items() if k != 'edge'} for t in model.trace if t['lane'] == lane]
                      for model in models]
            self.assertEqual(traces[0], traces[1]); self.assertEqual(traces[0], traces[2])

    def test_signed_zero_and_original_boundary_materializations(self):
        request = Request(1, (0, 0x80000000) * 8, (0x3f800000,) * 16)
        for profile in ('LegacyV0', 'Qwen2OfficialBf16V2'):
            model, response, _ = run(request, Configuration('microsequence', 0, profile))
            self.assertEqual(response.value, request.gate)
            self.assertFalse(response.error)
            self.assertEqual(model.counts['bf16_lane_materializations'], 32 if profile != 'LegacyV0' else 0)
        gate = ref_bf(rn(Fraction(11, 10)))
        up = ref_bf(rn(Fraction(13, 10)))
        q = Request(2, (gate,) * 16, (up,) * 16)
        legacy = run(q)[0]
        official = run(q, Configuration('microsequence', 0, 'Qwen2OfficialBf16V2'))[0]
        self.assertEqual(legacy.phase_trace[:4] and [p['value'] for p in legacy.phase_trace[:4]],
                         [p['value'] for p in official.phase_trace[:4]])
        self.assertNotEqual(legacy.phase_trace[4]['value'], official.phase_trace[4]['value'])
        self.assertEqual(official.phase_trace[5]['raw'][0], ref_mul(official.phase_trace[4]['value'][0], up))

    def test_cutoff_boundary_and_overflow_inside_exp_ignored(self):
        gates = (0x429fffff, 0x42a00000, 0x42a00001, 0xc29fffff,
                 0xc2a00000, 0xc2a00001, 0x7f7fffff, 0xff7fffff) * 2
        q = Request(1, gates, (0x3f800000,) * 16)
        model, response, _ = run(q, Configuration('microsequence'))
        expected, traces = reference(q, 'LegacyV0')
        self.assertEqual(response.value, expected[-1]['value'])
        self.assertEqual(model.counts['lane_cutoff'], 12)
        for i in (1, 2, 4, 5, 6, 7):
            self.assertEqual(len(traces[i]), 1)
        ignored = [t for t in model.trace if t['flags'] & 4]
        self.assertEqual(len(ignored), 4)
        self.assertTrue(all(t['flags_ignored'] and not t['bad'] for t in ignored))

    def test_exact_stage_counts_and_source_wrapper_edges(self):
        for gate, delay in [(0, 25), (0x3f800000, 26), (0x42a00000, 25)]:
            q = Request(1, (gate,) * 16, (0x3f800000,) * 16)
            full = gate < 0x42a00000
            for mode, opt in [('legacy_wrapper', 0), ('microsequence', 0), ('microsequence', 16)]:
                model, _, visible = run(q, Configuration(mode, opt))
                spacing = 14 if opt else delay
                self.assertEqual(model.counts['divider_spacing_' + str(spacing)], 16)
                self.assertEqual(model.counts['lane_mul'], 16 * (12 if full else 4))
                self.assertEqual(model.counts['lane_add'], 16 * (9 if full else 1))
                self.assertEqual(model.counts['lane_exp_floor'], 16 if full else 0)
                self.assertEqual(visible, (22 if full else 5) + spacing + 2 + (12 if mode == 'legacy_wrapper' else 0))
                self.assertEqual(model.counts['phase_barriers'], 6)
                for lane in range(16):
                    alu = [t['edge'] for t in model.trace if t['lane'] == lane and t['operation'] != 'div']
                    self.assertEqual(len(alu), len(set(alu)))

    def test_preserved_global_barrier_no_early_lane_reuse(self):
        q = Request(1, (0x42a00000, 0x3f800000, 0) + (0x42a00000,) * 13, (0x3f800000,) * 16)
        model, _, _ = run(q, Configuration('microsequence'))
        self.assertEqual(model.phase_trace[0]['edge'], 18)
        self.assertEqual({t['edge'] for t in model.trace if t['phase'] == 1}, {19})
        self.assertEqual(model.counts['divider_spacing_26'], 1)
        self.assertEqual(model.counts['divider_spacing_25'], 15)
        last_return = max(t['edge'] for t in model.trace if t['phase'] == 2)
        self.assertEqual({t['edge'] for t in model.trace if t['phase'] == 3}, {last_return + 1})
        self.assertEqual(model.counts['lane_barrier_hold'], 14 * 17 + 15)

    def test_held_response_backpressure_debt_and_reuse(self):
        q = Request(99, (0x3f800000,) * 16, (0x40000000,) * 16)
        model, response, _ = run(q, Configuration('microsequence'), stall=113)
        self.assertEqual(model.counts['response_stall_edges'], 113)
        self.assertEqual((model.accepted, model.retired), (1, 1))
        self.assertTrue(model.tick(request=replace(q, tag=100))['accepted'])
        while model.response is None:
            model.tick()
        event = model.tick(request=replace(q, tag=101), response_ready=True)
        self.assertTrue(event['retired']); self.assertFalse(event['accepted'])
        self.assertEqual(event['response'], replace(response, tag=100))

    def test_abort_at_every_edge_drains_divider_and_holds_terminal(self):
        q = Request(5, (0, 0x3f800000) * 8, (0x3f800000,) * 16)
        for options in (0, 16):
            for abort_edge in range(1, 51):
                model = SiluCycleModel(Configuration('microsequence', options))
                model.tick(request=q)
                while model.edge < abort_edge and model.response is None:
                    model.tick()
                was_held = model.response
                model.tick(abort=True)
                while model.response is None:
                    model.tick()
                response = model.response
                self.assertEqual(model.counts['divider_accepts'], model.counts['divider_returns'])
                self.assertEqual(model.divider_debt, 0)
                if was_held:
                    self.assertEqual(response, was_held)  # late abort cannot mutate a held packet
                else:
                    self.assertTrue(response.error and response.aborted)
                for _ in range(3):
                    event = model.tick(abort=True, request=replace(q, tag=6))
                    self.assertEqual(event['response'], response)
                    self.assertEqual(event['debt'], 1)
                event = model.tick(response_ready=True)
                self.assertFalse(event['publish'])
                self.assertTrue(event['cancelled'])
                self.assertEqual(event['debt'], 0)

    def test_abort_on_held_response_and_ack_suppresses_publication(self):
        q = Request(8, (0x3f800000,) * 16, (0x3f800000,) * 16)
        for same_edge_ack in (False, True):
            model = SiluCycleModel(Configuration('microsequence'))
            model.tick(request=q)
            while model.response is None:
                model.tick()
            held = model.response
            event = model.tick(abort=True, response_ready=same_edge_ack)
            self.assertEqual(event['response'], held)
            self.assertTrue(event['cancelled'])
            self.assertFalse(event['publish'])
            if not same_edge_ack:
                for _ in range(17):
                    event = model.tick()
                    self.assertEqual(event['response'], held)
                    self.assertTrue(event['cancelled'])
                event = model.tick(response_ready=True)
                self.assertFalse(event['publish'])
                self.assertTrue(event['cancelled'])
            self.assertTrue(event['retired'])
            self.assertEqual(event['debt'], 0)
            self.assertTrue(model.tick(request=replace(q, tag=9))['accepted'])
            while model.response is None:
                model.tick()
            self.assertTrue(model.tick(response_ready=True)['publish'])

    def test_original_failure_phase_and_all_lane_drain(self):
        for gate, up, phase in [(0x7f800000, 0x3f800000, 0),
                                 (0x3f800000, 0x7fc00000, 5),
                                 (1, 0x3f800000, 4),
                                 (0x7f7fffff, 0x40000000, 5)]:
            q = Request(1, (gate,) + (0x3f800000,) * 15, (up,) + (0x3f800000,) * 15)
            for mode in ('legacy_wrapper', 'microsequence'):
                model, response, _ = run(q, Configuration(mode))
                self.assertTrue(response.error)
                self.assertEqual(response.failed_phase, phase)
                self.assertEqual(len(model.phase_trace), phase + 1)
                self.assertEqual(model.counts['divider_accepts'], model.counts['divider_returns'])

    def test_internal_flags_ignored_but_outer_underflow_fatal(self):
        def flags(op, a, b):
            result = primitive(op, a, b)
            return Primitive(result.bits, result.flags | 2)
        model, response, _ = run(Request(1, (0x3f800000,) * 16, (0x3f800000,) * 16),
                                 Configuration('microsequence'), arithmetic=flags)
        self.assertEqual(response.failed_phase, 1)
        self.assertFalse(model.phase_trace[0]['error'])
        self.assertEqual(model.counts['divider_accepts'], 0)

    def test_exact_subnormals_vs_fatal_inexact_and_min_normal_boundary(self):
        self.assertEqual(primitive('mul', 0x00800000, 0x3f000000), Primitive(0x00400000, 0))
        self.assertEqual(primitive('mul', 1, 0x3f000000), Primitive(0, 3))
        self.assertEqual(primitive('mul', 0x00800000, 0x3f7fffff), Primitive(0x00800000, 3))
        self.assertEqual(primitive('mul', 0x00800001, 0x3f7ffffe), Primitive(0x00800000, 1))
        self.assertEqual(primitive('div', 0x3f800000, 0), Primitive(0x7f800000, 8))
        self.assertEqual(primitive('div', 0, 0), Primitive(0x7fc00000, 16))

    def test_invalid_controls_do_not_mutate_state(self):
        model = SiluCycleModel()
        for kwargs in [dict(response_ready=1), dict(abort=1), dict(request=object())]:
            with self.assertRaises(ValueError):
                model.tick(**kwargs)
            self.assertEqual(model.edge, 0)
        for args in [(True, (0,) * 16, (0,) * 16), (1, [0] * 16, (0,) * 16),
                     (1, (True,) * 16, (0,) * 16), (1, (1 << 32,) * 16, (0,) * 16)]:
            with self.assertRaises(ValueError):
                Request(*args)
        self.assertFalse(model.tick(request=Request(1, (0,) * 16, (0,) * 16), abort=True)['accepted'])


if __name__ == '__main__':
    unittest.main()
