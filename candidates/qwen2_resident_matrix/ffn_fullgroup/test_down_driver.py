"""Standalone synthetic Down tests, not actual-input or fullgroup evidence.

Compile the unchanged transposed_down arithmetic in a temporary work directory.
Synthetic act is initialized only through descriptor/data/ACK transactions;
constant input operands drive accepted physical packets. Expected outputs are
constructed and examined only after execute_down returns its terminal result.
No official payload, saved output, td_reference call or installed package is
used. Full production geometry is exercised only to its first input read.
"""
import ctypes as C
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


class DownDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WORK.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='down_driver_test_', dir=WORK)
        cls.out = Path(cls.temporary.name)
        source = TASK.parent / 'transposed_down/numeric_smoke.cpp'
        cls.arithmetic_source, cls.arithmetic_digest = source, hashlib.sha256(source.read_bytes()).hexdigest()
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


if __name__ == '__main__':
    unittest.main()
