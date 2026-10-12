#!/usr/bin/env python3
"""Bounded source/schedule audit; does NOT compile, elaborate, or simulate Chisel.

The symbolic model checks reduction association and scratch lifetime. Source
checks bind important paths to this overlay but are not a Scala interpreter or
a substitute for the real BlockScalarFloat/owner regression.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION = ROOT / "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QkNorm256Owner.scala"
OVERLAY = HERE / "QkNorm256Owner.scala"
BASE = PRODUCTION.read_text()
NEW = OVERLAY.read_text()


def tokens(source: str) -> str:
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    return re.sub(r"\s+", "", source)


def block(source: str, anchor: str) -> str:
    start = source.index("{", source.index(anchor))
    depth = 1
    end = start + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start + 1:end - 1]


def symbolic_reduction():
    """Mirror the four reduction states, with poisoned old scratch contents.

    No floating-point values or captured native statistics are used. Compare
    the complete expression tree to the independently nested specification.
    """
    square_indices = []
    counts = Counter()
    accumulator = 0
    scratch = [0, ("poison",)]
    lane, state, value = 0, "square", ("poison",)
    while state != "mean":
        if state == "square":
            square_indices.append(lane)
            value = ("mul", ("x", lane), ("x", lane))
            counts["Mul"] += 1
            state = "term"
        elif state == "term":
            value = ("add", scratch[0], value)
            counts["Add"] += 1
            scratch[0] = value
            if lane >> 5 != 7:
                lane += 32
                state = "square"
            elif (lane >> 3) & 3 == 0:
                scratch[1], scratch[0] = value, 0
                lane, state = 8 | (lane & 7), "square"
            else:
                state = "residue"
        elif state == "residue":
            value = ("add", scratch[1], value)
            counts["Add"] += 1
            scratch[1] = value
            if (lane >> 3) & 3 == 3:
                state = "lane"
            else:
                scratch[0] = 0
                lane = ((((lane >> 3) & 3) + 1) << 3) | (lane & 7)
                state = "square"
        elif state == "lane":
            value = ("add", accumulator, value)
            counts["Add"] += 1
            accumulator = value
            if lane & 7 == 7:
                lane, state = 0, "mean"
            else:
                scratch[0] = 0
                lane, state = (lane & 7) + 1, "square"
        else:
            raise AssertionError(state)
    return accumulator, square_indices, counts, lane


class OverlayAudit(unittest.TestCase):
    def test_same_module_interface_and_register_declarations(self):
        for name in ("QkNorm256Job", "QkNorm256Result", "QkNorm256OwnerPort"):
            self.assertEqual(tokens(block(BASE, f"class {name} ")), tokens(block(NEW, f"class {name} ")))
        registers = r"^\s*val\s+\w+\s*=\s*Reg(?:Init)?\([^\n]*"
        self.assertEqual(re.findall(registers, BASE, re.M), re.findall(registers, NEW, re.M))
        self.assertNotRegex(NEW, r"Module\s*\(\s*new\b")
        self.assertNotRegex(NEW, r"(?:SyncReadMem|Mem)\s*\(")
        self.assertEqual(NEW.count("extends Module"), 1)
        self.assertIn("enableTorchDefaultPolicy: Boolean = false", NEW)

    def test_c1_arithmetic_paths_and_literal_coefficients_unchanged(self):
        for name in ("tree", "running", "mean", "slope", "intercept", "seedSquare", "normProduct", "half", "correction", "newton", "rescale", "gamma", "normalize", "weighted"):
            self.assertEqual(tokens(block(BASE, f"is({name})")), tokens(block(NEW, f"is({name})")), name)
        old_square = block(BASE, "is(square)")
        new_square = block(block(NEW, "is(square)"), ".otherwise")
        self.assertEqual(tokens(old_square), tokens(new_square))
        old_epsilon = block(BASE, "is(epsilon)")
        new_epsilon = block(NEW, "is(epsilon)").replace(".elsewhen(useTorchDefault) { operation := torchSqrt }", "")
        self.assertEqual(tokens(old_epsilon), tokens(new_epsilon))
        self.assertEqual(BASE.split("val rsqrtCoefficients =", 1)[1].split("when(state =/= idle", 1)[0],
                         NEW.split("val rsqrtCoefficients =", 1)[1].split("when(state =/= idle", 1)[0])
        enum = re.search(r"val square :: (.*?) :: Nil = Enum\((\d+)\)", NEW).group(1).split(" :: ")
        self.assertEqual(enum[-5:], ["torchTermAdd", "torchResidueFold", "torchLaneFold", "torchSqrt", "torchDivide"])
        self.assertIn("Enum(21)", NEW)  # One operation-state bit beyond C1's Enum(16).

    def test_c1_operand_mapping_preserved(self):
        for operand in ("a", "b"):
            anchor = f"io.scalar.request.bits.{operand} :="
            old = BASE.split(anchor, 1)[1].split("))", 1)[0]
            new = NEW.split(anchor, 1)[1].split("))", 1)[0]
            old_pairs = re.findall(r"(\w+)\s*->\s*([^,\n]+)", old)
            new_pairs = dict(re.findall(r"(\w+)\s*->\s*([^,\n]+)", new))
            for operation, value in old_pairs:
                self.assertEqual(tokens(value), tokens(new_pairs[operation]), (operand, operation))
        self.assertIn("operation === torchSqrt, ScalarOp.Sqrt.U", NEW)
        self.assertIn("operation === torchDivide, ScalarOp.Div.U", NEW)
        self.assertIn('torchDivide -> "h3f800000".U', NEW)
        self.assertIn("torchSqrt -> 0.U(32.W)", NEW)

    def test_policy_domain_transport_and_commit_contracts(self):
        self.assertIn('val badPolicy = j.policy =/= "hc1".U && !(enableTorchDefaultPolicy.B && j.policy === "hc2".U)', NEW)
        self.assertIn('val useTorchDefault = enableTorchDefaultPolicy.B && job.policy === "hc2".U', NEW)
        # Descriptor acceptance is changed only in the explicit policy predicate.
        old_job = block(BASE, "when(io.job.fire)")
        new_job = block(NEW, "when(io.job.fire)")
        new_job = re.sub(r"\s*val badPolicy = [^\n]+", "", new_job)
        new_job = new_job.replace('badPolicy ||', 'j.policy =/= "hc1".U ||')
        self.assertEqual(tokens(old_job), tokens(new_job))
        for anchor in ("when(io.memory.fire)", "def nextHead()", "when(io.done.fire)"):
            self.assertEqual(tokens(block(BASE, anchor)), tokens(block(NEW, anchor)))
        old_response, new_response = block(BASE, "when(io.response.fire)"), block(NEW, "when(io.response.fire)")
        new_response = new_response.replace("when(useTorchDefault) { treeValues(0) := 0.U; treeValues(1) := 0.U }", "")
        self.assertEqual(tokens(old_response), tokens(new_response))
        for start, end in (("io.job.ready :=", "val heads ="), ("val heads =", "val inputLanes =")):
            old = BASE.split(start, 1)[1].split(end, 1)[0]
            new = NEW.split(start, 1)[1].split(end, 1)[0]
            new = re.sub(r"\s*val useTorchDefault = [^\n]+", "", new)
            self.assertEqual(tokens(old), tokens(new))

    def test_only_c2_sqrt_div_relax_flag_presence(self):
        self.assertIn("val torchInverseOperation = useTorchDefault && (operation === torchSqrt || operation === torchDivide)", NEW)
        self.assertIn("when(!torchInverseOperation && !io.scalarFlagsValid) { fail(Status.Protocol.U) }", NEW)
        self.assertIn("when(!torchInverseOperation) { exceptionFlags := exceptionFlags | io.scalarFlags }", NEW)
        self.assertIn("when(io.scalar.error || (!torchInverseOperation && io.scalarFlags(4, 1).orR) || !TensorMath.finite(r)) { rejectNorm(4.U) }", NEW)
        for operation in ("torchSqrt", "torchDivide"):
            self.assertIn("r(31) || r(30, 23) === 0.U || r(30, 23) === 255.U", block(NEW, f"is({operation})"))
        # No invented raw flags or mutated shared-scalar implementation.
        self.assertNotRegex(NEW, r"io\.scalarFlags(?:Valid)?\s*:=")

    def test_symbolic_schedule_and_scratch_lifetimes(self):
        expected, expected_indices = 0, []
        for lane in range(8):
            residues = []
            for residue in range(4):
                total = 0
                for term in range(8):
                    index = 32 * term + 8 * residue + lane
                    expected_indices.append(index)
                    total = ("add", total, ("mul", ("x", index), ("x", index)))
                residues.append(total)
            total = residues[0]
            for residue in residues[1:]:
                total = ("add", total, residue)
            expected = ("add", expected, total)
        result, indices, counts, next_lane = symbolic_reduction()
        self.assertEqual(result, expected)
        self.assertEqual(indices, expected_indices)
        self.assertEqual(sorted(indices), list(range(256)))
        self.assertEqual(counts, Counter(Add=288, Mul=256))
        self.assertEqual(next_lane, 0)
        total = counts + Counter(Mul=1 + 256 * 2, Add=1 + 256, Sqrt=1, Div=1)
        self.assertEqual(total, Counter(Add=545, Mul=769, Sqrt=1, Div=1))
        self.assertEqual(sum(total.values()), 1316)
        # Bind the schedule's bit layout and initialized scratch to source.
        for fragment in (
            "torchTermAdd -> treeValues(0)", "torchResidueFold -> treeValues(1)",
            "torchLaneFold -> accumulator", "lane := lane + 32.U; operation := square",
            "lane := Cat(0.U(3.W), 1.U(2.W), lane(2, 0))",
            "lane := Cat(0.U(3.W), (lane(4, 3) + 1.U)(1, 0), lane(2, 0))",
            "lane := Cat(0.U(5.W), (lane(2, 0) + 1.U)(2, 0))",
            "treeValues(1) := r; treeValues(0) := 0.U",
            "when(lane(2, 0) === 7.U) { lane := 0.U; operation := mean }",
        ):
            self.assertIn(fragment, NEW)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OverlayAudit))
    print(json.dumps({
        "kind": "static_source_and_symbolic_schedule_only",
        "checks_passed": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "baseline_sha256": hashlib.sha256(PRODUCTION.read_bytes()).hexdigest(),
        "overlay_sha256": hashlib.sha256(OVERLAY.read_bytes()).hexdigest(),
        "scalar_requests_per_head": {"C1": 1290, "C2": 1316, "delta": 26},
        "new_arithmetic_modules": 0,
        "new_data_register_declarations": 0,
        "operation_state_width_delta_bits": 1,
        "scala_compiled": False,
        "chisel_elaborated": False,
        "rtl_simulated": False,
        "production_source_replaced": False,
    }, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
