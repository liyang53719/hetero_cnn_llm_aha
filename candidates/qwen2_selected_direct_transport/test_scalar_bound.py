"""Exact necessary-QK-Scalar regression; isolated imports and no fixture writes."""

import argparse
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("scalar_bound", HERE / "scalar_bound.py")
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("Cannot load exact adjacent scalar_bound.py")
bound = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bound)
SOURCE_ROOT = None


class ScalarFormulaTests(unittest.TestCase):
    def test_scores_and_mandatory_operations(self):
        result = bound.scalar_bound()
        self.assertEqual(result["mandatory_qk_scores"], 99072)
        self.assertEqual(result["mandatory_qk_scalar_adds"], 1585152)
        self.assertEqual(result["mandatory_qk_scalar_scale_muls"], 99072)
        self.assertEqual(result["mandatory_qk_scalar_operations"], 1684224)

    def test_minimum_span_has_correct_edge_endpoints(self):
        result = bound.scalar_bound()
        operations = result["mandatory_qk_scalar_operations"]
        self.assertEqual(result["first_qk_scalar_accept_to_last_qk_scalar_result_span_lower_bound"],
                         3 * (operations - 1) + 2)
        self.assertEqual(result["first_qk_scalar_accept_to_last_qk_scalar_result_span_lower_bound"], 5052671)
        self.assertNotEqual(result["first_qk_scalar_accept_to_last_qk_scalar_result_span_lower_bound"], 3 * operations)

    def test_max_combination_never_sum(self):
        result = bound.scalar_bound()
        self.assertEqual(result["matrix_layer1_cycles_lower_bound"], 2310144)
        self.assertEqual(result["combined_max_service_clock_cycles_lower_bound"], 5052671)
        self.assertNotEqual(result["combined_max_service_clock_cycles_lower_bound"], 2310144 + 5052671)

    def test_exact_whole_block_fixed4096_fraction(self):
        result = bound.scalar_bound()
        self.assertEqual(result["fixed_4096_whole_block_capacity_denominator"], 20695740416)
        self.assertEqual(result["scalar_layer2_utilization_upper_bound"], Fraction(1468464, 5052671))
        self.assertEqual(result["combined_architecture_utilization_upper_bound"], Fraction(1468464, 5052671))
        self.assertLess(result["combined_architecture_utilization_upper_bound"], Fraction(30593, 48128))

    def test_reject_each_noncanonical_input(self):
        for key, value in bound.CANONICAL_INPUTS.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                bound.scalar_bound(**{key: value + 1})

    def test_reject_fifteen_add_shortcut_and_changed_throughput(self):
        for override in ({"qk_adds_per_score": 15}, {"qk_scale_muls_per_score": 0},
                         {"scalar_acceptance_spacing_lower_bound": 1},
                         {"scalar_acceptance_to_result_spacing_lower_bound": 1},
                         {"fixed_matrix_macs": 512}, {"fixed_matrix_macs": 8192}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                bound.scalar_bound(**override)

    def test_reject_non_integer_and_unscoped_budget_inputs(self):
        for value in (True, "4096", 4096.0, Fraction(4096), None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bound.scalar_bound(fixed_matrix_macs=value)
        for name in ("python_cycles", "pv_six_cycle_budget", "silu_budget", "extra_scalar_instances"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                bound.scalar_bound(**{name: 0})

    def test_returned_inputs_cannot_mutate_canonical_calculation(self):
        result = bound.scalar_bound()
        result["inputs"]["qk_adds_per_score"] = 15
        self.assertEqual(bound.scalar_bound()["mandatory_qk_scalar_operations"], 1684224)


class ScalarEvidenceTests(unittest.TestCase):
    def setUp(self):
        if SOURCE_ROOT is None:
            self.fail("Explicit --source-root is required; no fixture is inferred")

    def test_actual_pinned_blockfloat_bytes_and_anchors(self):
        verified = bound.verify_scalar_source(SOURCE_ROOT)
        self.assertTrue(verified["unchanged_blockfloat_body_hash_and_anchors_verified"])
        self.assertFalse(verified["selected_qwen2block_body_read_by_this_program"])
        self.assertFalse(verified["identity_proof_file_read_by_this_program"])
        source = verified["pins"]["sources"][bound.BLOCKFLOAT_PATH]
        self.assertEqual(source["sha256"], bound.BLOCKFLOAT_SHA256)
        self.assertEqual(source["git_blob"], bound.BLOCKFLOAT_GIT_BLOB)

    def test_requires_explicit_fixture_root(self):
        with self.assertRaises(ValueError):
            bound.verify_scalar_source(None)

    def test_tampered_blockfloat_rejected_without_writes(self):
        original = Path.read_bytes
        target = Path(SOURCE_ROOT) / bound.BLOCKFLOAT_PATH

        def altered(path):
            raw = original(path)
            return raw + b" " if path == target else raw

        with mock.patch.object(Path, "read_bytes", altered):
            with self.assertRaisesRegex(ValueError, "source byte identity"):
                bound.verify_scalar_source(SOURCE_ROOT)

    def test_tampered_dedicated_pins_rejected_without_writes(self):
        original = Path.read_bytes
        target = HERE / "SCALAR_SOURCE_PINS.json"

        def altered(path):
            raw = original(path)
            return raw + b" " if path == target else raw

        with mock.patch.object(Path, "read_bytes", altered):
            with self.assertRaisesRegex(ValueError, "SCALAR_SOURCE_PINS byte identity"):
                bound.verify_scalar_source(SOURCE_ROOT)

    def test_json_is_exact_and_not_a_timing_claim(self):
        result = bound.evidence(SOURCE_ROOT)
        self.assertEqual(result["exact_bound"]["combined_architecture_utilization_upper_bound"],
                         {"numerator": 1468464, "denominator": 5052671})
        self.assertTrue(result["not_measured_utilization"])
        self.assertFalse(result["python_scheduler_ticks_used_as_hardware_cycles"])
        self.assertIn("MAX", result["layer_combination"])

        def walk(value):
            self.assertNotIsInstance(value, float)
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(result)
        self.assertEqual(result, json.loads(json.dumps(result)))

    def test_selected_and_unchanged_source_are_distinct(self):
        anchors = bound.evidence(SOURCE_ROOT)["reviewed_source_anchors"]
        for anchor in anchors:
            if anchor["path"] == bound.BLOCKFLOAT_PATH:
                self.assertEqual(anchor["source_kind"], "unchanged_current_main_dependency")
                self.assertEqual(anchor["sha256"], bound.BLOCKFLOAT_SHA256)
            else:
                self.assertEqual(anchor["source_kind"], "selected_scala_postimage")
                self.assertEqual(anchor["sha256"], bound.QWEN2BLOCK_SHA256)
        text = json.dumps(anchors)
        for required in ("BlockScalarFloat", "ScalarOp.Add", "lane===15.U", "ScalarOp.Mul",
                         "io.request.ready:=state===idle", "io.result.valid:=state===done",
                         "is(done){when(io.result.fire){state:=idle}}"):
            self.assertIn(required, text)

    def test_layer1_artifact_still_has_original_bound(self):
        layer1 = json.loads((HERE / "ARCHITECTURE_BOUND.json").read_bytes())
        self.assertEqual(layer1["exact_bound"]["hardware_service_clock_cycles_lower_bound"], 2310144)
        self.assertEqual(layer1["exact_bound"]["architecture_utilization_upper_bound"],
                         {"numerator": 30593, "denominator": 48128})

    def test_checked_in_evidence_is_reproducible(self):
        saved = json.loads((HERE / "SCALAR_BOUND.json").read_bytes())
        self.assertEqual(saved, bound.evidence(SOURCE_ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    args, rest = parser.parse_known_args()
    SOURCE_ROOT = args.source_root
    unittest.main(argv=[sys.argv[0]] + rest)
