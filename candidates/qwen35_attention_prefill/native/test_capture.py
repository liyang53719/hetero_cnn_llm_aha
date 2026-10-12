"""Bounded metadata/mocked artifact tests. No Torch import or model arithmetic."""
from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from . import capture as c


def manifest(m=128):
    tensors = {}
    def tensor(key, shape, dtype, digest="0" * 64):
        tensors[key] = dict(file=key + ".bin", shape=shape, dtype=dtype,
                            bytes=c.math.prod(shape) * c.WIDTHS[dtype], sha256=digest)
        return key
    cases = []
    for i in range(2):
        label = str(i)
        layers = [dict(layer=j, input=tensor(label + f"_in{j}", [1, m, 1024], "BF16"),
                       output=tensor(label + f"_out{j}", [1, m, 1024], "BF16")) for j in range(4)]
        prior, final = {}, {}
        for j in range(4):
            specs = (("conv_state", [1, 6144, 4], "BF16"), ("recurrent_state", [1, 16, 128, 128], "F32")) if j < 3 else (
                ("key", [1, 2, (i + 1) * m, 256], "BF16"), ("value", [1, 2, (i + 1) * m, 256], "BF16"))
            final[str(j)] = {name: tensor(label + f"_cache{j}_" + name, shape, dtype) for name, shape, dtype in specs}
            prior[str(j)] = {name: None if not i else cases[0]["final_cache"][str(j)][name] for name, _, _ in specs}
        cases.append(dict(past_tokens=i * m, final_tokens=(i + 1) * m, source_token_slice=[i * 128, i * 128 + m],
            position_span=[i * 128, i * 128 + m], cache_object_id=123, prior_cache=prior, final_cache=final,
            retained_kv_prefix={name: prior["3"][name] for name in ("key", "value")}, layers=layers,
            token_ids=tensor(label + "_tokens", [1, m], "I64"), position_ids=tensor(label + "_positions", [1, m], "I64"),
            rope_position_ids=tensor(label + "_rope_positions", [3, 1, m], "I64"),
            attention_mask=tensor(label + "_mask", [1, 1, m, (i + 1) * m], "BF16"),
            rope_cos=tensor(label + "_cos", [1, m, 64], "BF16"), rope_sin=tensor(label + "_sin", [1, m, 64], "BF16"),
            embedding=tensor(label + "_embedding", [1, m, 1024], "BF16"), input=layers[3]["input"], output=layers[3]["output"],
            mask_uses_actual_cache_length=True, packed_q_gate_split_verified=True,
            official_function_counts=dict(rope=1, eager=1, attention=1, chunk=3, norm=4, norm_core=4), dispatch_events=[dict(op="metadata_fixture_only")]))
    return dict(schema_version=1, scope=c.SCOPE, status="CAPTURED_OFFICIAL_SOFTWARE_REFERENCE_ONLY",
        model_id=c.MODEL_ID, revision=c.REVISION, framework_revision=c.FRAMEWORK_REVISION, query_tokens=m,
        case_identity="cold128_then_carried128" if m == 128 else "cold16_then_carried16_from_second_window",
        hardware_executed=False, owner_executed=False, official_full_model_executed=False,
        numerical_comparison_performed=False, numerical_acceptance_gate_added=False, previous_fp32_gate_replaced=False,
        official_TextModel_prefix_executed=True, contract_sha256=c.CONTRACT_SHA256,
        official_source_sha256=deepcopy(c.OFFICIAL_SOURCES), tensors=tensors, cases=cases)


class CaptureContractTests(unittest.TestCase):
    def test_import_and_help_do_not_import_model_libraries(self):
        code = "from candidates.qwen35_attention_prefill.native import capture; import sys; assert not {'torch', 'numpy', 'transformers'} & set(sys.modules)"
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=c.ROOT, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, "-B", str(Path(c.__file__)), "--help"], capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--payload-extra", result.stdout)

    def test_distinct_m16_m128_fixture_and_cache_semantics(self):
        for m in (16, 128):
            self.assertIs(c.validate_manifest(value := manifest(m)), value)
        value = manifest(16)
        value["cases"][1]["past_tokens"] = 128
        with self.assertRaisesRegex(ValueError, "actual cache length"):
            c.validate_manifest(value)
        value = manifest(16)
        value["cases"][1]["position_span"] = [16, 32]
        with self.assertRaisesRegex(ValueError, "position span"):
            c.validate_manifest(value)

    def test_reject_scope_checkpoint_source_and_contract_overclaims(self):
        mutations = (
            lambda v: v.update(schema_version=True), lambda v: v.update(query_tokens=True),
            lambda v: v.update(status="PASS"), lambda v: v.update(revision="another-checkpoint"),
            lambda v: v.update(contract_sha256="1" * 64),
            lambda v: v["official_source_sha256"].update(masking="1" * 64),
            *(lambda v, key=key: v.update({key: True}) for key in ("hardware_executed", "owner_executed",
                "official_full_model_executed", "numerical_comparison_performed", "numerical_acceptance_gate_added", "previous_fp32_gate_replaced")),
        )
        for change in mutations:
            with self.subTest(change=change):
                value = manifest()
                change(value)
                with self.assertRaises(ValueError):
                    c.validate_manifest(value)

    def test_reject_discontinuous_or_invented_prefix_and_cache(self):
        mutations = (
            lambda v: v["cases"][0]["prior_cache"]["3"].update(key="0_cache3_key"),
            lambda v: v["cases"][1].update(cache_object_id=999),
            lambda v: v["cases"][1].update(final_tokens=128),
            lambda v: v["cases"][1]["retained_kv_prefix"].update(key="1_cache3_key"),
            lambda v: v["tensors"]["0_in3"].update(sha256="1" * 64),
            lambda v: v["cases"][0]["layers"].reverse(),
            lambda v: v["tensors"]["1_cache0_recurrent_state"].update(dtype="BF16", bytes=524288),
            lambda v: v["cases"][1].update(mask_uses_actual_cache_length=False),
            lambda v: v["cases"][1].update(packed_q_gate_split_verified=False),
            lambda v: v["cases"][1]["official_function_counts"].update(chunk=2),
            lambda v: v["cases"][0].update(dispatch_events=[]),
            lambda v: v["cases"][0].update(dispatch_events=[{"result": {"tensor": "missing"}}]),
            lambda v: v["cases"][0]["official_function_counts"].update(norm=3),
            lambda v: v["cases"][0].update(source_token_slice=[1, 129]),
        )
        for index, change in enumerate(mutations):
            with self.subTest(index=index):
                value = manifest()
                change(value)
                with self.assertRaises(ValueError):
                    c.validate_manifest(value)

    def test_reject_shape_dtype_path_and_hash_errors(self):
        good = dict(file="x.bin", shape=[2], dtype="BF16", bytes=4, sha256="0" * 64)
        for field, replacement in (("shape", [True, 2]), ("shape", [0]), ("shape", [2.0]),
                ("shape", "2"), ("dtype", "FP16"), ("dtype", "bfloat16"), ("bytes", True), ("bytes", 8),
                ("file", "../escape"), ("file", "/tmp/x.bin"), ("file", "."), ("sha256", "x" * 64)):
            with self.subTest(field=field, replacement=replacement), self.assertRaises(ValueError):
                c.validate_tensor_record(dict(good, **{field: replacement}))
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            raw = b"\x80\x3f\x00\x40"
            record = dict(good, sha256=c.sha(raw))
            (directory / "x.bin").write_bytes(raw)
            c.validate_tensor_record(record, directory)
            (directory / "x.bin").write_bytes(raw[::-1])
            with self.assertRaisesRegex(ValueError, "bytes/hash"):
                c.validate_tensor_record(record, directory)
            (directory / "link.bin").symlink_to(directory / "x.bin")
            with self.assertRaisesRegex(ValueError, "path escape"):
                c.validate_tensor_record(dict(record, file="link.bin"), directory)

    def test_reject_nonfinite_raw_storage_without_float_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for dtype, fmt, bits in (("BF16", "<H", 0x7F80), ("BF16", "<H", 0x7FC1),
                                     ("F32", "<I", 0xFF800000), ("F32", "<I", 0x7FC00001)):
                raw = struct.pack(fmt, bits)
                record = dict(file="x.bin", shape=[1], dtype=dtype, bytes=len(raw), sha256=c.sha(raw))
                (directory / "x.bin").write_bytes(raw)
                with self.subTest(dtype=dtype, bits=bits), self.assertRaisesRegex(ValueError, "nonfinite"):
                    c.validate_tensor_record(record, directory)
            for dtype, fmt, bits in (("BF16", "<H", 0xFF7F), ("F32", "<I", 0x80000000)):
                raw = struct.pack(fmt, bits)
                record = dict(file="x.bin", shape=[], dtype=dtype, bytes=len(raw), sha256=c.sha(raw))
                (directory / "x.bin").write_bytes(raw)
                c.validate_tensor_record(record, directory)


class TensorJournalTests(unittest.TestCase):
    @staticmethod
    def record(name="first.bin", raw=b"\x80\x3f"):
        return dict(file=name, shape=[len(raw) // 2], dtype="BF16", bytes=len(raw), sha256=c.sha(raw))

    def test_mid_capture_index_failure_preserves_completed_entries_and_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            journal = c.TensorJournal(directory)
            raw = b"\x80\x3f"
            first = self.record()
            journal.persist("cold.actual_input", first, raw)
            runner = c.file_record(c.__file__)
            c.write_durable(directory / "capture_start.json", c.encoded({"runner": runner}))
            c.write_durable(directory / "verified_source_identity.json", c.encoded({"test_source": runner}))
            original_write = c.write_durable
            def interrupted_append(path, data, mode="xb"):
                if Path(path) == journal.path and mode == "ab":
                    original_write(path, data[:13], mode)
                    raise OSError("mock index append interrupted")
                return original_write(path, data, mode)
            try:
                with patch.object(c, "write_durable", side_effect=interrupted_append):
                    journal.persist("cold.actual_next", self.record("second.bin"), raw)
            except OSError as exc:
                failure = c.write_failure_receipt(directory, exc, m=16, start=c.time.monotonic(), runner_at_start=runner)
            else:
                self.fail("mock failure did not occur")
            recovered = c.recover_tensor_journal(directory)
            self.assertEqual(recovered["tensors"], {"cold.actual_input": first})
            self.assertEqual(recovered["ignored_unterminated_tail_bytes"], 13)
            self.assertTrue(recovered["partial_evidence_only"])
            self.assertFalse(recovered["model_resume_supported"])
            self.assertEqual((directory / "second.bin").read_bytes(), raw)
            self.assertEqual(failure["runner_at_start"], runner)
            self.assertIn("mock index append interrupted", failure["traceback"])
            self.assertEqual(failure["exception_type"], "OSError")
            self.assertEqual(set(failure["persisted_evidence"]), {"tensor_index.jsonl", "capture_start.json", "verified_source_identity.json"})
            self.assertFalse(failure["partial_evidence_is_success"])
            self.assertFalse((directory / "manifest.json").exists())

    def test_partial_raw_write_does_not_create_an_index_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            journal = c.TensorJournal(directory)
            journal.persist("completed", self.record(), b"\x80\x3f")
            original_write = c.write_durable
            def interrupted_raw(path, data, mode="xb"):
                if Path(path).name == "second.bin":
                    original_write(path, data[:1], mode)
                    raise OSError("mock raw write interrupted")
                return original_write(path, data, mode)
            with patch.object(c, "write_durable", side_effect=interrupted_raw), self.assertRaisesRegex(OSError, "raw write"):
                journal.persist("incomplete", self.record("second.bin"), b"\x80\x3f")
            recovered = c.recover_tensor_journal(directory)
            self.assertEqual(set(recovered["tensors"]), {"completed"})
            self.assertEqual(recovered["ignored_unterminated_tail_bytes"], 0)
            self.assertEqual((directory / "second.bin").read_bytes(), b"\x80")

    def test_same_key_conflict_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            journal = c.TensorJournal(directory)
            journal.persist("observed", self.record(), b"\x80\x3f")
            before = journal.path.read_bytes()
            with self.assertRaisesRegex(ValueError, "journal key"):
                journal.persist("observed", self.record("second.bin", b"\x00\x40"), b"\x00\x40")
            self.assertEqual(journal.path.read_bytes(), before)
            self.assertFalse((directory / "second.bin").exists())
            # Completed duplicate lines are corruption, including identical ones.
            c.write_durable(journal.path, before, "ab")
            with self.assertRaisesRegex(ValueError, "journal key"):
                c.recover_tensor_journal(directory)

    def test_only_unterminated_final_line_can_be_ignored(self):
        for suffix, ignored in ((b'{"key":', True), (b'{"valid_json_but_uncommitted":true}', True),
                                (b'{"key":\n', False), (b'not-json\n', False)):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                journal = c.TensorJournal(directory)
                journal.persist("complete", self.record(), b"\x80\x3f")
                before = journal.path.read_bytes()
                c.write_durable(journal.path, suffix, "ab")
                if ignored:
                    recovered = c.recover_tensor_journal(directory)
                    self.assertEqual(recovered["completed_records"], 1)
                    self.assertEqual(recovered["ignored_unterminated_tail_bytes"], len(suffix))
                else:
                    with self.assertRaisesRegex(ValueError, "completed tensor journal line"):
                        c.recover_tensor_journal(directory)
                self.assertEqual(journal.path.read_bytes(), before + suffix)

    def test_recovery_rejects_changed_raw_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            journal = c.TensorJournal(directory)
            journal.persist("complete", self.record(), b"\x80\x3f")
            (directory / "first.bin").write_bytes(b"\x00\x40")
            with self.assertRaisesRegex(ValueError, "bytes/hash"):
                c.recover_tensor_journal(directory)


if __name__ == "__main__":
    unittest.main()
