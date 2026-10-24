"""Bounded control/client integration tests, NOT numeric/native/RTL evidence.

Run with Python or Python -O and required --source-root RAW_CHECKOUT. Production PackedClient and
LegacyMatrixClient definition ASTs execute unchanged; only their shared service
is the explicitly synthetic ScriptedService test fixture. All checks survive -O.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from routing_test_support import (EXTRACTED, HERE, SOURCE_PACKAGE, SOURCE_ROOT, RoutedScriptedService,
    client, deliver, drive_owner, expose, full_qk, load_owner_modules, load_routing,
    make_owner, matrix, need, pv, qk, ScalarControlAdapter)


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routing = load_routing()

    def setUp(self):
        self.service = RoutedScriptedService()
        self.owner = self.service.owner = SimpleNamespace(
            packed_schedule=SimpleNamespace(active_qk_keys=3), useful_macs=0)
        self.router = self.routing.Qk16LegacyPvClient(self.service, self.owner)

    def reject_without_service_change(self, request):
        before = (self.service.group, self.service.result, self.service._done,
                  tuple(self.service.events), self.service.legacy_reply,
                  self.service.counts['normal_steps'], self.service.counts['normal_groups'])
        with self.assertRaises(matrix.MatrixProtocolError):
            self.router.tick(request=request)
        after = (self.service.group, self.service.result, self.service._done,
                 tuple(self.service.events), self.service.legacy_reply,
                 self.service.counts['normal_steps'], self.service.counts['normal_groups'])
        self.assertEqual(before, after)

    def retire_qk(self, result):
        retired = deliver(self.router, client.PackedConsumerAck(result.tag))
        self.assertIs(type(retired), client.PackedRetired)
        self.assertEqual(retired.tag, result.tag)
        self.assertTrue(self.router.drained)
        return retired

    def test_qk_final_only_legacy_each_key_then_next_qk_one_service(self):
        identity = self.service.resource_address
        result = full_qk(self.router)
        self.assertIs(type(result), client.PackedResult)
        self.assertIs(result.service_result, self.service.result)
        self.assertEqual(len(result.selected), 3 * 16)
        self.assertEqual(self.service.counts['normal_steps'], 8)
        self.assertEqual(self.service.counts['normal_results'], 0)
        self.assertEqual([step.emit for step in self.service.steps], [False] * 7 + [True])
        self.retire_qk(result)
        for index in range(3):
            response = deliver(self.router, pv(index))
            self.assertIs(type(response), matrix.LegacyResult)
            self.assertIsNotNone(response.value)
            self.assertFalse(response.error)
            self.assertEqual(self.service.counts['legacy_replies'], index + 1)
            self.assertEqual(self.router.drained, index == 2)
        next_result = full_qk(self.router)
        self.assertNotEqual(next_result.tag.ticket, result.tag.ticket)
        self.retire_qk(next_result)
        self.assertEqual([(g.opcode, g.profile, g.slice_mask) for g in self.service.groups],
                         [(0x23, 2, 255), (0x24, 0, 1), (0x23, 2, 255)])
        self.assertEqual(self.service.step_profiles, [2] * 8 + [0] * 3 + [2] * 8)
        self.assertEqual(self.service.counts['normal_groups'], 3)
        self.assertEqual(self.service.counts['normal_steps'], 19)
        self.assertEqual(self.service.counts['normal_results'], 5)
        self.assertEqual(self.service.counts['normal_done'], 3)
        self.assertEqual(self.service.counts['owner_acquires'], 1)
        self.assertEqual(self.service.counts['owner_releases'], 0)
        self.assertEqual(self.service.resource_address, identity)
        self.assertTrue(all(event[-1] == identity for event in self.service.events if event[0] == 'group'))
        # Source-useful lane accounting, NOT a fabricated native FMA counter.
        self.assertEqual(len(result.selected) * 8 + 3 * 16, 432)
        self.assertEqual(self.owner.useful_macs, 2 * 3 * 128)
        self.assertIs(self.router.packed.service, self.service)
        self.assertIs(self.router.legacy.service, self.service)
        self.assertIs(type(self.router.packed), client.PackedClient)
        self.assertIs(type(self.router.legacy), matrix.LegacyMatrixClient)
        self.assertEqual(self.service.lib.matrix_normal_fmas(), 0)
        self.service.retire_owner_response(self.owner)
        self.service.release(self.owner)
        self.assertEqual(self.service.counts['owner_releases'], 1)

    def test_packed_switch_rejected_between_nonfinal_steps(self):
        result = deliver(self.router, qk(0))
        self.assertIs(type(result), client.PackedStepAccepted)
        self.assertFalse(self.router.drained)
        self.reject_without_service_change(pv())
        self.assertEqual(self.service.counts['normal_steps'], 1)

    def test_switch_fenced_before_result_done_and_owner_facing_retired(self):
        result = full_qk(self.router, held=True)
        self.reject_without_service_change(pv())
        self.assertTrue(self.router.tick(result_ready=True)['result_fire'])
        self.reject_without_service_change(pv())
        self.assertTrue(self.router.tick(request=client.PackedConsumerAck(result.tag))['request_fire'])
        self.reject_without_service_change(pv())
        self.assertTrue(self.router.tick(service_done_ready=False)['service_result_fire'])
        self.assertIsNone(self.service.result)
        self.assertIsNotNone(self.service.done)
        self.reject_without_service_change(pv())
        self.assertFalse(self.router.tick(service_done_ready=False)['service_done_fire'])
        self.assertTrue(self.router.tick()['service_done_fire'])
        self.assertIs(type(self.router.ports()['result']), client.PackedRetired)
        self.assertFalse(self.router.drained)
        self.reject_without_service_change(pv())
        self.assertTrue(self.router.tick(result_ready=True)['result_fire'])
        self.assertTrue(self.router.drained)
        self.assertTrue(self.router.tick(request=pv())['request_fire'])

    def test_held_packed_payload_is_stable_under_backpressure(self):
        result = full_qk(self.router, held=True)
        raw = result.value.raw
        for _ in range(5):
            p = self.router.tick(result_ready=False)
            self.assertIs(p['result'], result)
            self.assertIs(self.router.ports()['result'], result)
            self.assertIs(self.service.result, result.service_result)
            self.assertEqual(result.value.raw, raw)
            self.assertFalse(p['result_fire'])
            self.assertFalse(p['service_result_fire'])
        self.assertEqual(self.service.counts['normal_results'], 0)

    def test_legacy_active_group_cannot_switch_to_qk(self):
        first = deliver(self.router, pv(0))
        self.assertIs(type(first), matrix.LegacyResult)
        self.assertFalse(self.router.drained)
        self.reject_without_service_change(qk())
        deliver(self.router, pv(1))
        self.reject_without_service_change(qk())
        last = expose(self.router, pv(2))
        self.assertIsNone(self.service.group)
        self.assertIsNone(self.service.result)
        self.assertIsNotNone(self.service.legacy_reply)
        self.assertIs(type(last), matrix.LegacyResult)
        self.reject_without_service_change(qk())
        for _ in range(4):
            p = self.router.tick()
            self.assertIs(p['result'], last)
            self.assertFalse(p['result_fire'])
        self.assertTrue(self.router.tick(result_ready=True)['result_fire'])
        self.assertTrue(self.router.drained)
        self.assertTrue(self.router.tick(request=qk())['request_fire'])

    def test_legacy_final_waits_for_done_before_visible_reply(self):
        self.assertTrue(self.router.tick(request=pv(0, 1))['request_fire'])
        for _ in range(12):
            p = self.router.tick(result_ready=True, service_done_ready=False)
            self.assertFalse(p['result_fire'])
            self.assertIsNone(self.router.ports()['result'])
        self.assertIsNone(self.service.result)
        self.assertIsNotNone(self.service.done)
        self.assertEqual(self.service.counts['normal_results'], 1)
        self.assertEqual(self.service.counts['normal_done'], 0)
        self.reject_without_service_change(qk())
        self.assertTrue(self.router.tick()['service_done_fire'])
        self.assertFalse(self.router.drained)
        self.assertTrue(self.router.tick(result_ready=True)['result_fire'])
        self.assertTrue(self.router.drained)

    def test_omitted_packed_consumer_ack_never_retires_or_switches(self):
        result = full_qk(self.router)
        for _ in range(6):
            p = self.router.tick(result_ready=True)
            self.assertFalse(p['service_result_fire'])
            self.assertFalse(p['service_done_fire'])
            self.assertIs(self.service.result, result.service_result)
            self.assertFalse(self.router.drained)
        self.reject_without_service_change(pv())
        self.assertEqual(self.service.counts['normal_results'], 0)

    def test_omitted_done_never_manufactures_owner_completion(self):
        result = full_qk(self.router)
        self.service.suppress_done = True
        self.router.tick(request=client.PackedConsumerAck(result.tag))
        self.assertTrue(self.router.tick()['service_result_fire'])
        for _ in range(6):
            p = self.router.tick(result_ready=True)
            self.assertFalse(p['result_fire'])
            self.assertFalse(p['service_done_fire'])
            self.assertFalse(self.router.drained)
        self.reject_without_service_change(pv())
        self.assertEqual(self.service.counts['normal_done'], 0)
        self.service.suppress_done = False
        self.assertTrue(self.router.tick()['service_done_fire'])
        self.assertTrue(self.router.tick(result_ready=True)['result_fire'])
        self.assertTrue(self.router.drained)

    def test_duplicate_packed_consumer_completion_is_rejected(self):
        result = full_qk(self.router)
        ack = client.PackedConsumerAck(result.tag)
        self.assertTrue(self.router.tick(request=ack)['request_fire'])
        self.reject_without_service_change(ack)
        self.router.tick()
        self.router.tick()
        self.router.tick(result_ready=True)
        self.reject_without_service_change(ack)
        self.assertEqual(self.service.counts['normal_results'], 1)
        self.assertEqual(self.service.counts['normal_done'], 1)

    def test_foreign_and_stale_consumer_ack_cannot_discharge_current_result(self):
        result = full_qk(self.router)
        for field in ('owner_tag', 'group', 'ticket', 'epoch'):
            with self.subTest(field=field):
                bad = replace(result.tag, **{field: getattr(result.tag, field) + 1})
                self.reject_without_service_change(client.PackedConsumerAck(bad))
                self.assertIs(self.service.result, result.service_result)
        self.retire_qk(result)
        deliver(self.router, pv(0, 1))
        next_result = full_qk(self.router)
        self.reject_without_service_change(client.PackedConsumerAck(result.tag))
        self.assertIs(self.service.result, next_result.service_result)
        self.retire_qk(next_result)

    def test_foreign_done_cannot_complete_or_switch(self):
        result = full_qk(self.router)
        self.router.tick(request=client.PackedConsumerAck(result.tag))
        self.router.tick()
        done = self.service.done
        for field in ('tag', 'ticket', 'epoch'):
            with self.subTest(field=field):
                with self.assertRaises(matrix.MatrixProtocolError):
                    self.router.tick(done_override=replace(done, **{field: getattr(done, field) + 1}))
                self.assertIs(self.service.done, done)
                self.assertEqual(self.service.counts['normal_done'], 0)
                self.reject_without_service_change(pv())

    def test_write_debt_proxies_gate_retirement_and_foreign_ack(self):
        result = full_qk(self.router)
        tag = client.PackedWriteTag(result.tag, 'output', 0x40000, 0, 1)
        self.router.register_write(tag)
        self.assertEqual(self.router.ports()['write_debts'], 1)
        self.assertEqual(self.router.held_tag, result.tag)
        for bad in (replace(tag, bank='foreign'), replace(tag, generation=1),
                    replace(tag, address=0x40040), replace(tag, serial=2)):
            with self.assertRaises(matrix.MatrixProtocolError):
                self.router.commit_write(client.PackedWriteAck(bad))
            self.assertEqual(self.router.ports()['write_debts'], 1)
        self.assertFalse(self.router.tick(request=client.PackedConsumerAck(result.tag))['request_fire'])
        self.reject_without_service_change(pv())
        self.assertTrue(self.router.commit_write(client.PackedWriteAck(tag)))
        with self.assertRaises(matrix.MatrixProtocolError):
            self.router.commit_write(client.PackedWriteAck(tag))
        self.retire_qk(result)
        self.assertEqual(self.service.counts['packed_write_debts'], 1)
        self.assertEqual(self.service.counts['packed_write_acks'], 1)

    def test_request_branch_is_exact_and_no_packed_pv_is_admitted(self):
        for bad in (replace(qk(), opcode=0x24, steps=1, last=True, slice_mask=15),
                    replace(pv(), opcode=0x23), object()):
            with self.subTest(request=type(bad).__name__):
                self.reject_without_service_change(bad)
                self.assertEqual(self.service.counts['normal_groups'], 0)
        class ForeignPacked(client.PackedRequest):
            pass
        self.reject_without_service_change(ForeignPacked(**vars(qk())))
        class ForeignLegacy(matrix.LegacyRequest):
            pass
        self.reject_without_service_change(ForeignLegacy(**vars(pv())))

    def test_stale_ack_while_legacy_active_is_not_a_branch_change(self):
        result = full_qk(self.router)
        self.retire_qk(result)
        deliver(self.router, pv(0))
        self.reject_without_service_change(client.PackedConsumerAck(result.tag))
        self.assertEqual(self.service.counts['normal_done'], 1)
        self.assertEqual(self.service.counts['legacy_replies'], 1)
        deliver(self.router, pv(1))
        deliver(self.router, pv(2))
        self.assertTrue(self.router.drained)

    def test_resource_or_acquisition_change_rejected_for_either_branch(self):
        for legacy in (False, True):
            for field in ('resource_address', 'owner_tag'):
                with self.subTest(legacy=legacy, field=field):
                    self.setUp()
                    if legacy:
                        deliver(self.router, pv(0))
                    old = getattr(self.service, field)
                    setattr(self.service, field, old + 1)
                    with self.assertRaises(matrix.MatrixProtocolError):
                        self.router.tick(request=pv(1) if legacy else qk())
                    setattr(self.service, field, old)
            self.setUp()
            if legacy:
                deliver(self.router, pv(0))
            self.service.counts['owner_acquires'] += 1
            with self.assertRaises(matrix.MatrixProtocolError):
                self.router.tick(request=pv(1) if legacy else qk())

    def test_accepted_qk_useful_work_is_retained_after_abort(self):
        result = deliver(self.router, qk(0))
        self.assertIs(type(result), client.PackedStepAccepted)
        self.assertEqual(self.owner.useful_macs, 3 * 16)
        self.assertEqual(self.service.counts['normal_steps'], 1)
        p = self.router.tick(abort=True, result_ready=True)
        self.assertTrue(p['service_done_fire'])
        self.assertTrue(self.router.drained)
        self.assertTrue(self.router.ports()['reset_required'])
        self.assertEqual(self.owner.useful_macs, 3 * 16)
        self.assertEqual(self.service.counts['normal_results'], 0)
        self.assertEqual(self.service.counts['aborts'], 1)
        self.reject_without_service_change(pv())

    def test_qk_key_count_requires_canonical_one_through_sixteen(self):
        for count in (False, True, 0, 17, -1, 1.0):
            with self.subTest(count=count):
                self.setUp()
                self.owner.packed_schedule.active_qk_keys = count
                self.reject_without_service_change(qk())
                self.assertEqual(self.owner.useful_macs, 0)
                self.assertEqual(self.service.counts['normal_steps'], 0)

    def test_duplicate_legacy_reply_and_owner_release_are_not_accepted(self):
        response = deliver(self.router, pv(0, 1))
        with self.assertRaises(matrix.MatrixProtocolError):
            self.service.retire_legacy_reply(self.owner, response.ticket, response.epoch)
        with self.assertRaises(matrix.MatrixProtocolError):
            self.service.release(self.owner)
        self.assertEqual(self.service.counts['owner_releases'], 0)
        self.service.retire_owner_response(self.owner)
        with self.assertRaises(matrix.MatrixProtocolError):
            self.service.retire_owner_response(self.owner)
        self.service.release(self.owner)
        with self.assertRaises(matrix.MatrixProtocolError):
            self.service.release(self.owner)
        self.assertEqual(self.service.counts['owner_acquires'], 1)
        self.assertEqual(self.service.counts['owner_releases'], 1)

    def test_fixture_client_definitions_remain_snapshot_bound_and_stdlib_only(self):
        snapshot = json.loads((HERE / 'INPUT_PINS.json').read_text())
        for relative in ('ffn_attention/matrix_service.py', 'attention_packed_owner/client.py',
                         'attention_packed_owner/test_client.py',
                         'ffn_public/prefix_arithmetic.py', 'ffn_public/prefix_owners.py',
                         'ffn_attention/attention_owner.py', 'ffn_attention/scalar_recipe.py',
                         'official_bf16/owners.py', 'attention_packed_owner/protocol.py'):
            source = SOURCE_PACKAGE / relative
            expected = snapshot['sources']['candidates/qwen2_resident_matrix/' + relative]['sha256']
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected)
            if relative in EXTRACTED:
                self.assertTrue(EXTRACTED[relative]['unchanged_definition_asts'])
        patch_relative = 'candidates/qwen2_resident_matrix/attention_packed_owner/owner.patch'
        self.assertEqual(hashlib.sha256((SOURCE_ROOT / patch_relative).read_bytes()).hexdigest(),
                         snapshot['sources'][patch_relative]['sha256'])
        self.assertNotIn('numpy', sys.modules)
        self.assertNotIn('ctypes', sys.modules)
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('MatrixService', vars(matrix))


class ComposedOwnerTests(unittest.TestCase):
    def test_actual_official_owner_tick_m1_m2_synthetic_control(self):
        for m in (1, 2):
            with self.subTest(m=m):
                modules, service, scalar, owner, job = make_owner(m)
                result = drive_owner(owner, job)
                pairs = m * (m + 1) // 2
                self.assertIs(modules.official.OfficialAttentionOwner.tick,
                              modules.attention.AttentionOwner.tick)
                self.assertEqual(result.response.status, None)
                self.assertEqual(result.response.tag, job.tag)
                self.assertEqual(result.response.write_bytes, m * 6144)
                self.assertEqual(result.response.useful_macs, 12 * pairs * 256)
                self.assertEqual(result.response.executed_macs, 0)
                self.assertEqual(owner.counts['job_fire'], 1)
                self.assertEqual(owner.counts['owner_results'], 1)
                self.assertEqual(owner.counts['matrix_requests'], 96 * m + 12 * m + 96 * pairs)
                self.assertEqual(owner.counts['packed_nonfinal_accept_completions'], 84 * m)
                self.assertEqual(owner.counts['packed_consumer_retirements'], 12 * m)
                self.assertEqual(owner.counts['matrix_results'], 12 * m + 96 * pairs)
                self.assertEqual(owner.counts['write_requests'], 96 * m)
                self.assertEqual(owner.counts['write_acks'], 96 * m)
                self.assertEqual(service.counts['normal_groups'], 108 * m)
                self.assertEqual(service.counts['normal_done'], 108 * m)
                self.assertEqual(service.counts['normal_steps'], 96 * m + 96 * pairs)
                self.assertEqual(service.counts['normal_results'], 12 * m + 96 * pairs)
                self.assertEqual(service.counts['legacy_replies'], 96 * pairs)
                self.assertEqual(service.counts['owner_acquires'], 1)
                self.assertEqual(service.counts['owner_responses'], 1)
                self.assertEqual(service.counts['owner_releases'], 1)
                self.assertEqual(scalar.acquisitions, 1)
                self.assertEqual(scalar.releases, 1)
                self.assertEqual(len(result.writes), 96 * m)
                self.assertEqual(len({q.tag for q in result.writes}), 96 * m)
                self.assertEqual(sorted(q.address for q in result.writes),
                                 list(range(job.dst, job.dst + job.write_bytes, 64)))
                self.assertTrue(all(q.data == bytes(64) for q in result.writes))
                self.assertTrue(all(g.profile == 2 and g.opcode == 0x23 and g.slice_mask == 255
                                    or g.profile == 0 and g.opcode == 0x24 and g.slice_mask == 1
                                    for g in service.groups))
                self.assertTrue(all(event[-1] == service.resource_address
                                    for event in service.events if event[0] == 'group'))
                self.assertIsNone(service.owner)
                self.assertIsNone(scalar.client)
                self.assertEqual(owner.state, 'idle')

    def test_actual_owner_terminal_backpressure_does_not_release_service_early(self):
        modules, service, scalar, owner, job = make_owner(1)
        result = drive_owner(owner, job, terminal_ready=False)
        held = result.response
        router = owner.matrix_client
        self.assertIs(type(router), modules.routing.Qk16LegacyPvClient)
        self.assertIs(router.service, service)
        self.assertIs(router.packed.service, service)
        self.assertIs(router.legacy.service, service)
        self.assertTrue(router.drained)
        self.assertEqual(service.counts['owner_releases'], 0)
        self.assertEqual(service.counts['owner_responses'], 0)
        for _ in range(5):
            p = owner.tick(response_ready=False)
            self.assertIs(p['response'], held)
            self.assertFalse(p['response_fire'])
            self.assertIs(service.owner, owner)
            self.assertEqual(service.counts['owner_releases'], 0)
        self.assertTrue(owner.tick(response_ready=True)['response_fire'])
        self.assertEqual(service.counts['owner_responses'], 1)
        self.assertEqual(service.counts['owner_releases'], 1)
        self.assertFalse(owner.tick(response_ready=True)['response_fire'])
        self.assertEqual(service.counts['owner_releases'], 1)

    def test_actual_owner_nonfinite_selected_result_drains_retains_accepted_work(self):
        _, service, scalar, owner, job = make_owner(1)
        service.words = {0: 0x7fc12345}
        result = drive_owner(owner, job)
        self.assertEqual(result.response.status, 'Numerical')
        self.assertEqual(result.response.useful_macs, 128)
        self.assertEqual(result.response.executed_macs, 0)
        self.assertEqual(result.response.write_bytes, 0)
        self.assertEqual(result.writes, [])
        self.assertEqual(service.counts['normal_steps'], 8)
        self.assertEqual(service.counts['normal_results'], 1)
        self.assertEqual(service.counts['normal_done'], 1)
        self.assertEqual(service.counts['legacy_replies'], 0)
        self.assertEqual(service.counts['aborts'], 1)
        self.assertEqual(service.counts['owner_acquires'], 1)
        self.assertEqual(service.counts['owner_releases'], 1)
        self.assertEqual(owner.counts['packed_consumer_retirements'], 0)
        self.assertEqual(owner.state, 'locked')
        self.assertIsNone(scalar.client)

    def test_selected_admission_rejects_bad_length_before_resource_acquisition(self):
        for length in (0, 129, True, 1.0):
            with self.subTest(length=length):
                _, service, scalar, owner, job = make_owner(1)
                owner.max_tokens = 1024
                self.assertTrue(owner.tick(job=replace(job, m=length))['job_fire'])
                self.assertEqual(owner.state, 'finish')
                self.assertEqual(owner.result.status, 'Bounds')
                self.assertEqual(service.counts['owner_acquires'], 0)
                self.assertEqual(scalar.acquisitions, 0)
                self.assertEqual(service.counts['normal_steps'], 0)
                self.assertIsNone(owner.matrix_client)
                self.assertTrue(owner.tick(response_ready=True)['response_fire'])
                self.assertEqual(service.counts['owner_releases'], 0)

    def test_explicit_entry_only_installs_on_exact_idle_original_owner(self):
        modules, service, _, owner, _ = make_owner(1, schedule=False)
        schedule = modules.entry.install(owner)
        self.assertIs(type(schedule), modules.selected.ProductionQk16Schedule)
        self.assertIs(owner.packed_schedule, schedule)
        self.assertIs(schedule.owner, owner)
        self.assertEqual(service.counts['owner_acquires'], 0)
        with self.assertRaises(ValueError):
            modules.entry.install(owner)
        with self.assertRaises(ValueError):
            modules.entry.authorize_full_numeric()
        modules, _, scalar, owner, _ = make_owner(1, schedule=False)
        base_owner = modules.attention.AttentionOwner(owner.matrix, scalar, max_tokens=128)
        with self.assertRaises(ValueError):
            modules.entry.install(base_owner)
        _, service, _, owner, job = make_owner(1, schedule=False)
        self.assertTrue(owner.tick(job=job)['job_fire'])
        with self.assertRaises(ValueError):
            modules.entry.install(owner)
        self.assertIsNone(owner.packed_schedule)
        self.assertEqual(service.counts['owner_acquires'], 1)

    def test_default_owner_keeps_original_1024_capacity(self):
        modules = load_owner_modules()
        service = RoutedScriptedService(acquired=False)
        owner = modules.official.OfficialAttentionOwner(service, ScalarControlAdapter())
        self.assertEqual(owner.max_tokens, 1024)
        self.assertIsNone(owner.packed_schedule)
        job = modules.prefix.Job('Attention', 7, 0x100000, 0x200000, 0x400000,
                                 129, 1536, 128, 129 * 6144, c=0x300000)
        owner._validate(job)
        self.assertEqual(service.counts['owner_acquires'], 0)
        self.assertTrue(owner.tick(job=job)['job_fire'])
        self.assertIs(type(owner.matrix_client), matrix.LegacyMatrixClient)
        self.assertEqual(owner.state, 'issue')
        self.assertEqual(service.counts['owner_acquires'], 1)
        self.assertEqual(service.counts['normal_steps'], 0)

    def test_default_owner_and_old_packed_profile_do_not_opt_in(self):
        modules, service, _, owner, job = make_owner(1, schedule=False)
        self.assertTrue(owner.tick(job=job)['job_fire'])
        self.assertIs(type(owner.matrix_client), matrix.LegacyMatrixClient)
        original = modules.packed_schedule.PackedSchedule()
        legacy_service = RoutedScriptedService()
        old_owner = SimpleNamespace(matrix=legacy_service)
        legacy_service.owner = old_owner
        modules.hooks.install(old_owner, original)
        self.assertIs(type(modules.hooks.client(old_owner)), client.PackedClient)
        class ImplicitSubclass(modules.selected.ProductionQk16Schedule):
            pass
        with self.assertRaises(ValueError):
            modules.hooks.install(SimpleNamespace(), ImplicitSubclass())


if __name__ == '__main__':
    unittest.main(verbosity=2)
