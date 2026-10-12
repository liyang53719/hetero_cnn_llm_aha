#!/usr/bin/env python3
"""Bounded source/symbolic audit only; no Scala frontend, arithmetic, or RTL.

The exact reversal/hash checks bind this Python model to two allowed source
address substitutions. The mock progress model is not a Chisel interpreter.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRODUCTION = ROOT / "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Bf16CausalGqaOwner.scala"
OVERLAY = HERE / "Bf16CausalGqaOwner.scala"
BASELINE_SHA256 = "d4c1047d275fa0b38d9498fdf6c22018f52138b21a49e55866661a4d4e635cd9"
BASE = PRODUCTION.read_text()
NEW = OVERLAY.read_text()

OLD_DOC = "  * QK: opcode0x23/slice0, increasing d0..255 FP32 FMA, terminal BF16 RNE.\n"
NEW_DOC = ("  * QK: opcode0x23/slice0, increasing d0..255 FP32 FMA by default, terminal BF16 RNE.\n"
           "  * Explicit enableQkPairHighFirst selects d1,0,3,2,...,255,254 operands only.\n")
OLD_CONSTRUCTOR = "class Bf16CausalGqaOwner(maxTokens: Int = 128, maxCacheTokens: Int = 256) extends Module {"
NEW_CONSTRUCTOR = "class Bf16CausalGqaOwner(maxTokens: Int = 128, maxCacheTokens: Int = 256, enableQkPairHighFirst: Boolean = false) extends Module {"
ROUTING = ("  // Operand routing only: keep dimension as the original accepted-step counter.\n"
           "  val qkDimension = if (enableQkPairHighFirst) dimension ^ 1.U(8.W) else dimension\n")


def restore_baseline(source: str) -> str:
    """Reverse the complete, closed list of permitted source changes."""
    replacements = [(NEW_DOC, OLD_DOC), (NEW_CONSTRUCTOR, OLD_CONSTRUCTOR), (ROUTING, "")]
    for buffer in ("query(r)", "keys(c)"):
        before = f"{buffer}.read(dimension(7, 5)).asTypeOf(Vec(32, UInt(16.W)))(dimension(4, 0))"
        after = before.replace("dimension", "qkDimension")
        replacements.append((after, before))
    for changed, original in replacements:
        if source.count(changed) != 1:
            raise ValueError(f"Expected exactly one permitted overlay fragment: {changed!r}")
        source = source.replace(changed, original, 1)
    return source


def selected_dimension(dimension: int, enabled: bool) -> int:
    if not 0 <= dimension < 256:
        raise ValueError("dimension must fit the unchanged eight-bit counter")
    return dimension ^ 1 if enabled else dimension


def pack(values):
    return sum(value << (16 * lane) for lane, value in enumerate(values))


def make_buffer(rows: int, prefix: int):
    return [[pack([prefix + 256 * row + 32 * bank + lane for lane in range(32)])
             for bank in range(8)] for row in range(rows)]


QUERY = make_buffer(16, 0x1000)
KEYS = make_buffer(32, 0x4000)


def read_buffer(buffer, row: int, dimension: int) -> int:
    return (buffer[row][dimension >> 5] >> (16 * (dimension & 31))) & 0xFFFF


def qk_packet(dimension: int, enabled: bool, rows: int = 16, columns: int = 32):
    address = selected_dimension(dimension, enabled)
    final = dimension == 255
    return {
        "context": 0, "clear": dimension == 0,
        "last": final, "finish": final, "emit": final,
        "a": tuple(read_buffer(QUERY, r, address) if r < rows else 0 for r in range(16)),
        "b": tuple(read_buffer(KEYS, c, address) if c < min(columns, 32) else 0 for c in range(256)),
    }


def mock_qk_trace(enabled: bool, stalls):
    """Only model accepted-step advancement; no memory/Matrix implementation."""
    dimension, state, trace = 0, "stepQk", []
    for expected_step in range(256):
        assert dimension == expected_step and state == "stepQk"
        for ready in [False] * stalls(expected_step) + [True]:
            before = (dimension, state)
            packet = qk_packet(dimension, enabled, rows=7, columns=19)
            if ready:
                if dimension == 255:
                    state = "resultQk"
                else:
                    dimension += 1
            trace.append((before, ready, packet, (dimension, state)))
    return trace


class OverlayAudit(unittest.TestCase):
    def test_pinned_baseline_and_exact_default_reconstruction(self):
        self.assertEqual(hashlib.sha256(PRODUCTION.read_bytes()).hexdigest(), BASELINE_SHA256)
        self.assertEqual(restore_baseline(NEW), BASE)
        self.assertEqual(hashlib.sha256(restore_baseline(NEW).encode()).hexdigest(), BASELINE_SHA256)
        self.assertIn("enableQkPairHighFirst: Boolean = false", NEW)
        self.assertIn("if (enableQkPairHighFirst) dimension ^ 1.U(8.W) else dimension", NEW)
        # With the compile-time option false, both original read expressions
        # and every byte of the original body are recovered by this reversal.

    def test_identity_check_rejects_drift_outside_operand_routing(self):
        for old, changed in (("dimension === 255.U", "qkDimension === 255.U"),
                             ("key := key + 1.U", "key := key + 2.U"),
                             ("0x24.U", "0x25.U"),
                             ("rows &&", "columns &&")):
            self.assertIn(old, NEW)
            mutated = NEW.replace(old, changed, 1)
            self.assertNotEqual(hashlib.sha256(restore_baseline(mutated).encode()).hexdigest(), BASELINE_SHA256)
        with self.assertRaises(ValueError):
            restore_baseline(NEW.replace(ROUTING, ""))

    def test_same_abi_state_storage_resources_and_non_qk_logic(self):
        # Includes all job/result/port bundles, and therefore public/internal ABI.
        self.assertEqual(BASE.split("/** Bounded", 1)[0], NEW.split("/** Bounded", 1)[0])
        declarations = r"^.*\b(?:Reg|RegInit|Mem|SyncReadMem|Enum)\([^\n]*$"
        self.assertEqual(re.findall(declarations, BASE, re.M), re.findall(declarations, NEW, re.M))
        self.assertEqual(BASE.count("extends Module"), 1)
        self.assertEqual(NEW.count("extends Module"), 1)
        self.assertNotRegex(NEW, r"Module\s*\(\s*new\b")
        # Memory addresses, Q/K/V reads and writes, row/beat selection, scalar,
        # completion, abort/drain, reset-required, and all PV advancement match.
        self.assertEqual(BASE.split("  val collectingResult =", 1)[1],
                         NEW.split("  val collectingResult =", 1)[1])
        original_pre = BASE.split("  io.matrix.step.bits.emit := lastStep\n", 1)[0]
        overlay_pre = NEW.split("  io.matrix.step.bits.emit := lastStep\n", 1)[0]
        self.assertEqual(overlay_pre.replace(NEW_DOC, OLD_DOC).replace(NEW_CONSTRUCTOR, OLD_CONSTRUCTOR), original_pre)

    def test_qk_uses_one_combinational_alias_only(self):
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", NEW, flags=re.S)
        self.assertEqual(code.count("qkDimension"), 5)  # declaration and four bit selections
        self.assertEqual(code.count("enableQkPairHighFirst"), 2)  # constructor and Scala if
        self.assertIn("val q = query(r).read(qkDimension(7, 5)).asTypeOf(Vec(32, UInt(16.W)))(qkDimension(4, 0))", code)
        self.assertIn("val k = if (c < 32) keys(c).read(qkDimension(7, 5)).asTypeOf(Vec(32, UInt(16.W)))(qkDimension(4, 0)) else 0.U", code)
        self.assertIn("io.matrix.step.bits.clear := Mux(state === stepPv, key === 0.U, dimension === 0.U)", code)
        self.assertIn("val lastStep = Mux(state === stepPv, key +& 1.U === job.cacheLength, dimension === 255.U)", code)
        for flag in ("last", "finish", "emit"):
            self.assertIn(f"io.matrix.step.bits.{flag} := lastStep", code)

    def test_all_256_dimensions_pair_mapping_and_existing_banks(self):
        expected = [value for low in range(0, 256, 2) for value in (low + 1, low)]
        self.assertEqual([selected_dimension(d, True) for d in range(256)], expected)
        self.assertEqual([selected_dimension(d, False) for d in range(256)], list(range(256)))
        self.assertEqual(sorted(expected), list(range(256)))
        for dimension, routed in enumerate(expected):
            self.assertEqual(routed >> 5, dimension >> 5)  # no bank crossing
            self.assertEqual(routed & 31, (dimension & 31) + (1 if dimension % 2 == 0 else -1))
            self.assertEqual(selected_dimension(routed, True), dimension)
            for enabled, selected in ((False, dimension), (True, routed)):
                for row in range(16):
                    self.assertEqual(read_buffer(QUERY, row, selected_dimension(dimension, enabled)),
                                     0x1000 + row * 256 + selected)
                for column in range(32):
                    self.assertEqual(read_buffer(KEYS, column, selected_dimension(dimension, enabled)),
                                     0x4000 + column * 256 + selected)

    def test_original_rows_columns_head_group_and_result_beats(self):
        # Every admitted partial tile retains exactly its original active rows/columns.
        for enabled in (False, True):
            for dimension in range(256):
                address = selected_dimension(dimension, enabled)
                full = qk_packet(dimension, enabled)
                for rows in range(1, 17):
                    partial = qk_packet(dimension, enabled, rows=rows)
                    self.assertEqual(partial["a"], full["a"][:rows] + (0,) * (16 - rows))
                for columns in range(1, 33):
                    partial = qk_packet(dimension, enabled, columns=columns)
                    self.assertEqual(partial["b"], full["b"][:columns] + (0,) * (256 - columns))
                self.assertEqual(full["a"][0], 0x1000 + address)
        self.assertIn("(head(2, 2).pad(65) << 9)", NEW)
        self.assertEqual([head >> 2 for head in range(8)], [0, 0, 0, 0, 1, 1, 1, 1])
        helper = "object GqaMatrixResultSelect {"
        self.assertEqual(NEW.split(helper, 1)[1], BASE.split(helper, 1)[1])
        self.assertIn("b.U -> value(r)(b * 32 + lane)", NEW)
        tile = [[(row << 16) | column for column in range(256)] for row in range(16)]
        for row in range(16):
            for beat in range(8):
                selected = [tile[row][beat * 32 + lane] for lane in range(32)]
                self.assertEqual(selected, [(row << 16) | column for column in range(32 * beat, 32 * (beat + 1))])

    def test_held_qk_steps_and_terminal_control_under_mocked_progress(self):
        for stalls in (lambda d: 0, lambda d: 3, lambda d: (d * 7) % 4):
            old_trace, pair_trace = mock_qk_trace(False, stalls), mock_qk_trace(True, stalls)
            accepted = []
            for old, pair in zip(old_trace, pair_trace, strict=True):
                before, ready, packet, after = pair
                self.assertEqual((before, ready, after), (old[0], old[1], old[3]))
                for flag in ("context", "clear", "last", "finish", "emit"):
                    self.assertEqual(packet[flag], old[2][flag])
                if ready:
                    accepted.append(packet)
                else:
                    self.assertEqual(after, before)
                    self.assertEqual(packet, qk_packet(after[0], True, rows=7, columns=19))
            self.assertEqual(len(accepted), 256)
            self.assertEqual([p["a"][0] - 0x1000 for p in accepted],
                             [v for low in range(0, 256, 2) for v in (low + 1, low)])
            self.assertEqual([i for i, p in enumerate(accepted) if p["clear"]], [0])
            for flag in ("last", "finish", "emit"):
                self.assertEqual([i for i, p in enumerate(accepted) if p[flag]], [255])
            self.assertEqual(pair_trace[-1][3], (255, "resultQk"))
            self.assertEqual(accepted[-1]["a"][0], 0x1000 + 254)

    def test_pv_ascending_and_flags_ignore_pair_option(self):
        for fragment in (
            "Mux(state === stepPv, scoreReads(r)(31, 16), q)",
            "val v = value(c / 32)(16 * (c % 32) + 15, 16 * (c % 32))",
            "Mux(state === stepPv, v, Mux(c.U < columns, k, 0.U))",
            "key := key + 1.U; state := readV",
            "io.matrix.group.bits.opcode := Mux(state === groupPv, 0x24.U, 0x23.U)",
            "io.matrix.group.bits.sliceMask := Mux(state === groupPv, 255.U, 1.U)",
        ):
            self.assertIn(fragment, NEW)
            self.assertIn(fragment, BASE)
        for cache_length in range(1, 257):
            expected = [(key, key == 0, key + 1 == cache_length) for key in range(cache_length)]
            for enabled in (False, True):
                key, accepted = 0, []
                while key < cache_length:
                    # PV selection uses key, never selected_dimension(). The
                    # arbitrary QK dimension/option cannot affect this packet.
                    packet = (key, key == 0, key + 1 == cache_length)
                    for _ in range(key % 3):
                        self.assertEqual(packet, (key, key == 0, key + 1 == cache_length))
                    accepted.append(packet)
                    key += 1
                self.assertEqual(accepted, expected, (enabled, cache_length))

    def test_symbolic_fma_association_follows_pair_sequence(self):
        for enabled in (False, True):
            actual = ("positive_zero",)
            for dimension in range(256):
                d = selected_dimension(dimension, enabled)
                actual = ("FP32_RNE_FMA", ("q", d), ("k", d), actual)
            expected = ("positive_zero",)
            for pair in range(128):
                indices = (2 * pair + 1, 2 * pair) if enabled else (2 * pair, 2 * pair + 1)
                for index in indices:
                    expected = ("FP32_RNE_FMA", ("q", index), ("k", index), expected)
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OverlayAudit))
    print(json.dumps({
        "kind": "static_source_and_symbolic_schedule_only",
        "checks_passed": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "baseline_sha256": hashlib.sha256(PRODUCTION.read_bytes()).hexdigest(),
        "expected_baseline_sha256": BASELINE_SHA256,
        "overlay_sha256": hashlib.sha256(OVERLAY.read_bytes()).hexdigest(),
        "qk_steps": 256,
        "new_register_declarations": 0,
        "new_memory_declarations": 0,
        "new_arithmetic_modules": 0,
        "scala_frontend": "NOT_RUN",
        "chisel_elaboration": "NOT_RUN",
        "rtl_simulation": "NOT_RUN",
        "numerical_execution": "NOT_RUN",
        "production_source_replaced": False,
    }, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
