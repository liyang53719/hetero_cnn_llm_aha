"""Cold NumPy-only source/shape/order/rounding gates; no Torch or work cache."""
from pathlib import Path
import ast
import json
import tempfile
import unittest

import numpy as np

from . import reference as r
from .diagnose import synthetic_cases
from .formula import NumericDomainError, bf16, decode, formula


class ReferenceTests(unittest.TestCase):
    def test_recovery_profile_preserves_binary_authority(self):
        profile, directory, pins = r.runtime_selection("historical_20261012")
        self.assertEqual(pins, r.RUNTIME_PINS)
        self.assertEqual(directory, r.RUNTIME)
        with self.assertRaisesRegex(ValueError, "unknown runtime profile"):
            r.runtime_selection("unreviewed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "candidates/qwen35_35b_rms/runtime_recovery_20261013.json"
            path.parent.mkdir(parents=True)
            pins = dict(r.RUNTIME_PINS)
            pins["python.sh"] = "1" * 64
            pins["runtime_receipt.json"] = "2" * 64
            path.write_text(json.dumps({"sha256": pins}))
            self.assertEqual(r.runtime_selection("recovery_20261013", root)[2], pins)
            key = next(n for n in pins if n.startswith("site-packages/"))
            pins[key] = "3" * 64
            path.write_text(json.dumps({"sha256": pins}))
            with self.assertRaisesRegex(ValueError, "arithmetic binary drift"):
                r.runtime_selection("recovery_20261013", root)
            del pins[key]
            path.write_text(json.dumps({"sha256": pins}))
            with self.assertRaisesRegex(ValueError, "pin set changed"):
                r.runtime_selection("recovery_20261013", root)

    def test_source_class_is_complete_and_preserves_original_code_location(self):
        identity = r.source_identity()
        self.assertEqual(identity["class_sha256"], r.CLASS_SHA)
        self.assertEqual(identity["class_lines"], [878, 895])
        self.assertFalse(identity["full_native_forward"])
        node, _ = r._source_definition()
        self.assertEqual([x.name for x in node.body if isinstance(x, ast.FunctionDef)],
                         ["__init__", "_norm", "forward", "extra_repr"])
        self.assertEqual(next(x.lineno for x in node.body if x.name == "forward"), 887)

    def test_changed_source_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / r.SOURCE
            path.parent.mkdir(parents=True)
            path.write_bytes((r.ROOT / r.SOURCE).read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "official modeling source drift"):
                r.source_identity(root)

    def test_synthetic_full_shapes_produce_complete_finite_outputs(self):
        for name, x, w, m, _ in synthetic_cases():
            with self.subTest(case=name):
                result = formula(x, w, m)
                self.assertEqual(len(result["output"]), m * 4096)
                self.assertTrue(np.isfinite(decode(result["output"], (m, 2048))).all())
                self.assertEqual(result["trace"]["sum"].shape, (1, m, 1))
                self.assertFalse(result["scalar_exception_policy_executed"])

    def test_repeating_edge_batch_keeps_every_fp32_node_and_output(self):
        small, large = list(synthetic_cases())[-2:]
        a, b = formula(*small[1:4]), formula(*large[1:4])
        self.assertEqual(a["output"] * 8, b["output"])
        for stage, value in a["trace"].items():
            repeated = np.tile(value, (1, 8, 1)) if value.ndim == 3 else value
            self.assertEqual(repeated.tobytes(), b["trace"][stage].tobytes())

    def test_legacy_control_detects_different_general_reduction(self):
        case = next(synthetic_cases())
        selected = formula(*case[1:4])
        legacy = formula(*case[1:4], reduction="legacy_ascending")
        self.assertFalse(np.array_equal(selected["trace"]["sum"].view("<u4"), legacy["trace"]["sum"].view("<u4")))

    def test_exact_power_of_two_square_sum_and_mean(self):
        x = bf16(np.full((16, 2048), 2, dtype="<f4"))
        result = formula(x, bytes(4096), 16)
        self.assertTrue(np.all(result["trace"]["squares"] == 4))
        self.assertTrue(np.all(result["trace"]["sum"] == 8192))
        self.assertTrue(np.all(result["trace"]["mean"] == 4))

    def test_bf16_ties_round_to_even_and_signed_zero_is_preserved(self):
        words = np.array([0x3f808000, 0x3f818000, 0xbf808000, 0xbf818000,
                          0, 0x80000000, 0x00010000], dtype="<u4")
        actual = np.frombuffer(bf16(words.view("<f4")), "<u2").tolist()
        self.assertEqual(actual, [0x3f80, 0x3f82, 0xbf80, 0xbf82, 0, 0x8000, 1])

    def test_complete_raw_shape_token_bounds_and_nonfinite_admission(self):
        weight, hidden = bytes(4096), bytes(4096)
        for args in ((hidden, weight, 0), (hidden, weight, True), (hidden, weight, 129),
                     (hidden[:-2], weight, 1), (hidden, weight[:-2], 1),
                     (bytearray(hidden), weight, 1), (b"\x80\x7f" + hidden[2:], weight, 1)):
            with self.subTest(args=(len(args[0]), len(args[1]), args[2])):
                with self.assertRaises(ValueError):
                    formula(*args)

    def test_finite_input_square_overflow_is_rejected_without_clamping(self):
        raw = np.full(2048, 0x7f7f, dtype="<u2").tobytes()
        with self.assertRaisesRegex(NumericDomainError, "nonfinite squares"):
            formula(raw, bytes(4096), 1)

    def test_unknown_reduction_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, "unknown reduction"):
            formula(bytes(4096), bytes(4096), 1, reduction="changed")

    def test_payload_api_requires_original_valid_row_ids_before_loading(self):
        for ids in ([256], [-1], [True], [], list(range(129))):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, "original embedding IDs"):
                r.payload_case(Path("does_not_exist"), "0" * 64, ids)

    def test_gamma_is_added_in_fp32_and_applied_before_final_materialization(self):
        x = bf16(np.full((1, 2048), .25, dtype="<f4"))
        weight = bf16(np.full(2048, -1, dtype="<f4"))
        result = formula(x, weight, 1)
        self.assertTrue(np.all(result["trace"]["gamma"] == 0))
        self.assertTrue(np.all(decode(result["output"], (1, 2048)) == 0))
        self.assertTrue(np.all(result["trace"]["scaled"] > 0))


if __name__ == "__main__":
    unittest.main()
