"""Source/diagnostic tests for default Torch-free, zero-skip CI.

Ordinary tests are NumPy-only and never execute a Prep owner or scalar. Run the
small official-AST checks through the pinned_smoke module and the existing
isolated runtime wrapper. No checkpoint, downloads, or full model are required.
"""
import ast
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import numpy as np

from . import reference as r


def bf16(values):
    words = np.asarray(values, dtype="<f4").view("<u4")
    return ((words + 0x7fff + ((words >> 16) & 1)) >> 16).astype("<u2").tobytes()


def inputs(rows=1):
    conv = bf16(np.array([
        [((i * 17 + token * 13) % 61 - 30) / 16 for i in range(r.CONV)]
        for token in range(rows)
    ], dtype="<f4"))
    ab = bf16(np.array([
        [(i - 17 + token) / 32 for i in range(32)] +
        [(i - 7 - token) / 16 for i in range(32)] for token in range(rows)
    ], dtype="<f4"))
    alog = np.array([(i - 13) / 37 for i in range(32)], dtype="<f4").tobytes()
    bias = bf16([(i - 14) / 64 for i in range(32)])
    return conv, ab, alog, bias


class SourceAndInputTests(unittest.TestCase):
    def test_pinned_complete_source_and_exact_forward_chunk_order(self):
        norm, nodes, prefix, identity = r._definitions()
        self.assertEqual(identity["source_sha256"], r.SOURCE_SHA)
        self.assertEqual(identity["config_sha256"], r.CONFIG_SHA)
        self.assertEqual(identity["class_name"], "Qwen3_5MoeGatedDeltaNet")
        self.assertEqual(identity["forward_preparation"]["lines"], [558, 577])
        self.assertEqual(identity["chunk_prefix"]["lines"], [271, 306])
        self.assertIn("torch.rsqrt((x * x).sum(dim=dim, keepdim=True) + eps)", ast.unparse(norm))
        self.assertIn("torch.split(mixed_qkv, [self.key_dim, self.key_dim, self.value_dim], dim=-1)", ast.unparse(nodes[0]))
        self.assertEqual(ast.unparse(nodes[-3]), "beta = b.sigmoid()")
        self.assertIn("a.float() + self.dt_bias", ast.unparse(nodes[-2]))
        self.assertIn("repeat_interleave", ast.unparse(nodes[-1]))
        text = ast.unparse(prefix)
        self.assertLess(text.index("x.transpose(1, 2).to(torch.float32"), text.index("query = l2norm"))
        self.assertLess(text.index("key = l2norm"), text.index("query = query * scaling"))
        self.assertEqual(ast.unparse(prefix.body[-1]), "return (query, key, value, decay, beta)")
        self.assertEqual(prefix.decorator_list, [])
        self.assertNotIn("F.pad(", text)
        self.assertFalse(identity["full_official_block_executed"])
        self.assertFalse(identity["recurrence_implemented"])

    def test_changed_official_source_or_config_is_rejected(self):
        for changed in (r.SOURCE, r.CONFIG):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name in (r.SOURCE, r.CONFIG):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((r.ROOT / name).read_bytes() + (b"\n" if changed == name else b""))
                with self.assertRaisesRegex(ValueError, "source drift|config drift"):
                    r.source_identity(root)

    def test_reference_does_not_import_actual_model_scalar_or_fixed_recipe(self):
        tree = ast.parse(Path(r.__file__).read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertEqual(imports[-1], "qwen35_35b_rms")
        self.assertTrue(all(not any(word in name for word in ("scalar", "prep.model", "prep.reference")) for name in imports))
        self.assertNotIn("actual_raw", list(r.native_prep.__code__.co_varnames[:r.native_prep.__code__.co_argcount]))

    def test_exact_raw_shapes_rows_and_all_parameter_lanes_are_consumed(self):
        data = inputs()
        r.validate_inputs(*data, 1)
        for rows in (0, 129, True, 1.0):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "geometry"):
                r.validate_inputs(*data, rows)
        for index in range(4):
            for changed in (data[index][:-2], data[index] + bytes(2), bytearray(data[index])):
                bad = list(data)
                bad[index] = changed
                with self.subTest(index=index, size=len(changed)), self.assertRaisesRegex(ValueError, "complete raw"):
                    r.validate_inputs(*bad, 1)
            bad = list(data)
            size = 4 if index == 2 else 2
            bad[index] = bad[index][:-size] + (struct.pack("<I", 0x7fc00001) if size == 4 else struct.pack("<H", 0xff80))
            with self.subTest(nonfinite_index=index), self.assertRaisesRegex(ValueError, "nonfinite"):
                r.validate_inputs(*bad, 1)

    def test_wrong_dispatch_environment_rejected_before_torch_use(self):
        with mock.patch.dict(os.environ, {"ATEN_CPU_CAPABILITY": "DEFAULT"}):
            with self.assertRaisesRegex(ValueError, "ATEN_CPU_CAPABILITY=default"):
                r.native_prep(*inputs(), 1)


class DiagnosticTests(unittest.TestCase):
    def test_absolute_relative_ulp_and_signed_zero_are_separate(self):
        expected = np.array([-1, 1, 0, 2], "<f4").view("<u4")
        actual = expected.copy()
        actual[:2] += 1
        actual[2] = 0x80000000
        result = r.compare_fp32(actual.tobytes(), expected.tobytes())
        self.assertEqual(result["max_fp32_ulp"], 1)
        self.assertEqual(result["bit_mismatches"], 3)
        self.assertEqual(result["numerical_mismatches"], 2)
        self.assertEqual(result["signed_zero_only_mismatches"], 1)
        self.assertEqual(result["max_relative"], 2 ** -23)
        self.assertEqual(result["mean_relative"], 2 ** -24)
        self.assertEqual(result["max_abs"], 2 ** -23)
        self.assertEqual(result["actual_sha256"], r.sha(actual.tobytes()))
        json.dumps(result, allow_nan=False)

    def test_relative_denominator_has_no_floor_or_silent_nonzero_over_zero(self):
        expected = np.array([0, 2 ** -120, 2], "<f4")
        actual = np.array([1, 2 ** -119, 3], "<f4")
        result = r.compare_fp32(actual.tobytes(), expected.tobytes())
        self.assertEqual(result["zero_reference_nonzero_actual"], 1)
        self.assertIsNone(result["max_relative"])
        self.assertIsNone(result["mean_relative"])
        self.assertEqual(result["max_relative_reference_nonzero"], 1)
        self.assertEqual(result["mean_relative_reference_nonzero"], .75)
        zero = r.compare_fp32(bytes(16), bytes(16))
        self.assertEqual(zero["max_relative"], 0)
        self.assertEqual(zero["mean_relative"], 0)
        self.assertIsNone(zero["max_relative_reference_nonzero"])
        json.dumps(result, allow_nan=False)

    def test_nonfinite_and_partial_comparisons_fail_closed(self):
        for bits in (0x7f800000, 0xff800000, 0x7fc00001):
            result = r.compare_fp32(struct.pack("<I", bits), bytes(4))
            self.assertEqual(result["actual_nonfinite"], 1)
            for field in ("max_abs", "mean_abs", "max_relative", "mean_relative", "max_fp32_ulp"):
                self.assertIsNone(result[field])
            json.dumps(result, allow_nan=False)
        for pair in ((b"", b""), (bytes(3), bytes(3)), (bytes(4), bytes(8)), (bytearray(4), bytes(4))):
            with self.subTest(pair=pair), self.assertRaisesRegex(ValueError, "comparison shape"):
                r.compare_fp32(*pair)

    def test_each_role_layout_and_coordinates_are_independent(self):
        rows = 2
        expected = bytes(rows * r.CORE * 4)
        positions = dict(query=(1, 2 * 128 + 7), key=(1, 4096 + 31 * 128 + 5),
                         value=(0, 8192 + 16 * 128 + 3), g=(1, 12288 + 30 * 16),
                         beta=(1, 12288 + 31 * 16 + 1), gate_padding=(1, 12288 + 31 * 16 + 15))
        coordinates = dict(query=[1, 2, 7], key=[1, 31, 5], value=[0, 16, 3],
                           g=[1, 30], beta=[1, 31], gate_padding=[1, 31, 13])
        for role, position in positions.items():
            with self.subTest(role=role):
                words = np.zeros((rows, r.CORE), "<u4")
                words[position] = 0x80000000 if role == "gate_padding" else 0x3f800000
                report = r.diagnose(words.tobytes(), expected, rows)
                self.assertEqual(report["roles"][role]["bit_mismatches"], 1)
                self.assertEqual(report["roles"][role]["first_bit_mismatch_coordinates"], coordinates[role])
                self.assertTrue(all(x["bit_mismatches"] == 0 for name, x in report["roles"].items() if name != role))
                self.assertEqual(report["all_gate_padding_positive_zero"], role != "gate_padding")
                self.assertIsNone(report["passed"])
                self.assertIsNone(report["thresholds"])
                self.assertEqual(report["official_stage_acceptance"], "UNASSIGNED")
                json.dumps(report, allow_nan=False)

    def test_bit_exact_outputs_still_do_not_assign_a_pass(self):
        raw = bytes(r.CORE * 4)
        identity = dict(output_sha256=r.sha(raw), rows=1)
        report = r.diagnose(raw, raw, 1, identity=identity)
        self.assertIsNone(report["passed"])
        self.assertEqual(report["status"], r.STATUS)
        self.assertTrue(report["all_gate_padding_positive_zero"])
        for changed in (dict(identity, rows=2), dict(identity, output_sha256="0" * 64), {}):
            with self.subTest(identity=changed), self.assertRaisesRegex(ValueError, "identity"):
                r.diagnose(raw, raw, 1, identity=changed)
        with self.assertRaisesRegex(ValueError, "complete FP32"):
            r.compare_roles(raw[:-4], raw, 1)


if __name__ == "__main__":
    unittest.main()
