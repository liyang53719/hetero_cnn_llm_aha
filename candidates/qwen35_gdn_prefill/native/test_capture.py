"""Small metadata rejection tests: no Torch, weights or official inference."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from . import capture as c


def manifest(m=128):
    tensors = {}
    def tensor(key, shape, dtype, digest="0" * 64):
        tensors[key] = dict(file=key + ".bin", shape=shape, dtype=dtype,
                            bytes=c.math.prod(shape) * c.WIDTHS[dtype], sha256=digest)
        return key
    cases = []
    for i in range(2):
        prefix = str(i)
        final = dict(conv_state=tensor(prefix + "_conv", [1, 6144, 4], "BF16"),
                     recurrent_state=tensor(prefix + "_state", [1, 16, 128, 128], "F32"))
        prior = dict(conv_state=None, recurrent_state=None) if i == 0 else dict(
            conv_state=tensor("prior_conv", [1, 6144, 4], "BF16"),
            recurrent_state=tensor("prior_state", [1, 16, 128, 128], "F32"))
        cases.append(dict(past_tokens=i * m, source_token_slice=[i * 128, i * 128 + m], cache_object_id=123,
            prior_cache=prior, final_cache=final,
            input=tensor(prefix + "_input", [1, m, 1024], "BF16"),
            output=tensor(prefix + "_output", [1, m, 1024], "BF16"),
            chunk_calls=[dict(chunk_size=64, num_chunks=(m + 63) // 64, sequence_length=m,
                pad_size=(64 - m % 64) % 64, official_function_body_observed=True,
                initial_state_is_actual_prior_cache=True, initial_state=prior["recurrent_state"], final_state=final["recurrent_state"])]))
    return dict(schema_version=1, scope=c.SCOPE, query_tokens=m,
        case_identity="cold128_then_carried128" if m == 128 else "cold16_then_carried16_from_second_window",
        hardware_executed=False, owner_executed=False, official_full_model_executed=False, tensors=tensors, cases=cases)


class CaptureContractTests(unittest.TestCase):
    def test_import_and_metadata_validation_do_not_import_torch(self):
        result = subprocess.run([sys.executable, "-B", "-c",
            "from candidates.qwen35_gdn_prefill.native import capture; import sys; assert 'torch' not in sys.modules"],
            cwd=c.ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_m16_and_m128_are_separate_valid_identities(self):
        for m in (16, 128):
            with self.subTest(m=m):
                self.assertIs(c.validate_manifest(value := manifest(m)), value)
        value = manifest(16)
        value["case_identity"] = "cold128_then_carried128"
        with self.assertRaisesRegex(ValueError, "case identity"):
            c.validate_manifest(value)
        value = manifest(16)
        value["cases"][1]["past_tokens"] = 128
        with self.assertRaisesRegex(ValueError, "past token"):
            c.validate_manifest(value)

    def test_shape_dtype_and_integer_ambiguity_rejected(self):
        good = dict(file="x.bin", shape=[1, 2], dtype="BF16", bytes=4, sha256="0" * 64)
        for field, replacement in (("shape", [True, 2]), ("shape", [1, 0]), ("shape", [1, -2]),
                                   ("shape", [1.0, 2]), ("shape", "1,2"), ("dtype", "float32"),
                                   ("dtype", "FP16"), ("bytes", True), ("bytes", 8)):
            with self.subTest(field=field, replacement=replacement):
                with self.assertRaises(ValueError):
                    c.validate_tensor_record(dict(good, **{field: replacement}))

    def test_raw_file_hash_size_path_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            raw = b"\x80\x3f\x00\x40"
            record = dict(file="x.bin", shape=[2], dtype="BF16", bytes=4, sha256=c.sha(raw))
            (directory / "x.bin").write_bytes(raw)
            c.validate_tensor_record(record, directory)
            (directory / "x.bin").write_bytes(raw[::-1])
            with self.assertRaisesRegex(ValueError, "bytes/hash"):
                c.validate_tensor_record(record, directory)
            (directory / "link.bin").symlink_to(directory / "x.bin")
            with self.assertRaisesRegex(ValueError, "path escape"):
                c.validate_tensor_record(dict(record, file="link.bin"), directory)
            for filename in ("../x.bin", "..", ".", "", "/tmp/x.bin"):
                with self.subTest(filename=filename), self.assertRaises(ValueError):
                    c.validate_tensor_record(dict(record, file=filename))

    def test_manifest_rejects_fake_cache_or_chunk_observation(self):
        changes = (
            lambda v: v.update(schema_version=True),
            lambda v: v.update(query_tokens=True),
            lambda v: v.update(hardware_executed=True),
            lambda v: v["cases"][1].update(cache_object_id=456),
            lambda v: v["cases"][0]["prior_cache"].update(recurrent_state="0_state"),
            lambda v: v["tensors"]["prior_state"].update(sha256="1" * 64),
            lambda v: v["tensors"]["0_state"].update(dtype="BF16", bytes=524288),
            lambda v: v["cases"][1]["chunk_calls"][0].update(chunk_size=128, num_chunks=1),
            lambda v: v["cases"][1]["chunk_calls"][0].update(num_chunks=1),
            lambda v: v["cases"][1]["chunk_calls"][0].update(official_function_body_observed=False),
            lambda v: v["cases"][1]["chunk_calls"][0].update(initial_state_is_actual_prior_cache=False),
            lambda v: v["cases"][1]["chunk_calls"][0].update(initial_state=None),
            lambda v: v["cases"][1]["chunk_calls"].append(deepcopy(v["cases"][1]["chunk_calls"][0])),
            lambda v: v["tensors"]["0_output"].update(file=v["tensors"]["0_input"]["file"]),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                value = manifest()
                change(value)
                with self.assertRaises(ValueError):
                    c.validate_manifest(value)


if __name__ == "__main__":
    unittest.main()
