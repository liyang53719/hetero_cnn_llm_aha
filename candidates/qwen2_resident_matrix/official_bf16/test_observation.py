"""Synthetic M1/M2 read-only capture checks; reuse a verified host library.

No build fallback, official checkpoint, full-profile run, hardware simulation,
or reference-injected candidate activation is used by this suite.
"""
from contextlib import nullcontext
from dataclasses import replace
import hashlib
import json
import random
import struct
import sys
import tempfile
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from candidates.qwen2_resident_matrix.official_bf16 import observation as o
from candidates.qwen2_resident_matrix.official_bf16 import owners, dense_silu
from candidates.qwen2_resident_matrix.official_bf16.test_owners import verified_library
from candidates.qwen2_resident_matrix.ffn_public import prefix_arithmetic as a
from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import (
    Harness, exact, rn, ref_add, ref_mul, ref_div, ref_bf)
from candidates.qwen2_resident_matrix.ffn_attention.test_scalar_recipe import reference_exp


def snapshot():
    sources = o.base.verify_execution_sources()
    for name in o.REQUIRED_SOURCES:
        sources[name] = hashlib.sha256((o.ROOT / name).read_bytes()).hexdigest()
    return sources


def independent(tokens, q, k, v):
    """Exact rational FP32 oracle; each BF16 edge explicitly materialized."""
    records, rows = {}, {}
    for token in range(tokens):
        for head in range(12):
            scores = []
            for key in range(token + 1):
                parts = [0] * 16
                for depth in range(128):
                    x = ref_bf(q[token * 1536 + head * 128 + depth])
                    y = ref_bf(k[key * 256 + head // 6 * 128 + depth])
                    lane = depth % 16
                    parts[lane] = rn(exact(x) * exact(y) + exact(parts[lane]))
                total = 0
                for part in parts:
                    total = ref_add(total, part)
                dot = ref_bf(total)
                score = ref_bf(ref_mul(dot, 0x3db504f3))
                scores.append(score)
                records[head, token, key] = dict(dot_parts=tuple(parts), unrounded_dot_sum=(total,),
                    dot_bf16=(dot,), scores_bf16=(score,))
            maximum = max(scores, key=exact)
            exps, total = [], 0
            for key, score in enumerate(scores):
                exponent = reference_exp(ref_add(score, maximum ^ 0x80000000))
                exps.append(exponent)
                total = ref_add(total, exponent)
                records[head, token, key]['softmax_exp'] = (exponent,)
            inverse = ref_div(0x3f800000, total)
            probabilities = []
            for key, exponent in enumerate(exps):
                probability = ref_mul(exponent, inverse)
                probabilities.append(ref_bf(probability))
                records[head, token, key].update(softmax_fp32=(probability,),
                    prob_bf16=(ref_bf(probability),), normalizer=(maximum, total, inverse))
            raw = []
            for col in range(128):
                accumulator = 0
                for key, probability in enumerate(probabilities):
                    value = ref_bf(v[key * 256 + head // 6 * 128 + col])
                    accumulator = rn(exact(probability) * exact(value) + exact(accumulator))
                raw.append(accumulator)
            rows[head, token] = dict(pv_raw=tuple(raw), pv_bf16=tuple(ref_bf(x) for x in raw))
    return records, rows


class OfficialObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = verified_library()

    def make(self, tokens=1):
        self.assertEqual(self.library.td_reset(), 0)
        owner = owners.OfficialAttentionOwner(dense_silu.OfficialMatrixService(self.library), a.ScalarService())
        job = p.Job('Attention', (9 << 16) | 12, 0x100000, 0x200000, 0x400000,
                    tokens, 1536, 128, tokens * 1536 * 4, c=0x200000 + tokens * 256 * 4)
        rng = random.Random(210128)
        data = tuple(tuple(ref_bf(a.word(rng.uniform(-bound, bound))) for _ in range(count))
                     for count, bound in ((tokens * 1536, 1), (tokens * 256, 1), (tokens * 256, 2)))
        harness = Harness(owner)
        for address, values in zip((job.a, job.b, job.c), data):
            harness.bus.input(address, values)
        harness.bus.output(job.dst, job.write_bytes)
        return harness, job, data

    def execute(self, tokens, observe):
        h, job, data = self.make(tokens)
        capture = o.OfficialAttentionObservation(h.owner, source_sha256=snapshot()) if observe else None
        trace = hashlib.sha256()
        with capture if capture else nullcontext():
            for tick in range(30000):
                edge = h.tick(job=job if tick == 0 else None, memory_ready=tick % 3 != 0,
                    respond=tick % 5 != 0, matrix_request_ready=tick % 7 != 0,
                    matrix_result_ready=tick % 11 != 0, service_result_ready=tick % 13 != 0,
                    service_done_ready=tick % 17 != 0, response_ready=tick % 19 == 0)
                trace.update(repr(tuple((key, edge[key]) for key in sorted(edge))).encode())
                if edge['response_fire']:
                    result = edge['response']
                    self.assertIsNone(result.status)
                    self.assertFalse(h.bus.outputs[job.dst].intersection(h.bus.readable))
                    h.bus.publish(h.owner, job)
                    break
            else:
                self.fail('small actual Attention watchdog')
        return h, job, data, result, trace.hexdigest(), capture

    def test_m1_m2_same_outputs_requests_ticks_counts_and_all_actual_nodes(self):
        for tokens in (1, 2):
            with self.subTest(tokens=tokens):
                baseline = self.execute(tokens, False)
                h, job, data, result, trace, capture = self.execute(tokens, True)
                self.assertEqual(trace, baseline[4])
                self.assertEqual(result, baseline[3])
                self.assertEqual(h.bus.trace, baseline[0].bus.trace)
                self.assertEqual(h.owner.report(), baseline[0].owner.report())
                self.assertEqual(h.owner.matrix.report(), baseline[0].owner.matrix.report())
                self.assertEqual(h.bus.raw(job.dst), baseline[0].bus.raw(job.dst))
                report = capture.report()
                self.assertEqual(report['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
                self.assertEqual(report['schema'], o.SOURCE_VERSION)
                self.assertEqual(report['source_version'], 'qwen2-official-bf16-attention-observation-v4')
                self.assertEqual(report['helper_source_version'], o.base.SOURCE_VERSION)
                self.assertIsNone(report['execution_source_commit'])
                self.assertEqual(report['execution_source_base_commit'], o.base.SOURCE_BASE_COMMIT)
                self.assertIn('borrower=false', report['execution_source_profile'])
                self.assertEqual(report['helper_source_sha256'], {o.HELPER: o.HELPER_SHA256})
                self.assertFalse(report['prior_observation_results_inherited'])
                self.assertEqual(report['historical_fullgraph'], dict(commit=o.base.RECEIPT_COMMIT,
                    path=o.base.RECEIPT, sha256=o.base.RECEIPT_SHA, results_inherited=False))
                self.assertFalse(report['future_scores_observed'] or report['full_29_node_gate']
                    or report['whole_block_terminal_observed'] or report['physical_publication_observed']
                    or report['hardware_simulation'])
                records, rows = independent(tokens, *data)
                for (head, token, key), fields in records.items():
                    for name, expected in fields.items():
                        offset = (head * tokens + token) * tokens + key
                        if name == 'dot_parts':
                            offset *= 16
                        elif name == 'normalizer':
                            offset = (head * tokens + token) * 3
                        self.assertEqual(tuple(capture.fields[name]['words'][offset:offset + len(expected)]), expected)
                output = struct.unpack('<%dI' % (tokens * 1536), h.bus.raw(job.dst))
                for (head, token), fields in rows.items():
                    for name, expected in fields.items():
                        offset = (head * tokens + token) * 128
                        self.assertEqual(tuple(capture.fields[name]['words'][offset:offset + 128]), expected)
                    offset = (token * 12 + head) * 128
                    self.assertEqual(output[offset:offset + 128], fields['pv_bf16'])
                if tokens == 2:
                    self.assertNotEqual(capture.fields['unrounded_dot_sum']['words'], capture.fields['dot_bf16']['words'])
                    self.assertNotEqual(capture.fields['pv_raw']['words'], capture.fields['pv_bf16']['words'])
                    for name in ('dot_parts', 'unrounded_dot_sum', 'dot_bf16', 'scores_bf16',
                                 'softmax_exp', 'softmax_fp32', 'prob_bf16'):
                        width = 16 if name == 'dot_parts' else 1
                        for head in range(12):
                            offset = (head * 4 + 1) * width
                            self.assertEqual(tuple(capture.fields[name]['words'][offset:offset + width]), (o.SENTINEL,) * width)
                            self.assertEqual(capture.fields[name]['observed'][offset:offset + width], bytearray(width))
                            self.assertEqual(tuple(capture.fields[name]['frequency'][offset:offset + width]), (0,) * width)
                    self.assertEqual(report['fields']['prob_bf16']['identical_repeats'], 7 * 36)

    def test_idle_prefix_before_attention_and_auto_disarm_before_later_work(self):
        h, job, _ = self.make()
        prefix = Harness(owners.OfficialPrefixOwner(h.owner.scalar))
        bias = p.Job('Bias', 99, 0x500000, 0x600000, 0x700000, 1, 256, 256, 1024)
        for address in (bias.a, bias.b):
            prefix.bus.input(address, (0x3f810000,) * 256)
        prefix.bus.output(bias.dst, bias.write_bytes)
        with o.OfficialAttentionObservation(h.owner, source_sha256=snapshot()) as capture:
            self.assertIsNone(prefix.run(bias).status)
            self.assertEqual(capture.started, 0)
            self.assertIsNone(h.run(job, publish=False).status)
            self.assertTrue(capture.disarmed)
            self.assertIsNone(sys.gettrace())
            self.assertFalse(h.bus.outputs[job.dst].intersection(h.bus.readable))
            before = {name: field['writes'] for name, field in capture.fields.items()}
            prefix.tick(reset=True)
            h.tick(local_reset=True)
            self.assertEqual(before, {name: field['writes'] for name, field in capture.fields.items()})
        self.assertEqual(capture.report()['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')

    def test_matrix_done_final_ack_and_held_terminal_do_not_seal(self):
        h, job, _ = self.make()
        with o.OfficialAttentionObservation(h.owner, source_sha256=snapshot()) as capture:
            h.tick(job=job)
            h.until(lambda: h.owner.matrix_client.state == 'wait_done', service_done_ready=False)
            for _ in range(3):
                h.tick(service_done_ready=False)
                self.assertIsNone(capture.terminal)
                self.assertEqual(h.bus.writes, [])
            h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                    and h.owner.ack_bytes == job.write_bytes - 64)
            for _ in range(3):
                h.tick(respond=False)
                self.assertIsNone(capture.terminal)
                self.assertIsNone(h.owner.ports()['response'])
            h.until(lambda: h.owner.ports()['response'] is not None)
            for _ in range(3):
                h.tick()
                self.assertIsNone(capture.terminal)
            with self.assertRaisesRegex(ValueError, 'close the observer'):
                capture.report()
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        h.tick(response_ready=True)
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')

    def test_failed_final_ack_wrong_done_and_resets_cannot_seal(self):
        for mode in ('last_ack', 'wrong_done', 'active_reset', 'held_terminal_reset'):
            with self.subTest(mode=mode):
                h, job, _ = self.make()
                with o.OfficialAttentionObservation(h.owner, source_sha256=snapshot()) as capture:
                    h.tick(job=job)
                    if mode == 'last_ack':
                        h.until(lambda: h.bus.pending is not None and h.bus.pending.write
                                and h.owner.ack_bytes == job.write_bytes - 64)
                        h.tick(response=p.MemoryResponse(h.bus.pending.tag, error=True))
                    elif mode == 'wrong_done':
                        h.until(lambda: h.owner.matrix_client.state == 'wait_done', service_done_ready=False)
                        done = h.owner.matrix.done
                        h.tick(done_override=replace(done, tag=done.tag + 1))
                    elif mode == 'active_reset':
                        h.until(lambda: h.owner.matrix_client.state == 'wait_result')
                        h.tick(local_reset=True)
                    else:
                        h.until(lambda: h.owner.ports()['response'] is not None)
                        self.assertFalse(h.tick(local_reset=True, response_ready=True)['response_fire'])
                    h.until(lambda: h.owner.ports()['response'] is not None)
                    result = h.tick(response_ready=True)['response']
                    self.assertFalse(h.bus.outputs[job.dst].intersection(h.bus.readable))
                self.assertEqual(result.status, 'Memory' if mode == 'last_ack' else 'Protocol')
                self.assertEqual(capture.report()['status'], 'INCOMPLETE')
                self.assertTrue(capture.disarmed)
                self.assertIsNone(sys.gettrace())

    def test_snapshot_requires_exact_v4_inventory_and_all_extra_dependencies(self):
        h, _, _ = self.make()
        original = snapshot()
        frozen_raw = (o.ROOT / o.base.RECEIPT).read_bytes()
        frozen = json.loads(frozen_raw)['source_sha256']
        execution = o.verify_source_snapshot(original)
        self.assertEqual(len(execution), 75)
        self.assertEqual(set(execution), set(frozen))
        self.assertEqual({name for name in execution if execution[name] != frozen[name]},
                         set(o.base.EXECUTION_SOURCE_REPLACEMENTS))
        self.assertEqual(len(o.base.EXECUTION_SOURCE_REPLACEMENTS), 6)
        self.assertEqual(hashlib.sha256(frozen_raw).hexdigest(), o.base.RECEIPT_SHA)
        self.assertEqual(set(original) - set(execution), set(o.REQUIRED_SOURCES))
        for name in (*execution, *o.REQUIRED_SOURCES):
            changed = dict(original)
            changed.pop(name)
            with self.subTest(omitted=name), self.assertRaises(ValueError):
                o.OfficialAttentionObservation(h.owner, source_sha256=changed)
        for name in o.REQUIRED_SOURCES:
            changed = dict(original)
            changed[name] = '0' * 64
            with self.subTest(drift=name), self.assertRaisesRegex(ValueError, 'source drift'):
                o.OfficialAttentionObservation(h.owner, source_sha256=changed)
        for name in o.base.EXECUTION_SOURCE_REPLACEMENTS:
            changed = dict(original)
            changed[name] = frozen[name]
            with self.subTest(historical=name), self.assertRaisesRegex(ValueError, 'exact v4 75-source'):
                o.OfficialAttentionObservation(h.owner, source_sha256=changed)
        # Runner-specific supersets are allowed only with every extra identity
        # checked. They do not add entries to the exact 75-source inventory.
        extra = 'candidates/qwen2_resident_matrix/official_bf16/observation_monitoring.py'
        extended = dict(original, **{extra: hashlib.sha256((o.ROOT / extra).read_bytes()).hexdigest()})
        self.assertEqual(o.verify_source_snapshot(extended), execution)
        extended[extra] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source drift'):
            o.verify_source_snapshot(extended)
        real_read = Path.read_bytes
        def drift(path):
            raw = real_read(path)
            return raw + b'\n# unreviewed helper drift\n' if path == o.ROOT / o.HELPER else raw
        with patch.object(Path, 'read_bytes', drift):
            with self.assertRaisesRegex(ValueError, 'helper source drift'):
                o.verify_source_snapshot(original)
        good = o.base.EXECUTION_SOURCE_REPLACEMENTS
        missing = dict(good)
        missing.pop(next(iter(missing)))
        for changed in (missing, dict(good, **{'extra.py': ('a' * 64, 'b' * 64)})):
            with self.subTest(replacements=tuple(changed)), patch.object(o.base, 'EXECUTION_SOURCE_REPLACEMENTS', changed):
                with self.assertRaisesRegex(ValueError, 'replacement closure'):
                    o.OfficialAttentionObservation(h.owner, source_sha256=original)
        capture = o.OfficialAttentionObservation(h.owner, source_sha256=original)
        original[o.OWNER] = '0' * 64
        self.assertNotEqual(capture.sources[o.OWNER], original[o.OWNER])
        self.assertEqual(h.owner.state, 'idle')

    def test_loaded_new_old_driver_alias_instance_and_default_patches_rejected(self):
        from candidates.qwen2_resident_matrix.ffn_attention.attention_owner import AttentionOwner
        from candidates.qwen2_resident_matrix.ffn_public import fullgraph_execution
        h, _, _ = self.make()
        replacements = (
            (owners, 'exp_negative', lambda *args: 0),
            (owners.OfficialAttentionOwner, '_attention', lambda *args: None),
            (AttentionOwner, 'tick', lambda *args: {}),
            (dense_silu.OfficialMatrixService, 'acquire', lambda *args: True),
            (fullgraph_execution, 'execute_public_suffix', lambda *args: None),
            (h.owner.scalar, 'op', lambda *args: 0),
            (dense_silu, 'ROLE_SHAPES', types.MappingProxyType({})),
            (dense_silu.DenseBinding, '__setattr__', lambda *args: None),
            (o.base, '_same_code', lambda *args: True),
            (o.base, 'SOURCE_VERSION', 'qwen2-existing-attention-observation-v1'),
            (o.base, 'verify_execution_sources', lambda: {}),
            (o, 'HELPER_SHA256', '0' * 64),
        )
        for target, name, replacement in replacements:
            with self.subTest(name=name), patch.object(target, name, replacement):
                with self.assertRaisesRegex(ValueError, 'changed|patched|source drift|exact v4 75-source'):
                    o.OfficialAttentionObservation(h.owner, source_sha256=snapshot())
        with patch.object(owners.OfficialAttentionOwner, '_advance', lambda *args: None, create=True):
            with self.assertRaisesRegex(ValueError, 'inventory changed'):
                o.OfficialAttentionObservation(h.owner, source_sha256=snapshot())
        with patch.object(dense_silu.OfficialMatrixService.__init__, '__defaults__', (None,)):
            with self.assertRaisesRegex(ValueError, 'defaults/globals changed'):
                o.OfficialAttentionObservation(h.owner, source_sha256=snapshot())
        capture = o.OfficialAttentionObservation(h.owner, source_sha256=snapshot())
        with patch.object(owners, 'exp_negative', lambda *args: 0):
            with self.assertRaisesRegex(ValueError, 'import changed'):
                capture.__enter__()
        self.assertIsNone(sys.gettrace())

    def test_existing_trace_exception_and_replaced_trace_leave_incomplete(self):
        h, _, _ = self.make()
        capture = o.OfficialAttentionObservation(h.owner, source_sha256=snapshot())
        def existing(frame, event, arg):
            return None
        sys.settrace(existing)
        try:
            with self.assertRaisesRegex(ValueError, 'existing tracer'):
                capture.__enter__()
            self.assertIs(sys.gettrace(), existing)
        finally:
            sys.settrace(None)
        with self.assertRaisesRegex(RuntimeError, 'driver stopped'):
            with o.OfficialAttentionObservation(h.owner, source_sha256=snapshot()) as capture:
                raise RuntimeError('driver stopped')
        self.assertIn('exception', capture.report()['observer_error'])
        with o.OfficialAttentionObservation(h.owner, source_sha256=snapshot()) as capture:
            sys.settrace(None)
        self.assertIn('replaced', capture.report()['observer_error'])

    def test_causal_mask_duplicates_and_observer_failures_reject_seal_only(self):
        _, _, _, _, _, capture = self.execute(2, True)
        field = capture.fields['scores_bf16']
        field['words'][1], field['words'][0] = field['words'][0], o.SENTINEL
        field['observed'][1], field['observed'][0] = 1, 0
        field['frequency'][1], field['frequency'][0] = 1, 0
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        for mode in ('missing', 'duplicate', 'error'):
            h, job, _ = self.make()
            with o.OfficialAttentionObservation(h.owner, source_sha256=snapshot()) as capture:
                if mode == 'missing':
                    capture.points['score'] = -1
                else:
                    original = capture._put
                    def put(name, coordinates, values):
                        original(name, coordinates, values)
                        if name == 'scores_bf16':
                            if mode == 'error':
                                raise RuntimeError('diagnostic failure')
                            original(name, coordinates, values)
                    capture._put = put
                self.assertIsNone(h.run(job).status)
            self.assertEqual(capture.report()['status'], 'INCOMPLETE')
            self.assertIsNone(sys.gettrace())

    def test_changed_accepted_read_changes_captured_causal_nodes_and_pv(self):
        h, job, inputs = self.make(2)
        changed = list(inputs[0])
        changed[1536:1552] = [a.word(2.0)] * 16
        with o.OfficialAttentionObservation(h.owner, source_sha256=snapshot()) as capture:
            h.tick(job=job)
            h.until(lambda: h.bus.pending is not None and not h.bus.pending.write
                    and h.bus.pending.address == job.a + 1536 * 4)
            h.tick(response=p.MemoryResponse(h.bus.pending.tag, tuple(changed[1536:1552])))
            h.until(lambda: h.owner.ports()['response'] is not None)
            self.assertTrue(h.tick(response_ready=True)['response_fire'])
        expected, rows = independent(2, changed, *inputs[1:])
        original, _ = independent(2, *inputs)
        self.assertNotEqual(expected[0, 1, 0]['scores_bf16'], original[0, 1, 0]['scores_bf16'])
        self.assertEqual(capture.fields['scores_bf16']['words'][2], expected[0, 1, 0]['scores_bf16'][0])
        self.assertEqual(capture.report()['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
        output = struct.unpack('<3072I', h.bus.raw(job.dst))
        for (head, token), fields in rows.items():
            offset = (token * 12 + head) * 128
            self.assertEqual(output[offset:offset + 128], fields['pv_bf16'])

    def test_saved_pack_has_distinct_raw_materialized_and_presence_files(self):
        _, _, _, _, _, capture = self.execute(1, True)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'actual'
            report = capture.save(output)
            self.assertEqual(report, capture.report())
            for name, field in report['fields'].items():
                self.assertEqual(hashlib.sha256((output / (name + '.u32le')).read_bytes()).hexdigest(), field['raw_sha256'])
                self.assertEqual(hashlib.sha256((output / (name + '.presence')).read_bytes()).hexdigest(), field['presence_sha256'])
            with self.assertRaises(FileExistsError):
                capture.save(output)


if __name__ == '__main__':
    unittest.main()
