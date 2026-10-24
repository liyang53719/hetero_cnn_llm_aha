"""Stdlib-only exact formula and pin-manifest regression; no simulated cycles."""

import argparse
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
_BOUND_SPEC = importlib.util.spec_from_file_location(
    "architecture_bound", HERE / "architecture_bound.py"
)
if _BOUND_SPEC is None or _BOUND_SPEC.loader is None:
    raise ImportError("Cannot load the exact adjacent architecture_bound.py")
bound = importlib.util.module_from_spec(_BOUND_SPEC)
_BOUND_SPEC.loader.exec_module(bound)


SOURCE_ROOT = None


class ExactArchitectureBoundTests(unittest.TestCase):
    def test_exact_counts_and_dense_ceiling(self):
        result = bound.architecture_bound()
        self.assertEqual(result["causal_pairs"], 8256)
        self.assertEqual(result["qk_key_groups_per_head"], 576)
        self.assertEqual(result["qk_normal_issue_slots"], 55296)
        self.assertEqual(result["pv_normal_issue_slots"], 792576)
        self.assertEqual(result["attention_disjoint_normal_issue_slots"], 847872)
        self.assertEqual(result["dense_useful_macs_given"], 5989466112)
        self.assertEqual(result["attention_useful_macs_reconciled"], 25362432)
        self.assertEqual(result["ideal_dense_normal_issue_slots_lower_bound"], 1462272)

    def test_whole_block_fixed_resource_denominator(self):
        result = bound.architecture_bound()
        self.assertEqual(result["hardware_service_clock_cycles_lower_bound"], 2310144)
        self.assertEqual(result["fixed_4096_whole_block_capacity_denominator"], 9462349824)
        self.assertEqual(result["architecture_utilization_upper_bound"], Fraction(30593, 48128))
        self.assertEqual(result["architecture_useful_macs_per_service_clock_upper_bound"],
                         Fraction(122372, 47))
        self.assertLess(result["architecture_utilization_upper_bound"], 1)

    def test_pv_inactive_slices_cannot_be_filled_by_dense(self):
        result = bound.architecture_bound()
        # Incorrect active-slice amortization would divide legacy PV slots by 8.
        wrong_slots = 55296 + 792576 // 8 + 1462272
        self.assertGreater(result["hardware_service_clock_cycles_lower_bound"], wrong_slots)
        self.assertNotEqual(result["architecture_utilization_upper_bound"],
                            Fraction(6014828544, 4096 * wrong_slots))

    def test_attention_is_not_hidden_under_dense_slots(self):
        result = bound.architecture_bound()
        wrong_overlapped_slots = max(55296 + 792576, 1462272)
        self.assertGreater(result["hardware_service_clock_cycles_lower_bound"], wrong_overlapped_slots)

    def test_reject_each_noncanonical_input(self):
        for key, value in bound.CANONICAL_INPUTS.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                bound.architecture_bound(**{key: value + 1})

    def test_reject_wrong_resource_caps(self):
        for capacity in (0, 512, 2048, 8192, 16384, -4096):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                bound.architecture_bound(fixed_matrix_macs=capacity)
        with self.assertRaises(ValueError):
            bound.architecture_bound(wide_normal_steps_per_service_clock=8)

    def test_reject_non_integer_and_unknown_inputs(self):
        for value in (True, "4096", Fraction(4096), None, 4096.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bound.architecture_bound(fixed_matrix_macs=value)
        with self.assertRaises(ValueError):
            bound.architecture_bound(python_cycles=2310144)

    def test_returned_inputs_cannot_change_later_calls(self):
        result = bound.architecture_bound()
        result["inputs"]["fixed_matrix_macs"] = 512
        self.assertEqual(bound.architecture_bound()["inputs"]["fixed_matrix_macs"], 4096)


class PinnedEvidenceTests(unittest.TestCase):
    def setUp(self):
        if SOURCE_ROOT is None:
            self.fail("Run with an explicit --source-root; no default fixture is inferred")

    def test_real_fixture_manifest_matches_fixed_pins(self):
        result = bound.verify_source_pins(SOURCE_ROOT)
        self.assertEqual(len(result["selected_scala_postimages"]), 5)
        self.assertEqual(result["manifest_sha256"], bound.POSTIMAGE_MANIFEST_SHA256)
        self.assertFalse(result["selected_postimage_bodies_verified_by_this_program"])
        self.assertFalse(result["raw_main_scala_used_as_selected_postimage"])

    def test_missing_explicit_source_root_rejected(self):
        with self.assertRaises(ValueError):
            bound.verify_source_pins(None)

    def test_reject_tampered_fixture_manifest_without_writes(self):
        original_read = Path.read_bytes
        target = Path(SOURCE_ROOT) / bound.POSTIMAGE_MANIFEST

        def corrupted_read(path):
            data = original_read(path)
            return data + b" " if path == target else data

        with mock.patch.object(Path, "read_bytes", corrupted_read):
            with self.assertRaisesRegex(ValueError, "byte identity"):
                bound.verify_source_pins(SOURCE_ROOT)

    def test_reject_changed_selected_hash_without_writes(self):
        original_read = Path.read_bytes
        target = Path(bound.__file__).with_name("INPUT_PINS.json")

        def corrupted_read(path):
            data = original_read(path)
            if path == target:
                value = json.loads(data)
                value["selected_scala_postimages"][0]["post_sha256"] = "0" * 64
                return json.dumps(value).encode()
            return data

        with mock.patch.object(Path, "read_bytes", corrupted_read):
            with self.assertRaisesRegex(ValueError, "hashes differ"):
                bound.verify_source_pins(SOURCE_ROOT)

    def test_reject_duplicate_selected_path(self):
        rows = bound.verify_source_pins(SOURCE_ROOT)["selected_scala_postimages"]
        rows[-1] = rows[0]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            bound._pin_map(rows)

    def test_json_evidence_has_exact_fraction_and_no_floats(self):
        result = bound.evidence(SOURCE_ROOT)
        self.assertEqual(result["exact_bound"]["architecture_utilization_upper_bound"],
                         {"numerator": 30593, "denominator": 48128})
        self.assertTrue(result["not_measured_utilization"])
        self.assertFalse(result["python_scheduler_ticks_used_as_hardware_cycles"])

        def check(value):
            self.assertNotIsInstance(value, float)
            if isinstance(value, dict):
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        check(result)
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_reviewed_anchors_identify_selected_source_not_raw_main(self):
        anchors = bound.evidence(SOURCE_ROOT)["reviewed_selected_source_anchors"]
        for anchor in anchors:
            self.assertEqual(anchor["source_kind"], "selected_scala_postimage")
            self.assertEqual(anchor["sha256"], bound.SELECTED_POSTIMAGES[anchor["path"]])
            first, last = anchor["lines_inclusive"]
            self.assertGreater(first, 0)
            self.assertGreaterEqual(last, first)
        text = json.dumps(anchors)
        for required in ("io.port.step.fire", "wideSteps:=wideSteps+1.U",
                         "legacy.io.port.step.ready:=false.B", "dense.matrix.step.ready:=false.B",
                         "io.port.group.ready:=state===idle", "io.port.done.fire"):
            self.assertIn(required, text)

    def test_checked_in_evidence_reproducible(self):
        saved = json.loads(Path(__file__).with_name("ARCHITECTURE_BOUND.json").read_bytes())
        self.assertEqual(saved, bound.evidence(SOURCE_ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    args, rest = parser.parse_known_args()
    SOURCE_ROOT = args.source_root
    unittest.main(argv=[sys.argv[0]] + rest)
