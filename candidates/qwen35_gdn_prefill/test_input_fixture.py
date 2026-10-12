"""Offline byte-fixture tests; no model, large synthetic weights or download."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from candidates.qwen35_gdn_prefill import input_fixture as f


class Response:
    status = 206

    def __init__(self, shard, spec, raw):
        self.raw = raw
        self.headers = {"Content-Range": f'bytes {spec["start"]}-{spec["end"]}/{shard["file_bytes"]}',
                        "Content-Length": str(spec["bytes"])}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        if limit != len(self.raw) + 1:
            raise AssertionError("unexpected bounded read")
        return self.raw


class InputFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shard, cls.specs = f.prefix.selection(f.ROOT)
        cls.pins = f.prefix.payload_pin(f.ROOT, cls.specs)
        cls.spec = next(s for s in cls.specs if s["local_name"] == f.NAME)
        # Distinct raw rows make reorder, substitution and partition errors visible.
        cls.raw = b"".join(struct.pack("<H", token) * 1024 for token in range(256))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.embedding = self.base / "embedding"
        self.output = self.base / "inputs"
        self.calls = []
        # Only transport payload hashes are synthetic. Real geometry, revision,
        # header, range and fixed token IDs remain the repository's pinned ones.
        pins = dict(self.pins, **{f.NAME: f.sha256(self.raw)})
        p = patch.object(f.prefix, "payload_pin", return_value=pins)
        p.start()
        self.addCleanup(p.stop)

    def opener(self, request, timeout):
        self.assertEqual(timeout, 90)
        self.assertEqual(request.full_url, self.shard["url"])
        self.assertEqual(request.get_header("Range"), f'bytes={self.spec["start"]}-{self.spec["end"]}')
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.calls.append(request)
        return Response(self.shard, self.spec, self.raw)

    def collect(self):
        return f.collect_embedding(f.ROOT, self.embedding, opener=self.opener)

    def rewrite(self, manifest, directory=None):
        (self.embedding if directory is None else directory).joinpath("manifest.json").write_bytes(f._encoded(manifest))

    def mock_layer0(self):
        """Test the existing guarded loader boundary without 43 MB fake weights."""
        manifest = json.loads((f.ROOT / f.gdn.PIN_PATH).read_text())
        self.layer0 = self.base / "layer0"
        self.layer0.mkdir()
        (self.layer0 / "manifest.json").write_bytes(f._encoded(manifest))
        p = patch.object(f.gdn, "load_payload", return_value=(manifest, {t["local_name"]: b"" for t in manifest["tensors"]}))
        mocked = p.start()
        self.addCleanup(p.stop)
        return manifest, mocked

    def test_real_metadata_selects_only_fixed_embedding(self):
        shard, spec, digest = f.embedding_spec(f.ROOT)
        self.assertEqual(len(self.specs), 29)
        self.assertEqual(spec["shape"], [256, 1024])
        self.assertEqual(spec["bytes"], 524288)
        self.assertEqual(spec["end"] - spec["start"] + 1, 524288)
        self.assertEqual(shard, self.shard)
        self.assertEqual(digest, f.sha256(self.raw))

    def test_one_bounded_request_and_roundtrip(self):
        manifest = self.collect()
        loaded, raw = f.load_embedding(f.ROOT, self.embedding)
        self.assertEqual(manifest, loaded)
        self.assertEqual(raw, self.raw)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(manifest["tensors"]), 1)
        self.assertFalse(manifest["complete_prefix_payload"])
        self.assertFalse(manifest["official_forward_executed"])

    def test_manifest_tampering_and_wrong_domain(self):
        original = self.collect()
        mutations = [
            lambda m: m.update(schema_version=True),
            lambda m: m.update(revision="f" * 40),
            lambda m: m.update(model_id="Qwen/Qwen2-1.5B-Instruct"),
            lambda m: m.update(header_sha256="0" * 64),
            lambda m: m.update(payload_bytes=True),
            lambda m: m.update(complete_prefix_payload=True),
            lambda m: m["tensors"][0].update(shape=[128, 2048]),
            lambda m: m["tensors"][0].update(dtype="F32"),
            lambda m: m["tensors"][0].update(start=self.spec["start"] + 1),
            lambda m: m["tensors"][0].update(file="../escaped.bin"),
            lambda m: m["tensors"][0]["http"].update(status=200),
            lambda m: m["tensors"][0]["http"].update(bytes=True),
            lambda m: m["tensors"][0]["http"].update(requested_url="https://other.example/payload"),
            lambda m: m["tensors"][0]["http"].update(content_range="bytes 0-1/2"),
            lambda m: m["tensors"].append(deepcopy(m["tensors"][0])),
        ]
        for change in mutations:
            with self.subTest(change=change):
                candidate = deepcopy(original)
                change(candidate)
                self.rewrite(candidate)
                with self.assertRaises(ValueError):
                    f.load_embedding(f.ROOT, self.embedding)

    def test_raw_and_rehashed_tampering_cannot_replace_pin(self):
        manifest = self.collect()
        changed = b"\xff" + self.raw[1:]
        (self.embedding / f.FILENAME).write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "bytes/hash"):
            f.load_embedding(f.ROOT, self.embedding)
        manifest["tensors"][0]["sha256"] = f.sha256(changed)
        manifest["tensors"][0]["http"]["sha256"] = f.sha256(changed)
        self.rewrite(manifest)
        with self.assertRaises(ValueError):
            f.load_embedding(f.ROOT, self.embedding)

    def test_symlink_escape_and_extra_file_rejected(self):
        self.collect()
        data = self.embedding / f.FILENAME
        outside = self.base / "outside.bin"
        data.rename(outside)
        data.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "path escape"):
            f.load_embedding(f.ROOT, self.embedding)
        data.unlink()
        data.write_bytes(self.raw)
        (self.embedding / "extra.bin").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "inventory"):
            f.load_embedding(f.ROOT, self.embedding)

    def test_existing_directory_and_dangling_symlink_are_not_fresh(self):
        self.embedding.mkdir()
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.collect()
        self.embedding.rmdir()
        self.embedding.symlink_to(self.base / "absent")
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.collect()
        self.assertEqual(self.calls, [])

    def test_bad_response_or_hash_never_publishes_manifest(self):
        for status in (200, 206):
            with self.subTest(status=status):
                response = Response(self.shard, self.spec, b"\xff" * len(self.raw))
                response.status = status
                with self.assertRaises(ValueError):
                    f.collect_embedding(f.ROOT, self.embedding, opener=lambda *a, **k: response)
                self.assertFalse(self.embedding.exists())

    def test_raw_hidden_exact_order_and_boundary(self):
        ids, files = f.hidden_inputs(f.ROOT, self.raw)
        self.assertEqual(struct.unpack("<256I", files["token_ids.u32le"]), tuple(ids))
        for name, start in (("cold128.hidden.bf16le", 0), ("carried128.hidden.bf16le", 128)):
            hidden = files[name]
            self.assertEqual(len(hidden), 262144)
            for token in (0, 63, 64, 127):
                self.assertEqual(hidden[token * 2048:(token + 1) * 2048], struct.pack("<H", ids[start + token]) * 1024)
        self.assertEqual(len(set(ids)), 256)

    def test_invalid_hidden_input_and_token_domains(self):
        for raw in (self.raw[:-2], bytearray(self.raw)):
            with self.assertRaises(ValueError):
                f.hidden_inputs(f.ROOT, raw)
        valid = f.prefix.token_fixture(f.ROOT)
        for value in (-1, 256, True, 1.0, 92):
            changed = deepcopy(valid)
            changed["token_ids"][0] = value
            with patch.object(f.prefix, "token_fixture", return_value=changed), self.assertRaises(ValueError):
                f.hidden_inputs(f.ROOT, self.raw)

    def test_build_and_load_only_raw_inputs_preserve_parameter_dtypes(self):
        self.collect()
        gm, loader = self.mock_layer0()
        manifest = f.build_fixture(f.ROOT, self.embedding, self.layer0, self.output)
        loader.assert_called_once_with(f.ROOT, self.layer0)
        self.assertEqual(len(manifest["sources"]["layer0_tensors"]), 14)
        self.assertEqual({r["local_name"] for r in manifest["sources"]["layer0_tensors"] if r["dtype"] == "F32"},
                         {"linear_attn.A_log", "linear_attn.norm.weight"})
        self.assertEqual({p.name for p in self.output.iterdir()},
                         {"manifest.json", "cold128.hidden.bf16le", "carried128.hidden.bf16le", "token_ids.u32le"})
        loaded, files = f.load_fixture(f.ROOT, self.output)
        self.assertEqual(loaded, manifest)
        self.assertFalse(manifest["intermediate_tensors_generated"])
        self.assertFalse(manifest["state_generated"])
        with self.assertRaisesRegex(ValueError, "fresh"):
            f.build_fixture(f.ROOT, self.embedding, self.layer0, self.output)
        target = self.output / "carried128.hidden.bf16le"
        target.write_bytes(b"\xff" + files[target.name][1:])
        with self.assertRaisesRegex(ValueError, "bytes drift"):
            f.load_fixture(f.ROOT, self.output)

    def test_invalid_layer0_fails_before_output_publication(self):
        self.collect()
        gm, loader = self.mock_layer0()
        for mutation in (lambda m: m.update(layer_id=3),
                         lambda m: m.update(revision="e" * 40),
                         lambda m: next(r for r in m["tensors"] if r["local_name"] == "linear_attn.A_log").update(dtype="BF16")):
            with self.subTest(mutation=mutation):
                candidate = deepcopy(gm)
                mutation(candidate)
                loader.return_value = (candidate, {r["local_name"]: b"" for r in candidate["tensors"]})
                with self.assertRaises(ValueError):
                    f.build_fixture(f.ROOT, self.embedding, self.layer0, self.output)
                self.assertFalse(self.output.exists())

    def test_fixture_manifest_or_tokens_tampering_rejected(self):
        self.collect()
        self.mock_layer0()
        manifest = f.build_fixture(f.ROOT, self.embedding, self.layer0, self.output)
        changed = deepcopy(manifest)
        changed["cases"][1]["past_tokens"] = 0
        self.rewrite(changed, self.output)
        with self.assertRaisesRegex(ValueError, "manifest drift"):
            f.load_fixture(f.ROOT, self.output)


if __name__ == "__main__":
    unittest.main()
