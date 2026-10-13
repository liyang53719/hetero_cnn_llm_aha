"""Small offline/fake HTTP regressions; never requests actual model payloads."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import urllib.request

import pytest

from candidates.qwen35_35b_payload import packer as p
from heteronpu.model_geometry import ModelContractError
from heteronpu.weight_header_contract import decode_header, sha256

ROOT = Path(__file__).resolve().parents[3]


def test_real_metadata_selection_and_bounded_ranges():
    initial = p.selection(ROOT)
    full = p.selection(ROOT, include_qkv=True)
    assert initial["payload_bytes"] == 1_052_672
    assert initial["total_download_bytes"] == 1_242_776
    assert full["payload_bytes"] == 34_607_104
    assert full["total_download_bytes"] == 34_820_560
    assert [s["start"] for s in full["tensors"]] == [1017119744, 208280, 23352]
    assert [s["end"] for s in full["tensors"]] == [1018168319, 212375, 33577783]
    assert [s["source_tensor_bytes"] for s in full["tensors"]] == [1017118720, 4096, 33554432]
    assert len(initial["shards"]) == 2 and len(full["shards"]) == 3
    assert full["tensors"][0]["source_rows"] == [0, 256]
    assert full["tensors"][0]["source_shape"] == [248320, 2048]
    spans = [span for spec in full["tensors"] for span in p.ranges(spec)]
    assert len(spans) == 6 and max(b-a+1 for a,b in spans) == 8_388_608
    assert sum(b-a+1 for a,b in spans) == 34_607_104
    assert full["forward_revision"] == "42ca97014c85d71a88ad60d55f08cb9fb4d26e2c"
    assert full["claim_boundary"]["complete_native_runtime_source_closure"] == "not pinned"


def _tiny_plan():
    specs, shards, bodies, expected = [], [], {}, {}
    entries = [("embedding", [5, 3], [1, 3], "BF16"),
               ("norm", [3], None, "BF16"), ("qkv", [4, 3], None, "BF16"),
               ("f32", [2], None, "F32")]
    for index, (name, shape, rows, dtype) in enumerate(entries):
        count = 1
        for d in shape:
            count *= d
        item = 4 if dtype == "F32" else 2
        data = bytes((index * 31 + n) % 256 for n in range(count * item))
        header = {name: {"dtype": dtype, "shape": shape, "data_offsets": [0, len(data)]}}
        encoded = json.dumps(header, separators=(",", ":")).encode()
        raw = len(encoded).to_bytes(8, "little") + encoded
        shard_name = f"shard{index}.safetensors"
        url = "https://fixture.invalid/immutable/" + shard_name
        shard = {"file": shard_name, "url": url, "file_bytes": len(raw) + len(data),
                 "header": {"bytes": len(raw), "sha256": sha256(raw)},
                 "advertised_lfs_sha256_unverified": sha256(raw + data)}
        start = len(raw) + (0 if rows is None else rows[0] * shape[1] * item)
        selected_shape = shape if rows is None else [rows[1]-rows[0], shape[1]]
        size = len(data) if rows is None else (rows[1]-rows[0]) * shape[1] * item
        spec = {"name": name, "local_name": name, "file": name + ".bin", "dtype": dtype,
                "shape": selected_shape, "source_shape": shape, "source_rows": rows,
                "source_data_offsets": [0,len(data)], "source_tensor_start": len(raw),
                "source_tensor_end": len(raw)+len(data)-1, "source_tensor_bytes": len(data),
                "start": start, "end": start+size-1, "bytes": size, "shard": shard_name,
                "header_bytes": len(raw), "header_sha256": sha256(raw), "transform": "none"}
        p._spec_from_header(spec, shard, raw, decode_header(raw, shard["file_bytes"]))
        specs.append(spec)
        shards.append(shard)
        bodies[url] = raw + data
        expected[name] = bodies[url][start:start+size]
    return {"tensors":specs, "shards":shards, "payload_bytes":sum(s["bytes"] for s in specs)}, bodies, expected


class Response:
    def __init__(self, start, end, total, body, *, status=206, headers=None):
        self.status = status
        self.headers = {"Content-Range":f"bytes {start}-{end}/{total}", "Content-Length":str(end-start+1)}
        self.headers.update(headers or {})
        self.body = body
        self.reads = 0
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, limit):
        self.reads += 1
        assert limit == int(self.headers["Content-Length"]) + 1
        return self.body[:limit]


@pytest.fixture
def tiny(monkeypatch):
    plan, bodies, expected = _tiny_plan()
    monkeypatch.setattr(p, "selection", lambda root, **kw: deepcopy(plan))
    monkeypatch.setattr(p, "ranges", lambda spec: ((start,min(start+7,spec["end"]))
                        for start in range(spec["start"],spec["end"]+1,8)))
    calls = []
    def opener(request, timeout):
        assert timeout == 90
        assert request.get_header("Accept-encoding") == "identity"
        start,end = map(int,request.get_header("Range").removeprefix("bytes=").split("-"))
        whole = bodies[request.full_url]
        calls.append((request.full_url,start,end))
        return Response(start,end,len(whole),whole[start:end+1])
    return plan, bodies, expected, calls, opener


def _acquire(tmp_path, tiny):
    _, _, _, _, opener = tiny
    output = tmp_path / "payload"
    manifest = p.collect(ROOT, output, opener=opener)
    digest = sha256((output / "manifest.json").read_bytes())
    return output, manifest, digest


def test_multishard_subranges_assemble_exact_bits(tiny,tmp_path):
    plan,bodies,expected,calls,_ = tiny
    output,manifest,digest = _acquire(tmp_path,tiny)
    loaded,values = p.load_payload(ROOT,output,manifest_sha256=digest)
    assert loaded == manifest and values == expected
    assert len(calls) == 4 + 2 + 1 + 3 + 1
    assert all(start == 0 for _,start,_ in calls[:4])
    assert all(start > 0 for _,start,_ in calls[4:])
    assert [len(r["http_ranges"]) for r in manifest["tensors"]] == [2,1,3,1]
    assert not manifest["official_forward_executed"] and not manifest["full_checkpoint_sha256_verified"]


def test_local_http_real_urllib_range_path(tiny,tmp_path):
    plan,bodies,expected,_,_ = tiny
    by_name = {url.rsplit("/",1)[-1]:raw for url,raw in bodies.items()}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = by_name[self.path.rsplit("/",1)[-1]]
            start,end = map(int,self.headers["Range"].removeprefix("bytes=").split("-"))
            self.send_response(206)
            self.send_header("Content-Range",f"bytes {start}-{end}/{len(data)}")
            self.send_header("Content-Length",str(end-start+1))
            self.end_headers()
            self.wfile.write(data[start:end+1])
        def log_message(self,*args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
    worker = threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        for shard in plan["shards"]:
            shard["url"] = f"http://127.0.0.1:{server.server_port}/" + shard["file"]
        output = tmp_path / "http_payload"
        p.collect(ROOT,output,opener=urllib.request.urlopen)
        digest = sha256((output / "manifest.json").read_bytes())
        _,values = p.load_payload(ROOT,output,manifest_sha256=digest)
        assert values == expected
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.mark.parametrize("status,headers",[
    (200,{}),(206,{"Content-Range":"bytes 1-4/8"}),
    (206,{"Content-Length":"99"}),(206,{"Content-Encoding":"gzip"}),
])
def test_server_ignored_or_wrong_range_refused_before_body(status,headers):
    response = Response(0,3,8,b"abcd",status=status,headers=headers)
    with pytest.raises(ModelContractError):
        p.fetch_range("https://fixture.invalid/immutable",0,3,8,opener=lambda *a,**kw:response)
    assert response.reads == 0


@pytest.mark.parametrize("body",[b"ab",b"abcde"])
def test_short_or_overlong_body_refused(body):
    with pytest.raises(ModelContractError,match="body length"):
        p.fetch_range("https://fixture.invalid/immutable",0,3,8,
                      opener=lambda *a,**kw:Response(0,3,8,body))


def test_remote_header_drift_stops_before_payload(tiny,tmp_path):
    _,bodies,_,calls,_ = tiny
    first = next(iter(bodies))
    raw = bytearray(bodies[first]);raw[9] ^= 1;bodies[first] = bytes(raw)
    with pytest.raises(ModelContractError,match="remote header hash"):
        _acquire(tmp_path,tiny)
    assert len(calls) == 1 and not (tmp_path / "payload/manifest.json").exists()


def test_prior_observed_hash_pins_reacquisition(tiny,tmp_path):
    plan,bodies,_,_,opener = tiny
    output,_,digest = _acquire(tmp_path,tiny)
    p.collect(ROOT,tmp_path/"repeat",expected_manifest=output/"manifest.json",
              expected_manifest_sha256=digest,opener=opener)
    shard = plan["shards"][0]
    changed = bytearray(bodies[shard["url"]]);changed[plan["tensors"][0]["start"]] ^= 1
    bodies[shard["url"]] = bytes(changed)
    with pytest.raises(ModelContractError,match="prior observed pin"):
        p.collect(ROOT,tmp_path/"bad",expected_manifest=output/"manifest.json",
                  expected_manifest_sha256=digest,opener=opener)
    assert not (tmp_path/"bad/manifest.json").exists()


def test_rehashed_payload_and_manifest_rejected_by_external_pin(tiny,tmp_path):
    output,manifest,digest = _acquire(tmp_path,tiny)
    target = output / manifest["tensors"][0]["file"]
    raw = b"X" * target.stat().st_size
    target.write_bytes(raw)
    with pytest.raises(ModelContractError,match="payload hash"):
        p.load_payload(ROOT,output,manifest_sha256=digest)
    manifest["tensors"][0]["sha256"] = sha256(raw)
    (output/"manifest.json").write_bytes(p._json_bytes(manifest))
    with pytest.raises(ModelContractError,match="manifest digest pin"):
        p.load_payload(ROOT,output,manifest_sha256=digest)


@pytest.mark.parametrize("mutate",[
    lambda m:m.update(schema_version=True),
    lambda m:m["plan"].update(revision="wrong"),
    lambda m:m["tensors"][0].update(shape=[True,3]),
    lambda m:m["tensors"][0].update(file="../alias.bin"),
    lambda m:m["tensors"].reverse(),
    lambda m:m["tensors"][0]["http_ranges"][0].update(status=200),
    lambda m:m["tensors"][0]["http_ranges"][0].update(sha256="0"*64),
    lambda m:m["tensors"][0]["http_ranges"].reverse(),
    lambda m:m["header_http_ranges"][0].update(sha256="0"*64),
    lambda m:m.update(official_forward_executed=True),
    lambda m:m.update(full_checkpoint_sha256_verified=True),
])
def test_manifest_semantics_rejected_even_with_new_digest(tiny,tmp_path,mutate):
    output,manifest,_ = _acquire(tmp_path,tiny)
    mutate(manifest)
    raw = p._json_bytes(manifest);(output/"manifest.json").write_bytes(raw)
    with pytest.raises(ModelContractError):
        p.load_payload(ROOT,output,manifest_sha256=sha256(raw))


@pytest.mark.parametrize("kind",["symlink","hardlink","extra_file"])
def test_local_file_aliases_rejected(tiny,tmp_path,kind):
    output,manifest,digest = _acquire(tmp_path,tiny)
    target = output / manifest["tensors"][0]["file"]
    if kind == "extra_file":
        (output/"alias.bin").write_bytes(b"x")
    else:
        external = tmp_path / "copy.bin"
        target.rename(external)
        if kind == "symlink":
            target.symlink_to(external)
        else:
            os.link(external,target)
    with pytest.raises(ModelContractError):
        p.load_payload(ROOT,output,manifest_sha256=digest)


def test_no_stale_success_or_checkout_weights(tiny,tmp_path):
    output,_,_ = _acquire(tmp_path,tiny)
    with pytest.raises(ModelContractError,match="fresh"):
        p.collect(ROOT,output,opener=lambda *a,**kw:pytest.fail("network"))
    with pytest.raises(ModelContractError,match="ignored work"):
        p.collect(ROOT,ROOT/"candidates/qwen35_35b_payload/forbidden",opener=lambda *a,**kw:pytest.fail("network"))


@pytest.mark.parametrize("field,value",[
    ("dtype","F32"),("source_shape",[True,3]),("source_data_offsets",[0,6]),
    ("start",0),("source_tensor_end",1),("source_rows",[0,6]),
])
def test_source_full_extent_dtype_rows_fail_closed(field,value):
    plan,bodies,_ = _tiny_plan()
    spec = deepcopy(plan["tensors"][0]);spec[field] = value
    shard = plan["shards"][0]
    raw = bodies[shard["url"]][:shard["header"]["bytes"]]
    with pytest.raises(ModelContractError):
        p._spec_from_header(spec,shard,raw,decode_header(raw,shard["file_bytes"]))


def test_duplicate_selection_and_overlapping_ranges_rejected():
    plan,_,_ = _tiny_plan()
    specs = plan["tensors"]
    with pytest.raises(ModelContractError,match="alias"):
        p._reject_aliases(specs + [deepcopy(specs[0])])
    specs[1]["shard"] = specs[0]["shard"]
    specs[1]["start"],specs[1]["end"] = specs[0]["start"],specs[0]["end"]
    with pytest.raises(ModelContractError,match="overlapping"):
        p._reject_aliases(specs)


def test_source_manifest_drift(tmp_path):
    path = tmp_path/p.SOURCE_PATH;path.parent.mkdir(parents=True);path.write_text("{}")
    with pytest.raises(ModelContractError,match="source manifest hash"):
        p.selection(tmp_path)


def test_raw_nk_to_kn_preserves_bf16_words_including_nan_signed_zero():
    words = [0x0000,0x8000,0x3f80,0x7f80,0xff80,0x7fc1]
    raw = b"".join(x.to_bytes(2,"little") for x in words)
    result = p.raw_nk_to_kn(raw,2,3)
    assert result == b"".join(words[i].to_bytes(2,"little") for i in [0,3,1,4,2,5])
    assert p.raw_nk_to_kn(result,3,2) == raw
    for n,k in [(True,3),(0,3),(2,4)]:
        with pytest.raises(ModelContractError):
            p.raw_nk_to_kn(raw,n,k)
