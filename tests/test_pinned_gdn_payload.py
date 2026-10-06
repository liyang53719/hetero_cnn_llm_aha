"""Offline fail-closed tests for bounded mixed-dtype real GDN payload slices."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from heteronpu import pinned_gdn_payload as payload
from heteronpu.model_geometry import ModelContractError
from heteronpu.weight_header_contract import sha256

ROOT = Path(__file__).resolve().parents[1]


def test_real_mixed_storage_inventory_and_split_bounded_ranges():
    shard, specs = payload.selection(ROOT)
    pins = payload.payload_pin(ROOT, specs)
    assert len(specs) == len(pins) == 14
    assert sum(s["bytes"] for s in specs) == 43111008
    assert {s["local_name"] for s in specs if s["dtype"] == "F32"} == payload.F32_NAMES
    assert next(s for s in specs if s["local_name"] == "linear_attn.dt_bias")["dtype"] == "BF16"
    all_ranges = [r for s in specs for r in payload.ranges(s)]
    assert len(all_ranges) == 15
    assert max(hi-lo+1 for lo,hi in all_ranges) == 8*1024*1024
    assert sum(hi-lo+1 for lo,hi in all_ranges) == 43111008
    assert shard["file_bytes"] == 1746942600
    assert all(len(x) == 64 for x in pins.values())


class Response:
    status = 206
    def __init__(self, start, end, body):
        self.headers = {"Content-Range": f"bytes {start}-{end}/20", "Content-Length": str(end-start+1)}
        self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit):
        assert limit == len(self.body)+1
        return self.body


def tiny(monkeypatch, tmp_path):
    spec = {"name": payload.PREFIX + "x", "local_name": "x", "dtype": "F32", "shape": [2], "start": 10, "end": 17, "bytes": 8}
    shard = {"url": "https://example.com/pinned", "file_bytes": 20, "header": {"sha256": "0"*64}, "advertised_lfs_sha256_unverified": "1"*64}
    monkeypatch.setattr(payload, "selection", lambda root: (shard, [spec]))
    monkeypatch.setattr(payload, "payload_pin", lambda root, specs: {"x": sha256(b"12345678")})
    monkeypatch.setattr(payload, "TOTAL_BYTES", 8)
    monkeypatch.setattr(payload, "MAX_RANGE_BYTES", 4)
    def opener(request, timeout):
        start,end=map(int,request.get_header("Range").removeprefix("bytes=").split("-"))
        return Response(start,end,b"12345678"[start-10:end-9])
    directory=tmp_path/"payload"
    manifest=payload.collect(tmp_path,directory,opener=opener)
    return directory,manifest


def test_split_acquire_and_load_exact_hashes(monkeypatch,tmp_path):
    directory,manifest=tiny(monkeypatch,tmp_path)
    loaded,values=payload.load_payload(tmp_path,directory)
    assert values=={"x":b"12345678"} and loaded==manifest
    assert len(manifest["tensors"][0]["http_ranges"])==2
    assert not manifest["official_forward_executed"] and not manifest["full_checkpoint_sha256_verified"]


@pytest.mark.parametrize("mutate",[
    lambda m:m.update(revision="a"*40), lambda m:m.update(layer_id=False),
    lambda m:m.update(header_sha256="a"*64),lambda m:m.update(payload_bytes=True),
    lambda m:m["tensors"][0].update(dtype="BF16"),lambda m:m["tensors"][0].update(shape=[1,2]),
    lambda m:m["tensors"][0].update(start=11),lambda m:m["tensors"][0].update(file="../x.bin"),
    lambda m:m["tensors"][0]["http_ranges"][0].update(status=200),
    lambda m:m["tensors"][0]["http_ranges"][1].update(requested_url="https://attacker.example"),
    lambda m:m["tensors"][0]["http_ranges"].reverse(),
    lambda m:m["tensors"][0]["http_ranges"].pop(),
    lambda m:m["tensors"][0]["http_ranges"][1].update(sha256="a"*64),
    lambda m:m["tensors"].append(deepcopy(m["tensors"][0])),
])
def test_manifest_drift_is_rejected(monkeypatch,tmp_path,mutate):
    directory,manifest=tiny(monkeypatch,tmp_path)
    mutate(manifest);(directory/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelContractError):payload.load_payload(tmp_path,directory)


def test_rehashed_payload_tampering_still_rejected(monkeypatch,tmp_path):
    directory,manifest=tiny(monkeypatch,tmp_path)
    raw=b"evil1234";(directory/"x.bin").write_bytes(raw)
    manifest["tensors"][0]["sha256"]=sha256(raw)
    for i,h in enumerate(manifest["tensors"][0]["http_ranges"]):h["sha256"]=sha256(raw[i*4:i*4+4])
    (directory/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelContractError,match="observed pin"):payload.load_payload(tmp_path,directory)


def test_payload_pin_tamper_rejected(tmp_path):
    p=tmp_path/payload.PIN_PATH;p.parent.mkdir(parents=True);p.write_text("{}")
    with pytest.raises(ModelContractError,match="digest pin drift"):payload.payload_pin(tmp_path,[])


def test_no_stale_success_reuse(monkeypatch,tmp_path):
    directory,_=tiny(monkeypatch,tmp_path)
    with pytest.raises(ModelContractError,match="fresh or empty"):
        payload.collect(tmp_path,directory,opener=lambda *a,**k:pytest.fail("network opened"))


def test_failed_chunk_digest_never_writes_success(monkeypatch,tmp_path):
    tiny(monkeypatch,tmp_path)
    with pytest.raises(ModelContractError,match="digest differs"):
        payload.collect(tmp_path,tmp_path/"bad",opener=lambda r,**k:Response(*map(int,r.get_header("Range").removeprefix("bytes=").split("-")),b"evil"))
    assert not (tmp_path/"bad/manifest.json").exists()
