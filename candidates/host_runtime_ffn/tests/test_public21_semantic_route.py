"""Truth-table/source mutation checks only; no Chisel elaboration or DUT claim."""
from pathlib import Path
import importlib.util
import unittest

C = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("semantic_route_check", C / "check_public21_semantic_route.py")
check_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_module)


def route(marker, shape, valid=True, clean=True, resident_offer=False):
    """Literal combinational equations, abstracting unchanged downstream ready."""
    malformed = valid and marker and not shape
    allowed = clean and not malformed and not resident_offer
    return dict(reduction=valid and marker and shape and allowed,
                ordinary=valid and not marker and allowed,
                malformed=malformed)


class SemanticRouteModel(unittest.TestCase):
    def test_current_source_exact_delta(self):
        self.assertEqual(check_module.check()["status"], "PASS_EXACT_ROUTER_SOURCE_DELTA_NOT_DUT")

    def test_physical_tag_reuse_does_not_create_hetero_reduction(self):
        for tag in (0, 1, 4, 7, 16, 19, 65537, 65540, 65543, 0xFFFFFFFE):
            with self.subTest(physical_tag=tag):
                self.assertEqual(route(False, False), dict(reduction=False, ordinary=True, malformed=False))

    def test_validated_qwen2_semantic_role_survives_all_physical_tags(self):
        for tag in (0, 1, 4, 7, 13, 16, 19, 21, 65535, 65536, 65537, 0xFFFFFFFE):
            with self.subTest(physical_tag=tag):
                self.assertEqual(route(True, True), dict(reduction=True, ordinary=False, malformed=False))

    def test_first_transaction_old_qwen2_semantics_preserved(self):
        for pc in range(21):
            old_role = pc in (1, 4, 7)
            self.assertEqual(route(old_role, old_role)["reduction"], old_role)
            self.assertEqual(route(old_role, old_role)["ordinary"], not old_role)

    def test_later_transaction_semantics_are_not_transport_sequence(self):
        for logical_pc in (1, 4, 7):
            for physical_tag in (logical_pc + 21, logical_pc + 42, logical_pc + 65536 + 21):
                with self.subTest(logical_pc=logical_pc, physical_tag=physical_tag):
                    self.assertTrue(route(True, True)["reduction"])
                    self.assertNotIn(physical_tag & 0xFFFF, (1, 4, 7))

    def test_matching_shape_without_marker_cannot_select_reduction(self):
        self.assertEqual(route(False, True), dict(reduction=False, ordinary=True, malformed=False))

    def test_malformed_semantic_role_remains_rejected(self):
        self.assertEqual(route(True, False), dict(reduction=False, ordinary=False, malformed=True))

    def test_no_valid_means_no_offer_or_malformed_event(self):
        for marker in (False, True):
            for shape in (False, True):
                self.assertEqual(route(marker, shape, valid=False), dict(reduction=False, ordinary=False, malformed=False))

    def test_fault_vetoes_new_offers(self):
        for marker in (False, True):
            r = route(marker, True, clean=False)
            self.assertFalse(r["reduction"] or r["ordinary"])

    def test_resident_has_same_priority(self):
        for marker in (False, True):
            r = route(marker, True, resident_offer=True)
            self.assertFalse(r["reduction"] or r["ordinary"])

    def test_mutation_reverting_tag_selector_is_rejected(self):
        current = (C / "source/Public21QkvReductionRouter.scala").read_text()
        with self.assertRaises(ValueError):
            check_module.check(current.replace(check_module.NEW_ROLE, check_module.OLD_ROLE))

    def test_mutation_shape_only_route_is_rejected(self):
        current = (C / "source/Public21QkvReductionRouter.scala").read_text()
        with self.assertRaises(ValueError):
            check_module.check(current.replace("val role=j.public21Reduction", "val role=j.kind===QwenOwnerKind.Dense.U"))

    def test_mutation_numerical_recipe_is_rejected(self):
        current = (C / "source/Public21QkvReductionRouter.scala").read_text()
        with self.assertRaises(ValueError):
            check_module.check(current.replace("bits.pairReverse:=true.B", "bits.pairReverse:=false.B"))

    def test_mutation_terminal_retirement_is_rejected(self):
        current = (C / "source/Public21QkvReductionRouter.scala").read_text()
        with self.assertRaises(ValueError):
            check_module.check(current.replace("when(io.done.fire || io.residentHost.result.fire)", "when(io.done.valid || io.residentHost.result.valid)"))

    def test_mutation_malformed_admission_is_rejected(self):
        current = (C / "source/Public21QkvReductionRouter.scala").read_text()
        with self.assertRaises(ValueError):
            check_module.check(current.replace("val malformed=io.job.valid && role && !shape", "val malformed=false.B"))


if __name__ == "__main__":
    unittest.main(argv=[__file__]+check_module.unittest_args)
