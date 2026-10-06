"""Offline fail-closed coverage of real prefix embedding and layers1/2 slices."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from heteronpu import pinned_prefix_payload as payload
from heteronpu.model_geometry import ModelContractError
from heteronpu.weight_header_contract import sha256

ROOT = Path(__file__).resolve().parents[1]


def test_bounded_real_prefix_inventory_and_explicit_token_fixture():
    shard, specs = payload.selection(ROOT)
    pins = payload.payload_pin(ROOT, specs)
    assert len(specs) == len(pins) == 29
    assert sum(s["bytes"] for s in specs) == 86746304
    embedding = specs[0]
    assert embedding["name"] == "model.language_model.embed_tokens.weight"
    assert embedding["source_shape"] == [248320, 1024]
    assert embedding["source_rows"] == [0, 256]
    assert embedding["source_data_offsets"] == [10368, 508569728]
    assert embedding["shape"] == [256, 1024] and embedding["dtype"] == "BF16"
    assert (embedding["start"], embedding["end"], embedding["bytes"]) == (70216, 594503, 524288)
    assert len([s for s in specs if s["dtype"] == "F32"]) == 4
    chunks = [r for s in specs for r in payload.ranges(s)]
    assert len(chunks) == 31 and max(b-a+1 for a,b in chunks) == 8388608
    assert sum(b-a+1 for a,b in chunks) == payload.TOTAL_BYTES
    assert shard["file_bytes"] == 1746942600
    fixture = payload.token_fixture(ROOT)
    assert sorted(fixture["token_ids"]) == list(range(256))
    assert fixture["token_ids"][:3] == [19, 92, 165]
    assert fixture["tokenizer_used"] is False


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
    spec = {"name": "model.language_model.layers.1.x", "local_name": "layers.1.x", "dtype": "F32", "shape": [2], "start": 10, "end": 17, "bytes": 8}
    shard = {"url": "https://example.com/pinned", "file_bytes": 20, "header": {"sha256": "0"*64}, "advertised_lfs_sha256_unverified": "1"*64}
    monkeypatch.setattr(payload, "selection", lambda root: (shard, [spec]))
    monkeypatch.setattr(payload, "payload_pin", lambda root, specs: {"layers.1.x": sha256(b"12345678")})
    monkeypatch.setattr(payload, "TOTAL_BYTES", 8)
    monkeypatch.setattr(payload, "ranges", lambda spec: [(10,13),(14,17)])
    def opener(request, timeout):
        start,end=map(int,request.get_header("Range").removeprefix("bytes=").split("-"))
        return Response(start,end,b"12345678"[start-10:end-9])
    directory=tmp_path/"payload"
    manifest=payload.collect(tmp_path,directory,opener=opener)
    return directory,manifest


def test_split_download_reload_exact_bytes(monkeypatch,tmp_path):
    directory,manifest=tiny(monkeypatch,tmp_path)
    loaded,values=payload.load_payload(tmp_path,directory)
    assert values=={"layers.1.x":b"12345678"} and loaded==manifest
    assert len(manifest["tensors"][0]["http_ranges"])==2
    assert not manifest["official_forward_executed"] and not manifest["full_checkpoint_sha256_verified"]


@pytest.mark.parametrize("mutate",[
    lambda m:m.update(revision="a"*40),lambda m:m.update(header_sha256="a"*64),lambda m:m.update(payload_bytes=True),
    lambda m:m["tensors"][0].update(dtype="BF16"),lambda m:m["tensors"][0].update(shape=[1,2]),
    lambda m:m["tensors"][0].update(start=11),lambda m:m["tensors"][0].update(file="../x.bin"),
    lambda m:m["tensors"][0].update(local_name="layers.2.x"),lambda m:m["tensors"][0].update(name="model.language_model.layers.2.x"),
    lambda m:m["tensors"][0]["http_ranges"][0].update(status=200),
    lambda m:m["tensors"][0]["http_ranges"][1].update(requested_url="https://attacker.example"),
    lambda m:m["tensors"][0]["http_ranges"].reverse(),lambda m:m["tensors"][0]["http_ranges"].pop(),
    lambda m:m["tensors"][0]["http_ranges"][1].update(sha256="a"*64),
    lambda m:m["tensors"].append(deepcopy(m["tensors"][0])),
])
def test_manifest_drift_rejected(monkeypatch,tmp_path,mutate):
    directory,manifest=tiny(monkeypatch,tmp_path)
    mutate(manifest);(directory/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelContractError):payload.load_payload(tmp_path,directory)


def test_rehashed_payload_still_rejected(monkeypatch,tmp_path):
    directory,manifest=tiny(monkeypatch,tmp_path)
    raw=b"evil1234";(directory/"layers.1.x.bin").write_bytes(raw)
    manifest["tensors"][0]["sha256"]=sha256(raw)
    for i,h in enumerate(manifest["tensors"][0]["http_ranges"]):h["sha256"]=sha256(raw[i*4:i*4+4])
    (directory/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ModelContractError,match="observed pin"):payload.load_payload(tmp_path,directory)


@pytest.mark.parametrize("path,loader,match",[(payload.PIN_PATH,lambda p:payload.payload_pin(p,[]),"payload digest pin"),
                                             (payload.FIXTURE_PATH,payload.token_fixture,"token fixture")])
def test_immutable_pin_files_reject_tamper(tmp_path,path,loader,match):
    p=tmp_path/path;p.parent.mkdir(parents=True);p.write_text("{}")
    with pytest.raises(ModelContractError,match=match):loader(tmp_path)


def test_no_stale_manifest_reuse(monkeypatch,tmp_path):
    directory,_=tiny(monkeypatch,tmp_path)
    with pytest.raises(ModelContractError,match="fresh or empty"):
        payload.collect(tmp_path,directory,opener=lambda *a,**k:pytest.fail("network opened"))


def test_acquisition_failure_never_publishes_success(monkeypatch,tmp_path):
    tiny(monkeypatch,tmp_path)
    with pytest.raises(ModelContractError,match="observed pin"):
        payload.collect(tmp_path,tmp_path/"bad",opener=lambda r,**k:Response(*map(int,r.get_header("Range").removeprefix("bytes=").split("-")),b"evil"))
    assert not (tmp_path/"bad/manifest.json").exists()
