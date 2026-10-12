"""Raw public attention admission/completion controls, with opaque terminals.

These tests perform no tensor arithmetic and are not full-block numerical
acceptance. They use original Command128/descriptor bytes and the shared typed
reader, including the original 21-command suffix and virtual consumers.
"""
from types import SimpleNamespace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.ffn_public import fixture, model as m


def terminal(job, **changes):
    values = dict(tag=job.tag, status=None, write_bytes=job.write_bytes,
                  useful_macs=17, executed_macs=29)
    values.update(changes)
    return SimpleNamespace(**values)


def launch(rows=16, attention=True, resident=True):
    f = fixture.make_qwen2_21_fixture(rows)
    frontend = m.PublicFrontend(f.memory, f.config)
    host = m.group.HostControl(enabled=resident, legacy_prefix=True, legacy_attention=attention)
    assert frontend.launch(host)
    for pc in range(10):
        host.tick()
        job = host.ports()['ordinary_request']
        assert job is not None and host.pc == pc
        host.tick()
        host.tick(owner_result=terminal(job))
        host.tick(completion_ready=True)
    return f, frontend, host


def mutate_command(f, pc, **changes):
    # Deliberately malformed bytes must reach the actual frontend; the public
    # packer correctly refuses to construct these illegal Command128 objects.
    fields = dict(opcode=(0, 8), flags=(11, 13), event_wait=(24, 16),
                  event_signal=(40, 16), src0=(56, 24), src1=(80, 24), dst=(104, 24))
    word = int.from_bytes(f.commands[pc].to_bytes(), 'little')
    for name, value in changes.items():
        shift, bits = fields[name]
        assert 0 <= value < 1 << bits
        word = (word & ~(((1 << bits) - 1) << shift)) | (value << shift)
    f.memory.write_word(f.config.command, pc, word)


def decode(host):
    for _ in range(256):
        if host.state not in ('decode', 'scan'):
            return
        host.tick()
    raise AssertionError('bounded decode/scan did not terminate')


class AttentionDecodeTests(unittest.TestCase):
    def test_explicit_opt_in_and_parameter_domain(self):
        _, _, host = launch(attention=False)
        decode(host)
        self.assertEqual((host.status, host.jobs, host.completed), ('Unsupported', 10, 10))
        for values in ({'legacy_attention': True}, {'legacy_prefix': True, 'legacy_attention': 1},
                       {'legacy_prefix': True, 'legacy_attention': True, 'profile': 'native'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                m.group.HostControl(**values)

    def test_original_m16_m128_three_command_binding_and_scan(self):
        for rows in (16, 128):
            f, front, host = launch(rows)
            decode(host)
            job = host.ports()['ordinary_request']
            self.assertEqual((host.state, host.status, host.pc), ('issue', None, 12))
            self.assertIsNone(host.ports()['group_request'])
            self.assertEqual((job.kind, job.tag, job.m, job.n, job.k, job.write_bytes),
                             ('Attention', (7 << 16) | 12, rows, 1536, 128, rows * 1536 * 4))
            self.assertEqual((job.a, job.b, job.c, job.dst),
                             tuple(f.specs[n][0] for n in ('q', 'cache_k', 'cache_v', 'att')))
            self.assertFalse(job.weight_bf16 or job.activation_bf16 or job.output_bf16)
            self.assertEqual(host.scanner.trace,
                [(pc, slot, root) for pc, command in enumerate(f.commands)
                 for slot, root in enumerate((command.src0, command.src1, command.dst))
                 if not (pc == 11 and slot == 1)])
            self.assertEqual(len(host.scanner.trace), 62)
            self.assertFalse(any(index == m.NULL for _, index in front.reader.reads))
            self.assertEqual(len(host.virtual), 2)
            self.assertEqual(host.events, set(range(11)))
            self.assertEqual((host.completed, host.jobs), (10, 10))

    def test_result_then_three_held_completions_publish_only_final(self):
        _, _, host = launch()
        decode(host)
        job = host.bound
        for _ in range(3):
            self.assertFalse(host.tick(request_ready=False)['request_fire'])
            self.assertEqual(host.ports()['ordinary_request'], job)
        host.tick()
        self.assertTrue(host.tick(owner_result=terminal(job))['owner_result_fire'])
        before = list(host.published)
        for pc in (10, 11, 12):
            held = host.ports()['completion']
            self.assertEqual(held.pc, pc)
            for _ in range(3):
                self.assertFalse(host.tick()['completion_fire'])
                self.assertEqual(host.ports()['completion'], held)
                self.assertEqual(host.published, before)
            self.assertTrue(host.tick(completion_ready=True)['completion_fire'])
            self.assertIn(pc + 1, host.events)
            if pc < 12:
                self.assertEqual(host.published, before)
        self.assertEqual(host.published[-1], (job.dst, job.dst + job.write_bytes))
        self.assertEqual((host.pc, host.completed, host.jobs), (13, 13, 11))

    def test_complete_original_program_control_only(self):
        _, _, host = launch()
        executed = []
        while host.state != 'finish':
            decode(host)
            self.assertIsNone(host.status, host.reason)
            job = host.bound
            pcs = tuple(range(host.pc - 2, host.pc + 1)) if host.group_commands else (host.pc,)
            executed.append((pcs, job.kind))
            host.tick()
            host.tick(owner_result=terminal(job))
            for pc in pcs:
                self.assertEqual(host.ports()['completion'].pc, pc)
                host.tick(completion_ready=True)
        self.assertEqual(executed, [((10, 11, 12), 'Attention'), ((13,), 'Dense'),
            ((14,), 'Add'), ((15,), 'Norm'), ((16, 17, 18), 'Activation'),
            ((19,), 'Dense'), ((20,), 'Add')])
        self.assertEqual((host.completed, host.jobs), (21, 17))
        self.assertEqual(host.result['completed'], 21)
        self.assertEqual(host.events, set(range(22)))
        for start, end in host.virtual:
            self.assertNotIn((start, end), host.published)

    def test_softmax_null_b_and_consecutive_opcode_order(self):
        for pc, changes in ((11, {'src1': 0}), (10, {'src1': m.NULL}),
                            (11, {'opcode': 0x30}), (12, {'opcode': 0x20})):
            f, _, host = launch()
            mutate_command(f, pc, **changes)
            decode(host)
            self.assertIsNotNone(host.status)
            self.assertEqual((host.jobs, host.completed), (10, 10))
            self.assertNotIn(11, host.events)

    def test_policy_transpose_bits_aux_and_softmax_arity(self):
        for pc, slot, flip in ((10, 3, 1 << (56 + 59)), (10, 3, 1 << (56 + 57)),
                               (12, 3, 1 << (56 + 59)), (10, 4, 1 << 80),
                               (11, 3, 3 << (56 + 16))):
            f, _, host = launch()
            index = f.roots[pc][0] + slot
            word = f.records[index].pack()
            f.memory.write_word(f.config.descriptor, index, word ^ flip)
            decode(host)
            self.assertIsNotNone(host.status)
            self.assertEqual(host.jobs, 10)

    def test_bad_wait_duplicate_signal_and_reserved_bits(self):
        for pc, changes in ((11, {'event_wait': 1}), (12, {'event_signal': 11}),
                            (10, {'event_signal': 10}), (11, {'flags': 1})):
            f, _, host = launch()
            mutate_command(f, pc, **changes)
            decode(host)
            self.assertIsNotNone(host.status)
            self.assertEqual(host.jobs, 10)

    def test_future_virtual_consumer_and_destination_rejected_before_issue(self):
        for slot in ('src0', 'src1', 'dst'):
            for root_pc in (10, 11):
                f, _, host = launch()
                mutate_command(f, 20, **{slot: f.roots[root_pc][2]})
                decode(host)
                self.assertEqual(host.status, 'Dependency', host.reason)
                self.assertEqual((host.jobs, host.virtual), (10, []))

    def test_captured_command_change_during_scan_rejected(self):
        f, _, host = launch()
        host.tick()
        self.assertEqual(host.state, 'scan')
        mutate_command(f, 11, event_signal=23)
        decode(host)
        self.assertEqual(host.status, 'Protocol')
        self.assertEqual((host.jobs, host.virtual), (10, []))

    def test_cache_views_must_be_disjoint(self):
        f, _, host = launch()
        mutate_command(f, 12, src1=f.roots[10][1])
        decode(host)
        self.assertEqual(host.status, 'Permission')
        self.assertEqual(host.jobs, 10)

    def test_terminal_error_tag_bytes_and_poison_publish_nothing(self):
        for changes, poison in (({'status': 'Memory'}, False), ({'tag': 0}, False),
                                ({'write_bytes': 64}, False), ({}, True)):
            _, _, host = launch()
            decode(host)
            job = host.bound
            before = list(host.published)
            host.tick()
            host.tick(owner_result=terminal(job, **changes), reset_required=poison)
            self.assertIsNotNone(host.status)
            self.assertEqual(host.published, before)
            self.assertEqual(host.events, set(range(11)))
            self.assertEqual(host.completed, 10)

    def test_held_success_poison_and_reset_preserve_profile(self):
        _, _, host = launch()
        decode(host)
        host.tick(); host.tick(owner_result=terminal(host.bound))
        edge = host.tick(completion_ready=True, reset_required=True)
        self.assertFalse(edge['completion_fire'])
        self.assertEqual(host.status, 'Protocol')
        self.assertNotIn(11, host.events)
        host.tick(coordinated_reset=m.group.RESET_DOMAIN)
        self.assertTrue(host.legacy_attention and host.legacy_prefix and host.enabled)
        self.assertEqual(host.state, 'idle')

    def test_attention_poison_fence_does_not_depend_on_resident_ffn_option(self):
        _, _, host = launch(resident=False)
        decode(host)
        host.tick(); host.tick(owner_result=terminal(host.bound))
        before = list(host.published)
        edge = host.tick(completion_ready=True, reset_required=True)
        self.assertFalse(edge['completion_fire'])
        self.assertEqual((host.status, host.completed, host.published), ('Protocol', 10, before))
        self.assertNotIn(11, host.events)


if __name__ == '__main__':
    unittest.main()
