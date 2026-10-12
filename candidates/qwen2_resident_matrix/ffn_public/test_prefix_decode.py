"""Public21 prefix decode controls only; injected credits are not arithmetic.

Real tensor execution is exercised by the separate shared-memory prefix gate.
This suite stops before the unimplemented attention group and never marks the
21-command program complete.
"""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import fixture, model as m


def launch(rows=16, *, enabled=True):
    f = fixture.make_qwen2_21_fixture(rows)
    front = m.PublicFrontend(f.memory, f.config)
    host = m.group.HostControl(enabled=True, legacy_prefix=enabled)
    assert front.launch(host)
    return f, front, host


def opaque_terminal(job, **changes):
    values = dict(tag=job.tag, status=None, write_bytes=job.write_bytes,
                  useful_macs=17, executed_macs=29)
    values.update(changes)
    return SimpleNamespace(**values)


class PrefixDecodeTests(unittest.TestCase):
    def test_default_subset_still_rejects_norm(self):
        f, front, host = launch(enabled=False)
        host.tick()
        self.assertEqual(host.status, 'Unsupported')
        self.assertEqual(host.jobs, 0)
        self.assertEqual(host.published, [])

    def test_full_image_prefix_jobs_source_addresses_and_publication(self):
        expected = ['Norm', 'Dense', 'Bias', 'Rope', 'Dense', 'Bias', 'Rope', 'Dense', 'Bias', 'KvAppend']
        for rows in (16, 128):
            with self.subTest(rows=rows):
                f, front, host = launch(rows)
                for pc, kind in enumerate(expected):
                    self.assertEqual(host.pc, pc)
                    host.tick()
                    job = host.ports()['ordinary_request']
                    self.assertIsNotNone(job)
                    op = f.manifest['schedule'][pc]
                    self.assertEqual((job.kind, job.m), (kind, rows))
                    self.assertEqual((job.a, job.b, job.dst), tuple(f.specs[op[key]][0] for key in ('a', 'b', 'dst')))
                    self.assertEqual(job.k, f.specs[op['a']][1][1])
                    self.assertEqual(job.n, 256 if kind == 'KvAppend' else f.specs[op['dst']][1][1])
                    self.assertEqual(job.weight_bf16, kind == 'Dense')
                    self.assertEqual(getattr(job, 'c', 0), job.b + 1024 * 64 * 4 if kind == 'Rope' else 0)
                    for _ in range(2):
                        self.assertFalse(host.tick(request_ready=False)['request_fire'])
                        self.assertEqual(host.ports()['ordinary_request'], job)
                    self.assertTrue(host.tick()['request_fire'])
                    self.assertTrue(host.tick(owner_result=opaque_terminal(job))['owner_result_fire'])
                    before = list(host.published)
                    for _ in range(2):
                        self.assertFalse(host.tick()['completion_fire'])
                        self.assertEqual(host.published, before)
                        self.assertNotIn(pc + 1, host.events)
                    edge = host.tick(completion_ready=True)
                    self.assertTrue(edge['completion_fire'])
                    self.assertEqual(edge['completion'].pc, pc)
                    self.assertEqual(host.published[-1], (job.dst, job.dst + job.write_bytes))
                self.assertEqual((host.pc, host.completed, host.jobs), (10, 10, 10))
                self.assertEqual(host.state, 'decode')
                self.assertIsNone(host.result)
                self.assertEqual(front.command_reads, list(range(10)))
                self.assertFalse(any(pc == 9 for pc, _ in front.policy_reads))
                self.assertTrue(all(r['physical_bytes'] == 64 for r in front.port.trace))
                host.tick()
                self.assertEqual(host.status, 'Unsupported')  # attention remains an explicit gap
                self.assertEqual(host.completed, 10)

    def test_norm_dtype_and_shape_rejected_before_owner(self):
        for dtype, dims in ((5, (1, 1536, 1, 1)), (7, (1, 1520, 1, 1))):
            f, front, host = launch()
            root = f.roots[0][1]
            address = f.specs['gamma0'][0]
            r = fixture.tensor_base_record(address, dtype=dtype, rank=2, next_index=root + 1)
            f.memory.write_word(f.config.descriptor, root, r.pack())
            shape = fixture.shape4_record(dims, next_index=root + 2)
            stride = fixture.stride3_record((dims[1], 1, 1), next_index=m.NULL)
            f.memory.write_word(f.config.descriptor, root + 1, shape.pack())
            f.memory.write_word(f.config.descriptor, root + 2, stride.pack())
            host.tick()
            self.assertEqual(host.status, 'Unsupported')
            self.assertEqual(host.jobs, 0)

    def test_terminal_tag_bytes_and_same_edge_poison_fail_closed(self):
        for changes, poison in (({'tag': 1}, False), ({'write_bytes': 64}, False), ({}, True)):
            f, front, host = launch()
            host.tick(); job = host.ports()['ordinary_request']; host.tick()
            host.tick(owner_result=opaque_terminal(job, **changes), reset_required=poison)
            self.assertEqual(host.status, 'Protocol')
            self.assertEqual(host.published, [])
            self.assertEqual(host.completed, 0)

    def test_prefix_mode_and_trig_capacity_survive_coordinated_reset(self):
        f, front, host = launch()
        host.tick(); host.tick()
        host.tick(coordinated_reset=m.group.RESET_DOMAIN)
        self.assertTrue(host.legacy_prefix)
        self.assertEqual(host.max_tokens, 1024)
        self.assertTrue(front.launch(host))
        host.tick()
        self.assertEqual(host.ports()['ordinary_request'].kind, 'Norm')

    def test_prefix_mode_rejects_native_extra_root_profile(self):
        with self.assertRaises(ValueError):
            m.group.HostControl(legacy_prefix=True, profile='qwen35_gdn')


if __name__ == '__main__':
    unittest.main()
