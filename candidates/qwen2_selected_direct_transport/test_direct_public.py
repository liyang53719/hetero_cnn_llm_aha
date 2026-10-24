"""Actual direct-public edges, with explicitly synthetic Host/Dense/arithmetic.

One M2 Attention job is a bounded control regression only. It is not two M1
jobs and not a full block, M128 numeric, native, RTL, or hardware-cycle pass.
"""
from pathlib import Path
import sys

# Explicit sibling support works under -I without adding the source tree to
# sys.path or native-importing any production module prelude.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import direct_test_support as s

from collections import Counter
from dataclasses import replace
import ast
import resource
import subprocess
import tempfile
import unittest
from types import SimpleNamespace


class DirectPublicControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = s.make_case()
        cls.report = s.runtime.direct.run(cls.case.x, cls.case.physical, cls.case.job,
                                         final_ack_stall=5)

    def test_actual_pinned_definitions_without_native_imports(self):
        extracted = s.prior.EXTRACTED
        for path, name in (
                ('ffn_public/execute_numeric.py', 'PublicExecution'),
                ('ffn_public/fullgraph_execution.py', 'execute_attention_owner'),
                ('ffn_public/prefix_execution.py', 'PhysicalMemory'),
                ('ffn_attention/attention_owner.py', 'AttentionOwner'),
                ('official_bf16/owners.py', 'OfficialAttentionOwner'),
                ('production_qk16_model/schedule.py', 'ProductionQk16Schedule'),
                ('production_qk16_model/routing.py', 'Qk16LegacyPvClient')):
            with self.subTest(path=path):
                self.assertTrue(extracted[path]['unchanged_definition_asts'])
                self.assertIn(name, extracted[path]['definitions'])
        self.assertEqual(len(s.PINS['sources']), 51)
        for name in ('numpy', 'torch', 'ctypes'):
            self.assertNotIn(name, sys.modules)
        self.assertIs(type(self.case.host), s.SyntheticHostControl)
        self.assertIs(type(self.case.dense), s.SyntheticIdleDense)
        self.assertIs(type(self.case.physical), s.runtime.physical.PhysicalMemory)
        self.assertIs(type(self.case.owner), s.modules.official.OfficialAttentionOwner)
        self.assertIs(type(self.case.prefix), s.modules.prefix.PrefixOwner)

    def test_one_actual_m2_job_not_two_m1_invocations(self):
        c = self.case
        self.assertEqual(c.job.m, 2)
        self.assertEqual(c.probe.accepted_jobs, [c.job])
        self.assertIs(c.probe.accepted_jobs[0], c.job)
        self.assertEqual((c.x.attention_jobs, c.x.attention_results), (1, 1))
        self.assertEqual((c.host.request_fires, c.host.terminal_fires), (1, 1))
        self.assertEqual(c.owner.counts['job_fire'], 1)
        self.assertEqual(c.owner.counts['owner_results'], 1)
        self.assertEqual(c.owner.peak_score_words, 2)
        self.assertEqual(c.owner.peak_probability_words, 2)
        self.assertEqual(c.dense.clock, c.owner.clock)
        self.assertEqual(c.host.ticks, c.owner.clock)
        self.assertEqual(c.x.counts['request_fire'], 1)
        self.assertEqual(c.x.counts['owner_result_fire'], 1)
        self.assertTrue(self.report['backend']['synthetic_shape'])
        self.assertIsNone(self.report['backend']['fullgraph_profile'])
        self.assertEqual(self.report['backend']['matrix_normal_fma_calls'], 0)

    def test_every_core_read_maps_once_in_order_to_external_ddr(self):
        c = self.case
        expected = s.expected_requests(c.job)
        self.assertEqual([(q.write, q.address) for q in c.probe.core_requests], expected)
        core_reads = [q for q in c.probe.core_requests if not q.write]
        self.assertEqual([q for q, _ in c.probe.external_reads], core_reads)
        self.assertTrue(all(actual is core for (actual, _), core in
                            zip(c.probe.external_reads, core_reads)))
        self.assertEqual([q for q, _ in c.probe.core_responses], c.probe.core_requests)
        physical_data = {q.tag: data for q, data in c.probe.external_reads}
        for q, response in c.probe.core_responses:
            self.assertEqual(response.tag, q.tag)
            self.assertEqual(response.nbytes, 64)
            if not q.write:
                self.assertIs(response.data, physical_data[q.tag])
                self.assertIs(type(response.data), bytes)
                self.assertEqual(len(response.data), 64)
                self.assertEqual(len(__import__('struct').unpack('<16I', response.data)), 16)
        self.assertEqual(c.physical.read_regions, Counter(q=192 * 64, k=288 * 64, v=288 * 64))
        self.assertEqual(len(core_reads), 768)
        # Repeated K/V locations stay repeated external reads; no hidden cache hit.
        kv_addresses = [q.address for q in core_reads
                        if c.job.b <= q.address < c.job.b + c.job.m * 1024
                        or c.job.c <= q.address < c.job.c + c.job.m * 1024]
        self.assertGreater(len(kv_addresses), len(set(kv_addresses)))
        self.assertEqual(len(kv_addresses), 576)

    def test_write_command_data_ack_fence_and_final_terminal(self):
        c, report = self.case, self.report
        writes = [q for q in c.probe.core_requests if q.write]
        commands = [v for kind, v, _ in c.probe.write_events if kind == 'command']
        data = [v for kind, v, _ in c.probe.write_events if kind == 'data']
        acks = [(v, tick) for kind, v, tick in c.probe.write_events if kind == 'ack']
        self.assertEqual(len(writes), 192)
        self.assertEqual([kind for kind, _, _ in c.probe.write_events],
                         ['command', 'data', 'ack'] * 192)
        self.assertEqual([(v.address, v.tag, v.beats) for v in commands],
                         [(q.address, q.tag, 1) for q in writes])
        self.assertEqual([v.words for v in data], [q.words for q in writes])
        self.assertTrue(all(v.mask == (1 << 64) - 1 and len(v.words) == 16 and v.last
                            for v in data))
        self.assertEqual([v.tag for v, _ in acks], [q.tag for q in writes])
        self.assertTrue(all(v.nbytes == 64 and not v.error for v, _ in acks))
        fence = report['final_ack_fence']
        self.assertEqual(fence['held_ticks'], 5)
        self.assertEqual(fence['final_ack_tick'], acks[-1][1])
        self.assertGreater(fence['terminal_tick'], fence['final_ack_tick'])
        self.assertEqual(fence['terminal_tick'], c.probe.terminal_clock)
        self.assertEqual(report['accepted']['requests'], 960)
        self.assertEqual(report['accepted']['responses'], 960)
        self.assertEqual(report['accepted']['write_acks'], 192)
        self.assertEqual(c.physical.counts['write_ack_bytes'], c.job.write_bytes)
        output = c.physical.regions['attention_output']
        self.assertEqual(output['written'], output['acked'])
        self.assertTrue(output['terminal'])
        self.assertFalse(output['published'])
        self.assertEqual(c.host.published, [])
        self.assertIsNone(c.physical.pending)
        # PhysicalMemory keeps even ACKed output unreadable before publication.
        with self.assertRaisesRegex(ValueError, 'public publication'):
            type(c.physical).read_bytes64(c.physical, c.job.dst)

    def test_one_shared_matrix_acquisition_and_no_raw_or_scratch_operations(self):
        c = self.case
        self.assertEqual(c.service.counts['owner_acquires'], 1)
        self.assertEqual(c.service.counts['owner_releases'], 1)
        self.assertEqual(c.service.counts['owner_responses'], 1)
        self.assertEqual((c.scalar.acquisitions, c.scalar.releases), (1, 1))
        self.assertIsNone(c.service.owner)
        self.assertIsNone(c.scalar.client)
        self.assertEqual(Counter(g.profile for g in c.service.groups), Counter({2: 24, 0: 192}))
        self.assertEqual(Counter(c.service.step_profiles), Counter({2: 192, 0: 288}))
        self.assertEqual(c.service.counts['normal_done'], 216)
        self.assertEqual(c.probe.scratch_events, 0)
        self.assertIsNone(c.x.attention_transport)
        self.assertIsNone(c.x.attention_transport_binding)
        self.assertEqual(c.x.counts['raw_kv_parent_edges'], 0)
        self.assertTrue(s.runtime.direct.no_scratch(c.owner))
        self.assertTrue(s.runtime.direct.dense_retired(c.dense))
        for banks in (c.dense.a_banks, c.dense.b_banks):
            self.assertEqual((banks.reads, banks.writes, banks.calls), ({}, {}, 0))
        self.assertFalse(any(name.endswith(('.raw_kv.model', '.raw_kv_parent.model',
                                           '.raw_kv_public.model')) for name in sys.modules))
        self.assertEqual(c.x.bank_ids, (id(c.dense), id(c.dense.a_banks),
                                      id(c.dense.b_banks), id(c.dense.tiles.banks)))

    def test_direct_runtime_cannot_enable_raw_driver_or_copy_payload(self):
        tree = ast.parse((s.HERE / 'direct_transport.py').read_text())
        run = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
        calls = [node for node in ast.walk(run) if isinstance(node, ast.Call) and
                 isinstance(node.func, ast.Name) and node.func.id == 'execute_attention_owner']
        self.assertEqual(len(calls), 1)
        raw = next(k.value for k in calls[0].keywords if k.arg == 'enable_raw_kv')
        self.assertIsInstance(raw, ast.Constant)
        self.assertIs(raw.value, False)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertFalse(names.intersection({'ParentLoan', 'RawKvPort', 'PublicKvTransport',
                                            'bytearray', 'bytes', 'array'}))
        self.assertIs(self.case.x.selected_direct_binding.schedule, self.case.owner.packed_schedule)

    def _mutation_rejected(self, mutate, *, pending=False):
        c = s.make_case()
        s.runtime.direct.bind(c.x, c.physical, c.job)
        self.assertTrue(c.x.attention_edge(job=c.job)['job_fire'])
        # Observe the actual newly acquired router on a held, no-memory edge
        # before mutating its identity; this also checks stable held requests.
        held = c.owner.ports()['memory']
        self.assertFalse(c.x.attention_edge(memory_ready=False)['memory_fire'])
        self.assertIs(c.owner.ports()['memory'], held)
        inputs = dict(memory_ready=True)
        if pending:
            edge = c.x.attention_edge(memory_ready=True)
            self.assertTrue(edge['memory_fire'])
            q = edge['memory']
            raw = c.physical.read_bytes64(q.address)
            inputs['memory_response'] = s.modules.prefix.MemoryResponse(q.tag, raw)
        before = s.snapshot(c)
        mutate(c)
        with self.assertRaises(ValueError):
            c.x.attention_edge(**inputs)
        self.assertEqual(s.snapshot(c), before,
                         'mutation was not rejected before the next owner/Host/memory edge')

    def test_raw_transport_binding_and_schedule_mutations_before_memory_step(self):
        mutations = {
            'raw transport': lambda c: setattr(c.x, 'attention_transport', object()),
            'raw binding': lambda c: setattr(c.x, 'attention_transport_binding', (object(),)),
            'direct binding replacement': lambda c: setattr(c.x, 'selected_direct_binding', object()),
            'direct binding detachment': lambda c: setattr(c.x, 'selected_direct_binding', None),
            'selected schedule replacement': lambda c: setattr(c.owner, 'packed_schedule', object()),
            'client replacement': lambda c: setattr(c.owner, 'matrix_client', object()),
            'active client detached': lambda c: setattr(c.owner, 'matrix_client', None),
        }
        for pending in (False, True):
            for name, mutate in mutations.items():
                with self.subTest(name=name, pending=pending):
                    self._mutation_rejected(mutate, pending=pending)

    def test_router_and_packed_legacy_link_mutations_before_memory_step(self):
        def foreign_router(c):
            foreign = s.prior.RoutedScriptedService(acquired=False)
            self.assertTrue(foreign.acquire(c.owner, 'normal', c.job.tag))
            c.owner.matrix_client = s.modules.routing.Qk16LegacyPvClient(foreign, c.owner)
        mutations = {
            'exact-type foreign-service router': foreign_router,
            'same-service replacement router': lambda c: setattr(c.owner, 'matrix_client',
                s.modules.routing.Qk16LegacyPvClient(c.service, c.owner)),
            'router service': lambda c: setattr(c.owner.matrix_client, 'service', object()),
            'router owner': lambda c: setattr(c.owner.matrix_client, 'owner', object()),
            'packed service': lambda c: setattr(c.owner.matrix_client.packed, 'service', object()),
            'packed owner': lambda c: setattr(c.owner.matrix_client.packed, 'owner', object()),
            'legacy service': lambda c: setattr(c.owner.matrix_client.legacy, 'service', object()),
            'legacy owner': lambda c: setattr(c.owner.matrix_client.legacy, 'owner', object()),
        }
        for pending in (False, True):
            for name, mutate in mutations.items():
                with self.subTest(name=name, pending=pending):
                    self._mutation_rejected(mutate, pending=pending)

    def test_original_bank_service_and_physical_map_mutations_before_memory_step(self):
        mutations = {
            'a banks': lambda c: setattr(c.dense, 'a_banks', s.UntouchedBanks()),
            'b banks': lambda c: setattr(c.dense, 'b_banks', s.UntouchedBanks()),
            'tile banks': lambda c: setattr(c.dense.tiles, 'banks', s.UntouchedBanks()),
            'Dense identity': lambda c: setattr(c.x, 'owner', s.SyntheticIdleDense()),
            'Matrix identity': lambda c: setattr(c.x, 'matrix_service', s.prior.RoutedScriptedService()),
            'Matrix resource': lambda c: setattr(c.service, 'resource_address', c.service.resource_address + 1),
            'owner Matrix': lambda c: setattr(c.owner, 'matrix', s.prior.RoutedScriptedService()),
            'owner scalar': lambda c: setattr(c.owner, 'scalar', s.prior.ScalarControlAdapter()),
            'prefix scalar': lambda c: setattr(c.prefix, 'scalar', s.prior.ScalarControlAdapter()),
            'metadata memory': lambda c: setattr(c.frontend, 'memory', c.physical.metadata_port()),
            'metadata port memory': lambda c: setattr(c.frontend.port, 'memory', c.physical.metadata_port()),
            'physical map': lambda c: setattr(c.frontend.memory, 'physical_memory', object()),
            'physical region': lambda c: c.physical.regions.__setitem__('q', dict(c.physical.regions['q'])),
            'physical payload': lambda c: c.physical.regions['attention_output'].__setitem__('data', bytearray(c.job.write_bytes + 128)),
            'physical provider': lambda c: c.physical.regions['q'].__setitem__('provider', lambda offset: bytes(64)),
            'physical address': lambda c: c.physical.regions['q'].__setitem__('base', c.job.a + 64),
            'physical reserved span': lambda c: c.physical.regions['q'].__setitem__('reserved', 0),
            'physical payload resize': lambda c: c.physical.regions['attention_output']['data'].extend(bytes(64)),
        }
        for pending in (False, True):
            for name, mutate in mutations.items():
                with self.subTest(name=name, pending=pending):
                    self._mutation_rejected(mutate, pending=pending)

    def test_retained_dense_and_prefix_debts_before_memory_step(self):
        debts = dict(state='wait', error='retained', read_active=object(), a_hold=object(),
            a_rmw_pending=object(), pending=object(), fifo=[object()], seed_outstanding=True,
            seed_state='wait', write_state='wait', window_request=object(), window_result=object(),
            drain_request=object(), drain_result=object(), drain_expected=object(), lease=object(),
            drain_poison=True, response=object())
        for field, value in debts.items():
            with self.subTest(field=field):
                self._mutation_rejected(lambda c, f=field, v=value: setattr(c.dense, f, v))
        for field, value in dict(idle=False, leased=True, poison=True).items():
            with self.subTest(tile_field=field):
                self._mutation_rejected(lambda c, f=field, v=value: setattr(c.dense.tiles, f, v))
        self._mutation_rejected(lambda c: (setattr(c.dense, 'group_started', True),
                                           setattr(c.dense, 'group_done', False)))
        self._mutation_rejected(lambda c: setattr(c.prefix, 'state', 'wait'))
        self._mutation_rejected(lambda c: setattr(c.prefix, 'poison', True))

    def test_scratch_payload_and_debts_before_memory_step(self):
        action = s.prior.protocol.ScratchAction(1, 'write', 1, 0, 0, 4096, (0,) * 16)
        self.assertTrue(action.valid())
        fields = dict(scratch_request=action, scratch_pending=True, scratch_leased=True,
                      scratch_write_tag=object(), packed_memory_tag=object(), scratch_last=action)
        for pending in (False, True):
            for field, value in fields.items():
                with self.subTest(field=field, pending=pending):
                    self._mutation_rejected(lambda c, f=field, v=value: setattr(c.owner, f, v),
                                            pending=pending)

    def test_bind_checks_dispatch_and_retirement_before_install_or_acquisition(self):
        mutations = {
            'raw transport': lambda c: setattr(c.x, 'attention_transport', object()),
            'raw binding': lambda c: setattr(c.x, 'attention_transport_binding', (object(),)),
            'Dense debt': lambda c: setattr(c.dense, 'lease', object()),
            'scratch debt': lambda c: setattr(c.owner, 'scratch_pending', True),
            'physical write debt': lambda c: setattr(c.physical, 'pending', object()),
            'wrong dispatch object': lambda c: setattr(c.host, 'job', replace(c.job)),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                c = s.make_case()
                mutate(c)
                before = s.snapshot(c)
                with self.assertRaises(ValueError):
                    s.runtime.direct.bind(c.x, c.physical, c.job)
                self.assertEqual(s.snapshot(c), before)
                self.assertIsNone(c.owner.packed_schedule)
                self.assertIsNone(getattr(c.x, 'selected_direct_binding', None))
                self.assertEqual(c.service.counts['owner_acquires'], 0)

    def test_process_resource_bounds(self):
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_CPU)[0], 20)
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_AS)[0], 256 * 1024 * 1024)
        if hasattr(s.os, 'sched_getaffinity'):
            self.assertEqual(len(s.os.sched_getaffinity(0)), 1)

    def test_invalid_final_ack_stall_rejected_before_binding_and_valid_retry(self):
        for invalid in (0, -1, True, '5'):
            with self.subTest(invalid=invalid):
                c = s.make_case()
                before = s.snapshot(c)
                with self.assertRaises(ValueError):
                    s.runtime.direct.run(c.x, c.physical, c.job, final_ack_stall=invalid)
                self.assertEqual(s.snapshot(c), before)
                self.assertIsNone(c.owner.packed_schedule)
                self.assertIsNone(getattr(c.x, 'selected_direct_binding', None))
                self.assertEqual(c.service.counts['owner_acquires'], 0)
                report = s.runtime.direct.run(c.x, c.physical, c.job, final_ack_stall=1)
                self.assertEqual(report['final_ack_fence']['held_ticks'], 1)
                self.assertEqual(c.probe.accepted_jobs, [c.job])
                self.assertEqual(c.service.counts['owner_acquires'], 1)

    def test_source_root_is_required_even_in_isolated_mode(self):
        result = subprocess.run([sys.executable, '-I', '-B',
            str(s.HERE / 'direct_test_support.py')], cwd='/tmp',
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('required: --source-root', result.stderr)

    def test_source_pin_mismatch_fails_before_prior_ast_loading(self):
        # Only the first source exists in this deliberately invalid root.
        # Reaching a later source, prior support or AST loader would instead
        # produce FileNotFoundError, not this first-file pin mismatch.
        relative = next(iter(s.PINS['sources']))
        with tempfile.TemporaryDirectory(prefix='selected-direct-bad-pin-') as directory:
            root = Path(directory)
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes((s.SOURCE_ROOT / relative).read_bytes() + b'\n')
            result = subprocess.run([sys.executable, '-O', '-I', '-B',
                str(s.HERE / 'direct_test_support.py'), '--source-root', str(root)],
                cwd='/tmp', capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn('source pin mismatch: ' + relative, result.stderr)
        self.assertNotIn('FileNotFoundError', result.stderr)
        self.assertNotIn('_spec.loader.exec_module', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
