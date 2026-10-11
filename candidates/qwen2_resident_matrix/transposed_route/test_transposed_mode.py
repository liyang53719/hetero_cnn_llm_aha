#!/usr/bin/env python3
"""Routing + abstract group/credit tests; no endpoint arithmetic or RTL."""
from dataclasses import replace
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import check_transposed_matrix_frontend as frontend
from check_transposed_matrix_frontend import TASK, ROOT, PREFIX, check_inputs, build_overlay, check
from transposed_model import Group, ServiceContract, Step, Return, physical_result, route, OperandGraph

A = tuple(range(0x1100, 0x1110))
B = tuple(range(0x2200, 0x2300))


class RoutingTests(unittest.TestCase):
    def test_all_4096_transposed_coordinates_and_bijection(self):
        # Input values encode their logical axis, independently of physical order.
        weights = tuple(0x5000+n for n in range(32))
        activation = tuple(0x1000+m for m in range(128))
        a, b = weights[:16], activation+weights[16:]+(0,)*112
        routed = route(a, b, True)
        observed = set()
        for s, (av, bv) in enumerate(routed):
            for r in range(16):
                for c in range(32):
                    m, n = (s % 4)*32+c, (s//4)*16+r
                    self.assertEqual((av[r], bv[c]), (weights[n], activation[m]))
                    observed.add((m, n))
        self.assertEqual(observed, {(m, n) for m in range(128) for n in range(32)})

    def test_all_4096_normal_coordinates(self):
        for s, (av, bv) in enumerate(route(A, B)):
            for r in range(16):
                for c in range(32):
                    self.assertEqual((av[r], bv[c]), (A[r], B[32*s+c]))

    def test_special_bit_patterns_preserved_without_numerical_policy_claim(self):
        patterns = (0, 0x8000, 1, 0x7f, 0x80, 0x3f80, 0xbf80, 0x7f80, 0xff80, 0x7fc1, 0x7f81, 0xffff)
        for offset in range(len(patterns)):
            a = tuple(patterns[(i+offset) % len(patterns)] for i in range(16))
            b = tuple(patterns[(i*3+offset) % len(patterns)] for i in range(256))
            for mode in (False, True):
                result = route(a, b, mode)
                for s, (av, bv) in enumerate(result):
                    self.assertEqual(av, a if s < 4 or not mode else b[128:144])
                    start = 32*(s % 4 if mode else s)
                    self.assertEqual(bv, b[start:start+32])

    def test_reserved_payload_ignored_only_in_transposed(self):
        changed = B[:144]+tuple(x ^ 0xffff for x in B[144:])
        self.assertEqual(route(A, B, True), route(A, changed, True))
        self.assertNotEqual(route(A, B, False), route(A, changed, False))

    def test_original_output_interface_and_logical_inverse_all_coordinates(self):
        leaves = [tuple((s<<16)|(r<<8)|c for r in range(16) for c in range(32)) for s in range(8)]
        output = physical_result(leaves)
        observed = {}
        for row in range(16):
            for col in range(256):
                s, c = divmod(col, 32)
                self.assertEqual(output[row][col], (s<<16)|(row<<8)|c)
                observed[((s % 4)*32+c, (s//4)*16+row)] = output[row][col]
        self.assertEqual(len(observed), 4096)
        self.assertEqual(observed[(127, 31)], (7<<16)|(15<<8)|31)
        self.assertEqual(physical_result(leaves, 0)[0], (0,)*256)

    def test_payload_shape_and_word_bounds(self):
        for a, b in ((A[:-1], B), (A, B[:-1]), (A, B+(0,)), ((65536,)+A[1:], B), ((-1,)+A[1:], B)):
            with self.assertRaises(ValueError): route(a, b, True)


class GroupLifecycleTests(unittest.TestCase):
    def running(self, transposed=True, enabled=True, bits=0):
        m = ServiceContract(enabled, bits)
        m.cycle(group=Group(tag=0x1234, transposed=transposed if enabled else None), group_valid=True)
        self.assertEqual(m.state, "command")
        m.cycle()
        self.assertEqual(m.state, "running")
        return m

    def step(self, m, step=None, **kw):
        return m.cycle(step=step, a=A, b=B, **kw)

    def test_exhaustive_transposed_opcode_mask_rejection_before_endpoint_issue(self):
        rejected = 0
        for op in range(256):
            for mask in range(256):
                m = ServiceContract(True)
                r = m.cycle(group=Group(op, mask, tag=99, transposed=True), group_valid=True)
                self.assertTrue(r["group_fire"])
                m.cycle()
                if (op, mask) == (0x20, 255):
                    self.assertEqual((m.state, m.command_count), ("running", 8))
                else:
                    rejected += 1
                    self.assertEqual((m.state, m.command_count, m.poison), ("finish", 0, True))
                    self.assertEqual(m.group.tag, 99)
        self.assertEqual(rejected, 65535)

    def test_normal_mode_preserves_existing_opcode_mask_contract(self):
        for enabled in (False, True):
            for opcode in (0x20, 0x21, 0x23, 0x24):
                for mask in range(1, 256):
                    m = ServiceContract(enabled)
                    m.cycle(group=Group(opcode, mask, transposed=False if enabled else None), group_valid=True)
                    m.cycle()
                    self.assertEqual(m.command_count, mask.bit_count())
                    self.assertEqual(m.state, "running")
                    self.assertEqual(self.step(m, Step(0, 0, clear=True))["operands"], route(A, B))

    def test_constructor_off_has_no_mode_pin(self):
        m = ServiceContract(False)
        with self.assertRaises(ValueError):
            m.cycle(group=Group(transposed=True), group_valid=True)
        m = ServiceContract(True)
        with self.assertRaises(ValueError):
            m.cycle(group=Group(), group_valid=True)

    def test_group_latched_only_on_accept_not_unaccepted_live_pins(self):
        m = ServiceContract(True)
        m.cycle(group=Group(transposed=True), group_valid=False)
        self.assertIsNone(m.group)
        original = Group(tag=91, transposed=True)
        m.cycle(group=original, group_valid=True)
        for i in range(12):
            r = m.cycle(group=Group(0xff, 0, i, False), group_valid=True, command_ready=False)
            self.assertFalse(r["group_fire"])
            self.assertEqual(m.group, original)
        m.cycle()
        for i in range(5):
            r = self.step(m, Step(0, i, context=i, clear=True), group=Group(0x24, 1, i, False), group_valid=True)
            self.assertFalse(r["group_fire"])
            self.assertEqual(r["operands"], route(A, B, True))
            self.assertEqual(m.group, original)

    def test_same_enabled_instance_can_run_normal_then_transposed_after_done(self):
        m = self.running(False)
        self.step(m, Step(0, 0, clear=True, last=True, finish=True))
        self.step(m, returned=Return(0, last=True))
        self.step(m, completion=True)
        self.assertEqual(m.state, "finish")
        for i in range(7):
            self.assertFalse(m.cycle(group=Group(tag=i, transposed=True), group_valid=True)["group_fire"])
        self.step(m, ready=True)
        m.cycle(done_ready=True)
        self.assertEqual(m.state, "idle")
        self.assertTrue(m.cycle(group=Group(tag=88, transposed=True), group_valid=True)["group_fire"])
        m.cycle()
        self.assertEqual(self.step(m, Step(0, 1, clear=True))["operands"], route(A, B, True))

    def test_eight_metadata_two_result_backpressure_and_simultaneous_replacement(self):
        m = self.running(bits=16)
        for i in range(8):
            self.assertTrue(self.step(m, Step(i, i, clear=i == 0))["accepted"])
        for _ in range(4): self.assertFalse(self.step(m, Step(99, 99))["accepted"])
        self.step(m, returned=Return(0)); self.step(m, returned=Return(1))
        hold = m.values[0]
        for i in range(12):
            r = self.step(m, returned=Return(2), group=Group(tag=i, transposed=False), group_valid=True)
            self.assertFalse(r["consumed"])
            self.assertEqual(r["offered"], hold)
            self.assertTrue(m.group.transposed)
        r = self.step(m, Step(8, 8), returned=Return(2), ready=True)
        self.assertTrue(r["accepted"] and r["consumed"])
        self.assertEqual([v.tag for v in m.values], [1, 2])
        self.assertEqual(r["operands"], route(A, B, True))

    def test_endpoint_not_ready_blocks_operand_acceptance(self):
        m = self.running()
        for _ in range(20): self.assertFalse(self.step(m, Step(0, 0, clear=True), endpoint_ready=False)["accepted"])
        self.assertFalse(m.tags)
        self.assertTrue(self.step(m, Step(0, 0, clear=True))["accepted"])

    def test_five_contexts_return_tags_and_terminal_group_tag(self):
        for width in (0, 1, 16, 32):
            m = self.running(bits=width)
            maximum = (1 << width)-1
            for c in range(5):
                r = self.step(m, Step(maximum, c, context=c, clear=True, last=True, finish=c == 4))
                self.assertTrue(r["accepted"])
            got = []
            for c in range(5):
                r = self.step(m, returned=Return(c, context=c, last=True), ready=True)
                if r["delivered"]: got.append(r["delivered"])
            r = self.step(m, ready=True, completion=True)
            if r["delivered"]: got.append(r["delivered"])
            self.assertEqual([v.token for v in got], list(range(5)))
            self.assertEqual([v.tag for v in got], [maximum if width else None]*5)
            self.assertEqual(m.cycle(done_ready=True)["group_tag"], 0x1234)
            self.assertEqual(m.state, "idle")

    def test_abort_drains_preserves_old_buffered_outputs_and_requires_reset(self):
        m = self.running()
        for c in range(3): self.step(m, Step(0, c, clear=c == 0))
        self.step(m, returned=Return(0))
        r = self.step(m, Step(0, 9), returned=Return(1), abort=True)
        self.assertFalse(r["accepted"])
        self.assertEqual(m.state, "draining")
        self.assertEqual(len(m.values), 2)
        self.step(m, returned=Return(2), abort=True)
        self.assertEqual(len(m.values), 2)
        m.cycle(abort=True)
        self.assertEqual(m.state, "finish")
        self.step(m, ready=True); self.step(m, ready=True)
        m.cycle(done_ready=True)
        self.assertEqual(m.state, "locked")
        self.assertFalse(m.cycle(group=Group(transposed=False), group_valid=True)["group_fire"])
        m.cycle(reset=True)
        self.assertEqual((m.state, m.group, m.poison), ("idle", None, False))
        m.cycle(group=Group(transposed=False), group_valid=True); m.cycle()
        self.assertEqual(self.step(m, Step(0, 0, clear=True))["operands"], route(A, B))

    def test_reset_mid_group_discards_mode_and_provisional_state(self):
        for stage in ("command", "running", "finish", "locked"):
            m = ServiceContract(True)
            m.cycle(group=Group(transposed=True), group_valid=True)
            if stage == "running":
                m.cycle(); self.step(m, Step(0, 0, clear=True))
            elif stage in ("finish", "locked"):
                m.cycle(abort=True); m.cycle()
                if stage == "locked": m.cycle(done_ready=True)
            self.assertEqual(m.state, stage)
            m.cycle(reset=True)
            self.assertEqual((m.state, m.group, len(m.tags), len(m.values)), ("idle", None, 0, 0))

    def test_illegal_context_or_clear_never_issues_endpoint_operand(self):
        for step in (Step(0, 0, context=5, clear=True), Step(0, 0, clear=False), Step(0, 0, clear=True, finish=True)):
            m = self.running()
            r = self.step(m, step, endpoint_ready=False)
            self.assertTrue(r["input_fire"])
            self.assertFalse(r["accepted"])
            self.assertIsNone(r["operands"])
            self.assertEqual(m.state, "draining")

    def test_bad_return_and_endpoint_error_keep_existing_poison_scope(self):
        for issue in ("context", "last", "endpoint"):
            m = self.running()
            self.step(m, Step(0, 0, clear=True))
            self.step(m, returned=Return(0, context=int(issue == "context"), last=issue == "last"), endpoint_error=issue == "endpoint")
            self.assertTrue(m.poison)
            self.assertEqual(m.state, "draining")


class SourceBindingTests(unittest.TestCase):
    def test_exact_pins_and_combined_patch_equal_guarded_overlay(self):
        manifest = json.loads((TASK/"manifest.json").read_text())
        source = check_inputs(manifest)
        with tempfile.TemporaryDirectory(prefix="transposed_overlay_") as temp:
            top = Path(temp)
            build_overlay(source, top/"sequential", manifest)
            combined = top/"combined"; combined.mkdir()
            for name in manifest["patched_sources"]:
                path = combined/PREFIX/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(source[name])
            subprocess.run(["git", "apply", "--check", str(TASK/"combined_service.patch")], cwd=combined, check=True)
            subprocess.run(["git", "apply", str(TASK/"combined_service.patch")], cwd=combined, check=True)
            for name, digest in manifest["patched_sources"].items():
                check((combined/PREFIX/name).read_bytes(), digest, name)
                self.assertEqual((combined/PREFIX/name).read_bytes(), (top/"sequential"/PREFIX/name).read_bytes())

    def test_mode_is_part_of_original_group_latch_and_resource_graph(self):
        manifest = json.loads((TASK/"manifest.json").read_text())
        inputs = check_inputs(manifest)
        with tempfile.TemporaryDirectory(prefix="transposed_source_") as temp:
            directory = Path(temp)/"overlay"
            build_overlay(inputs, directory, manifest)
            source = (directory/PREFIX/"MatrixPipeline.scala").read_text()
        self.assertEqual(source.count("group:=io.port.group.bits"), 1)
        self.assertIn("when(io.port.group.fire){\n    group:=io.port.group.bits", source)
        self.assertIn("val group=Reg(new MatrixStreamGroup(enableTransposedDense))", source)
        self.assertNotRegex(source, r"Reg(?:Init)?\([^\n]*transposedDense")
        self.assertEqual(source.count("Seq.fill(8)(Module(new RetainedMatrixEndpoint))"), 1)
        self.assertEqual(source.count("Module(new Queue(new Meta,8,pipe=true))"), 1)
        self.assertEqual(source.count("Module(new MatrixResultFifo(returnTagBits))"), 1)
        self.assertIn("io.port.group.ready:=state===idle && !poison", source)
        self.assertIn("values.io.enq.bits.value(r)(i*32+c):=Mux(selected(i),e.out_acc_o((r*32+c)*32+31,(r*32+c)*32),0.U)", source)


class IdentityNegativeTests(unittest.TestCase):
    def test_each_candidate_input_hash_drift_is_rejected(self):
        original = json.loads((TASK/"manifest.json").read_text())
        for name in original["task_files"]:
            changed = json.loads(json.dumps(original))
            changed["task_files"][name] = "0"*64
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, "identity drift"):
                check_inputs(changed)

    def test_each_dependency_hash_drift_is_rejected(self):
        original = json.loads((TASK/"manifest.json").read_text())
        for name in original["dependencies"]:
            changed = json.loads(json.dumps(original))
            changed["dependencies"][name] = "0"*64
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, "identity drift"):
                check_inputs(changed)

    def test_each_original_source_hash_drift_is_rejected(self):
        original = json.loads((TASK/"manifest.json").read_text())
        for name in original["original_sources"]:
            changed = json.loads(json.dumps(original))
            changed["original_sources"][name] = "0"*64
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, "identity drift"):
                check_inputs(changed)

    def test_missing_source_pin_is_rejected(self):
        changed = json.loads((TASK/"manifest.json").read_text())
        del changed["task_files"]["transposed_mode.patch"]
        with self.assertRaisesRegex(ValueError, "manifest file set changed"):
            check_inputs(changed)

    def test_extra_and_escaping_manifest_paths_are_rejected(self):
        for path in ("extra.py", "../transposed_model.py", "/tmp/transposed_model.py"):
            changed = json.loads((TASK/"manifest.json").read_text())
            changed["task_files"][path] = "0"*64
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "manifest file set changed"):
                check_inputs(changed)

    def test_wrong_base_and_malformed_hash_are_rejected(self):
        changed = json.loads((TASK/"manifest.json").read_text())
        changed["source_base_commit"] = "HEAD"
        with self.assertRaisesRegex(ValueError, "source baseline"):
            check_inputs(changed)
        changed = json.loads((TASK/"manifest.json").read_text())
        changed["task_files"]["transposed_model.py"] = "z"*64
        with self.assertRaisesRegex(ValueError, "invalid path or SHA256"):
            check_inputs(changed)

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="transposed_path_") as temp:
            directory = Path(temp)
            (directory/"outside").symlink_to(ROOT)
            with self.assertRaisesRegex(ValueError, "escapes its root"):
                frontend.bounded_file(directory, "outside/scripts/check_transposed_matrix_frontend.py")

    def test_executing_runner_identity_is_checked_separately_from_repo_copy(self):
        manifest = json.loads((TASK/"manifest.json").read_text())
        with tempfile.TemporaryDirectory(prefix="transposed_runner_") as temp:
            foreign = Path(temp)/"runner.py"
            foreign.write_text("# a different executing runner identity\n")
            with patch.object(frontend, "__file__", str(foreign)):
                with self.assertRaisesRegex(ValueError, "executing frontend runner"):
                    check_inputs(manifest)


class OperandGraphNegativeTests(unittest.TestCase):
    def fixture(self):
        def pack(words):
            result = words[0]
            for word in words[1:]: result = f"cat({word}, {result})"
            return result
        body = ["circuit MatrixPipelineService :", "  module MatrixPipelineService :"]
        body.append("    node av = "+pack([f"io.port.step.bits.a[{i}]" for i in range(16)]))
        for s in range(8):
            body.append(f"    node bv{s} = "+pack([f"io.port.step.bits.b[{32*s+i}]" for i in range(32)]))
            body.append(f"    connect leaves_{s}.step_a_i, av")
            body.append(f"    connect leaves_{s}.step_b_i, bv{s}")
        return "\n".join(body)+"\n"

    def test_unrelated_module_cannot_overwrite_operand_node(self):
        base = self.fixture()
        noise = "  module Unrelated :\n    node av = unsupported(foo)\n    connect leaves_0.step_a_i, bogus\n"
        self.assertEqual(OperandGraph(base+noise).evaluate(A, B, False, True), route(A, B))

    def test_missing_or_duplicate_service_module_is_rejected(self):
        for text in (self.fixture().replace("  module MatrixPipelineService :", "  module Other :"),
                     self.fixture()+"  module MatrixPipelineService :\n"):
            with self.assertRaisesRegex(ValueError, "exactly one MatrixPipelineService"):
                OperandGraph(text)

    def test_duplicate_operand_node_and_connect_are_rejected(self):
        for suffix in ("    node av = io.port.step.bits.a[0]\n", "    connect leaves_0.step_a_i, av\n"):
            with self.assertRaisesRegex(ValueError, "duplicate operand-cone"):
                OperandGraph(self.fixture()+suffix)

    def test_conditional_operand_driver_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "conditional operand-cone"):
            OperandGraph(self.fixture().replace("    connect leaves_0.step_a_i", "      connect leaves_0.step_a_i"))

    def test_unsupported_operand_expression_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported operand-cone"):
            OperandGraph(self.fixture().replace("connect leaves_0.step_a_i, av", "connect leaves_0.step_a_i, add(av, av)"))

    def test_cyclic_operand_graph_is_rejected(self):
        text = self.fixture().replace("connect leaves_0.step_a_i, av", "connect leaves_0.step_a_i, loop")+"    node loop = loop\n"
        with self.assertRaisesRegex(ValueError, "cyclic operand-cone"):
            OperandGraph(text)

    def test_live_group_mode_is_rejected_even_in_unselected_mux_branch(self):
        text = self.fixture().replace("connect leaves_0.step_a_i, av",
              "connect leaves_0.step_a_i, mux(group.transposedDense, av, mux(io.port.group.bits.transposedDense, av, av))")
        with self.assertRaisesRegex(ValueError, "live group pin"):
            OperandGraph(text)

    def test_out_of_range_input_and_bad_expression_arity_are_rejected(self):
        for expression in ("io.port.step.bits.b[256]", "cat(av)", "mux(av, av)"):
            text = self.fixture().replace("connect leaves_0.step_a_i, av", "connect leaves_0.step_a_i, "+expression)
            with self.assertRaises(ValueError): OperandGraph(text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
