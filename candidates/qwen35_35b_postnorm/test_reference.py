"""Cold stdlib-only AST/shape/admission gates. No Torch, NumPy, or weights."""
import ast
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from . import reference as r


class ReferenceTests(unittest.TestCase):
    def test_source_pins_complete_classes_and_exact_statements(self):
        nodes, identity = r._source_definition()
        self.assertEqual(identity["source_sha256"], "ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30")
        self.assertEqual(identity["decoder_lines"], [898, 954])
        self.assertEqual(identity["decoder_sha256"], r.DECODER_SHA)
        self.assertEqual(identity["rms"]["class_lines"], [878, 895])
        self.assertEqual(identity["rms"]["class_sha256"], r.RMS_CLASS_SHA)
        self.assertEqual([node.lineno for node in nodes], [943, 947])
        self.assertEqual([item["sha256"] for item in identity["statements"]], [r.RESIDUAL_SHA, r.POSTNORM_SHA])
        for field in ("full_native_forward", "mlp_executed", "installed_moe_module_imported",
                      "rtl_executed", "reference_bytes_may_fill_producer"):
            self.assertFalse(identity[field])

    def test_wrapping_preserves_node_identity_attributes_and_original_location(self):
        nodes, _ = r._source_definition()
        for node, name, args in zip(nodes, ("residual", "postnorm"),
                                    (("residual", "hidden_states"), ("self", "hidden_states"))):
            before = ast.dump(copy.deepcopy(node), include_attributes=True)
            wrapped = r._statement_module(node, name, args)
            self.assertIs(wrapped.body[0].body[0], node)
            self.assertEqual(ast.dump(node, include_attributes=True), before)
            self.assertEqual(len(wrapped.body[0].body), 2)
            self.assertIsInstance(wrapped.body[0].body[1], ast.Return)
        (residual_fn, postnorm_fn), _ = r.source_functions()
        self.assertEqual(residual_fn.__code__.co_firstlineno, 943)
        self.assertEqual(postnorm_fn.__code__.co_firstlineno, 947)
        self.assertEqual(residual_fn.__code__.co_filename, str(r.ROOT / r.SOURCE))

    def test_original_operand_order_and_module_call_with_symbolic_values(self):
        calls, actual_o, observed_residual, normalized = [], object(), object(), object()

        class Hidden:
            def __add__(self, other):
                calls.append(("original_hidden_plus_actual_o", other))
                return observed_residual

        def original_norm(value):
            calls.append(("original_post_attention_norm", value))
            return normalized

        (residual_fn, postnorm_fn), _ = r.source_functions()
        result = residual_fn(Hidden(), actual_o)
        self.assertIs(result, observed_residual)
        self.assertIs(postnorm_fn(SimpleNamespace(post_attention_layernorm=original_norm), result), normalized)
        self.assertEqual(calls, [("original_hidden_plus_actual_o", actual_o),
                                 ("original_post_attention_norm", observed_residual)])

    def test_changed_source_or_config_fails_cold(self):
        for target, pattern in ((r.SOURCE, "modeling source drift"), (r.CONFIG, "model config drift")):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for relative in (r.SOURCE, r.CONFIG):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((r.ROOT / relative).read_bytes() + (b"\n" if relative == target else b""))
                with self.assertRaisesRegex(ValueError, pattern):
                    r.source_identity(root)

    def test_decoder_and_statement_pins_are_independently_enforced(self):
        for constant, message in (("DECODER_SHA", "decoder class drift"),
                                  ("RESIDUAL_SHA", "statement drift at line 943"),
                                  ("POSTNORM_SHA", "statement drift at line 947")):
            with self.subTest(pin=constant), mock.patch.object(r, constant, "0" * 64):
                with self.assertRaisesRegex(ValueError, message):
                    r.source_identity()

    def test_complete_finite_raw_shapes_and_signed_zero_subnormals(self):
        edge = struct.pack("<6H", 0, 0x8000, 1, 0x8001, 0x7f7f, 0xff7f)
        weight = (edge * 342)[:4096]
        for tokens in (1, 16, 128):
            self.assertIsNone(r.validate_raw(weight * tokens, bytes(tokens * 4096), weight, tokens))

    def test_bad_token_type_bounds_shapes_and_byte_types_rejected(self):
        valid = [bytes(4096), bytes(4096), bytes(4096), 1]
        cases = []
        for tokens in (False, True, 0, -1, 129, 1.0, "1"):
            cases.append(valid[:3] + [tokens])
        for index in range(3):
            for value in (bytes(4094), bytes(4098), bytearray(4096), memoryview(bytes(4096)), None):
                case = list(valid)
                case[index] = value
                cases.append(case)
        for case in cases:
            with self.subTest(types=[type(value).__name__ for value in case]):
                with self.assertRaises(ValueError):
                    r.validate_raw(*case)

    def test_nonfinite_each_input_is_rejected_before_torch_import(self):
        for index in range(3):
            for word in (0x7f80, 0xff80, 0x7fc0, 0xffc1):
                case = [bytes(4096), bytes(4096), bytes(4096), 1]
                case[index] = struct.pack("<H", word) + case[index][2:]
                with self.subTest(input=index, word=word), self.assertRaisesRegex(ValueError, "nonfinite BF16"):
                    r.component(*case)

    def test_dispatch_contract_has_one_bf16_add_and_original_ten_rms_ops(self):
        self.assertEqual(len(r.SEQUENCE), 11)
        self.assertEqual(r.SEQUENCE[0], ("aten.add.Tensor", "residual"))
        self.assertEqual(r.SEQUENCE[1:], r.RMS_SEQUENCE)
        self.assertEqual([name for _, name in r.RMS_SEQUENCE], ["input_fp32", "squares", "mean", "mean_eps",
                         "inverse", "scaled", "weight_fp32", "gamma", "weighted", "output"])
        self.assertNotIn("sum_auxiliary", [name for _, name in r.SEQUENCE])

    def test_runtime_reuses_existing_rms_profile_and_binary_pins(self):
        self.assertIs(r.runtime_identity, r.rms.runtime_identity)
        self.assertIs(r.runtime_selection, r.rms.runtime_selection)
        profile, _, pins = r.runtime_selection("recovery_20261013")
        self.assertEqual(profile, "recovery_20261013")
        for name in pins:
            if name.startswith("site-packages/"):
                self.assertEqual(pins[name], r.rms.RUNTIME_PINS[name])

    def test_cold_subprocess_forbids_arithmetic_imports_and_work_reads(self):
        script = '''
import builtins
from pathlib import Path
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in ('torch', 'numpy'):
        raise AssertionError('cold path imported ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
original_read = Path.read_bytes
repository_root = Path.cwd().resolve()
def guarded_read(self, *args, **kwargs):
    if self.resolve().is_relative_to(repository_root / 'work'):
        raise AssertionError('cold path read work artifact')
    return original_read(self, *args, **kwargs)
Path.read_bytes = guarded_read
from candidates.qwen35_35b_postnorm import reference as r
r.source_identity()
r.source_functions()
r.validate_raw(bytes(4096), bytes(4096), bytes(4096), 1)
r.runtime_selection('recovery_20261013')
# A CI checkout may itself have an ancestor named work. Only its own
# artifact directory is forbidden, including a symlink into that directory.
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    saved_root = repository_root
    repository_root = Path(tmp) / 'work' / 'checkout'
    repository_root.mkdir(parents=True)
    source = repository_root / 'config' / 'source'
    source.parent.mkdir()
    source.write_bytes(b'official source')
    assert source.read_bytes() == b'official source'
    artifact = repository_root / 'work' / 'raw'
    artifact.parent.mkdir()
    artifact.write_bytes(b'artifact')
    alias = repository_root / 'alias'
    alias.symlink_to(artifact)
    for path in (artifact, alias):
        try:
            path.read_bytes()
        except AssertionError as error:
            assert str(error) == 'cold path read work artifact'
        else:
            raise AssertionError('artifact read guard failed')
    repository_root = saved_root
print('PASS cold stdlib path')
'''
        result = subprocess.run([sys.executable, "-S", "-c", script], cwd=r.ROOT,
                                text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), "PASS cold stdlib path")


if __name__ == "__main__":
    unittest.main()
