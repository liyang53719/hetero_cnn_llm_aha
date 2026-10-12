"""Standalone synthetic Down tests, not actual-input or fullgroup evidence.

Reuse a source/binary-verified strict transposed_down library, or compile it in
a temporary work directory.
Legacy synthetic act is initialized through descriptor/data/ACK transactions.
Dense inputs use explicit readonly or prior-ACK-published physical spans.
Expected outputs are constructed and examined only after the driver returns
its terminal result.
No official payload, saved output, td_reference call or installed package is
used. Full production geometry is exercised only to its first input read.
"""
import ctypes as C
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest


sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
WORK = ROOT / 'work/qwen2_ffn_fullgroup_20261012'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


driver = load_module('down_driver_standalone_test', TASK / 'down_driver.py')
model = load_module('down_driver_standalone_model', TASK.parent / 'ffn_drain/model.py')
drain = load_module('down_driver_standalone_ddr', TASK.parent / 'ffn_drain/check_numeric.py')


class Trace:
    def __init__(self):
        self.digest, self.records = hashlib.sha256(), 0

    def event(self, value):
        self.digest.update((json.dumps(value, sort_keys=True) + '\n').encode())
        self.records += 1

    def report(self):
        return dict(sha256=self.digest.hexdigest(), records=self.records)


class FirstReadReached(Exception):
    pass


class NoArithmetic:
    def __getattr__(self, name):
        raise AssertionError('Arithmetic called during admission-only test: ' + name)


class SyntheticMemory:
    """Physical address dispatch over ACK-written act and constant BF16 weight."""
    def __init__(self, rows, k, n, *, stop_at_first_read=False):
        self.k, self.n, self.weight_base = k, n, 0x6000000
        self.stop_at_first_read = stop_at_first_read
        self.act = drain.DestinationMemory(rows, base=0xA000000, width=k)
        # 1.0 is a synthetic input, not an output/reference or saved tensor.
        sequence = 0
        for address in range(self.act.base, self.act.base + self.act.extent, 1024):
            beats = min(16, (self.act.base + self.act.extent - address) // 64)
            command = model.WriteCommand(address, beats, (0x414354 << 32) | sequence)
            self.act.accept_command(command)
            for index in range(beats):
                self.act.accept_data(model.WriteBeat((0x3f800000,) * 16, index + 1 == beats))
            self.act.accept_ack(model.WriteAck(command.tag, nbytes=beats * 64))
            sequence += 1
        assert self.act.pending is None and self.act.ack_bytes == self.act.extent
        assert self.act.write_addresses == set(range(self.act.base, self.act.base + self.act.extent, 64))

    def read64(self, address):
        if self.act.base <= address and address + 64 <= self.act.base + self.act.extent:
            assert self.act.pending is None and self.act.ack_bytes == self.act.extent
            assert address in self.act.write_addresses
            if self.stop_at_first_read:
                assert address == self.act.base
                raise FirstReadReached()
            return 'act', struct.unpack_from('<16I', self.act.data, 64 + address - self.act.base)
        if self.weight_base <= address and address + 64 <= self.weight_base + self.k * self.n * 2:
            return 'down_weight', (0x3f00,) * 32  # Synthetic BF16 0.5 input.
        raise AssertionError('Unexpected physical operand address')


def make_owner_job(rows, k, n, split):
    workspace = model.PrefixWorkspace(0x10000000, n // 32 * 16384, 123, split)
    owner = model.FfnDrainOwnerModel(workspace, enable_ffn_window=True,
        enable_ffn_tiles=True, enable_ffn_drain=True)
    owner.read_sequence, owner.write_sequence = 117, 379
    job = model.Job(m=rows, k=k, n=n, tag=0x51464703, a=0xA000000, b=0x6000000,
        dst=0xB000000, activation_bf16=False, weight_bf16=True, output_bf16=False,
        write_bytes=rows * n * 4)
    return owner, job


class SharedDenseMemory:
    """Synthetic address map with real staged writes, ACKs and publication.

    Labels deliberately differ from the historical act/down_weight labels.
    No output is initialized from its expected value or bulk-copied at finish.
    """
    def __init__(self):
        self.regions, self.events, self.early_reads_blocked = {}, [], 0

    def add_input(self, base, words, *, bf16=False):
        raw = struct.pack('<' + str(len(words)) + ('H' if bf16 else 'I'), *words)
        self.regions[base] = dict(raw=raw, extent=len(raw), bf16=bf16,
                                  provenance='readonly', published=True)

    def source(self, base):
        entry = self.regions[base]
        return driver.DenseSource(base, entry['extent'], entry['provenance'],
            ready=lambda: entry['published'], raw=lambda: self.raw(base),
            write_acks=lambda: tuple(entry.get('write_acks', ())))

    def raw(self, base):
        entry = self.regions[base]
        if 'destination' in entry:
            return bytes(entry['destination'].data[64:-64])
        return entry['raw']

    def read64(self, address):
        matches = [(base, entry) for base, entry in self.regions.items()
                   if base <= address and address + 64 <= base + entry['extent']]
        driver.require(len(matches) == 1, 'shared physical address must select exactly one region')
        base, entry = matches[0]
        driver.require(entry['published'], 'shared physical output is not published')
        return 'shared_physical_' + str(base), struct.unpack_from(
            '<32H' if entry['bf16'] else '<16I', self.raw(base), address - base)

    def output_sink(self, job, owner, *, fail_on=None):
        destination = drain.DestinationMemory(job.m, base=job.dst, width=job.n)
        entry = dict(destination=destination, extent=destination.extent, bf16=False,
                     provenance='published', published=False, write_acks=[])
        self.regions[job.dst] = entry

        def event(kind, value):
            self.events.append((kind, value, owner.clock))
            if kind == 'command':
                destination.accept_command(value)
            elif kind == 'data':
                # The inherited ordinary port has an implicit full mask.
                destination.accept_data(model.WriteBeat(value.words, value.last))
            elif kind == 'ack':
                command = destination.pending
                destination.accept_ack(value)
                entry['write_acks'].append((command, value))
            elif kind == 'terminal':
                driver.require(owner.state == 'idle' and value == (job.tag, None, job.write_bytes),
                               'shared output terminal identity')
                driver.require(destination.pending is None and
                               destination.ack_bytes == destination.data_bytes == destination.extent,
                               'shared output terminal before full physical ACKs')
                entry['published'] = True
            else:
                raise AssertionError('unexpected output event')
            if kind != 'terminal':
                try:
                    self.read64(job.dst)
                except ValueError as exc:
                    assert 'not published' in str(exc)
                    self.early_reads_blocked += 1
                else:
                    raise AssertionError('shared physical output readable before terminal')
            if kind == fail_on:
                raise ValueError('injected shared output fault')
        return event


class DownDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WORK.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='down_driver_test_', dir=WORK)
        cls.out = Path(cls.temporary.name)
        source = TASK.parent / 'transposed_down/numeric_smoke.cpp'
        cls.arithmetic_source, cls.arithmetic_digest = source, hashlib.sha256(source.read_bytes()).hexdigest()
        library = None
        # Reuse only an existing binary tied to an identical frozen source and
        # strict compile receipt. This reads no historical tensor or result.
        cached = WORK / 'actual_m128_01'
        receipt_path = cached / 'summary.json'
        frozen_source = cached / 'frozen_sources' / source.relative_to(ROOT)
        cached_library = cached / 'numeric_recipe.so'
        if all(path.is_file() for path in (receipt_path, frozen_source, cached_library)):
            compiled = json.loads(receipt_path.read_text())['compile']
            if (hashlib.sha256(frozen_source.read_bytes()).hexdigest() == cls.arithmetic_digest and
                    hashlib.sha256(cached_library.read_bytes()).hexdigest() == compiled['binary_sha256'] and
                    {'-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math'} <= set(compiled['argv'])):
                library = cached_library
        if library is None:
            library = cls.out / 'numeric_smoke.so'
            command = ['g++', '-std=c++17', '-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math',
                       '-fPIC', '-shared', str(source), '-o', str(library)]
            with (cls.out / 'compile.log').open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
        cls.lib = C.CDLL(str(library))
        u16, u32 = C.POINTER(C.c_uint16), C.POINTER(C.c_uint32)
        for name, args in (
            ('td_reset', []), ('td_group', [C.c_uint] * 3),
            ('td_seed_begin', [C.c_uint]), ('td_seed_beat', [C.c_uint, C.c_uint, u32]),
            ('td_seed_commit', [C.c_uint]), ('td_step', [C.c_uint] * 6 + [u16, u16, u32])):
            getattr(cls.lib, name).argtypes, getattr(cls.lib, name).restype = args, C.c_int

    @classmethod
    def tearDownClass(cls):
        try:
            assert hashlib.sha256(cls.arithmetic_source.read_bytes()).hexdigest() == cls.arithmetic_digest
        finally:
            cls.temporary.cleanup()

    def case_dir(self, name):
        path = self.out / name
        path.mkdir()
        return path

    def test_physical_region_sentinel_bounds_and_guards(self):
        region = driver.PhysicalRegion(0x10000, 128)
        self.assertEqual(region.read64(region.base), (driver.SENTINEL_WORD,) * 16)
        region.write64(region.base + 64, tuple(range(16)))
        self.assertEqual(region.read64(region.base + 64), tuple(range(16)))
        for address in (region.base - 64, region.base + 1, region.base + 128):
            with self.subTest(address=address), self.assertRaises(ValueError):
                region.read64(address)
        with self.assertRaises(ValueError):
            region.write64(region.base, (0,) * 15)
        with self.assertRaises(ValueError):
            region.write64(region.base, (1 << 32,) * 16)
        region.check_guards()

    def test_capped_records_hash_all_bytes_and_preserve_prefix(self):
        path = self.out / 'capped_records.bin'
        records = driver.CappedRecords(path, cap=10)
        try:
            for raw in (b'12345678', b'abc', b'x'):
                records.write(raw)
            report = records.report()
        finally:
            records.close()
        self.assertEqual(path.read_bytes(), b'12345678')
        self.assertEqual(report['sha256'], hashlib.sha256(b'12345678abcx').hexdigest())
        self.assertEqual((report['records'], report['total_bytes_hashed']), (3, 12))

    def test_physical_prefix_permutation_is_complete(self):
        self.assertEqual(sorted(model.down.prefix_ddr_beat(index) for index in range(256)), list(range(256)))

    def test_production_default_rejects_tiny_geometry(self):
        owner, job = make_owner_job(16, 256, 32, 128)
        memory = SyntheticMemory(16, 256, 32)
        with self.assertRaisesRegex(ValueError, 'full Down requires'):
            driver.execute_down(model, owner, NoArithmetic(), memory, job,
                                self.case_dir('rejected_default'), time.monotonic() + 5, Trace())
        self.assertEqual(owner.clock, 0)

    def test_synthetic_geometry_rejects_unapproved_shape(self):
        owner, job = make_owner_job(16, 384, 32, 128)
        memory = SyntheticMemory(16, 384, 32)
        with self.assertRaisesRegex(ValueError, 'synthetic Down restricted'):
            driver.execute_down(model, owner, NoArithmetic(), memory, job,
                self.case_dir('rejected_synthetic'), time.monotonic() + 5, Trace(), synthetic_geometry=True)
        self.assertEqual(owner.clock, 0)

    def test_admission_rejects_retained_lease(self):
        owner, job = make_owner_job(16, 256, 32, 128)
        owner.lease = object()
        memory = SyntheticMemory(16, 256, 32)
        with self.assertRaisesRegex(ValueError, 'lease invalidation'):
            driver.execute_down(model, owner, NoArithmetic(), memory, job,
                self.case_dir('rejected_lease'), time.monotonic() + 5, Trace(), synthetic_geometry=True)
        self.assertEqual(owner.clock, 0)

    def test_production_m16_and_m128_admission_only(self):
        for rows in (16, 128):
            with self.subTest(rows=rows):
                owner, job = make_owner_job(rows, 8960, 1536, 2560)
                memory = SyntheticMemory(rows, 8960, 1536, stop_at_first_read=True)
                before = (id(owner), id(owner.a_banks), id(owner.b_banks))
                with self.assertRaises(FirstReadReached):
                    driver.execute_down(model, owner, NoArithmetic(), memory, job,
                        self.case_dir('admission_m%d' % rows), time.monotonic() + 5, Trace())
                self.assertEqual((id(owner), id(owner.a_banks), id(owner.b_banks)), before)
                self.assertEqual((owner.read_sequence, owner.write_sequence), (117, 379))
                self.assertEqual(owner.read_active[0].address, memory.act.base)
                self.assertIsNone(owner.error)
                self.assertEqual(owner.accepted_steps, 0)

    def run_synthetic(self, k):
        owner, job = make_owner_job(16, k, 32, 128)
        memory = SyntheticMemory(16, k, 32)
        target = self.case_dir('synthetic_k%d' % k)
        self.assertEqual(self.lib.td_reset(), 0)
        report, actual = driver.execute_down(model, owner, self.lib, memory, job, target,
            time.monotonic() + 10, Trace(), synthetic_geometry=True)
        # Comparison is deliberately after the actual driver terminal.
        # Repeated 1.0 * 0.5 is exactly representable for these tiny K values.
        expected = struct.unpack('<I', struct.pack('<f', k / 2))[0]
        self.assertEqual(list(actual), [expected] * (16 * 32))
        for snapshot in report['prefix']['physical_sweeps']:
            words = struct.unpack('<4096I', (target / snapshot['path']).read_bytes())
            active = struct.unpack('<I', struct.pack('<f', snapshot['version'] * 64.0))[0]
            for row in range(128):
                for col in range(32):
                    physical_row, physical_col = model.down.output_coordinate(row, col)
                    self.assertEqual(words[physical_row * 256 + physical_col], active if row < 16 else 0)
        self.assertEqual(report['scope'], 'SYNTHETIC_TINY_DOWN_HOST_MODEL_ONLY')
        self.assertEqual(report['accepted']['completed_host_physical_fmas'], k * 4096)
        self.assertEqual(report['accepted']['observed_valid_logical_cells'], k * 16 * 32)
        self.assertEqual(report['final_ack_fence']['held_ticks'], 5)
        self.assertGreater(report['final_ack_fence']['terminal_tick'], report['final_ack_fence']['final_ack_tick'])
        self.assertEqual(report['prefix']['completed_sweeps'], k // 128 - 1)
        for version in report['prefix']['versions'].values():
            self.assertEqual(version, dict(ack_beats=256, read_beats=256, seed_beats=256))
        self.assertTrue(report['prefix']['seed_ack_before_overwrite'])
        self.assertTrue(report['ddr']['implicit_mask_observed'])
        self.assertFalse(report['ddr']['explicit_mask_observed'])
        self.assertFalse(report['reference_arithmetic_executed'])
        self.assertFalse(report['saved_phase13_decoded'])

    def test_synthetic_two_chunks(self):
        self.run_synthetic(256)

    def test_synthetic_four_chunks(self):
        self.run_synthetic(512)

    def dense_case(self, name, *, rows=16, k=32, n=32, split=2560, extent=64):
        owner, job = make_owner_job(rows, k, n, split)
        owner.workspace = replace(owner.workspace, extent=extent)
        memory = SharedDenseMemory()
        memory.add_input(job.a, [0x3f800000] * (rows * k))
        memory.add_input(job.b, [0x3f00] * (k * n), bf16=True)
        return owner, job, memory, self.case_dir(name)

    def test_dense_single_chunk_no_prefix_and_real_output_events(self):
        owner, job, memory, target = self.dense_case('dense_no_prefix', k=48, n=256)
        identity = (id(owner), id(owner.a_banks), id(owner.b_banks), id(owner.workspace))
        edges = []
        def tick(**inputs):
            edges.append(inputs)
            return owner.tick(**inputs)
        self.assertEqual(self.lib.td_reset(), 0)
        report, actual = driver.execute_dense(model, owner, self.lib, memory, job, target,
            time.monotonic() + 10, Trace(), a_source=memory.source(job.a),
            output_event=memory.output_sink(job, owner), owner_tick=tick)
        expected = struct.pack('<f', 24.0) * (job.m * job.n)
        self.assertEqual(actual.raw(), expected)
        self.assertEqual(memory.raw(job.dst), actual.raw())
        self.assertEqual(identity, (id(owner), id(owner.a_banks), id(owner.b_banks), id(owner.workspace)))
        self.assertEqual(report['prefix']['active_extent'], 0)
        self.assertEqual(report['prefix']['completed_sweeps'], 0)
        self.assertEqual(report['prefix']['ack_bytes'], 0)
        self.assertEqual(report['prefix']['versions'], {})
        self.assertEqual(report['prefix']['seed_records']['records'], 0)
        self.assertFalse(any('seed_ack' in edge for edge in edges))
        self.assertEqual(report['owner_counter_deltas']['responses'], 1)
        self.assertEqual(report['owner_counter_deltas']['groups'], 2)
        self.assertEqual(len(edges), report['protocol_model_ticks'])
        self.assertEqual(report['final_ack_fence']['held_ticks'], 5)
        self.assertGreater(memory.events[-1][2], [e[2] for e in memory.events if e[0] == 'ack'][-1])
        self.assertEqual(memory.events[-1][0], 'terminal')
        self.assertGreater(memory.early_reads_blocked, 0)
        self.assertTrue(memory.regions[job.dst]['published'])
        self.assertFalse(report['protocol_model_ticks_are_hardware_cycles'])

    def test_dense_same_owner_published_output_feeds_next_job(self):
        owner, first, memory, target = self.dense_case('dense_first', k=32, n=64, extent=16384)
        self.assertEqual(self.lib.td_reset(), 0)
        report1, actual1 = driver.execute_dense(model, owner, self.lib, memory, first, target,
            time.monotonic() + 10, Trace(), a_source=memory.source(first.a),
            output_event=memory.output_sink(first, owner))
        second = replace(first, a=first.dst, b=0x7000000, dst=0xC000000, k=64, n=32,
                         tag=first.tag + 1, write_bytes=16 * 32 * 4)
        memory.add_input(second.b, [0x3f00] * (second.k * second.n), bf16=True)
        before = (owner.clock, owner.read_sequence, owner.write_sequence, owner.group_sequence, owner.responses)
        # No owner or arithmetic reset between ordinary jobs.
        report2, actual2 = driver.execute_dense(model, owner, self.lib, memory, second,
            self.case_dir('dense_second'), time.monotonic() + 10, Trace(), a_source=memory.source(second.a),
            output_event=memory.output_sink(second, owner))
        self.assertEqual(actual1.raw(), struct.pack('<f', 16.0) * (16 * 64))
        self.assertEqual(actual2.raw(), struct.pack('<f', 512.0) * (16 * 32))
        self.assertEqual(memory.raw(second.dst), actual2.raw())
        self.assertEqual(report2['actual_a_source']['sha256'], report1['ddr']['sha256'])
        self.assertTrue(report2['actual_a_source']['actual_prior_ack_written'])
        self.assertEqual(report2['actual_a_source']['provenance'], 'published')
        self.assertEqual(report2['owner_start_tick'], before[0])
        self.assertEqual(report2['owner_counter_deltas'], dict(read_descriptors=128,
            write_descriptors=16, groups=1, responses=1))
        self.assertEqual(report2['accepted']['accepted_steps'], 64)
        self.assertEqual(report2['actual_a_rmw_commits'], 16 * 64)
        self.assertEqual(owner.responses, before[-1] + 1)

    def test_dense_multi_chunk_uses_capacity_without_changing_workspace(self):
        owner, job, memory, target = self.dense_case('dense_spare_prefix', k=272,
                                                   split=128, extent=3 * 16384)
        workspace = owner.workspace
        self.assertEqual(self.lib.td_reset(), 0)
        report, actual = driver.execute_dense(model, owner, self.lib, memory, job, target,
            time.monotonic() + 10, Trace(), a_source=memory.source(job.a),
            output_event=memory.output_sink(job, owner))
        self.assertIs(owner.workspace, workspace)
        self.assertEqual(actual.raw(), struct.pack('<f', 136.0) * (16 * 32))
        self.assertEqual(report['prefix']['extent'], 3 * 16384)
        self.assertEqual(report['prefix']['active_extent'], 16384)
        self.assertEqual(report['prefix']['ack_bytes'], 2 * 16384)
        self.assertEqual(report['prefix']['completed_sweeps'], 2)

    def test_dense_admits_target_shapes_only_to_first_read(self):
        for n in (256, 1536):
            owner, job, memory, target = self.dense_case('dense_admit_' + str(n), rows=128,
                                                        k=1536, n=n, extent=786432)
            def stop(address):
                self.assertEqual(address, job.a)
                raise FirstReadReached()
            memory.read64 = stop
            with self.assertRaises(FirstReadReached):
                driver.execute_dense(model, owner, NoArithmetic(), memory, job, target,
                    time.monotonic() + 5, Trace(), a_source=memory.source(job.a),
                    output_event=memory.output_sink(job, owner))
            self.assertEqual(owner.accepted_steps, 0)

    def test_dense_rechecks_source_readiness_at_admission(self):
        owner, job, memory, target = self.dense_case('dense_recheck')
        calls = iter((True, False))
        source = replace(memory.source(job.a), ready=lambda: next(calls))
        with self.assertRaisesRegex(ValueError, 'not ready'):
            driver.execute_dense(model, owner, NoArithmetic(), memory, job, target,
                time.monotonic() + 5, Trace(), a_source=source,
                output_event=memory.output_sink(job, owner))
        self.assertEqual(owner.clock, 0)

    def test_dense_rejects_claimed_publication_without_actual_ack_records(self):
        owner, job, memory, target = self.dense_case('dense_missing_ack')
        source = replace(memory.source(job.a), provenance='published')
        with self.assertRaisesRegex(ValueError, 'lacks full prior physical write ACK coverage'):
            driver.execute_dense(model, owner, NoArithmetic(), memory, job, target,
                time.monotonic() + 5, Trace(), a_source=source,
                output_event=memory.output_sink(job, owner))
        self.assertEqual(owner.clock, 0)

    def test_dense_fault_after_actual_write_ack_never_publishes(self):
        owner, job, memory, target = self.dense_case('dense_sink_fault', n=64)
        self.assertEqual(self.lib.td_reset(), 0)
        with self.assertRaisesRegex(ValueError, 'injected shared output fault'):
            driver.execute_dense(model, owner, self.lib, memory, job, target,
                time.monotonic() + 10, Trace(), a_source=memory.source(job.a),
                output_event=memory.output_sink(job, owner, fail_on='ack'))
        self.assertGreater(memory.regions[job.dst]['destination'].ack_bytes, 0)
        self.assertFalse(memory.regions[job.dst]['published'])
        self.assertFalse(any(kind == 'terminal' for kind, _, _ in memory.events))
        self.assertFalse((target / 'actual_dense.f32le').exists())

    def test_dense_actual_nonuniform_address_payloads_and_tail_group(self):
        owner, job, memory, target = self.dense_case('dense_nonuniform', k=16, n=192)
        memory.add_input(job.a, [struct.unpack('<I', struct.pack('<f', row + 1))[0]
                                for row in range(job.m) for _ in range(job.k)])
        memory.add_input(job.b, [struct.unpack('<I', struct.pack('<f',
            (k % 2 + 1) * (n % 3 + 1) / 2))[0] >> 16
            for k in range(job.k) for n in range(job.n)], bf16=True)
        self.assertEqual(self.lib.td_reset(), 0)
        report, actual = driver.execute_dense(model, owner, self.lib, memory, job, target,
            time.monotonic() + 10, Trace(), a_source=memory.source(job.a),
            output_event=memory.output_sink(job, owner))
        expected = b''.join(struct.pack('<f', 12 * (row + 1) * (n % 3 + 1))
                            for row in range(job.m) for n in range(job.n))
        self.assertEqual(actual.raw(), expected)
        self.assertEqual([group['contexts'] for group in report['groups']], [5, 1])

    def test_dense_small_m128_complete_uses_all_physical_rows(self):
        owner, job, memory, target = self.dense_case('dense_m128_small', rows=128, k=16)
        self.assertEqual(self.lib.td_reset(), 0)
        report, actual = driver.execute_dense(model, owner, self.lib, memory, job, target,
            time.monotonic() + 10, Trace(), a_source=memory.source(job.a),
            output_event=memory.output_sink(job, owner))
        self.assertEqual(actual.raw(), struct.pack('<f', 8.0) * (128 * 32))
        self.assertEqual(report['useful_macs'], report['executed_macs'])

    def test_dense_preserves_workspace_capacity_and_alias_rejections(self):
        for name, k, extent, base in (('capacity', 256, 64, 0x10000000),
                                     ('alias', 32, 64, 0xA000000)):
            with self.subTest(name=name):
                owner, job, memory, target = self.dense_case('dense_bad_' + name,
                    k=k, split=128, extent=extent)
                owner.workspace = replace(owner.workspace, base=base)
                with self.assertRaisesRegex(ValueError, 'prefix workspace'):
                    driver.execute_dense(model, owner, NoArithmetic(), memory, job, target,
                        time.monotonic() + 5, Trace(), a_source=memory.source(job.a),
                        output_event=memory.output_sink(job, owner))
                self.assertEqual(owner.clock, 0)

    def test_dense_rejects_corrupt_prior_publication_ack(self):
        owner, job, memory, target = self.dense_case('dense_bad_prior_ack')
        command = model.WriteCommand(job.a, 16, 9)
        source = replace(memory.source(job.a), provenance='published',
                         write_acks=lambda: [(command, model.WriteAck(10, nbytes=1024))])
        with self.assertRaisesRegex(ValueError, 'malformed prior physical write ACK'):
            driver.execute_dense(model, owner, NoArithmetic(), memory, job, target,
                time.monotonic() + 5, Trace(), a_source=source,
                output_event=memory.output_sink(job, owner))
        self.assertEqual(owner.clock, 0)

    def test_dense_source_mutation_prevents_terminal_publication(self):
        owner, job, memory, target = self.dense_case('dense_source_mutation')
        sink = memory.output_sink(job, owner)
        def event(kind, value):
            sink(kind, value)
            if kind == 'ack':
                memory.regions[job.a]['raw'] = struct.pack('<I', 0x40000000) * (job.m * job.k)
        self.assertEqual(self.lib.td_reset(), 0)
        with self.assertRaisesRegex(ValueError, 'source act mutation'):
            driver.execute_dense(model, owner, self.lib, memory, job, target,
                time.monotonic() + 10, Trace(), a_source=memory.source(job.a), output_event=event)
        self.assertEqual(owner.state, 'idle')
        self.assertFalse(memory.regions[job.dst]['published'])
        self.assertFalse(any(kind == 'terminal' for kind, _, _ in memory.events))


if __name__ == '__main__':
    unittest.main()
