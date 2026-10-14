"""Cold real Host/public/Tile checks only; no arithmetic library or mocks."""
import ast
from contextlib import redirect_stdout
import inspect
import io
from pathlib import Path
import pickle
import sys
import time
import unittest

from candidates.qwen2_live_attention_model_m16.budget_fixture import attention_fixture
from candidates.qwen2_resident_matrix.ffn_public import model as public
from candidates.qwen2_resident_matrix.ffn_public import prefix_execution as prefix
from candidates.qwen2_resident_matrix.ffn_public.execute_numeric import PublicExecution, numeric
from candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain import DenseReductionOwner
from .owner import DenseIdleOwnerV1, diagnostics
from .public_binding import (DenseIdlePublic3ExecutionV1, DenseIdlePV32PublicExecutionV1,
                             DenseIdlePV32ReductionDriverV1, PV32PublicExecution, PV32ReductionDriver)
from .probe import (DenseReturnCapture, EdgeRecorder, Graph, first_difference, full_public_state,
                    main, method_identities, source_manifest, snapshot_load, normalized_backend_report, fixture_identity)


def actual_public(new, rows=8):
    """Real metadata frontend, Host and TileBank; no service-shaped fake."""
    f = attention_fixture(rows)
    memory = prefix.PhysicalMemory(f, {})
    region = f.config.regions[3]
    owner_class = DenseIdleOwnerV1 if new else DenseReductionOwner
    owner = owner_class(numeric.model.PrefixWorkspace(region.base, region.limit - region.base,
        f.config.epoch + 1, 2560), enable_dense_drain=True, enable_k_window=True,
        enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
    cls = DenseIdlePublic3ExecutionV1 if new else PublicExecution
    x = cls(public.PublicFrontend(memory.metadata_port(), f.config), owner, numeric.CappedTrace(),
        time.monotonic() + 30,
        host=public.group.HostControl(enabled=True, legacy_prefix=True, legacy_attention=True))
    return x, memory


class ProbeCold(unittest.TestCase):
    def test_default_does_not_load_runtime(self):
        # The default branch performs no source snapshot, compile or C call.
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(main([]), 0)
        self.assertIn('NOT_EXECUTED', stream.getvalue())
        for argv in (['--out', 'anything'], ['--cpu', '0'], ['--child-config', 'anything']):
            with self.assertRaisesRegex(ValueError, 'explicit --actual-budget'):
                main(argv)

    def test_all_execution_methods_are_inherited_identity(self):
        report = method_identities()
        self.assertTrue(report)
        self.assertIs(DenseIdlePublic3ExecutionV1.attention_edge, PublicExecution.attention_edge)
        self.assertIs(DenseIdlePV32PublicExecutionV1.attention_edge, PV32PublicExecution.attention_edge)
        self.assertIs(DenseIdlePV32ReductionDriverV1.tick, PV32ReductionDriver.tick)
        self.assertIs(DenseIdlePV32ReductionDriverV1.run, PV32ReductionDriver.run)
        for cls in (DenseIdlePublic3ExecutionV1, DenseIdlePV32PublicExecutionV1, DenseIdlePV32ReductionDriverV1):
            self.assertEqual([n for n, v in vars(cls).items() if inspect.isfunction(v)], ['__init__'])

    def test_exact_owner_admission_rejects_original_and_foreign_subclass(self):
        x, _ = actual_public(False)
        with self.assertRaisesRegex(ValueError, 'exact DenseIdleOwnerV1'):
            DenseIdlePublic3ExecutionV1(x.frontend, x.owner, x.trace, x.deadline)
        class Foreign(DenseIdleOwnerV1):
            pass
        owner = Foreign(x.owner.workspace, enable_dense_drain=True, enable_k_window=True,
                        enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
        with self.assertRaisesRegex(ValueError, 'exact DenseIdleOwnerV1'):
            DenseIdlePublic3ExecutionV1(x.frontend, owner, x.trace, x.deadline)

    def test_real_public_host_tile_edges_and_full_state(self):
        old, om = actual_public(False)
        new, nm = actual_public(True)
        self.assertEqual(full_public_state(old, om), full_public_state(new, nm))
        obuf, nbuf = io.BytesIO(), io.BytesIO()
        orec, nrec = EdgeRecorder(obuf), EdgeRecorder(nbuf)
        for inputs in ({}, {}, {}, {'read_command_ready': True}, {}):
            oe, ne = old.idle_edge(**inputs), new.idle_edge(**inputs)
            self.assertEqual(Graph().encode(oe), Graph().encode(ne))
            self.assertEqual(list(oe), list(ne))
            self.assertIs(oe['a_reads'], oe['tile']['reads'])
            self.assertIs(ne['a_reads'], ne['tile']['reads'])
            self.assertIs(oe['a_writes'], oe['tile']['writes'])
            self.assertIs(ne['a_writes'], ne['tile']['writes'])
            orec.record(old, inputs, oe, om)
            nrec.record(new, inputs, ne, nm)
            self.assertEqual(full_public_state(old, om), full_public_state(new, nm))
        self.assertEqual(obuf.getvalue(), nbuf.getvalue())
        self.assertEqual(orec.edges, 5)
        self.assertEqual(diagnostics(new.owner), {'fast': 4, 'fallback': 1})
        self.assertEqual(old.counts['host_model_ticks'], 5)
        self.assertEqual(new.counts['host_model_ticks'], 5)
        self.assertEqual(old.owner.clock, new.owner.clock)
        self.assertEqual(old.owner.tiles.cycle, new.owner.tiles.cycle)

    def test_cold_profile_verifies_real_calls_without_patching(self):
        old, _ = actual_public(False)
        new, _ = actual_public(True)
        wanted = {'host': public.group.HostControl.tick.__code__,
                  'tile': type(old.owner.tiles).tick.__code__,
                  'new_owner': DenseIdleOwnerV1.tick.__code__,
                  'old_owner': DenseReductionOwner.tick.__code__}
        counts = {name: 0 for name in wanted}
        def profile(frame, event, arg):
            if event == 'call':
                for name, code in wanted.items():
                    if frame.f_code is code:
                        counts[name] += 1
        self.assertIsNone(sys.getprofile(), 'cold call count refuses an existing profiler')
        try:
            sys.setprofile(profile)
            for _ in range(3):
                old.idle_edge()
                new.idle_edge()
        finally:
            sys.setprofile(None)
        self.assertEqual(counts, {'host': 6, 'tile': 6, 'new_owner': 3, 'old_owner': 3})

    def test_graph_retains_types_order_and_aliases(self):
        x, _ = actual_public(False)
        edge = x.idle_edge()
        encoded = Graph().encode(edge)
        detached = dict(edge, a_reads=dict(edge['a_reads']))
        self.assertNotEqual(encoded, Graph().encode(detached))
        reordered = dict(reversed(list(edge.items())))
        self.assertNotEqual(encoded, Graph().encode(reordered))
        different_type = dict(edge, window_fire=0)
        self.assertNotEqual(encoded, Graph().encode(different_type))
        restored = pickle.loads(pickle.dumps(edge, protocol=4))
        self.assertEqual(encoded, Graph().encode(restored))
        self.assertIs(restored['a_reads'], restored['tile']['reads'])

    def test_m2_m8_actual_fixture_identities_are_distinct(self):
        identities = []
        for rows in (2, 8):
            x, memory = actual_public(False, rows=rows)
            job = x.advance_to_request()['ordinary_request']
            identity = fixture_identity(memory.fixture, job)
            self.assertEqual(identity['decoded_job']['m'], rows)
            self.assertEqual(identity['tables']['commands']['record_count'], 3)
            identities.append(identity)
        self.assertNotEqual(identities[0]['scope'], identities[1]['scope'])
        self.assertNotEqual(identities[0]['tables']['descriptors']['packed_span_sha256'],
                            identities[1]['tables']['descriptors']['packed_span_sha256'])

    def test_only_verified_accumulator_report_root_is_normalized(self):
        report = {'matrix_resource_address': 12345, 'other_id': 12345, 'counts': {'zero': 0}}
        actual = normalized_backend_report(report, 12345)
        self.assertEqual(list(actual), list(report))
        self.assertEqual(actual['matrix_resource_address'], '@same_pinned_matrix_accumulator')
        self.assertEqual(actual['other_id'], 12345)
        self.assertIs(actual['counts'], report['counts'])
        self.assertEqual(report['matrix_resource_address'], 12345)
        with self.assertRaisesRegex(ValueError, 'verified Matrix accumulator root'):
            normalized_backend_report(report, 54321)
        with self.assertRaisesRegex(ValueError, 'verified Matrix accumulator root'):
            normalized_backend_report({'other_id': 12345}, 12345)

    def test_first_difference_identifies_exact_field(self):
        self.assertEqual(first_difference({'a': [1, 2]}, {'a': [1, 3]})['path'], "$['a'][1]")
        self.assertEqual(first_difference({'a': 1, 'b': 2}, {'b': 2, 'a': 1})['reason'], 'ordered_keys')
        self.assertEqual(first_difference(True, 1)['reason'], 'type')

    def test_public21_constructor_delta_is_only_exact_class_admission(self):
        # Supplemental source guard. Behavioral evidence above uses real models.
        old = ast.parse(inspect.getsource(inspect.getmodule(PV32PublicExecution)))
        new = ast.parse(Path(__file__).with_name('public_binding.py').read_text())
        rename = {'DenseIdleOwnerV1': 'base.DenseReductionOwner',
                  'DenseIdlePV32PublicExecutionV1': 'PV32PublicExecution'}
        class Normalize(ast.NodeTransformer):
            def visit_Name(self, node):
                return ast.parse(rename[node.id], mode='eval').body if node.id in rename else node
        for a, b in (('PV32PublicExecution', 'DenseIdlePV32PublicExecutionV1'),
                     ('PV32ReductionDriver', 'DenseIdlePV32ReductionDriverV1')):
            ca = next(n for n in old.body if isinstance(n, ast.ClassDef) and n.name == a)
            cb = next(n for n in new.body if isinstance(n, ast.ClassDef) and n.name == b)
            ia = next(n for n in ca.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
            ib = next(n for n in cb.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
            self.assertEqual(ast.dump(ia, include_attributes=False), ast.dump(Normalize().visit(ib), include_attributes=False))


class DenseRecorderCold(unittest.TestCase):
    def capture(self, x):
        return DenseReturnCapture(x.owner, source_sha256=source_manifest())

    def assert_released(self, capture, tool):
        self.assertTrue(capture.closed)
        self.assertIsNone(capture.tool_id)
        self.assertIsNone(sys.monitoring.get_tool(tool))
        self.assertEqual(sys.monitoring.get_events(tool), 0)
        self.assertEqual(sys.monitoring.get_local_events(tool, capture.code), 0)
        self.assertIsNone(sys.monitoring.register_callback(tool, sys.monitoring.events.PY_RETURN, None))

    def test_real_return_aliases_and_recorder_no_model_writes(self):
        outputs = []
        for new in (False, True):
            x, memory = actual_public(new)
            capture = self.capture(x)
            raw = io.BytesIO()
            recorder = EdgeRecorder(raw, dense_capture=capture, execution=x, memory=memory)
            initial = full_public_state(x, memory)
            with capture:
                tool = capture.tool_id
                self.assertEqual(initial, full_public_state(x, memory))
                for _ in range(4):
                    actual = x.idle_edge()
                    self.assertIs(capture.pending, actual)
                    self.assertIs(capture.pending['a_reads'], actual['tile']['reads'])
                    state = full_public_state(x, memory)
                    recorder.record(x, {}, actual, memory)
                    self.assertEqual(state, full_public_state(x, memory))
                self.assertEqual(capture.returns, 4)
                self.assertEqual(capture.consumed, 4)
            self.assert_released(capture, tool)
            self.assertEqual(recorder.invariant.seal()['checked_edges'], 4)
            outputs.append(raw.getvalue())
        self.assertEqual(outputs[0], outputs[1])

    def test_named_root_replacement_is_not_normalized_away(self):
        x, memory = actual_public(False)
        capture = self.capture(x)
        recorder = EdgeRecorder(io.BytesIO(), dense_capture=capture, execution=x, memory=memory)
        with capture:
            edge = x.idle_edge()
            original_trace = x.trace
            x.trace = numeric.CappedTrace()
            try:
                with self.assertRaisesRegex(ValueError, 'root object replaced'):
                    recorder.record(x, {}, edge, memory)
            finally:
                x.trace = original_trace

    def test_foreign_owner_code_and_subclass_fail_closed(self):
        class Foreign(DenseIdleOwnerV1):
            pass
        x, _ = actual_public(False)
        foreign = Foreign(x.owner.workspace, enable_dense_drain=True, enable_k_window=True,
            enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
        with self.assertRaisesRegex(ValueError, 'exact Dense class'):
            DenseReturnCapture(foreign, source_sha256=source_manifest())
        for mode in ('owner', 'code'):
            capture = self.capture(x)
            other, _ = actual_public(False)
            before = full_public_state(x, x.frontend.memory.physical_memory)
            with self.assertRaisesRegex(ValueError, 'foreign Dense'):
                with capture:
                    tool = capture.tool_id
                    if mode == 'owner':
                        other.owner.tick()
                    else:
                        capture._return(self.test_foreign_owner_code_and_subclass_fail_closed.__func__.__code__, 0, {})
            self.assert_released(capture, tool)
            self.assertEqual(before, full_public_state(x, x.frontend.memory.physical_memory))

    def test_unrelated_monitoring_callbacks_masks_and_actual_calls_preserved(self):
        monitor = sys.monitoring
        self.assertIsNone(monitor.get_tool(3))
        counts = {'host': 0, 'tile': 0}
        host_code = public.group.HostControl.tick.__code__
        x, _ = actual_public(False)
        tile_code = type(x.owner.tiles).tick.__code__
        def callback(code, offset, value):
            if code is host_code:
                counts['host'] += 1
            if code is tile_code:
                counts['tile'] += 1
        monitor.use_tool_id(3, 'cold-independent-public-counter')
        prior = monitor.register_callback(3, monitor.events.PY_RETURN, callback)
        self.assertIsNone(prior)
        monitor.set_local_events(3, host_code, monitor.events.PY_RETURN)
        monitor.set_local_events(3, tile_code, monitor.events.PY_RETURN)
        try:
            for new in (False, True):
                x, memory = actual_public(new)
                capture = self.capture(x)
                with capture:
                    self.assertEqual(capture.tool_id, 4)
                    for _ in range(3):
                        actual = x.idle_edge()
                        self.assertIs(capture.take(), actual)
                self.assertEqual(monitor.get_tool(3), 'cold-independent-public-counter')
                self.assertEqual(monitor.get_local_events(3, host_code), monitor.events.PY_RETURN)
                self.assertEqual(monitor.get_local_events(3, tile_code), monitor.events.PY_RETURN)
                self.assertEqual(monitor.get_events(3), 0)
            self.assertEqual(counts, {'host': 6, 'tile': 6})
        finally:
            monitor.set_local_events(3, host_code, 0)
            monitor.set_local_events(3, tile_code, 0)
            self.assertIs(monitor.register_callback(3, monitor.events.PY_RETURN, prior), callback)
            monitor.free_tool_id(3)

    def test_existing_trace_profile_and_stale_callback_are_preserved(self):
        x, _ = actual_public(False)
        def existing(*args):
            return existing
        for setter, getter in ((sys.settrace, sys.gettrace), (sys.setprofile, sys.getprofile)):
            capture = self.capture(x)
            self.assertIsNone(getter())
            setter(existing)
            try:
                with self.assertRaisesRegex(ValueError, 'existing tracer/profiler'):
                    capture.__enter__()
                self.assertIs(getter(), existing)
                self.assertIsNone(capture.tool_id)
            finally:
                setter(None)
        capture = self.capture(x)
        monitor = sys.monitoring
        prior = monitor.register_callback(4, monitor.events.PY_RETURN, existing)
        self.assertIsNone(prior)
        try:
            with self.assertRaisesRegex(ValueError, 'stale callback'):
                capture.__enter__()
            self.assertIsNone(monitor.get_tool(4))
            self.assertEqual(monitor.get_local_events(4, capture.code), 0)
            self.assertIs(monitor.register_callback(4, monitor.events.PY_RETURN, None), existing)
        finally:
            monitor.register_callback(4, monitor.events.PY_RETURN, prior)

    def test_body_exit_exceptions_cleanup_and_foreign_callback_preserved(self):
        x, _ = actual_public(False)
        capture = self.capture(x)
        with self.assertRaisesRegex(RuntimeError, 'cold body failure'):
            with capture:
                tool = capture.tool_id
                raise RuntimeError('cold body failure')
        self.assert_released(capture, tool)
        capture = self.capture(x)
        with self.assertRaisesRegex(ValueError, 'unconsumed Dense return'):
            with capture:
                tool = capture.tool_id
                x.owner.tick()
        self.assert_released(capture, tool)
        capture = self.capture(x)
        monitor = sys.monitoring
        def replacement(*args):
            pass
        try:
            with self.assertRaisesRegex(ValueError, 'registration replaced'):
                with capture:
                    tool = capture.tool_id
                    self.assertIs(monitor.register_callback(tool, monitor.events.PY_RETURN, replacement), capture.callback)
            self.assertEqual(monitor.get_tool(tool), capture.name)
            self.assertEqual(monitor.get_local_events(tool, capture.code), 0)
            self.assertIs(monitor.register_callback(tool, monitor.events.PY_RETURN, None), replacement)
        finally:
            monitor.register_callback(tool, monitor.events.PY_RETURN, None)
            monitor.free_tool_id(tool)


if __name__ == '__main__':
    unittest.main()
