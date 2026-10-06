"""Offline acquisition, provenance, and mathematical smoke-contract tests."""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from heteronpu import pinned_block_payload as payload
from heteronpu.model_geometry import ModelContractError
from heteronpu.qwen35_numpy_reference import compare, decode_bf16, forward, synthetic_input
from heteronpu.weight_header_contract import sha256

ROOT = Path(__file__).resolve().parents[1]


def test_real_bounded_payload_inventory_and_independent_digest_pin():
    shard, specs = payload.selection(ROOT)
    pins = payload.payload_pin(ROOT, specs)
    assert len(specs) == len(pins) == 11
    assert sum(s["bytes"] for s in specs) == 36705280
    assert specs[0]["start"] == 1215886312
    assert specs[-1]["end"] == 1252591591
    assert max(s["bytes"] for s in specs) == payload.MAX_RANGE_BYTES
    assert shard["file_bytes"] == 1746942600
    assert all(len(h) == 64 for h in pins.values())


class Response:
    def __init__(self, status=206, headers=None, body=b"1234"):
        self.status = status
        self.headers = {"Content-Range": "bytes 10-13/20", "Content-Length": "4"} if headers is None else headers
        self.body = body
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        self.read_limits.append(limit)
        return self.body


def test_range_reads_exact_bound_and_records_local_digest():
    response = Response()
    requests = []
    def opener(request, timeout):
        requests.append((request, timeout))
        return response
    raw, receipt = payload.fetch_range("https://example.com/pinned", 10, 13, 20, opener=opener)
    assert raw == b"1234" and response.read_limits == [5]
    assert requests[0][0].get_header("Range") == "bytes=10-13"
    assert requests[0][0].get_header("Accept-encoding") == "identity"
    assert receipt["sha256"] == sha256(raw)


@pytest.mark.parametrize("start,end,total", [(-1, 4, 20), (3, 2, 20), (1, 20, 20),
    (0, payload.MAX_RANGE_BYTES, payload.MAX_RANGE_BYTES + 1), (True, 3, 10), (0, 3.0, 10), (0, 3, False)])
def test_invalid_ranges_do_not_open_network(start, end, total):
    with pytest.raises(ModelContractError):
        payload.fetch_range("https://example.com", start, end, total, opener=lambda *a, **k: pytest.fail("opened network"))


@pytest.mark.parametrize("status,headers", [
    (200, {"Content-Length": "10000000000"}),
    (206, {"Content-Range": "bytes 0-3/20", "Content-Length": "4"}),
    (206, {"Content-Range": "bytes 10-13/21", "Content-Length": "4"}),
    (206, {"Content-Range": "bytes 10-13/20", "Content-Length": "5"}),
    (206, {"Content-Range": "bytes 10-13/20", "Content-Length": "4", "Content-Encoding": "gzip"}),
])
def test_bad_range_headers_rejected_before_read(status, headers):
    r = Response(status, headers)
    with pytest.raises(ModelContractError):
        payload.fetch_range("https://example.com", 10, 13, 20, opener=lambda *a, **k: r)
    assert r.read_limits == []


@pytest.mark.parametrize("body", [b"", b"123", b"12345"])
def test_bad_body_length_is_rejected(body):
    r = Response(body=body)
    with pytest.raises(ModelContractError, match="body length"):
        payload.fetch_range("https://example.com", 10, 13, 20, opener=lambda *a, **k: r)
    assert r.read_limits == [5]


def tiny(monkeypatch, tmp_path):
    spec = {"name": payload.PREFIX + "x", "local_name": "x", "dtype": "BF16", "shape": [2], "start": 10, "end": 13, "bytes": 4}
    shard = {"url": "https://example.com/pinned", "file_bytes": 20, "header": {"sha256": "0" * 64}, "advertised_lfs_sha256_unverified": "1" * 64}
    monkeypatch.setattr(payload, "selection", lambda root: (shard, [spec]))
    monkeypatch.setattr(payload, "payload_pin", lambda root, specs: {"x": sha256(b"1234")})
    monkeypatch.setattr(payload, "TOTAL_BYTES", 4)
    directory = tmp_path / "payload"
    manifest = payload.collect(tmp_path, directory, opener=lambda *a, **k: Response())
    return directory, manifest


def test_acquire_and_load_actual_byte_identity(monkeypatch, tmp_path):
    directory, manifest = tiny(monkeypatch, tmp_path)
    loaded, values = payload.load_payload(tmp_path, directory)
    assert values == {"x": b"1234"} and loaded == manifest
    assert manifest["official_forward_executed"] is False
    assert manifest["full_checkpoint_sha256_verified"] is False


@pytest.mark.parametrize("mutate", [
    lambda m: m.update(revision="a" * 40), lambda m: m.update(layer_id=True),
    lambda m: m.update(header_sha256="a" * 64), lambda m: m.update(payload_bytes=True),
    lambda m: m["tensors"][0].update(shape=[1, 2]), lambda m: m["tensors"][0].update(start=11),
    lambda m: m["tensors"][0].update(file="../x.bin"),
    lambda m: m["tensors"][0]["http"].update(status=200),
    lambda m: m["tensors"][0]["http"].update(requested_url="https://attacker.example"),
    lambda m: m["tensors"].append(deepcopy(m["tensors"][0])),
])
def test_load_rejects_manifest_drift(monkeypatch, tmp_path, mutate):
    directory, manifest = tiny(monkeypatch, tmp_path)
    mutate(manifest)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelContractError):
        payload.load_payload(tmp_path, directory)


def test_rehashed_tampering_still_rejected_by_independent_pin(monkeypatch, tmp_path):
    directory, manifest = tiny(monkeypatch, tmp_path)
    (directory / "x.bin").write_bytes(b"evil")
    manifest["tensors"][0]["sha256"] = sha256(b"evil")
    manifest["tensors"][0]["http"]["sha256"] = sha256(b"evil")
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelContractError, match="observed pin"):
        payload.load_payload(tmp_path, directory)


def test_failed_acquisition_writes_no_pass_and_cannot_reuse_directory(monkeypatch, tmp_path):
    directory, _ = tiny(monkeypatch, tmp_path)
    with pytest.raises(ModelContractError, match="fresh or empty"):
        payload.collect(tmp_path, directory, opener=lambda *a, **k: pytest.fail("opened network"))
    output = tmp_path / "failure"
    with pytest.raises(ModelContractError, match="digest differs"):
        payload.collect(tmp_path, output, opener=lambda *a, **k: Response(body=b"evil"))
    assert not (output / "manifest.json").exists()


def test_pin_file_tampering_is_rejected(tmp_path):
    p = tmp_path / payload.PIN_PATH
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    with pytest.raises(ModelContractError, match="digest pin drift"):
        payload.payload_pin(tmp_path, [])


def test_synthetic_input_and_bf16_decode_are_exact():
    x = synthetic_input()
    assert x.shape == (1, 128, 1024) and x.dtype == np.float32
    assert sha256(x.astype("<f4").tobytes()) == "5ccb230fe634c858cef834753b9d24d939377c06c414b2d8df6437f86ac99e6e"
    assert not np.array_equal(x, synthetic_input(128))
    assert np.array_equal(decode_bf16(bytes.fromhex("803f00c00000"), [3]), [1, -2, 0])


def test_zero_weight_full_shape_oracle_preserves_residual_and_empty_kv():
    _, specs = payload.selection(ROOT)
    # Broadcast views avoid allocating a second giant checkpoint in unit tests.
    weights = {s["local_name"]: np.broadcast_to(np.float64(0), s["shape"]) for s in specs}
    x = synthetic_input()
    y, (k, v) = forward(x, weights)
    assert np.array_equal(y, x) and not k.any() and not v.any()
    assert k.shape == v.shape == (1, 2, 128, 256)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_comparator_rejects_nonfinite(bad):
    with pytest.raises(ValueError, match="nonfinite"):
        compare([bad], [0])


def test_comparator_checks_every_element_and_shape():
    r = compare([0, 1, 2], [0, 1, 3])
    assert r["elements"] == 3 and r["mismatches"] == 1
    with pytest.raises(ValueError, match="shape"):
        compare([1, 2], [[1, 2]])
