"""Clean-checkout numeric recipe and capture guards; no local tensors required."""
from array import array
import ctypes as C
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ffn_window_numeric_check_tests", HERE / "check_numeric.py")
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check
spec.loader.exec_module(check)


def bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


class RecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ffn_window_recipe_")
        cls.pins = check.load_pins(check_provenance=False)
        cls.lib, cls.compile = check.build_library(Path(cls.temp.name), cls.pins)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_verbatim_physical_mapping_returns_dot(self):
        # K16 synthetic protocol test: all physical outputs have exact sum16.
        self.assertEqual(self.lib.td_reset(), 0)
        self.assertEqual(self.lib.td_group(0, 16, 1), 0)
        a = (C.c_uint16 * 16)(*([0x3f80] * 16))
        b = (C.c_uint16 * 256)(*([0x3f80] * 144 + [0] * 112))
        output = (C.c_uint32 * 4096)()
        for k in range(16):
            end = int(k == 15)
            self.assertEqual(self.lib.td_step(k, 0, int(k == 0), end, end, end, a, b, output), end)
        self.assertEqual(list(output), [bits(16.)] * 4096)

    def test_physical_recipe_rejects_nonsequential_k(self):
        self.assertEqual(self.lib.td_group(0, 16, 1), 0)
        a, b, output = (C.c_uint16 * 16)(), (C.c_uint16 * 256)(), (C.c_uint32 * 4096)()
        self.assertEqual(self.lib.td_step(1, 0, 0, 0, 0, 0, a, b, output), -1)

    def test_physical_recipe_rejects_nonzero_padding(self):
        self.assertEqual(self.lib.td_group(0, 16, 1), 0)
        a, b, output = (C.c_uint16 * 16)(), (C.c_uint16 * 256)(), (C.c_uint32 * 4096)()
        b[255] = 1
        self.assertEqual(self.lib.td_step(0, 0, 1, 0, 0, 0, a, b, output), -2)

    def test_independent_reference_uses_ng_output_major_stride(self):
        # Sparse synthetic arrays keep the test light while distinguishing N/K.
        a = (C.c_uint32 * (16 * check.K))()
        weights = (C.c_uint16 * (64 * check.K))()
        out = (C.c_uint32 * (16 * 32))()
        for m in range(16):
            a[m * check.K + 17] = bits(float(m + 1))
        for n in range(32, 64):
            weights[n * check.K + 17] = bits(float(n - 31)) >> 16
        self.assertEqual(self.lib.fw_reference(a, weights, out, 16, 32, 32), 0)
        self.assertEqual(list(out), [bits(float((m + 1) * (n + 1))) for m in range(16) for n in range(32)])

    def test_unchanged_silu_vector_equals_flat(self):
        gate = (C.c_uint32 * 16)(*[bits((i - 8) / 2) for i in range(16)])
        up = (C.c_uint32 * 16)(*[bits(1 + i / 8) for i in range(16)])
        out, ref = (C.c_uint32 * 16)(), (C.c_uint32 * 16)()
        values, flags, errors = (C.c_uint32 * 96)(), (C.c_uint32 * 96)(), (C.c_uint32 * 16)()
        self.assertEqual(self.lib.sf_vector(gate, up, out, values, flags, errors), 0)
        self.assertEqual(self.lib.sf_reference(gate, up, ref, 16), 0)
        self.assertEqual(list(out), list(ref))


class AddressTests(unittest.TestCase):
    def test_internal_dma_tag_trace_preserves_job_and_sequence(self):
        tag = (0xf1234567 << 32) | 0x89abcdef
        command = SimpleNamespace(kind="b", address=0x4000000, beats=1, tag=tag)
        record = check.descriptor_record(command)
        self.assertEqual(struct.unpack("<cQIQ", record), (b"b", 0x4000000, 1, tag))

    def test_virtual_ddr_selects_weight_only_by_address(self):
        inputs = {"n1": array("I", [bits(1)] * (128 * check.K)),
                  "gate_weight": array("H", [0x3f80] * (32 * check.K)),
                  "up_weight": array("H", [0x4000] * (32 * check.K))}
        memory = check.SourceMemory(inputs)
        self.assertEqual(memory.read64(check.SOURCE_BASES["gate_weight"]), ("gate_weight", (0x3f80,) * 32))
        self.assertEqual(memory.read64(check.SOURCE_BASES["up_weight"]), ("up_weight", (0x4000,) * 32))
        self.assertEqual(memory.read64(check.SOURCE_BASES["n1"]), ("n1", (bits(1),) * 16))
        with self.assertRaisesRegex(ValueError, "unmapped"):
            memory.read64(check.DESTINATION_BASES["gate"])

    def test_full_n_stride_and_nonzero_window(self):
        k = 16
        raw = array("I", range(224 * k))
        base, ng = 0x2000000, 160
        address = base + (7 * check.SOURCE_N + ng + 32) * 2
        self.assertEqual(check.weight_response(raw, address, base, k, ng, 64),
                         tuple((ng + 32 + lane) * k + 7 for lane in range(32)))

    def test_wrong_compact_stride_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "escaped"):
            check.weight_response(array("H", [0] * (224 * 16)), 0x2000000 + (64 + 160) * 2,
                                  0x2000000, 16, 160, 64)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ffn_window_capture_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pins = json.loads((HERE / "precision_pins.json").read_text())
        for name in self.pins["sources"]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((check.ROOT / name).read_bytes())

    def test_unit_recipe_mode_does_not_require_local_work(self):
        self.assertFalse((self.root / "work").exists())
        with patch.object(check, "ROOT", self.root):
            self.assertEqual(check.load_pins(False)["sources"], self.pins["sources"])

    def test_actual_default_requires_local_provenance(self):
        with patch.object(check, "ROOT", self.root):
            with self.assertRaises(FileNotFoundError):
                check.load_pins()

    def test_actual_default_rejects_drifted_provenance(self):
        for name in self.pins["provenance"]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"changed provenance")
        with patch.object(check, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "frozen source identity drift: work/"):
                check.load_pins()

    def test_arithmetic_source_drift_rejected_even_without_provenance(self):
        path = self.root / next(iter(self.pins["sources"]))
        path.write_bytes(b"changed source")
        with patch.object(check, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "frozen source identity drift:"):
                check.load_pins(False)

    def test_post_capture_source_drift_is_fatal(self):
        path = self.root / "model.py"
        path.write_bytes(b"changed source")
        report = {"source_sha256": {"model.py": check.sha(b"original source")}}
        with patch.object(check, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "source changed during frozen"):
                check.verify_capture_sources(report)
        self.assertEqual(report["source_changed_since_freeze"], ["model.py"])


if __name__ == "__main__":
    unittest.main()
