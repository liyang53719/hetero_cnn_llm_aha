"""Bounded control-only tests. No production imports, native loads or arithmetic.

Compile unchanged AST nodes from full_driver.py against named synthetic doubles.
Only the orchestration, snapshot, resource guard and commit methods execute.
No model constructor, NumPy, Scalar/Vector/Matrix operation, payload or build runs.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace as NS
from typing import NamedTuple
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name('full_driver.py')
# Verbatim source-only baseline from this repository (Apache-2.0, see LICENSE):
# candidates/qwen35_gdn_prefill/full_driver.py at 69cd7dd47eaebeb04d23700d072e5e546a8d44b6.
# Parse under the current interpreter; never import or execute the full fixture.
BASELINE_PATH = SOURCE.parent / 'fixtures' / 'full_driver_before_progress.py.txt'
BASELINE_SHA256 = 'd68d50143749f73d3c8c098953d4906216c0e7b5ebaca196bdc48d107cbb63ad'


def baseline_source(raw):
    if hashlib.sha256(raw).hexdigest() != BASELINE_SHA256:
        raise ValueError('frozen source-only baseline SHA-256 mismatch')
    return raw.decode('utf-8')


BASELINE_BYTES = BASELINE_PATH.read_bytes()
BASELINE_SOURCE = baseline_source(BASELINE_BYTES)
TREE = ast.parse(SOURCE.read_text())
METHODS = {'_progress_snapshot', 'run_window', 'tick', '_check_resources', '_commit', '_fail'}


def load_control_nodes():
    """No model module import, monkeypatch or numerical constructor is needed."""
    nodes = []
    names = {'require', 'sha', 'status', 'CommittedRoots', 'FullBlockResult',
             'FullBlockProgress', 'ProjectionPolicy', 'run'}
    for node in TREE.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names:
            nodes.append(deepcopy(node))
        elif isinstance(node, ast.ClassDef) and node.name == 'FullBlockCoordinator':
            selected = deepcopy(node)
            selected.body = [n for n in selected.body if isinstance(n, ast.FunctionDef) and n.name in METHODS]
            nodes.append(selected)
    module = ModuleType('_full_progress_cold')
    module.__dict__.update(dataclass=dataclass, NamedTuple=NamedTuple, Enum=Enum,
        hashlib=hashlib, Path=Path, json=json, SCOPE='SYNTHETIC_CONTROL_ONLY',
        rms=NS(ReductionPolicy=NS(Torch210CpuDefault1024='rms')),
        chunk=NS(ep=NS(LEGACY_EXP='legacy')), LEGACY_POLICY='legacy-vector',
        LEGACY_BACKEND='legacy-backend')
    sys.modules[module.__name__] = module
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 str(SOURCE), 'exec'), module.__dict__)
    return module


F = load_control_nodes()
Coordinator = F.FullBlockCoordinator


class Clock:
    def __init__(self, values):
        self.values, self.calls = iter(values), 0

    def monotonic(self):
        self.calls += 1
        return next(self.values)


class LoopDouble(Coordinator):
    """Deterministic nonnumeric tick/work log, not a model or owner receipt."""
    def __init__(self, ticks=8, drain=False):
        self.limit, self.drain = ticks, drain
        self.ticks, self.commands, self.log = 0, [], []
        self.roots = NS(generation=0)
        self.chunk = NS(context={'phase': 'matmul', 'head': 3, 'chunk': 1})
        self.active = NS(owner=NS(state='wait', ticks=0))
        self.response = None

    def start(self, phase, **kwargs):
        self.phase, self.role = phase, 'chunk'
        self.log.append(('start', phase, kwargs))

    def tick(self, **controls):
        self.log.append(('tick', self.ticks, dict(controls)))
        self.ticks += 1
        self.active.owner.ticks += 1
        if self.drain:
            if controls.get('abort'):
                self.commands.append('real-synthetic-abort-terminal')
                self.response = NS(status='Aborted')
        elif self.ticks == self.limit:
            self.commands.append('real-synthetic-success-terminal')
            self.response = NS(status=None)


class SnapshotAndLoopTests(unittest.TestCase):
    def execute(self, values, *, progress=None, hook=None, **kwargs):
        coordinator = LoopDouble(kwargs.pop('ticks', 8), kwargs.pop('drain', False))
        clock = Clock(values)
        with patch.object(F, 'time', clock, create=True):
            result = coordinator.run_window('cold', cold=True, expected_generation=0,
                progress=progress, hook=hook, **kwargs)
        return coordinator, clock, result

    def test_snapshot_is_immutable_detached_exact_primitives(self):
        coordinator = LoopDouble()
        coordinator.start('cold')
        snapshot = coordinator._progress_snapshot(1.25)
        self.assertEqual(snapshot.chunk_head, 3)
        self.assertEqual(snapshot.chunk_subchunk, 1)
        self.assertTrue(all(type(value) in (str, int, float, type(None)) for value in snapshot))
        self.assertFalse(hasattr(snapshot, '__dict__'))
        with self.assertRaises(AttributeError):
            snapshot.ticks = 99
        with self.assertRaises(TypeError):
            snapshot[0] = 'bad'
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(snapshot, 'ticks', 99)
        snapshot._asdict()['ticks'] = 99
        coordinator.chunk.context.update(head=15, chunk=0)
        coordinator.active.owner.state = 'finish'
        self.assertEqual((snapshot.chunk_head, snapshot.chunk_subchunk, snapshot.owner_state), (3, 1, 'wait'))
        self.assertEqual(coordinator.ticks, 0)

    def test_mutable_or_subclass_values_never_reach_callback(self):
        class IntSubclass(int):
            pass
        for field, value in (('head', []), ('chunk', object()), ('phase', {}), ('head', IntSubclass(1))):
            with self.subTest(field=field, value=type(value)):
                coordinator = LoopDouble()
                coordinator.start('cold')
                coordinator.chunk.context[field] = value
                with self.assertRaisesRegex(ValueError, 'exact primitives'):
                    coordinator._progress_snapshot(0.)
        coordinator.chunk.context = NS(phase='bad')
        with self.assertRaisesRegex(ValueError, 'plain chunk context'):
            coordinator._progress_snapshot(0.)

    def test_no_active_owner_exposes_no_stale_chunk_or_owner_handle(self):
        coordinator = LoopDouble()
        coordinator.start('cold')
        coordinator.active = None
        snapshot = coordinator._progress_snapshot(0.)
        self.assertEqual(snapshot[3:8], (None,) * 5)

    def test_cadence_no_catchup_no_extra_clock_and_identical_work_controls(self):
        timestamps = [100., 100., 100.2, 100.9, 101., 101.1, 110., 110.1, 111.]
        snapshots = []
        hook = lambda c: {'response_ready': c.ticks % 2 == 0, 'ack_ready': True}
        baseline, clock0, _ = self.execute(timestamps, hook=hook)
        observed, clock1, _ = self.execute(timestamps, hook=hook,
            progress=lambda snapshot: snapshots.append(snapshot) or {'abort': True},
            progress_interval_seconds=1)
        self.assertEqual(baseline.log, observed.log)
        self.assertEqual(baseline.commands, observed.commands)
        self.assertEqual(clock0.calls, clock1.calls)
        self.assertEqual(clock1.calls, 9)
        self.assertEqual([s.elapsed_seconds for s in snapshots], [0., 1., 10., 11.])
        self.assertEqual([s.ticks for s in snapshots], [0, 3, 5, 7])
        self.assertEqual(observed.ticks, 8)

    def test_previous_committed_loop_has_same_default_timing_and_controls(self):
        original = ast.parse(BASELINE_SOURCE)
        cls = next(n for n in original.body if isinstance(n, ast.ClassDef) and n.name == 'FullBlockCoordinator')
        method = deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run_window'))
        namespace = {'require': F.require}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), namespace)
        for draining in (False, True):
            times = [0., 0., .5, 1.] if draining else [0., 0., .5, 1., 2.]
            old, new = LoopDouble(ticks=4, drain=draining), LoopDouble(ticks=4, drain=draining)
            hook = lambda c: {'ack_ready': c.ticks % 2 == 0}
            clock0, clock1 = Clock(times), Clock(times)
            namespace['time'] = clock0
            old_result = namespace['run_window'](old, 'cold', cold=True, expected_generation=0,
                budget_seconds=1 if draining else 10, hook=hook)
            with patch.object(F, 'time', clock1, create=True):
                new_result = new.run_window('cold', cold=True, expected_generation=0,
                    budget_seconds=1 if draining else 10, hook=hook)
            self.assertEqual(old.log, new.log)
            self.assertEqual(old_result.status, new_result.status)
            self.assertEqual(old.commands, new.commands)
            self.assertEqual(clock0.calls, clock1.calls)

    def test_callback_and_hook_order_before_tick(self):
        order = []
        coordinator = LoopDouble(ticks=1)
        def hook(c):
            order.append('hook')
            c.log.append(('hook',))
            return {'ack_ready': False}
        def progress(snapshot):
            order.append('progress')
            self.assertEqual(snapshot.ticks, 0)
            self.assertEqual(coordinator.log[-1], ('hook',))
        with patch.object(F, 'time', Clock([0., 0.]), create=True):
            coordinator.run_window('cold', cold=True, expected_generation=0,
                hook=hook, progress=progress)
        self.assertEqual(order, ['hook', 'progress'])
        self.assertEqual(coordinator.log[-1], ('tick', 0, {'ack_ready': False}))

    def test_timeout_abort_overrides_hook_without_changing_order(self):
        snapshots = []
        times = [0., 0., .5, 1.]
        hook = lambda c: {'abort': False, 'ack_ready': False}
        baseline, clock0, _ = self.execute(times, hook=hook, drain=True, budget_seconds=1)
        observed, clock1, result = self.execute(times, hook=hook, drain=True, budget_seconds=1,
            progress=snapshots.append, progress_interval_seconds=1)
        self.assertEqual(observed.log, baseline.log)
        self.assertEqual(clock0.calls, clock1.calls)
        self.assertEqual(observed.log[-1], ('tick', 2, {'abort': True}))
        self.assertEqual(result.status, 'Aborted')
        self.assertEqual([s.ticks for s in snapshots], [0, 2])

    def test_abort_drain_deadline_fails_before_hook_callback_or_tick(self):
        for progress_enabled in (False, True):
            coordinator = LoopDouble(ticks=100)
            hooks, snapshots = [], []
            with patch.object(F, 'time', Clock([0., 1., 61.]), create=True):
                with self.assertRaisesRegex(ValueError, 'abort drain exceeded'):
                    coordinator.run_window('cold', cold=True, expected_generation=0, budget_seconds=1,
                        hook=lambda c: hooks.append(c.ticks),
                        progress=snapshots.append if progress_enabled else None, progress_interval_seconds=1)
            self.assertEqual(hooks, [0])
            self.assertEqual(coordinator.ticks, 1)
            self.assertIsNone(coordinator.response)
            self.assertEqual(len(snapshots), int(progress_enabled))

    def test_callback_exception_has_no_tick_or_fabricated_terminal(self):
        coordinator = LoopDouble()
        def fail(snapshot):
            raise RuntimeError('observer stopped')
        with patch.object(F, 'time', Clock([0., 0.]), create=True):
            with self.assertRaisesRegex(RuntimeError, 'observer stopped'):
                coordinator.run_window('cold', cold=True, expected_generation=0, progress=fail)
        self.assertEqual(coordinator.ticks, 0)
        self.assertEqual(coordinator.commands, [])
        self.assertIsNone(coordinator.response)

    def test_invalid_cadence_and_existing_window_ceiling_before_start(self):
        for value in (0, -1, .1, True, float('nan'), float('inf'), 7201, '30'):
            coordinator = LoopDouble()
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'cadence'):
                coordinator.run_window('cold', cold=True, expected_generation=0,
                    progress=lambda s: None, progress_interval_seconds=value)
            self.assertEqual(coordinator.log, [])
        coordinator = LoopDouble()
        with self.assertRaisesRegex(ValueError, 'wall budget'):
            coordinator.run_window('cold', cold=True, expected_generation=0, budget_seconds=10800)
        self.assertEqual(coordinator.log, [])
        # Disabled telemetry does not interpret its otherwise-unused option.
        self.execute([0., 0.], ticks=1, progress_interval_seconds='unused')


class TickDouble(Coordinator):
    """Real coordinator tick/guard/commit, with explicit nonnumeric resources."""
    def __init__(self):
        self.events, self.commands, self.receipts, self.producer_hashes = [], [], {}, {}
        self.scalar = NS(op=object())
        self.vector = NS()
        self.matrix = NS(resource_address=123, lib=NS(matrix_accumulator_address=lambda: 123))
        self.rms, self.conv, self.prep, self.norm, self.elementwise = (
            NS(scalar=self.scalar) for _ in range(5))
        self.chunk = NS(scalar=self.scalar, vector=self.vector, host_batch=True, geometry=(16, 128, 128))
        self.memory = NS(regions={k: NS(published=False) for k in (1, 2, 3)})
        self.allocations = self.memory.regions.copy()
        self.resource_identity = self._resource_identity()
        self.roots = F.CommittedRoots()
        self.plan = {'history': 1, 'state': 2, 'output': 3}
        self._prepared_roots = F.CommittedRoots(1, 1, 2, 3)
        self.phase, self.role, self.response = 'cold', 'output', None
        self.ticks, self._index, self.aborted, self.locked = 0, 15, False, False
        self.held = NS(status=None)
        self.source_version = 'original'
        self.active = NS(owner=NS(ports=lambda: {'response': self.held}, state='finish', ticks=4),
            response=None, tick=self.driver_tick, report=lambda: {}, job=NS(tag=16),
            output=NS(base=3, raw=lambda: b'synthetic-test-only'))
        self.guards = 0

    def _resource_identity(self):
        self.guards = getattr(self, 'guards', 0) + 1
        return (id(self.scalar), self.scalar.op, id(self.matrix), id(self.vector))

    def start(self, *args, **kwargs):
        pass

    def _preflight_commit(self, held):
        self.events.append('preflight')
        self._check_resources()

    def driver_tick(self, **controls):
        self.events.append('driver_source_guard')
        F.require(self.source_version == 'original', 'synthetic source changed before acceptance')
        self.events.append('accept')
        self.active.response = self.held
        self.memory.regions[3].published = True
        return {'response_fire': True}

    def _commit(self):
        self.events.append('joint_commit')
        return super()._commit()


class GuardAndCommitTests(unittest.TestCase):
    def test_progress_is_outside_preflight_acceptance_joint_commit(self):
        coordinator = TickDouble()
        coordinator.observe = lambda *args: coordinator.events.append('terminal_observe')
        with patch.object(F, 'time', Clock([0., 0.]), create=True):
            coordinator.run_window('cold', cold=True, expected_generation=0,
                progress=lambda s: coordinator.events.append('progress'))
        self.assertEqual(coordinator.events, ['progress', 'preflight', 'driver_source_guard',
                                             'accept', 'joint_commit', 'terminal_observe'])
        self.assertEqual(coordinator.roots.generation, 1)
        self.assertTrue(all(region.published for region in coordinator.memory.regions.values()))
        self.assertEqual(len(coordinator.commands), 1)

    def test_persistent_arithmetic_resource_allocation_and_routing_mutations_trip_before_tick(self):
        mutations = (
            lambda c: setattr(c.scalar, 'op', object()),
            lambda c: setattr(c, 'vector', NS()),
            lambda c: c.memory.regions.update({4: NS(published=False)}),
            lambda c: setattr(c.rms, 'scalar', object()),
            lambda c: setattr(c.matrix, 'resource_address', 124))
        for mutate in mutations:
            coordinator = TickDouble()
            coordinator.observe = None
            with patch.object(F, 'time', Clock([0., 0.]), create=True):
                with self.assertRaises(ValueError):
                    coordinator.run_window('cold', cold=True, expected_generation=0,
                        progress=lambda s: mutate(coordinator))
            self.assertEqual(coordinator.events, [])
            self.assertEqual(coordinator.ticks, 0)
            self.assertEqual(coordinator.roots.generation, 0)
            self.assertEqual(coordinator.commands, [])
            self.assertIsNone(coordinator.response)

    def test_source_tripwire_precedes_acceptance_and_joint_commit(self):
        coordinator = TickDouble()
        coordinator.observe = None
        with patch.object(F, 'time', Clock([0., 0.]), create=True):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                coordinator.run_window('cold', cold=True, expected_generation=0,
                    progress=lambda s: setattr(coordinator, 'source_version', 'changed'))
        self.assertEqual(coordinator.events, ['preflight', 'driver_source_guard'])
        self.assertEqual(coordinator.roots.generation, 0)
        self.assertEqual(coordinator.commands, [])
        self.assertFalse(any(r.published for r in coordinator.memory.regions.values()))

    def test_no_progress_and_progress_preserve_guard_counts_and_terminal_work(self):
        runs = []
        for enabled in (False, True):
            coordinator = TickDouble()
            coordinator.observe = None
            with patch.object(F, 'time', Clock([0., 0.]), create=True):
                coordinator.run_window('cold', cold=True, expected_generation=0,
                    progress=(lambda s: None) if enabled else None)
            runs.append((coordinator.events, coordinator.guards, coordinator.ticks,
                         coordinator.roots, coordinator.commands))
        self.assertEqual(runs[0], runs[1])


class PublicRunTests(unittest.TestCase):
    def call(self, directory, *, times, fail=False, **kwargs):
        identity = dict(scalar_arithmetic_binding='synthetic', arithmetic_seal_schema='synthetic',
            chunk_exp_policy='legacy', chunk_exp_identity='synthetic', chunk_cumsum_policy='legacy',
            chunk_matmul_policy='legacy')
        calls = []
        class FakeCoordinator:
            def __init__(self, *args, **kw):
                self.roots, self.commands = NS(generation=0), []
            def run_window(self, phase, **kw):
                calls.append((phase, kw.copy()))
                if kw['progress'] is not None:
                    kw['progress'](F.FullBlockProgress(phase, 'input_norm', 0, 'idle', 0,
                        None, None, None, self.roots.generation, len(self.commands), 0.))
                if fail:
                    raise RuntimeError('owned progress failure')
                self.roots.generation += 1
                self.commands.extend(['synthetic'] * 16)
                return NS(status=None)
            def report(self):
                return dict(identity, roots={'generation': self.roots.generation})
        fixture = ModuleType('_cold.candidates.qwen35_gdn_prefill.input_fixture')
        fixture.ROOT = ROOT
        fixture.load_fixture = lambda *a: ({'sources': {'layer0_directory': directory}},
            {phase + '.hidden.bf16le': b'' for phase in ('cold128', 'carried128')})
        fixture.gdn = NS(load_payload=lambda *a: ({}, {}))
        matrix = ModuleType('_cold.candidates.qwen2_resident_matrix.ffn_attention.matrix_service')
        matrix.configure_library = lambda lib: lib
        verification = dict(source_unchanged=True, fixture_unchanged=True, library_unchanged=True,
                            vector_library_unchanged=True, identity_read_errors={})
        namespace = dict(__package__='_cold.candidates.qwen35_gdn_prefill',
            time=Clock(times), FullBlockCoordinator=FakeCoordinator,
            C=NS(CDLL=lambda path: NS(td_reset=lambda: 0)),
            d=NS(library_from_environment=lambda root: 'never-loaded', MatrixService=lambda lib: object()),
            _new_chunk_scalar=lambda *args: object(),
            freeze_identity=lambda *a, **kw: identity.copy(), final_identity=lambda *a: verification.copy(),
            rms=NS(ReductionPolicy=lambda value: NS(value=value)))
        with patch.dict(sys.modules, {fixture.__name__: fixture, matrix.__name__: matrix}), \
             patch.dict(F.__dict__, namespace):
            report = F.run('synthetic-fixture', Path(directory) / 'result', vector=object(), **kwargs)
        return report, calls

    def test_optional_window_cap_and_remaining_budget_propagation(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshots = []
            report, calls = self.call(directory, times=[0., 0., 4000., 6000.],
                budget_seconds=10800, window_budget_seconds=7200,
                progress=snapshots.append, progress_interval_seconds=17)
        self.assertEqual([kw['budget_seconds'] for _, kw in calls], [7200, 6800.])
        self.assertEqual([kw['expected_generation'] for _, kw in calls], [0, 1])
        self.assertEqual([kw['cold'] for _, kw in calls], [True, False])
        self.assertTrue(all(kw['progress_interval_seconds'] == 17 for _, kw in calls))
        self.assertEqual([s.generation for s in snapshots], [0, 1])
        self.assertEqual(report['terminal_count'], 32)

    def test_default_behavior_and_uncapped_legacy_budget_unchanged(self):
        for budget, expected in ((1800, [1800., 1700.]), (10800, [10800., 10700.])):
            with tempfile.TemporaryDirectory() as directory:
                _, calls = self.call(directory, times=[0., 0., 100., 200.], budget_seconds=budget)
            self.assertEqual([kw['budget_seconds'] for _, kw in calls], expected)
            self.assertTrue(all(kw['progress'] is None for _, kw in calls))
        # The double records the legacy >7200 propagation; the real window
        # admission test above proves that such an uncapped call still rejects.

    def test_invalid_window_caps_reject_before_creating_output(self):
        for cap in (0, -1, True, float('nan'), float('inf'), 7201, '7200'):
            with self.subTest(cap=cap), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, 'per-window'):
                    self.call(directory, times=[], window_budget_seconds=cap)
                self.assertFalse((Path(directory) / 'result').exists())

    def test_callback_exception_persists_owned_failed_summary_without_terminal(self):
        def broken(snapshot):
            raise RuntimeError('owned progress failure')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'owned progress failure'):
                self.call(directory, times=[0., 0., 1.], progress=broken)
            summary = json.loads((Path(directory) / 'result' / 'summary.json').read_text())
            self.assertEqual(summary['status'], 'FAILED')
            self.assertEqual(summary['roots']['generation'], 0)
            self.assertEqual(summary['output_files'], {})
            self.assertFalse((Path(directory) / 'result' / 'actual_terminal.json').exists())


class SourceInvarianceTests(unittest.TestCase):
    def test_all_arithmetic_guards_transport_commit_and_job_order_unchanged(self):
        base = ast.parse(BASELINE_SOURCE)
        def definitions(tree):
            return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        before, after = definitions(base), definitions(TREE)
        self.assertEqual(after.keys() - before.keys(), {'FullBlockProgress'})
        self.assertEqual(before.keys() - after.keys(), set())
        for name in before.keys() - {'run', 'FullBlockCoordinator'}:
            self.assertEqual(ast.dump(before[name]), ast.dump(after[name]), name)
        old = {n.name: n for n in before['FullBlockCoordinator'].body if isinstance(n, ast.FunctionDef)}
        new = {n.name: n for n in after['FullBlockCoordinator'].body if isinstance(n, ast.FunctionDef)}
        self.assertEqual(new.keys() - old.keys(), {'_progress_snapshot'})
        self.assertEqual(old.keys() - new.keys(), set())
        for name in old.keys() - {'run_window'}:
            self.assertEqual(ast.dump(old[name]), ast.dump(new[name]), name)
        def assignments(tree):
            return [ast.dump(n) for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))]
        self.assertEqual(assignments(base), assignments(TREE))

    def test_source_fixture_is_pinned_and_parsed_without_import(self):
        self.assertEqual(hashlib.sha256(BASELINE_BYTES).hexdigest(), BASELINE_SHA256)
        with self.assertRaisesRegex(ValueError, 'baseline SHA-256 mismatch'):
            baseline_source(BASELINE_BYTES + b' ')
        baseline = ast.parse(BASELINE_SOURCE)
        names = {node.name for node in baseline.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))}
        self.assertIn('FullBlockCoordinator', names)
        self.assertNotIn('FullBlockProgress', names)
        self.assertIn('run', names)



if __name__ == '__main__':
    unittest.main()
