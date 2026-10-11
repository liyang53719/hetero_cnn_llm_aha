"""Offline tests for exact Qwen2 selection, bounded reads, and safe resumption."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import qwen2_layer0_payload as payload
from heteronpu.model_geometry import ModelContractError
from heteronpu.weight_header_contract import sha256


def test_pinned_layer_and_selected_embedding_inventory():
    shard, specs = payload.selection(ROOT)
    pins = payload.payload_pin(ROOT, specs, shard)
    assert len(specs) == len(pins) == 13
    assert sum(s["bytes"] for s in specs) == 94382080
    assert sum(s["bytes"] for s in specs[1:]) == 93595648
    assert specs[1]["start"] == 466785928
    assert specs[-1]["end"] + 1 == 560381576
    embedding = specs[0]
    assert embedding["start"] == 38536
    assert embedding["shape"] == [256, 1536]
    assert embedding["source_shape"] == [151936, 1536]
    assert embedding["source_rows"] == [0, 256]
    assert embedding["source_data_offsets"] == [0, 466747392]
    assert all(s["dtype"] == "BF16" for s in specs)
    assert shard["file_bytes"] == 3087467144
    assert sum(len(p["segments"]) for p in pins.values()) == 22


def test_large_ffn_segments_exactly_cover_source_without_overlap():
    _, specs = payload.selection(ROOT)
    for spec in specs:
        spans = list(payload.ranges(spec))
        assert spans[0][0] == spec["start"] and spans[-1][1] == spec["end"]
        assert sum(end - start + 1 for start, end in spans) == spec["bytes"]
        assert all(0 < end - start + 1 <= 8 * 1024 * 1024 for start, end in spans)
        assert all(left[1] + 1 == right[0] for left, right in zip(spans, spans[1:]))
        if spec["local_name"].startswith("mlp."):
            assert [end - start + 1 for start, end in spans] == [8388608] * 3 + [2359296]


class Response:
    def __init__(self, start=10, end=13, body=b"1234", *, status=206, headers=None):
        self.status = status
        self.headers = {"Content-Range": f"bytes {start}-{end}/20", "Content-Length": str(end - start + 1)} if headers is None else headers
        self.body = body
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        self.read_limits.append(limit)
        return self.body


def _opener(calls):
    def open_range(request, timeout):
        request_range = request.get_header("Range")
        calls.append(request_range)
        assert request.get_header("Accept-encoding") == "identity"
        if request_range == "bytes=10-13":
            return Response()
        assert request_range == "bytes=14-17"
        return Response(14, 17, b"5678")
    return open_range


@pytest.fixture
def tiny(monkeypatch, tmp_path):
    spec = {"name": payload.PREFIX + "x", "local_name": "x", "dtype": "BF16", "shape": [1, 4],
            "source_shape": [1, 4], "source_data_offsets": [2, 10], "start": 10, "end": 17, "bytes": 8}
    shard = {"url": "https://example.com/pinned", "file_bytes": 20,
             "header": {"sha256": "0" * 64}, "advertised_lfs_sha256_unverified": "1" * 64}
    pin = {**spec, "sha256": sha256(b"12345678"), "segments": [
        {"start": 10, "end": 13, "bytes": 4, "sha256": sha256(b"1234")},
        {"start": 14, "end": 17, "bytes": 4, "sha256": sha256(b"5678")}]}
    monkeypatch.setattr(payload, "selection", lambda root: (shard, [spec]))
    monkeypatch.setattr(payload, "payload_pin", lambda root, specs, shard=None: {"x": pin})
    monkeypatch.setattr(payload, "TOTAL_BYTES", 8)
    return tmp_path / "payload"


def test_acquire_reload_and_complete_resume_without_network(tiny, tmp_path):
    calls = []
    manifest = payload.collect(tmp_path, tiny, opener=_opener(calls))
    loaded, values = payload.load_payload(tmp_path, tiny)
    assert manifest == loaded and values == {"x": b"12345678"}
    assert calls == ["bytes=10-13", "bytes=14-17"]
    assert manifest["official_forward_executed"] is False
    assert manifest["full_checkpoint_sha256_verified"] is False
    assert manifest["rtl_executed"] is False
    assert payload.collect(tmp_path, tiny, opener=lambda *a, **k: pytest.fail("opened network")) == manifest


def test_interrupted_acquisition_resumes_only_hash_validated_complete_segment(tiny, tmp_path):
    def interrupted(request, timeout):
        if request.get_header("Range") == "bytes=10-13":
            return Response()
        raise OSError("simulated transport interruption")
    with pytest.raises(OSError, match="transport interruption"):
        payload.collect(tmp_path, tiny, opener=interrupted)
    assert not (tiny / "manifest.json").exists()
    assert (tiny / "segments/x.000.bin").read_bytes() == b"1234"
    calls = []
    payload.collect(tmp_path, tiny, opener=_opener(calls))
    assert calls == ["bytes=14-17"]
    assert payload.load_payload(tmp_path, tiny)[1] == {"x": b"12345678"}


@pytest.mark.parametrize("damage", ["bytes", "receipt", "orphan", "temporary", "unknown", "symlink"])
def test_corrupt_resume_cache_rejected_before_network(tiny, tmp_path, damage):
    payload.collect(tmp_path, tiny, opener=_opener([]))
    (tiny / "manifest.json").unlink()
    first = tiny / "segments/x.000.bin"
    if damage == "bytes":
        first.write_bytes(b"evil")
    elif damage == "receipt":
        receipt = tiny / "segments/x.000.json"
        value = json.loads(receipt.read_text())
        value["content_range"] = "bytes 11-14/20"
        receipt.write_text(json.dumps(value))
    elif damage == "orphan":
        (tiny / "segments/x.000.json").unlink()
    elif damage == "temporary":
        (tiny / "segments/x.001.bin.tmp").write_bytes(b"partial")
    elif damage == "unknown":
        (tiny / "unrelated.bin").write_bytes(b"other")
    else:
        first.unlink()
        first.symlink_to(tmp_path / "outside.bin")
    with pytest.raises(ModelContractError):
        payload.collect(tmp_path, tiny, opener=lambda *a, **k: pytest.fail("opened network"))
    assert not (tiny / "manifest.json").exists()


def test_corrupt_later_cached_segment_rejected_before_fetching_missing_earlier_one(tiny, tmp_path):
    payload.collect(tmp_path, tiny, opener=_opener([]))
    (tiny / "manifest.json").unlink()
    (tiny / "segments/x.000.bin").unlink()
    (tiny / "segments/x.000.json").unlink()
    (tiny / "segments/x.001.bin").write_bytes(b"evil")
    with pytest.raises(ModelContractError, match="bytes/hash"):
        payload.collect(tmp_path, tiny, opener=lambda *a, **k: pytest.fail("opened network"))


def test_received_wrong_bytes_leave_no_complete_segment_or_manifest(tiny, tmp_path):
    with pytest.raises(ModelContractError, match="receipt drift"):
        payload.collect(tmp_path, tiny, opener=lambda *a, **k: Response(body=b"evil"))
    assert not (tiny / "manifest.json").exists()
    assert not list((tiny / "segments").iterdir())


@pytest.mark.parametrize("mutate", [
    lambda m: m.update(revision="a" * 40),
    lambda m: m.update(layer_id=False),
    lambda m: m.update(payload_bytes=True),
    lambda m: m.update(header_sha256="a" * 64),
    lambda m: m.update(official_forward_executed=True),
    lambda m: m.update(full_checkpoint_sha256_verified=True),
    lambda m: m.update(rtl_executed=True),
    lambda m: m["tensors"][0].update(shape=[True, 4]),
    lambda m: m["tensors"][0].update(source_data_offsets=[3, 11]),
    lambda m: m["tensors"][0].update(source_shape=[4, 1]),
    lambda m: m["tensors"][0].update(start=11),
    lambda m: m["tensors"][0].update(file="../x.bin"),
    lambda m: m["tensors"][0]["http_ranges"][0].update(status=200),
    lambda m: m["tensors"][0]["http_ranges"][0].update(requested_url="https://attacker.example"),
    lambda m: m["tensors"][0]["http_ranges"].reverse(),
    lambda m: m["tensors"][0]["http_ranges"].pop(),
    lambda m: m["tensors"].append(deepcopy(m["tensors"][0])),
])
def test_manifest_drift_is_rejected(tiny, tmp_path, mutate):
    manifest = payload.collect(tmp_path, tiny, opener=_opener([]))
    mutate(manifest)
    (tiny / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelContractError):
        payload.load_payload(tmp_path, tiny)


def test_rehashed_tensor_and_receipts_cannot_override_independent_pin(tiny, tmp_path):
    manifest = payload.collect(tmp_path, tiny, opener=_opener([]))
    (tiny / "x.bin").write_bytes(b"evil5678")
    manifest["tensors"][0]["sha256"] = sha256(b"evil5678")
    manifest["tensors"][0]["http_ranges"][0]["sha256"] = sha256(b"evil")
    (tiny / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelContractError, match="digest drift"):
        payload.load_payload(tmp_path, tiny)


def test_pin_file_tampering_is_rejected(tmp_path):
    pin_path = tmp_path / payload.PIN_PATH
    pin_path.parent.mkdir(parents=True)
    pin_path.write_text("{}")
    with pytest.raises(ModelContractError, match="digest pin drift"):
        payload.payload_pin(tmp_path, [])


@pytest.mark.parametrize("status,headers", [
    (200, {"Content-Length": "3087467144"}),
    (206, {"Content-Range": "bytes 0-3/20", "Content-Length": "4"}),
    (206, {"Content-Range": "bytes 10-13/21", "Content-Length": "4"}),
    (206, {"Content-Range": "bytes 10-13/20", "Content-Length": "5"}),
    (206, {"Content-Range": "bytes 10-13/20", "Content-Length": "4", "Content-Encoding": "gzip"}),
])
def test_unbounded_or_wrong_http_response_is_refused_before_body_read(status, headers):
    response = Response(status=status, headers=headers)
    with pytest.raises(ModelContractError):
        payload.fetch_range("https://example.com", 10, 13, 20, opener=lambda *a, **k: response)
    assert response.read_limits == []


@pytest.mark.parametrize("body", [b"", b"123", b"12345"])
def test_short_or_oversized_range_body_is_rejected(body):
    response = Response(body=body)
    with pytest.raises(ModelContractError, match="body length"):
        payload.fetch_range("https://example.com", 10, 13, 20, opener=lambda *a, **k: response)
    assert response.read_limits == [5]


@pytest.mark.parametrize("start,end,total", [(-1, 4, 20), (3, 2, 20), (1, 20, 20),
    (0, payload.MAX_RANGE_BYTES, payload.MAX_RANGE_BYTES + 1), (True, 3, 10), (0, 3.0, 10)])
def test_invalid_or_oversized_request_never_opens_network(start, end, total):
    with pytest.raises(ModelContractError):
        payload.fetch_range("https://example.com", start, end, total,
                            opener=lambda *a, **k: pytest.fail("opened network"))
