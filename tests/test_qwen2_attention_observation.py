"""Actual small software-owner observations, with independent integer arithmetic."""
from contextlib import nullcontext
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import observe_qwen2_attention_model as o
from scripts import build_shared_matrix_recipe as build
from candidates.qwen2_resident_matrix.ffn_attention import test_attention_owner as a


def setUpModule():
    if os.environ.get('QWEN2_ATTENTION_OBSERVATION_OUT'):
        build.from_environment(ROOT)
    a.setUpModule()


def tearDownModule():
    a.tearDownModule()


def execute(observe):
    h, job, inputs = a.make_harness(2)
    capture = o.AttentionObservation(h.owner) if observe else None
    trace = hashlib.sha256()
    with capture if capture is not None else nullcontext():
        for tick in range(20000):
            edge = h.tick(job=job if tick == 0 else None,
                memory_ready=tick % 3 != 0, respond=tick % 5 != 0,
                matrix_request_ready=tick % 7 != 0, matrix_result_ready=tick % 11 != 0,
                service_result_ready=tick % 13 != 0, service_done_ready=tick % 17 != 0,
                response_ready=tick % 19 == 0)
            # Every offered request and every handshake, including held pins.
            trace.update(repr(tuple((k, edge[k]) for k in sorted(edge))).encode())
            if edge['response_fire']:
                result = edge['response']
                h.bus.publish(h.owner, job)
                break
        else:
            raise AssertionError('small actual Attention watchdog')
    return h, job, inputs, result, trace.hexdigest(), capture


def independent(tokens, q, k):
    records = {}
    for token in range(tokens):
        for head in range(12):
            scores = []
            for key in range(token + 1):
                parts = [0]*16
                for depth in range(128):
                    x = a.ref_bf(q[token*1536 + head*128 + depth])
                    y = a.ref_bf(k[key*256 + (head//6)*128 + depth])
                    lane = depth % 16
                    parts[lane] = a.rn(a.exact(x)*a.exact(y) + a.exact(parts[lane]))
                total = 0
                for part in parts:
                    total = a.ref_add(total, part)
                score = a.ref_mul(total, 0x3db504f3)
                scores.append(score)
                records[head, token, key] = dict(dot_parts=tuple(parts), dot_sum=(total,), scores=(score,))
            maximum = max(scores, key=a.exact)
            exps, total = [], 0
            for key, score in enumerate(scores):
                e = a.reference_exp(a.ref_add(score, maximum ^ 0x80000000))
                exps.append(e)
                total = a.ref_add(total, e)
                records[head, token, key]['softmax_exp'] = (e,)
            inverse = a.ref_div(0x3f800000, total)
            for key, e in enumerate(exps):
                probability = a.ref_mul(e, inverse)
                records[head, token, key].update(softmax_fp32=(probability,),
                    prob=(a.ref_bf(probability),), normalizer=(maximum,total,inverse))
    return records


class ObservationTests(unittest.TestCase):
    def test_actual_words_match_independent_arithmetic_and_every_unobserved_edge(self):
        baseline = execute(False)
        actual = execute(True)
        h, job, inputs, result, trace, capture = actual
        self.assertEqual(trace, baseline[4])
        self.assertEqual(result, baseline[3])
        self.assertEqual(h.bus.trace, baseline[0].bus.trace)
        self.assertEqual(h.owner.report(), baseline[0].owner.report())
        self.assertEqual(h.bus.raw(job.dst), baseline[0].bus.raw(job.dst))
        self.assertEqual(h.bus.raw(job.dst), struct.pack('<3072I', *a.reference_attention(2,*inputs)))
        report = capture.report()
        self.assertEqual(report['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
        self.assertEqual(report['schema'], 'qwen2-existing-attention-observation-v2')
        self.assertEqual(report['source_version'], o.SOURCE_VERSION)
        self.assertEqual(report['execution_source_commit'], o.SOURCE_COMMIT)
        self.assertFalse(report['prior_observation_results_inherited'])
        self.assertEqual(report['historical_fullgraph'], dict(commit=o.RECEIPT_COMMIT,
            path=o.RECEIPT, sha256=o.RECEIPT_SHA, results_inherited=False))
        self.assertFalse(report['future_scores_observed'] or report['full_29_node_gate'] or
                         report['hardware_simulation'] or report['whole_block_terminal_observed'])
        self.assertEqual(report['fields']['prob']['identical_repeats'], 7*36)
        self.assertEqual(report['fields']['softmax_fp32']['identical_repeats'], 7*36)
        output = struct.unpack('<3072I',h.bus.raw(job.dst))
        for head in range(12):
            for token in range(2):
                observed = capture.fields['pv']['words'][(head*2+token)*128:(head*2+token+1)*128]
                self.assertEqual(tuple(observed),output[(token*12+head)*128:(token*12+head+1)*128])
        for (head,token,key), fields in independent(2,*inputs[:2]).items():
            for name, expected in fields.items():
                index = (head*2+token)*2+key
                if name == 'dot_parts':
                    index *= 16
                elif name == 'normalizer':
                    index = (head*2+token)*3
                words = capture.fields[name]['words']
                self.assertEqual(tuple(words[index:index+len(expected)]), expected)
        # Future entries remain absent, even if their sentinel bits are finite.
        for name in ('dot_sum','scores','softmax_exp','softmax_fp32','prob'):
            field = capture.fields[name]
            for head in range(12):
                index = head*4+1
                self.assertEqual(field['observed'][index], 0)
                self.assertEqual(field['words'][index], o.SENTINEL)
        if os.environ.get('QWEN2_ATTENTION_OBSERVATION_OUT'):
            out=Path(os.environ['QWEN2_ATTENTION_OBSERVATION_OUT'])
            capture.save(out)
            library=build.from_environment(ROOT)
            self.assertEqual(Path(a.LIB._name).resolve(),library)
            receipt=Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT'])
            (out/'test_identity.json').write_text(json.dumps(dict(
                stimulus='deterministic synthetic M2 Q/K/V; no official checkpoint',
                test_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                matrix_compile_receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
                matrix_library_sha256=build.sha(library),trace_sha256=trace,
                output_sha256=hashlib.sha256(h.bus.raw(job.dst)).hexdigest(),
                baseline_trace_equal=True,baseline_output_equal=True,
                independent_integer_oracle_checked=True,native_acceptance=False),indent=2)+'\n')
        with tempfile.TemporaryDirectory() as tmp:
            saved = capture.save(Path(tmp)/'actual')
            self.assertEqual(saved, report)
            for name, field in report['fields'].items():
                data = (Path(tmp)/'actual'/(name+'.u32le')).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), field['raw_sha256'])
            with self.assertRaises(FileExistsError):
                capture.save(Path(tmp)/'actual')

    def test_final_ack_and_held_success_do_not_seal(self):
        h, j, _ = a.make_harness()
        with o.AttentionObservation(h.owner) as capture:
            h.tick(job=j)
            h.until(lambda: h.bus.pending is not None and h.bus.pending.write and
                    h.owner.ack_bytes == j.write_bytes-64)
            for _ in range(4):
                h.tick(respond=False)
                self.assertIsNone(capture.terminal)
                self.assertIsNone(h.owner.ports()['response'])
            h.until(lambda: h.owner.ports()['response'] is not None)
            for _ in range(3):
                h.tick()
                self.assertIsNone(capture.terminal)
            with self.assertRaisesRegex(ValueError,'close the observer'):
                capture.report()
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        # A later unobserved acceptance cannot upgrade the closed capture.
        self.assertTrue(h.tick(response_ready=True)['response_fire'])
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')

    def test_failed_final_ack_preserves_partial_words_and_rejects_success(self):
        h, j, _ = a.make_harness()
        with o.AttentionObservation(h.owner) as capture:
            h.tick(job=j)
            h.until(lambda: h.bus.pending is not None and h.bus.pending.write and
                    h.owner.ack_bytes == j.write_bytes-64)
            pending = h.bus.pending
            h.tick(response=a.p.MemoryResponse(pending.tag,error=True))
            h.until(lambda: h.owner.ports()['response'] is not None)
            edge = h.tick(response_ready=True)
            self.assertTrue(edge['response_fire'])
            self.assertEqual(edge['response'].status,'Memory')
        report = capture.report()
        self.assertEqual(report['status'],'INCOMPLETE')
        self.assertEqual(report['terminal']['write_bytes'],j.write_bytes-64)
        self.assertEqual(report['fields']['prob']['observed_words'],12)

    def test_reset_of_held_terminal_cannot_publish_old_success(self):
        h, j, _ = a.make_harness()
        with o.AttentionObservation(h.owner) as capture:
            h.tick(job=j)
            h.until(lambda: h.owner.ports()['response'] is not None)
            edge = h.tick(local_reset=True,response_ready=True)
            self.assertFalse(edge['response_fire'])
            h.until(lambda: h.owner.ports()['response'] is not None)
            self.assertTrue(h.tick(response_ready=True)['response_fire'])
        self.assertEqual(capture.report()['status'],'INCOMPLETE')
        self.assertEqual(capture.terminal['status'],'Protocol')

    def test_observer_error_does_not_change_owner_arithmetic_or_terminal(self):
        h, j, _ = a.make_harness()
        with o.AttentionObservation(h.owner) as capture:
            capture.points['score'] = -1  # Simulate a failed diagnostic observation point.
            result = h.run(j)
        self.assertIsNone(result.status)
        self.assertEqual(capture.report()['status'],'INCOMPLETE')

    def test_duplicate_observer_events_are_not_silently_accepted(self):
        h, j, _ = a.make_harness()
        with o.AttentionObservation(h.owner) as capture:
            original = capture._put
            def duplicate(name, coordinates, values):
                original(name, coordinates, values)
                if name == 'scores':
                    original(name, coordinates, values)
            capture._put = duplicate
            self.assertIsNone(h.run(j).status)
        self.assertEqual(capture.report()['status'],'INCOMPLETE')
        self.assertEqual(capture.report()['fields']['scores']['identical_repeats'],12)

    def test_later_owner_reset_does_not_revoke_an_accepted_capture(self):
        h, j, _ = a.make_harness()
        with o.AttentionObservation(h.owner) as capture:
            self.assertIsNone(h.run(j).status)
        before = capture.report()
        self.assertEqual(before['status'],'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
        h.tick(local_reset=True)
        self.assertTrue(h.owner.poison)
        self.assertEqual(capture.report(),before)

    def test_changed_accepted_response_changes_actual_internals_and_output(self):
        h, j, inputs = a.make_harness(2)
        changed = list(inputs[0])
        changed[1536:1552] = [a.arithmetic.word(2.0)]*16
        with o.AttentionObservation(h.owner) as capture:
            h.tick(job=j)
            h.until(lambda: h.bus.pending is not None and not h.bus.pending.write and
                    h.bus.pending.address == j.a + 1536*4)
            h.tick(response=a.p.MemoryResponse(h.bus.pending.tag,tuple(changed[1536:1552])))
            h.until(lambda: h.owner.ports()['response'] is not None)
            self.assertTrue(h.tick(response_ready=True)['response_fire'])
        self.assertEqual(capture.report()['status'],'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
        expected = independent(2,changed,inputs[1])
        original = independent(2,*inputs[:2])
        self.assertNotEqual(expected[0,1,0]['scores'],original[0,1,0]['scores'])
        self.assertEqual(capture.fields['scores']['words'][2],expected[0,1,0]['scores'][0])
        expected_output = struct.pack('<3072I',*a.reference_attention(2,changed,*inputs[1:]))
        self.assertEqual(h.bus.raw(j.dst),expected_output)
        self.assertNotEqual(h.bus.raw(j.dst),struct.pack('<3072I',*a.reference_attention(2,*inputs)))

    def test_actual_numeric_matrix_and_active_reset_faults_never_seal(self):
        for mode in ('underflow','selected_nan','wrong_done','active_reset','offdiagonal_inf'):
            with self.subTest(mode=mode):
                q, k = [0]*1536,[0]*256
                if mode == 'underflow':
                    q[0],k[0] = 0x00010000,0x3f800000
                elif mode == 'selected_nan':
                    q[0],k[0] = 0x7fc10000,0x3f800000
                elif mode == 'offdiagonal_inf':
                    q[0],k[1] = 0x7f000000,0x7f000000
                h,j,_ = a.make_harness(q=tuple(q),k=tuple(k))
                with o.AttentionObservation(h.owner) as capture:
                    h.tick(job=j)
                    if mode == 'wrong_done':
                        h.until(lambda: h.owner.matrix_client.state=='wait_done',service_done_ready=False)
                        done = h.owner.matrix.done
                        h.tick(done_override=dataclasses.replace(done,tag=done.tag+1))
                    elif mode == 'active_reset':
                        h.until(lambda: h.owner.matrix_client.state=='wait_result')
                        h.tick(local_reset=True)
                    h.until(lambda: h.owner.ports()['response'] is not None)
                    result=h.tick(response_ready=True)['response']
                report=capture.report()
                if mode=='offdiagonal_inf':
                    self.assertIsNone(result.status)
                    self.assertEqual(report['status'],'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
                else:
                    self.assertIsNotNone(result.status)
                    self.assertEqual(report['status'],'INCOMPLETE')

    def test_source_loaded_code_and_existing_tracer_fail_closed_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in o.PINS:
                dst = Path(tmp)/path
                dst.parent.mkdir(parents=True,exist_ok=True)
                dst.write_bytes((ROOT/path).read_bytes())
            self.assertEqual(o.verify_sources(tmp),o.PINS)
            (Path(tmp)/o.OWNER).write_text('# changed\n')
            with self.assertRaisesRegex(ValueError,'source drift'):
                o.verify_sources(tmp)
        h, _, _ = a.make_harness()
        h.owner._attention = types.MethodType(lambda self,job: None,h.owner)
        with self.assertRaisesRegex(ValueError,'patched.*_attention'):
            o.AttentionObservation(h.owner)
        h, _, _ = a.make_harness()
        capture = o.AttentionObservation(h.owner)
        def existing(frame,event,arg):
            return None
        sys.settrace(existing)
        try:
            with self.assertRaisesRegex(ValueError,'existing tracer'):
                capture.__enter__()
            self.assertIs(sys.gettrace(),existing)
        finally:
            sys.settrace(None)
        self.assertEqual(h.owner.state,'idle')

    def test_v2_execution_inventory_replaces_only_two_exact_historical_sources(self):
        frozen = json.loads((ROOT / o.RECEIPT).read_bytes())['source_sha256']
        current = o.verify_execution_sources()
        self.assertEqual(set(current), set(frozen))
        self.assertEqual(len(current), 75)
        changed = {name for name in current if current[name] != frozen[name]}
        self.assertEqual(changed, set(o.EXECUTION_SOURCE_REPLACEMENTS))
        self.assertEqual(len(changed), 2)
        for name, (previous, successor) in o.EXECUTION_SOURCE_REPLACEMENTS.items():
            self.assertEqual(frozen[name], previous)
            self.assertEqual(current[name], successor)
        for name, digest in o.PINS.items():
            self.assertEqual(current[name], digest)
        self.assertEqual(hashlib.sha256((ROOT / o.RECEIPT).read_bytes()).hexdigest(), o.RECEIPT_SHA)

    def test_missing_extra_or_third_execution_source_replacement_is_rejected(self):
        good = o.EXECUTION_SOURCE_REPLACEMENTS
        missing = dict(good)
        del missing[next(iter(missing))]
        frozen = json.loads((ROOT / o.RECEIPT).read_bytes())['source_sha256']
        for changed in (missing, dict(good, **{'unreviewed.py': ('a'*64, 'b'*64)}),
                        {**good, o.OWNER: (frozen[o.OWNER], '0'*64)}):
            with self.subTest(keys=tuple(changed)), patch.object(o, 'EXECUTION_SOURCE_REPLACEMENTS', changed):
                with self.assertRaisesRegex(ValueError, 'replacement closure'):
                    o.verify_execution_sources()
        name = next(iter(good))
        for replacement, message in ((('0'*64, good[name][1]), 'replacement origin'),
                                     ((good[name][0], good[name][0]), 'replacement origin'),
                                     ((good[name][0], '0'*64), 'source identity mismatch')):
            with patch.object(o, 'EXECUTION_SOURCE_REPLACEMENTS', {**good, name: replacement}):
                with self.assertRaisesRegex(ValueError, message):
                    o.verify_execution_sources()

    def test_runtime_execution_rejects_third_source_drift_missing_file_and_receipt_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (*o.verify_execution_sources(), o.RECEIPT):
                dst = root / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes((ROOT / name).read_bytes())
            self.assertEqual(o.verify_execution_sources(root), o.verify_execution_sources())
            # A source outside the two reviewed replacements remains guarded.
            name = 'candidates/qwen2_resident_matrix/ffn_public/fullgraph_execution.py'
            original = (root / name).read_bytes()
            (root / name).write_bytes(original + b'\n# unreviewed drift\n')
            with self.assertRaisesRegex(ValueError, 'execution source drift'):
                o.verify_execution_sources(root)
            (root / name).unlink()
            with self.assertRaises(FileNotFoundError):
                o.verify_execution_sources(root)
            (root / name).write_bytes(original)
            frozen = json.loads((root / o.RECEIPT).read_bytes())
            missing = dict(frozen['source_sha256'])
            del missing[name]
            for sources in (missing, {**frozen['source_sha256'], 'extra.py': '0'*64},
                            o.verify_execution_sources()):
                (root / o.RECEIPT).write_text(json.dumps({**frozen, 'source_sha256': sources}))
                with self.assertRaisesRegex(ValueError, 'frozen execution-source inventory changed'):
                    o.verify_execution_sources(root)

    def test_loaded_arithmetic_alias_instance_and_type_guards(self):
        from candidates.qwen2_resident_matrix.ffn_attention import attention_owner, scalar_recipe
        h, _, _ = a.make_harness()
        with patch.object(attention_owner,'exp_negative',lambda *args: 0):
            with self.assertRaisesRegex(ValueError,'import changed'):
                o.AttentionObservation(h.owner)
        with patch.object(h.owner.scalar,'op',lambda *args: 0):
            with self.assertRaisesRegex(ValueError,'instance method'):
                o.AttentionObservation(h.owner)
        with patch.object(scalar_recipe,'EXP_COEFFICIENTS',(0,)*8):
            with self.assertRaisesRegex(ValueError,'constant changed'):
                o.AttentionObservation(h.owner)
        method=attention_owner.AttentionOwner._op
        with patch.object(method,'__kwdefaults__',{'policy':'vector'}):
            with self.assertRaisesRegex(ValueError,'defaults/globals changed'):
                o.AttentionObservation(h.owner)
        capture=o.AttentionObservation(h.owner)
        with patch.object(scalar_recipe,'exp_negative',lambda *args: 0):
            with self.assertRaisesRegex(ValueError,'changed'):
                capture.__enter__()
        self.assertIsNone(sys.gettrace())

    def test_exact_causal_mask_and_per_coordinate_frequency_are_required(self):
        _,_,_,_,_,capture=execute(True)
        field=capture.fields['scores']
        # Keep global counts and payload values; move one valid coordinate to
        # the uncomputed upper triangle. Aggregate counts alone cannot catch it.
        field['words'][1]=field['words'][0]
        field['observed'][1],field['observed'][0]=1,0
        field['frequency'][1],field['frequency'][0]=1,0
        field['words'][0]=o.SENTINEL
        self.assertEqual(capture.report()['status'],'INCOMPLETE')

    def test_cross_thread_entry_never_installs_a_tracer(self):
        import threading
        h,_,_=a.make_harness()
        capture=o.AttentionObservation(h.owner)
        result=[]
        def enter():
            try:
                capture.__enter__()
            except ValueError as error:
                result.append((str(error),sys.gettrace()))
        thread=threading.Thread(target=enter)
        thread.start();thread.join()
        self.assertEqual(result,[('observation thread changed',None)])

    def test_exception_and_trace_replacement_leave_capture_incomplete(self):
        h, _, _ = a.make_harness()
        with self.assertRaisesRegex(RuntimeError,'driver stopped'):
            with o.AttentionObservation(h.owner) as capture:
                raise RuntimeError('driver stopped')
        self.assertIsNone(sys.gettrace())
        self.assertEqual(capture.report()['status'],'INCOMPLETE')
        self.assertIn('exception',capture.report()['observer_error'])
        h, _, _ = a.make_harness()
        with o.AttentionObservation(h.owner) as capture:
            sys.settrace(None)
        self.assertIn('replaced',capture.report()['observer_error'])


if __name__ == '__main__':
    unittest.main()
