"""Small synthetic profiled-observer gates; no builds, weights or M16 replay.

Uses the existing receipt-verified Matrix ELF. One-token Attention demonstrates
unchanged capture/transport; idle and negative cases validate the new closure.
"""
from contextlib import nullcontext
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from . import observation as obs
from . import matrix_binding, profile
from ..official_bf16 import dense_silu, owners
from ..official_bf16.test_owners import verified_library
from ..ffn_public import prefix_arithmetic as fp, prefix_owners as p
from ..ffn_public.test_prefix_owners import Harness


def snapshot():
    sources = obs.base.verify_execution_sources()
    for relative in (*obs.original.REQUIRED_SOURCES,
                     obs.monitoring.MONITORING, *obs.EXTRA_SOURCES):
        sources[relative] = hashlib.sha256((obs.ROOT / relative).read_bytes()).hexdigest()
    return sources


def object_state(instance):
    return {name: (id(value), repr(value)) for name, value in vars(instance).items()}


class ProfiledObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = verified_library()

    def make(self, *, profiled=True):
        self.assertEqual(self.library.td_reset(), 0)
        service = (matrix_binding.ProfiledMatrixService(self.library, replace(profile.QWEN2_QKV_PROFILE))
                   if profiled else dense_silu.OfficialMatrixService(self.library))
        owner = owners.OfficialAttentionOwner(service, fp.ScalarService())
        job = p.Job('Attention', (9 << 16) | 12, 0x100000, 0x200000, 0x400000,
                    1, 1536, 128, 1536 * 4, c=0x200000 + 256 * 4)
        h = Harness(owner)
        for address, count, word in ((job.a, 1536, 0x3e000000),
                                      (job.b, 256, 0x3e800000), (job.c, 256, 0x3f400000)):
            h.bus.input(address, (word,) * count)
        h.bus.output(job.dst, job.write_bytes)
        return h, job

    def capture(self, h):
        return obs.ProfiledAttentionMonitoringObservation(h.owner, source_sha256=snapshot())

    def execute(self, transport=None, *, profiled=True):
        h, job = self.make(profiled=profiled)
        capture = transport(h.owner, source_sha256=snapshot()) if transport else None
        edges = hashlib.sha256()
        with capture if capture else nullcontext():
            for tick in range(12000):
                e = h.tick(job=job if tick == 0 else None, memory_ready=tick % 3 != 0,
                    respond=tick % 5 != 0, matrix_request_ready=tick % 7 != 0,
                    matrix_result_ready=tick % 11 != 0, service_result_ready=tick % 13 != 0,
                    service_done_ready=tick % 17 != 0, response_ready=tick % 19 == 0)
                edges.update(repr(tuple((key, e[key]) for key in sorted(e))).encode())
                if e['response_fire']:
                    self.assertIsNone(e['response'].status)
                    break
            else:
                self.fail('bounded one-token synthetic Attention watchdog')
        return h, job, capture, edges.hexdigest(), tick + 1

    def test_exact_reviewed_constructor_delta_and_inherited_capture_methods(self):
        obs.verify_constructor_delta()
        cls = obs.ProfiledAttentionMonitoringObservation
        parent = obs.monitoring.OfficialAttentionMonitoringObservation
        for name in ('_start', '_line', '_coverage', '_monitor_line', '_monitor_return',
                     '_stop', '_diagnostic_failure', '_put', '_bytes', 'save'):
            self.assertIs(getattr(cls, name), getattr(parent, name), name)
        self.assertEqual(set(name for name, value in vars(cls).items() if callable(value)),
                         {'__init__', '__enter__', '__exit__', 'report'})
        source = (obs.ROOT / obs.ADAPTER).read_text()
        changed = source.replace('self.active = self.closed = self.disarmed = False',
                                 'self.active = self.closed = self.disarmed = True')
        self.assertNotEqual(source, changed)
        real_read = Path.read_text
        def read(path, *args, **kwargs):
            return changed if path == obs.ROOT / obs.ADAPTER else real_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            with self.assertRaisesRegex(ValueError, 'minimal delta'):
                obs.verify_constructor_delta()

    def test_idle_constructor_entry_exit_preserve_owner_and_service_objects(self):
        h, _ = self.make()
        owner, service, scalar = h.owner, h.owner.matrix, h.owner.scalar
        before = tuple(object_state(x) for x in (owner, service, scalar))
        sources = snapshot()
        capture = obs.ProfiledAttentionMonitoringObservation(owner, source_sha256=sources)
        self.assertEqual(before, tuple(object_state(x) for x in (owner, service, scalar)))
        self.assertIs(capture.services[0], service)
        sources[obs.BINDING] = '0' * 64
        self.assertNotEqual(capture.sources[obs.BINDING], sources[obs.BINDING])
        with capture:
            tool = capture.tool_id
            self.assertIs(h.owner, owner)
            self.assertIs(owner.matrix, service)
            self.assertIs(owner.scalar, scalar)
        self.assertEqual(before, tuple(object_state(x) for x in (owner, service, scalar)))
        self.assertIsNone(sys.monitoring.get_tool(tool))
        self.assertEqual(capture.report()['status'], 'INCOMPLETE')
        self.assertGreater(capture.profiled_loaded_functions_checked, capture.loaded_functions_checked)

    def test_one_token_all_edges_capture_fields_and_saved_hashes_match_old(self):
        baseline = self.execute()
        observed = self.execute(obs.ProfiledAttentionMonitoringObservation)
        previous = self.execute(obs.monitoring.OfficialAttentionMonitoringObservation, profiled=False)
        bh, bj, _, bedges, bsteps = baseline
        h, job, capture, edges, steps = observed
        self.assertEqual((edges, steps), (bedges, bsteps))
        self.assertEqual(h.bus.trace, bh.bus.trace)
        self.assertEqual(h.owner.report(), bh.owner.report())
        self.assertEqual(h.owner.matrix.report(), bh.owner.matrix.report())
        self.assertEqual(h.bus.raw(job.dst), bh.bus.raw(bj.dst))
        self.assertEqual(capture.fields, previous[2].fields)
        self.assertEqual((edges, steps), (previous[3], previous[4]))
        report = capture.report()
        self.assertEqual(report['status'], 'COMPLETE_OWNER_OBSERVATION_NOT_NATIVE_ACCEPTED')
        self.assertEqual(report['profiled_observation_source_version'], obs.SOURCE_VERSION)
        self.assertEqual(report['source_version'], obs.CAPTURE_SOURCE_VERSION)
        self.assertEqual(report['helper_source_version'], obs.base.SOURCE_VERSION)
        self.assertFalse(report['prior_observation_results_inherited'])
        self.assertFalse(report['historical_fullgraph']['results_inherited'])
        self.assertEqual(len(report['fields']), 10)
        self.assertEqual(report['matrix_service_type'], 'ProfiledMatrixService')
        self.assertEqual(report['instrumentation_sha256'], snapshot()[obs.ADAPTER])
        self.assertFalse(report['matrix_binary_provenance_verified_by_observer'])
        self.assertFalse(report['hardware_simulation'])
        self.assertFalse(report['physical_publication_observed'])
        for key in ('job', 'terminal', 'accepted_retirement', 'observer_error', 'fields'):
            self.assertEqual(report[key], previous[2].report()[key])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'actual'
            self.assertEqual(capture.save(out), report)
            for name, field in report['fields'].items():
                self.assertEqual(hashlib.sha256((out / (name + '.u32le')).read_bytes()).hexdigest(),
                                 field['raw_sha256'])
                self.assertEqual(hashlib.sha256((out / (name + '.presence')).read_bytes()).hexdigest(),
                                 field['presence_sha256'])

    def test_missing_new_sources_and_drift_rejected_without_owner_mutation(self):
        h, _ = self.make()
        sources = snapshot()
        before = object_state(h.owner), object_state(h.owner.matrix)
        for relative in (*obs.EXTRA_SOURCES, obs.original.HELPER):
            changed = dict(sources)
            changed.pop(relative)
            with self.subTest(missing=relative), self.assertRaisesRegex(ValueError, 'snapshot must include'):
                obs.ProfiledAttentionMonitoringObservation(h.owner, source_sha256=changed)
            changed = dict(sources)
            changed[relative] = '0' * 64
            with self.subTest(drift=relative), self.assertRaisesRegex(ValueError, 'source drift'):
                obs.ProfiledAttentionMonitoringObservation(h.owner, source_sha256=changed)
        self.assertEqual(before, (object_state(h.owner), object_state(h.owner.matrix)))

    def test_exact_service_type_rejects_old_and_subclass_without_spoofing(self):
        h, _ = self.make(profiled=False)
        with self.assertRaisesRegex(ValueError, 'exact ProfiledMatrixService'):
            self.capture(h)
        class UnreviewedService(matrix_binding.ProfiledMatrixService):
            pass
        self.assertEqual(self.library.td_reset(), 0)
        owner = owners.OfficialAttentionOwner(
            UnreviewedService(self.library, profile.QWEN2_QKV_PROFILE), fp.ScalarService())
        with self.assertRaisesRegex(ValueError, 'exact ProfiledMatrixService'):
            obs.ProfiledAttentionMonitoringObservation(owner, source_sha256=snapshot())

    def test_loaded_binding_profile_and_participating_instance_patches_rejected(self):
        h, _ = self.make()
        for target, name, value in (
            (matrix_binding.ProfiledMatrixService, 'dense_library', lambda *args: None),
            (matrix_binding.ProfiledDenseAdapter, 'td_group', lambda *args: 0),
            (profile.ReductionProfile, 'validate', lambda *args: None),
            (profile.ReductionProfile, '__setattr__', lambda *args: None),
            (h.owner.matrix, 'dense_library', lambda *args: None),
            (h.owner, '_attention', lambda *args: None),
            (h.owner.scalar, 'op', lambda *args: 0),
            (obs.base, 'SOURCE_VERSION', 'qwen2-existing-attention-observation-v1'),
            (obs.original, 'SOURCE_VERSION', 'qwen2-official-bf16-attention-observation-v1'),
            (obs, 'CAPTURE_SHA256', '0' * 64),
        ):
            with self.subTest(name=name), patch.object(target, name, value):
                with self.assertRaisesRegex(ValueError, 'changed|patched'):
                    self.capture(h)
        policy = h.owner.matrix.profile
        object.__setattr__(policy, 'validate', lambda *args: None)
        try:
            with self.assertRaisesRegex(ValueError, 'unpatched immutable'):
                self.capture(h)
        finally:
            object.__delattr__(policy, 'validate')

    def test_entry_rechecks_source_and_loaded_code_before_claiming_monitor(self):
        h, _ = self.make()
        c = self.capture(h)
        c.sources[obs.BINDING] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source drift'):
            c.__enter__()
        self.assertIsNone(c.tool_id)
        self.assertFalse(c.active)
        c = self.capture(h)
        with patch.object(matrix_binding.ProfiledDenseAdapter, 'td_step', lambda *args: 0):
            with self.assertRaisesRegex(ValueError, 'changed'):
                c.__enter__()
        self.assertIsNone(c.tool_id)
        self.assertFalse(c.active)

    def test_exit_rechecks_extra_loaded_code_after_inherited_cleanup(self):
        h, _ = self.make()
        c = self.capture(h)
        c.__enter__()
        tool = c.tool_id
        with patch.object(profile.ReductionProfile, 'validate', lambda *args: None):
            with self.assertRaisesRegex(ValueError, 'changed'):
                c.__exit__(None, None, None)
        self.assertIsNone(sys.monitoring.get_tool(tool))
        self.assertIsNone(c.tool_id)
        self.assertFalse(c.active)
        self.assertTrue(c.closed)
        self.assertEqual(c.report()['status'], 'INCOMPLETE')
        self.assertIn('changed', c.report()['observer_error'])


if __name__ == '__main__':
    unittest.main()
