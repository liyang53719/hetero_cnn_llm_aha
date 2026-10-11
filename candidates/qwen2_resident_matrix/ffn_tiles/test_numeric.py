"""Small host recipe/domain tests; these do not run actual producer tiles."""
import ctypes as C
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ffn_numeric_check", HERE / "check_numeric.py")
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check
spec.loader.exec_module(check)


def bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


class RecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ffn_silu_test_")
        cls.pins = check.load_pins(check_provenance=False)
        cls.lib, cls.compile = check.build_library(Path(cls.tmp.name), cls.pins)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def vector(self, gate, up):
        gate = (C.c_uint32 * 16)(*gate)
        up = (C.c_uint32 * 16)(*up)
        out, values, flags, errors = (C.c_uint32 * 16)(), (C.c_uint32 * 96)(), (C.c_uint32 * 96)(), (C.c_uint32 * 16)()
        status = self.lib.sf_vector(gate, up, out, values, flags, errors)
        return status, list(out), list(values), list(flags), list(errors)

    def test_original_source_helpers_pinned(self):
        self.assertEqual(self.pins["sources"]["chisel/continuous_prefill/tests/qwen2_block.cpp"],
                         "d757e1271210e260ca320cddf4175c306d3cf52835ea45f20ca9dfb56ac34db5")

    def test_vector_equals_flat_with_branch_and_saturation(self):
        gates = [bits(x) for x in (0., -0., 1., -1., 2., -2., 5., -5., 12., -12., 79., -79., 80., -80., 100., -100.)]
        ups = [bits(0.5 + i / 16) for i in range(16)]
        status, output, values, flags, errors = self.vector(gates, ups)
        self.assertEqual(status, 0)
        self.assertEqual(errors, [0] * 16)
        reference = (C.c_uint32 * 16)()
        self.assertEqual(self.lib.sf_reference((C.c_uint32 * 16)(*gates), (C.c_uint32 * 16)(*ups), reference, 16), 0)
        self.assertEqual(output, list(reference))
        self.assertEqual(output[0], 0)
        self.assertEqual(output[1], 0x80000000)
        self.assertEqual(output[13], 0x80000000)
        self.assertEqual(output[15], 0x80000000)
        self.assertTrue(all(value == 0 for value in values[12:16]))
        self.assertTrue(all(flag & 30 == 0 for flag in flags[16:]))

    def test_legacy_mul_underflow_is_fatal(self):
        status, output, values, flags, errors = self.vector([bits(1)] * 16, [1] * 16)
        self.assertEqual(status, 6)
        self.assertEqual(errors, [1 << 5] * 16)
        self.assertTrue(all(flag & 2 for flag in flags[80:96]))

    def test_exact_subnormal_is_not_flushed_or_rejected(self):
        status, output, values, flags, errors = self.vector([bits(80)] * 16, [1] * 16)
        self.assertEqual(status, 0)
        self.assertEqual(output, [80] * 16)
        self.assertEqual(errors, [0] * 16)
        self.assertEqual(flags[80:96], [0] * 16)

    def test_legacy_mul_overflow_is_fatal(self):
        status, output, values, flags, errors = self.vector([bits(80)] * 16, [0x7f7fffff] * 16)
        self.assertEqual(status, 6)
        self.assertEqual(errors, [1 << 5] * 16)
        self.assertTrue(all(flag & 4 for flag in flags[80:96]))

    def test_nonfinite_input_is_rejected(self):
        for value in (0x7f800000, 0xff800000, 0x7fc00001):
            status, output, values, flags, errors = self.vector([value] * 16, [bits(1)] * 16)
            self.assertEqual(status, -1)
            self.assertEqual(errors, [64] * 16)

    def test_source_column_identity_is_not_group_number(self):
        source = list(range(16 * 8960))
        flat = check.flat_tile(source, 16, 96, 8864)
        self.assertEqual(flat[:96], tuple(source[8864:8960]))
        self.assertEqual(check.beat_from_flat(flat, 95, 96), tuple(m * 8960 + 8959 for m in range(16)))


class CaptureGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ffn_capture_guard_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pins = json.loads((check.TASK / "precision_pins.json").read_text())
        # Only tracked arithmetic sources are copied; no local work products.
        for name in self.pins["sources"]:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((check.ROOT / name).read_bytes())

    def test_recipe_pins_load_without_work_directory(self):
        self.assertFalse((self.root / "work").exists())
        with patch.object(check, "ROOT", self.root):
            self.assertEqual(check.load_pins(check_provenance=False)["sources"], self.pins["sources"])

    def test_actual_default_rejects_missing_provenance(self):
        with patch.object(check, "ROOT", self.root):
            with self.assertRaises(FileNotFoundError):
                check.load_pins()

    def test_actual_default_rejects_drifted_provenance(self):
        for name in self.pins["provenance"]:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"deliberately drifted provenance\n")
        with patch.object(check, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "frozen source identity drift: work/"):
                check.load_pins()

    def test_recipe_mode_still_rejects_arithmetic_source_drift(self):
        target = self.root / next(iter(self.pins["sources"]))
        target.write_bytes(target.read_bytes() + b"\n// deliberate drift\n")
        with patch.object(check, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "frozen source identity drift: chisel/"):
                check.load_pins(check_provenance=False)

    def test_capture_source_drift_is_fatal(self):
        name = "model.py"
        report = {"source_sha256": {name: check.sha(b"before capture")}}
        (self.root / name).write_bytes(b"after capture")
        with patch.object(check, "TASK", self.root):
            with self.assertRaisesRegex(ValueError, "source changed during frozen numerical capture"):
                check.verify_capture_sources(report, [name])
        self.assertEqual(report["source_changed_since_freeze"], [name])

    def test_unchanged_capture_source_passes(self):
        name, source = "model.py", b"unchanged captured source"
        report = {"source_sha256": {name: check.sha(source)}}
        (self.root / name).write_bytes(source)
        with patch.object(check, "TASK", self.root):
            check.verify_capture_sources(report, [name])
        self.assertEqual(report["source_changed_since_freeze"], [])
        self.assertEqual(report["source_sha256_after"], report["source_sha256"])


if __name__ == "__main__":
    unittest.main()
