"""Pure stdlib/mock tests. Never import a numerical package or run a model."""
import ast
import builtins
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
original_import = builtins.__import__


def prohibit_numerical(name, *args, **kwargs):
    if name.split(".")[0] in {"torch", "numpy", "transformers"}:
        raise AssertionError("forbidden numerical/model import during static/mock test: " + name)
    return original_import(name, *args, **kwargs)


builtins.__import__ = prohibit_numerical
spec = importlib.util.spec_from_file_location("official_capture_static_test", HERE / "capture.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class FakeTensor:
    def __init__(self, shape, dtype="bfloat16", payload=b"\0\0"):
        self.shape, self.dtype, self.device = shape, "torch." + dtype, "cpu"
        self.payload = payload

    def stride(self):
        return tuple(1 for _ in self.shape)

    def storage_offset(self):
        return 3

    def untyped_storage(self):
        return types.SimpleNamespace(data_ptr=lambda: id(self.payload), nbytes=lambda: len(self.payload))

    def detach(self):
        return self

    def clone(self):
        return FakeTensor(self.shape[:], self.dtype.removeprefix("torch."), self.payload)

    def contiguous(self):
        return self

    def view(self, dtype):
        return self

    def reshape(self, *shape):
        return self

    def tolist(self):
        return list(self.payload)

    def numel(self):
        return len(self.payload)

    def __getitem__(self, index):
        return FakeTensor([len(self.payload[index])], payload=self.payload[index])


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.pins = c.load_pins()

    def test_module_import_is_stdlib_only(self):
        self.assertFalse(set(sys.modules) & {"torch", "numpy", "transformers"})

    def test_public_execution_gate_closed_without_side_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "must_not_exist"
            with self.assertRaisesRegex(c.ExecutionDisabled, "EXECUTION_DISABLED"):
                c.run_capture("unused", output, {"run_id": "not_authority"})
            self.assertFalse(output.exists())

    def test_complete_29_geometry_and_13_original_inputs(self):
        self.assertEqual(len(self.pins["fields"]), 29)
        self.assertEqual(len(c.FIELD_ORDER), 29)
        self.assertEqual(len(self.pins["raw13"]), 13)
        self.assertEqual(sum(f["export_f32_bytes"] for f in self.pins["fields"].values()), 3720192)
        self.assertEqual(len({x["local_name"] for x in self.pins["raw13"]}), 13)
        self.assertEqual(sum(x["local_name"] != "embed_tokens.rows_0_255" for x in self.pins["raw13"]), 12)

    def test_mask_is_exact_cold_wrapper_input(self):
        words = [v[0] for v in struct.iter_unpack("<H", c.cold_mask_bytes())]
        self.assertEqual(words.count(0), 136)
        self.assertEqual(words.count(0xFF7F), 120)
        self.assertTrue(all(words[q * 16 + q] == 0 for q in range(16)))

    def test_exact_bf16_widening_including_sign_and_nonfinite(self):
        raw = b"\x80\x3f\x00\x80\x7f\xff\x80\x7f\xc0\x7f"
        self.assertEqual(c.widen_bf16(raw), b"\0\0\x80\x3f\0\0\0\x80\0\0\x7f\xff\0\0\x80\x7f\0\0\xc0\x7f")
        self.assertEqual(c.fp32_nonfinite_count(c.widen_bf16(raw)), 2)
        with self.assertRaises(ValueError):
            c.widen_bf16(b"\0")

    def test_snapshot_is_immediate_clone_and_hook_returns_none(self):
        observer = c.Observer(self.pins["fields"])
        value = FakeTensor([1, 16, 1536], payload=b"first")
        self.assertIsNone(observer.output_hook("n0")(None, (), value))
        value.payload = b"changed"
        self.assertEqual(observer.values["n0"].payload, b"first")
        self.assertEqual(observer.metadata["n0"]["storage_offset"], 3)

    def test_snapshot_error_does_not_escape_hook(self):
        def failed_snapshot(value):
            raise MemoryError("mock observation failure")
        observer = c.Observer(self.pins["fields"], snapshot=failed_snapshot)
        self.assertIsNone(observer.output_hook("n0")(None, (), FakeTensor([1, 16, 1536])))
        self.assertEqual(len(observer.errors), 1)
        self.assertFalse(observer.validate())

    def test_duplicate_observation_fails_without_replacing_first(self):
        observer = c.Observer(self.pins["fields"])
        observer.record("x", FakeTensor([1, 16, 1536], payload=b"first"))
        observer.record("x", FakeTensor([1, 16, 1536], payload=b"second"))
        self.assertEqual(observer.values["x"].payload, b"first")
        self.assertEqual(observer.order, ["x"])
        self.assertEqual(len(observer.errors), 1)

    def test_bad_rotary_and_decoder_outputs_do_not_change_control(self):
        observer = c.Observer(self.pins["fields"])
        self.assertIsNone(observer.rotary_hook(None, (), None))
        self.assertIsNone(observer.decoder_hook(None, (), None))
        self.assertEqual(len(observer.errors), 2)

    def test_trace_requires_exact_code_object(self):
        observer = c.Observer(self.pins["fields"])
        observer.attention_code = object()
        frame = types.SimpleNamespace(f_code=object(), f_lineno=280, f_locals={})
        self.assertIsNone(observer.trace(frame, "line", None))
        self.assertEqual(observer.order, [])

    def test_trace_records_original_cold_aliases(self):
        observer = c.Observer(self.pins["fields"])
        observer.attention_code, observer.attention = object(), object()
        q, k, v = (FakeTensor([1, h, 16, 128]) for h in (12, 2, 2))
        frame = types.SimpleNamespace(f_code=observer.attention_code, f_lineno=280,
                                      f_locals={"self": observer.attention, "query_states": q,
                                                "key_states": k, "value_states": v})
        observer.trace(frame, "call", None)
        observer.trace(frame, "line", None)
        self.assertIs(observer.objects["k"], observer.objects["cache_k"])
        self.assertIs(observer.objects["cache_v"], v)
        self.assertEqual(observer.order, ["q", "k", "cache_k", "cache_v"])
        observer.trace(frame, "return", None)
        self.assertIsNone(observer.attention_frame)

    def test_trace_error_is_observational_and_fail_closed_at_validation(self):
        observer = c.Observer(self.pins["fields"])
        observer.attention_code, observer.attention = object(), object()
        frame = types.SimpleNamespace(f_code=observer.attention_code, f_lineno=280,
                                      f_locals={"self": observer.attention})
        observer.trace(frame, "call", None)
        observer.trace(frame, "line", None)
        self.assertTrue(observer.errors)
        self.assertFalse(observer.validate())

    def test_softmax_actual_return_only_and_parent_bound(self):
        observer = c.Observer(self.pins["fields"])
        observer.softmax_code, observer.float32 = object(), object()
        logits = object()
        parent = types.SimpleNamespace(f_lineno=300, f_locals={"attn_weights": logits})
        observer.attention_frame = parent
        frame = types.SimpleNamespace(f_code=observer.softmax_code, f_back=parent,
                                      f_locals={"input": logits, "dim": -1, "dtype": observer.float32})
        observer.trace(frame, "call", None)
        output = FakeTensor([1, 12, 16, 16], dtype="float32")
        observer.trace(frame, "return", output)
        self.assertIs(observer.objects["softmax_fp32"], output)
        self.assertEqual(observer.softmax_calls, 1)
        self.assertEqual(observer.errors, [])

    def test_unrelated_softmax_ignored(self):
        observer = c.Observer(self.pins["fields"])
        observer.softmax_code = object()
        observer.attention_frame = object()
        frame = types.SimpleNamespace(f_code=observer.softmax_code, f_back=object())
        self.assertIsNone(observer.trace(frame, "call", None))
        self.assertEqual(observer.softmax_calls, 0)

    def test_complete_observation_validation_is_not_numeric_pass(self):
        observer = c.Observer(self.pins["fields"])
        for name in c.FIELD_ORDER:
            field = self.pins["fields"][name]
            value = observer.objects["k"] if name == "cache_k" else FakeTensor(field["shape"], field["dtype"])
            observer.record(name, value)
        observer.attention_calls = observer.softmax_calls = 1
        observer.line_visits = {line: 1 for line in c.LINE_FIELDS}
        self.assertTrue(observer.validate())
        observer.metadata["qr"]["native_dtype"] = "float32"
        self.assertFalse(observer.validate())

    def test_code_digest_binds_locations_constants_and_full_code(self):
        left = compile("def f(x):\n    return x + 1\n", "/fixed/source.py", "exec")
        same = compile("def f(x):\n    return x + 1\n", "/fixed/source.py", "exec")
        changed = compile("def f(x):\n    return x + 2\n", "/fixed/source.py", "exec")
        relocated = compile("def f(x):\n    return x + 1\n", "/else/source.py", "exec")
        self.assertEqual(c.code_sha256(left), c.code_sha256(same))
        self.assertNotEqual(c.code_sha256(left), c.code_sha256(changed))
        self.assertNotEqual(c.code_sha256(left), c.code_sha256(relocated))

    def test_fixed_source_line_boundaries_compile_without_import(self):
        source = Path(os.environ.get("QWEN2_OFFICIAL_MODEL_SOURCE", str(HERE.parents[1] / "config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py")))
        raw = source.read_bytes()
        self.assertEqual(c.sha256(raw), self.pins["official_files"][c.MODEL_REL])
        compiled = compile(raw, str(source), "exec", dont_inherit=True, optimize=sys.flags.optimize)
        forward = c.child_code(c.child_code(compiled, "Qwen2Attention"), "forward")
        actual_lines = {line for start, end, line in forward.co_lines()}
        self.assertTrue(set(c.LINE_FIELDS).issubset(actual_lines))
        lines = raw.decode().splitlines()
        self.assertIn("key_states = repeat_kv", lines[279])
        self.assertIn("softmax(attn_weights", lines[299])
        for name in c.CLASSES:
            c.child_code(compiled, name)

    def test_raw_hashes_verify_shape_bytes_and_payload_not_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entries = []
            for i in range(13):
                payload = bytes((i, 0))
                name = "raw" + str(i)
                (root / (name + ".bin")).write_bytes(payload)
                entries.append({"local_name": name, "dtype": "BF16", "shape": [1],
                                "bytes": 2, "sha256": c.sha256(payload)})
            verified = c.verify_raw13(root, {"raw13": entries})
            self.assertEqual(len(verified), 13)
            (root / "raw3.bin").write_bytes(b"\xff\0")
            with self.assertRaisesRegex(ValueError, "payload hash mismatch"):
                c.verify_raw13(root, {"raw13": entries})

    def test_chunked_actual_parameter_hash_uses_all_bytes(self):
        raw = bytes(range(256)) * 1024
        self.assertEqual(c.tensor_native_sha256(types.SimpleNamespace(uint8=object()),
                                              FakeTensor([len(raw)], payload=raw)), c.sha256(raw))

    def test_export_is_native_and_exact_widening_not_provider(self):
        observer = c.Observer({"x": {"shape": [2], "dtype": "bfloat16"}})
        observer.record("x", FakeTensor([2], payload=b"\x80\x3f\x00\x80"))
        with tempfile.TemporaryDirectory() as temp:
            exports = c.export_snapshots(types.SimpleNamespace(uint8=object()), observer,
                                         Path(temp), {"fields": {"x": {"export_f32_bytes": 8}}})
            self.assertEqual(exports["x"]["native_sha256"], c.sha256(b"\x80\x3f\x00\x80"))
            self.assertEqual((Path(temp) / "x.f32.bin").read_bytes(), b"\0\0\x80\x3f\0\0\0\x80")
            self.assertEqual(observer.errors, [])

    def test_no_numerical_import_at_top_level_or_dynamic_download_route(self):
        tree = ast.parse((HERE / "capture.py").read_text())
        for node in tree.body:
            if isinstance(node, ast.Import):
                self.assertTrue(all(x.name.split(".")[0] not in {"torch", "numpy", "transformers"}
                                    for x in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn(node.module.split(".")[0], {"torch", "numpy", "transformers"})
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse(names & {"from_pretrained", "hf_hub_download", "snapshot_download"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
