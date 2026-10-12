"""Read-only observation on the original public three-command software path."""
from dataclasses import asdict, replace
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import build_shared_matrix_recipe as build
from scripts import observe_qwen2_attention_model as observation
from candidates.qwen2_resident_matrix.ffn_public import test_fullgraph_execution as original


def setUpModule():
    # Explicit fresh/source-verified shared library; no fallback or skipped gate.
    build.from_environment(ROOT)


def setup():
    return original.setup(str(build.from_environment(ROOT)))


def virtual_pristine(memory):
    result = {}
    for name in ('scores', 'probabilities'):
        region = memory.regions[name]
        assert region['virtual'] and not any(region[k] for k in ('written', 'acked', 'terminal', 'published'))
        raw = bytes(region['data'])
        assert raw == original.p.SENTINEL * (len(raw) // 4)
        result[name] = hashlib.sha256(raw).hexdigest()
    memory.check_coexistence()
    return result


def snapshot(memory, execution):
    # PublicExecution.report exposes live request/completion/publication lists.
    # Freeze the boundary now; a later handshake must not rewrite old evidence.
    return deepcopy(dict(host=execution.report(), memory=memory.report(),
                virtual=virtual_pristine(memory),
                write_records=[(asdict(c) if hasattr(c, '__dataclass_fields__') else vars(c),
                                asdict(a) if hasattr(a, '__dataclass_fields__') else vars(a))
                               for c, a in memory.regions['att']['records']]))


class PublicObservationTests(unittest.TestCase):
    def run_success(self, traced):
        memory, x = setup()
        metadata = {name: hashlib.sha256(memory.raw(region['base'], region['extent'])).hexdigest()
                    for name, region in memory.regions.items()
                    if name in ('command_table', 'descriptor_table')}
        job = x.advance_to_request()['ordinary_request']
        self.assertEqual(job.tag & 0xffff, 2)
        self.assertEqual([int(c.opcode) for c in memory.fixture.commands], [0x23, 0x33, 0x24])
        before = snapshot(memory, x)
        if traced:
            report, capture = observation.execute_public_attention_observed(x, memory, job, final_ack_stall=7)
        else:
            report, capture = original.g.execute_attention_owner(x, memory, job, final_ack_stall=7), None
        checkpoints = [snapshot(memory, x)]
        self.assertEqual(report['accepted']['final_ack_stall'], 7)
        self.assertGreater(report['final_ack_fence']['terminal_tick'], report['final_ack_fence']['final_ack_tick'])
        self.assertEqual(x.host.completed, 0)
        self.assertEqual(x.host.jobs, 1)
        self.assertEqual(x.counts['owner_result_fire'], 1)
        self.assertEqual(x.host.published, [])
        self.assertIsNone(x.launch_result)
        self.assertTrue(memory.regions['att']['terminal'])
        self.assertFalse(memory.regions['att']['published'])
        self.assertIsNone(x.matrix_service.owner)
        with self.assertRaisesRegex(ValueError, 'read before ACK and public publication'):
            memory.read_bytes64(job.dst)
        with self.assertRaisesRegex(ValueError, 'publish before public completion'):
            memory.publish(job, x.host)
        for pc in (0, 1):
            x.publish_completions((pc,), stall_edges=5)
            self.assertEqual(x.host.completed, pc + 1)
            self.assertEqual(x.host.published, [])
            with self.assertRaisesRegex(ValueError, 'publish before public completion'):
                memory.publish(job, x.host)
            with self.assertRaisesRegex(ValueError, 'read before ACK and public publication'):
                memory.read_bytes64(job.dst)
            checkpoints.append(snapshot(memory, x))
        x.publish_completions((2,), stall_edges=5)
        self.assertEqual(x.host.completed, 3)
        self.assertEqual(x.host.published, [(job.dst, job.dst + job.write_bytes)])
        self.assertIsNotNone(x.ports()['launch_result'])
        self.assertIsNone(x.launch_result)  # Offered launch success is not accepted.
        self.assertEqual(x.counts['result_fire'], 0)
        self.assertFalse(memory.regions['att']['published'])
        with self.assertRaisesRegex(ValueError, 'read before ACK and public publication'):
            memory.read_bytes64(job.dst)
        checkpoints.append(snapshot(memory, x))
        memory.publish(job, x.host)
        self.assertEqual(memory.read64(job.dst)[1], (0x3e000000,) * 16)
        self.assertIsNone(x.launch_result)  # Physical publication follows PC2, not finish().
        checkpoints.append(snapshot(memory, x))
        terminal = x.finish(stall_edges=7)
        self.assertEqual((terminal['completed'], terminal['jobs'], terminal['write_bytes']), (3, 1, 6144))
        self.assertEqual(x.counts['completion_fire'], 3)
        self.assertEqual(x.counts['result_fire'], 1)
        self.assertEqual([c['pc'] for c in x.completions], [0, 1, 2])
        self.assertEqual(x.host.events, {0, 1, 2, 3})
        self.assertEqual(x.host.state, 'idle')
        self.assertEqual(x.counts['completion_backpressure_edges'], 15)
        self.assertEqual(x.counts['result_backpressure_edges'], 7)
        checkpoints.append(snapshot(memory, x))
        self.assertEqual(before['host']['completions'], [])
        self.assertEqual(before['host']['published'], [])
        self.assertEqual([len(s['host']['completions']) for s in checkpoints], [0, 1, 2, 3, 3, 3])
        self.assertEqual([bool(s['host']['published']) for s in checkpoints], [False, False, False, True, True, True])
        self.assertEqual([s['memory']['outputs']['att']['published'] for s in checkpoints], [False, False, False, False, True, True])
        self.assertEqual([s['host']['launch_result'] is not None for s in checkpoints], [False, False, False, False, False, True])
        expected = struct.pack('<1536I', *((0x3e000000,) * 768 + (0xbe800000,) * 768))
        self.assertEqual(memory.raw(job.dst, job.write_bytes), expected)
        if capture:
            r = capture.report()
            self.assertEqual(r['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
            self.assertFalse(r['whole_block_terminal_observed'] or r['full_29_node_gate'] or r['hardware_simulation'])
            self.assertEqual(capture._bytes('pv'), expected)
            self.assertEqual(tuple(capture.fields['prob']['words']), (0x3f800000,) * 12)
            self.assertEqual(tuple(capture.fields['scores']['words']), (0,) * 12)
        return dict(before=before, owner=report, checkpoints=checkpoints, metadata=metadata,
                    final=terminal, output_sha256=hashlib.sha256(expected).hexdigest()), capture

    def test_original_public_commands_output_schedule_and_all_publication_fences(self):
        baseline, _ = self.run_success(False)
        traced, capture = self.run_success(True)
        self.assertEqual(traced, baseline)
        out = os.environ.get('QWEN2_PUBLIC_ATTENTION_OBSERVATION_OUT')
        if out:
            destination = Path(out)
            destination.mkdir(parents=True, exist_ok=False)
            capture.save(destination / 'owner')
            receipt = Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT'])
            evidence = dict(schema=1, status='PASS_SYNTHETIC_PUBLIC3_OBSERVATION',
                stimulus='existing M1 public QK/Softmax/PV fixture, synthetic readonly Q/K/V',
                source_sha256={str(p.relative_to(ROOT)): build.sha(p) for p in
                    (Path(__file__), ROOT/'scripts/observe_qwen2_attention_model.py',
                     ROOT/'candidates/qwen2_resident_matrix/ffn_public/test_fullgraph_execution.py')},
                compile_receipt_sha256=build.sha(receipt), library_sha256=build.sha(build.from_environment(ROOT)),
                baseline_equal=True, execution=traced, public_commands=3, actual_owner_jobs=1,
                full_block=False, rtl_executed=False, m128_executed=False,
                native_acceptance='UNCHANGED_FAIL_POLICY_PENDING')
            (destination / 'evidence.json').write_text(json.dumps(evidence, indent=2)+'\n')

    def test_actual_numeric_failure_is_not_a_public_success(self):
        memory, x = setup()
        memory.regions['q']['provider'] = lambda offset: struct.pack('<16I', *((0x00010000,)+(0,)*15 if offset==0 else (0,)*16))
        memory.regions['k']['provider'] = lambda _: struct.pack('<16I', *((0x3f800000,)*16))
        job = x.advance_to_request()['ordinary_request']
        capture = observation.AttentionObservation(x.attention_owner)
        with self.assertRaisesRegex(ValueError, 'Attention owner error'):
            observation.execute_public_attention_observed(x, memory, job, observation=capture)
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        self.assertEqual((x.host.status, x.host.completed, x.host.published), ('Numerical', 0, []))
        self.assertIsNone(x.launch_result)
        self.assertFalse(memory.regions['att']['terminal'] or memory.regions['att']['published'])
        virtual_pristine(memory)

    def test_reset_after_owner_success_cannot_publish_held_public_success(self):
        memory, x = setup()
        job = x.advance_to_request()['ordinary_request']
        _, capture = observation.execute_public_attention_observed(x, memory, job)
        accepted_owner = capture.report()
        x.completion_ready = True
        x.attention_edge(local_reset=True)
        self.assertFalse(x.last_host_edge['completion_fire'])
        self.assertEqual((x.host.status, x.host.completed, x.host.published), ('Protocol', 0, []))
        self.assertIsNone(x.launch_result)
        with self.assertRaisesRegex(ValueError, 'publish before public completion'):
            memory.publish(job, x.host)
        with self.assertRaisesRegex(ValueError, 'read before ACK and public publication'):
            memory.read_bytes64(job.dst)
        # Previously accepted owner evidence is retained; it never claimed a public launch.
        self.assertEqual(capture.report(), accepted_owner)
        virtual_pristine(memory)

    def test_copied_public_job_and_disconnected_memory_remain_pre_dma_rejections(self):
        for case in ('copied', 'memory'):
            with self.subTest(case=case):
                memory, x = setup()
                job = x.advance_to_request()['ordinary_request']
                if case == 'copied':job = replace(job)
                else:x.frontend.port.memory = memory.fixture.memory
                before = memory.report()
                capture = observation.AttentionObservation(x.attention_owner)
                with self.assertRaisesRegex(ValueError, 'original fused public owner job|identical physical map'):
                    observation.execute_public_attention_observed(x, memory, job, observation=capture)
                self.assertEqual(x.host.jobs, 0)
                self.assertEqual(memory.report(), before)
                self.assertEqual(capture.report()['status'], 'INCOMPLETE')

    def test_capture_identity_reuse_and_patched_driver_are_rejected(self):
        memory, x = setup()
        job = x.advance_to_request()['ordinary_request']
        other_memory, other = setup()
        wrong = observation.AttentionObservation(other.attention_owner)
        with self.assertRaisesRegex(ValueError, 'belong to this actual Attention owner'):
            observation.execute_public_attention_observed(x, memory, job, observation=wrong)
        with patch.object(original.g, 'execute_attention_owner', lambda *a, **k: None):
            with self.assertRaisesRegex(ValueError, 'loaded public Attention driver changed'):
                observation.execute_public_attention_observed(x, memory, job)
        self.assertEqual(x.host.jobs, 0)
        _, capture = observation.execute_public_attention_observed(x, memory, job)
        with self.assertRaisesRegex(ValueError, 'single-use'):
            observation.execute_public_attention_observed(x, memory, job, observation=capture)
        self.assertEqual(x.host.jobs, 1)
        self.assertEqual(x.host.completed, 0)
        self.assertIsNone(x.launch_result)


if __name__ == '__main__':
    unittest.main()
