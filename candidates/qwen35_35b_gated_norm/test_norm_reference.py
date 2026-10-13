"""Torch-free candidate checks. Run with unittest, no runtime or weights needed."""
import ast
import builtins
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("norm_reference_candidate", HERE / "norm_reference.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)



class NormReferenceTorchFreeTests(unittest.TestCase):
    def test_import_and_source_identity_do_not_need_torch_or_numpy(self):
        real_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in ("torch", "numpy"):
                raise AssertionError("unexpected arithmetic runtime import: " + name)
            return real_import(name, *args, **kwargs)
        with mock.patch.object(builtins, "__import__", side_effect=guarded):
            identity = r.source_identity()
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("numpy", sys.modules)
        self.assertTrue(identity["original_forward_unchanged"])
        self.assertFalse(identity["full_transformers_module_executed"])

    def test_only_optional_decorators_removed_from_original_norm(self):
        (module, activation), identity = r._source_ast()
        original = r._find_class(ast.parse((r.ROOT / r.SOURCE).read_bytes()), r.NORM_CLASS)
        executable = module.body[0]
        self.assertEqual(ast.dump(r._forward(original)), ast.dump(r._forward(executable)))
        original.decorator_list = []
        self.assertEqual(ast.dump(original), ast.dump(executable))
        self.assertEqual([n.name for n in activation.body], ["SiLUActivation", "ClassInstantier"])
        self.assertEqual(identity["class_lines"], [176, 192])
        self.assertEqual(identity["activation_forward"], "return nn.functional.silu(input)")
        self.assertEqual(identity["activation_class"], "SiLUActivation")

    def test_original_dispatch_plan_contains_actual_assignments_and_casts(self):
        self.assertEqual(len(r.OP_SEQUENCE), 12)
        stages = {x[1]: x for x in r.OP_SEQUENCE}
        self.assertEqual(stages["variance"][0], "aten.mean.dim")
        self.assertEqual(stages["normalized_bf16"][4], "bfloat16")
        self.assertEqual(stages["weighted_fp32"][4], "float32")
        self.assertEqual(stages["silu_fp32"][0], "aten.silu.default")
        self.assertEqual(stages["gated_fp32"][4], "float32")
        self.assertEqual(stages["output_bf16"][4], "bfloat16")
        self.assertEqual([x[2] for x in r.OP_SEQUENCE if x[3].startswith("hidden_states assignment")],
                         [185, 188, 189, 190])

    def test_complete_raw_geometry_gamma_stays_fp32(self):
        for tokens in (1, 16, 128):
            raw = bytes(tokens * 32 * 128 * 2)
            r.validate_inputs(raw, raw, bytes(128 * 4), tokens)
        for tokens in (True, False, 0, 129, 1.0):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                r.validate_inputs(bytes(8192), bytes(8192), bytes(512), tokens)
        for values in ((bytes(8190), bytes(8192), bytes(512)),
                       (bytes(8192), bytes(8190), bytes(512)),
                       (bytes(8192), bytes(8192), bytes(256)),
                       (bytearray(8192), bytes(8192), bytes(512))):
            with self.subTest(lengths=[len(x) for x in values]), self.assertRaises(ValueError):
                r.validate_inputs(*values, 1)

    def test_nonfinite_rejected_subnormals_and_signed_zero_retained(self):
        for word in (0x7f80, 0xff80, 0x7fc0):
            bad = struct.pack("<H", word) + bytes(8190)
            for args in ((bad, bytes(8192), bytes(512)), (bytes(8192), bad, bytes(512))):
                with self.subTest(word=word), self.assertRaises(ValueError):
                    r.validate_inputs(*args, 1)
        for word in (0x7f800000, 0xff800000, 0x7fc00001):
            with self.subTest(gamma_word=word), self.assertRaises(ValueError):
                r.validate_inputs(bytes(8192), bytes(8192), struct.pack("<I", word) + bytes(508), 1)
        for core_word, gamma_word in ((1, 1), (0x8000, 0x80000000), (0x3f81, 0x3f801234)):
            core = struct.pack("<H", core_word) * 4096
            gamma = struct.pack("<I", gamma_word) * 128
            r.validate_inputs(core, core, gamma, 1)

    def test_source_pin_drift_rejected(self):
        for pin in ("SOURCE_SHA", "CONFIG_SHA", "ACTIVATIONS_SHA", "ACTIVATIONS_GIT_BLOB_SHA",
                    "NORM_CLASS_AST_SHA", "NORM_FORWARD_AST_SHA", "NORM_EXECUTABLE_CLASS_AST_SHA",
                    "SILU_CLASS_AST_SHA", "INSTANTIER_CLASS_AST_SHA"):
            with self.subTest(pin=pin), mock.patch.object(r, pin, "0" * 64), self.assertRaises(ValueError):
                r.source_identity()

    def test_no_setters_or_candidate_calls_or_external_writes(self):
        text = Path(r.__file__).read_text()
        tree = ast.parse(text)
        forbidden = {"use_deterministic_algorithms", "set_num_threads", "set_num_interop_threads",
                     "set_flush_denormal", "set_float32_matmul_precision", "write_text", "write_bytes"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                self.assertNotIn(name, forbidden)
                self.assertFalse(name.startswith("set_"))
        candidate_imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                             and n.module and n.module.startswith("candidates.")]
        self.assertEqual(candidate_imports, ["candidates.qwen35_35b_prep.chunk_reference"])
        self.assertNotIn("threshold=", text)
        self.assertNotIn("passed=True", text)

    def test_pre_runtime_rejection_is_torch_free(self):
        with mock.patch.dict(os.environ, {"ATEN_CPU_CAPABILITY": ""}), self.assertRaises(ValueError):
            r.native_norm(bytes(8192), bytes(8192), bytes(512), 1)
        self.assertNotIn("torch", sys.modules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
