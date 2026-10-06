"""Actual pinned header geometry + deliberately OPEN replay admission tests."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heteronpu.model_geometry import ModelContractError, load_json
from heteronpu import weight_header_contract as headers
from heteronpu import workload_evidence as workloads

spec = importlib.util.spec_from_file_location("header_collect", ROOT / "scripts/collect_weight_headers.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def pack(data):
    raw = json.dumps(data, separators=(",", ":")).encode()
    return len(raw).to_bytes(8, "little") + raw


def tiny():
    return {"x": {"dtype": "BF16", "shape": [2, 3], "data_offsets": [0, 12]},
            "y": {"dtype": "F32", "shape": [1], "data_offsets": [12, 16]}}


def test_actual_all_three_model_headers_and_storage_precision():
    report = workloads.validate_preparation(ROOT)
    assert report["status"] == "PASS_METADATA_PREPARATION_WITH_OPEN_REPLAY_GATES"
    counts = {"qwen2_1p5b": (1, 338, 338), "qwen3_5_0p8b": (1, 488, 320), "qwen3_5_35b_a3b": (14, 1811, 692)}
    for key, expected in counts.items():
        r = report["header_evidence"][key]
        assert (r["shards"], r["tensor_count"], r["main_text_shapes_verified"]) == expected
        assert r["tensor_payload_bytes_downloaded"] == 0
        for field in ("tensor_content_verified", "official_forward_executed", "rtl_executed", "mac_utilization_measured"):
            assert r[field] is False
        if key != "qwen2_1p5b":
            tensors = r["representative_tensor_headers"]
            prefix = "model.language_model.layers.0.linear_attn."
            assert tensors[prefix + "A_log"]["dtype"] == "F32"
            assert tensors[prefix + "norm.weight"]["dtype"] == "F32"
            assert tensors[prefix + "dt_bias"]["dtype"] == "BF16"
    assert sum(r["header_bytes_verified"] for r in report["header_evidence"].values()) == 321392
    assert len(report["workloads"]) == 5 and all(r["status"] == "OPEN" for r in report["workloads"])
    assert report["full_U00_complete"] is False
    assert report["required_performance_suite_frozen"] is False


def test_packed_moe_headers_are_actual_not_per_expert_invention():
    r = headers.verify_bundle(ROOT, "qwen3_5_35b_a3b")
    ts = r["representative_tensor_headers"]
    for i in (0, 3):
        prefix = f"model.language_model.layers.{i}.mlp.experts."
        assert ts[prefix + "gate_up_proj"]["shape"] == [256, 1024, 2048]
        assert ts[prefix + "down_proj"]["shape"] == [256, 2048, 512]


def test_qwen2_unsharded_and_forward_tag_resolved_to_commit():
    m = load_json(ROOT / workloads.MANIFEST_PATH)
    assert m["models"]["qwen2_1p5b"]["forward_revision"] == "9fe3f585bb4ea29f209dc705d269fbe292e1128f"
    bundle = load_json(ROOT / headers.BUNDLE_ROOT / "qwen2_1p5b/manifest.json")
    assert bundle["index"] is None and "404" in bundle["index_absence"]
    assert bundle["forward"]["sha256"] == "f1c7a117ced20ee632e4c17d09982863304d6e30bb44f0ccdebd4b27dde259ad"


def test_deterministic_offline_validation():
    assert workloads.validate_preparation(ROOT) == workloads.validate_preparation(ROOT)


def test_cannot_admit_open_workloads():
    with pytest.raises(ModelContractError, match="U00.2 OPEN"):
        workloads.validate_preparation(ROOT, require_complete=True)
    run = subprocess.run([sys.executable, str(ROOT / "scripts/validate_workload_evidence.py"), "--require-complete"], capture_output=True, text=True)
    assert run.returncode == 2 and "U00.2 OPEN" in run.stderr


@pytest.mark.parametrize("edit", [
    lambda m: m.update(status="PASS"),
    lambda m: m.update(schema_version=True),
    lambda m: m.update(required_performance_suite_frozen=True),
    lambda m: m.update(required_performance_suite_sha256="0" * 64),
    lambda m: m.update(weights_loaded=True),
    lambda m: m["models"].pop("qwen3_5_0p8b"),
    lambda m: m["models"]["qwen2_1p5b"].update(model_id="Qwen/Qwen2-1.5B"),
    lambda m: m["models"]["qwen3_5_35b_a3b"].update(model_revision="59d61f3ce65a6d9863b86d2e96597125219dc754"),
    lambda m: m["models"]["qwen3_5_0p8b"].update(forward_revision=m["models"]["qwen3_5_0p8b"]["model_revision"]),
    lambda m: m["models"]["qwen2_1p5b"]["forward"].update(sha256="0" * 64),
    lambda m: m["models"]["qwen2_1p5b"].update(header_bundle_sha256="0" * 64),
    lambda m: m["workloads"].pop(),
    lambda m: m["workloads"].__setitem__(1, deepcopy(m["workloads"][0])),
    lambda m: m["workloads"][0].update(query_tokens=256),
    lambda m: m["workloads"][0].update(query_tokens=128.0),
    lambda m: m["workloads"][0].update(batch=True),
    lambda m: m["workloads"][0].update(layer_id=False),
    lambda m: m["workloads"][0].update(layer_id=3),
    lambda m: m["workloads"][0]["missing_evidence"].pop("input_sha256"),
    lambda m: m["workloads"][0]["missing_evidence"].update(input_sha256=" "),
    lambda m: m["workloads"][3]["replay"].update(expert_route_histogram_sha256="uniform_routes"),
    lambda m: m["performance_contract"].update(minimum_matrix_useful_wall_utilization=0.89),
    lambda m: m["performance_contract"].update(denominator="active_lanes * active_cycles"),
    lambda m: m["performance_contract"].update(numerator="executed_macs_including_padding"),
    lambda m: m["performance_contract"].update(end_event="matrix_issue_finished"),
    lambda m: m["performance_contract"].update(matrix_vector_report_separately=1),
])
def test_preparation_rejects_promotion_identity_and_workload_drift(edit):
    m = load_json(ROOT / workloads.MANIFEST_PATH)
    edit(m)
    with pytest.raises(ModelContractError):
        workloads.validate_preparation(ROOT, m)


@pytest.mark.parametrize("field", sorted(workloads.OPEN_FIELDS))
@pytest.mark.parametrize("value", ["0" * 64, 0, True])
def test_unvalidated_replay_values_cannot_turn_open_into_pass(field, value):
    m = load_json(ROOT / workloads.MANIFEST_PATH)
    m["workloads"][0]["replay"][field] = value
    with pytest.raises(ModelContractError, match="unvalidated replay evidence"):
        workloads.validate_preparation(ROOT, m)


def test_header_scalar_and_zero_sized_tensor_support():
    data = {"a": {"dtype": "F32", "shape": [], "data_offsets": [0, 4]},
            "b": {"dtype": "BF16", "shape": [0, 2], "data_offsets": [4, 4]},
            "__metadata__": {"format": "pt"}}
    raw = pack(data)
    assert len(headers.decode_header(raw, len(raw) + 4)) == 2


@pytest.mark.parametrize("edit", [
    lambda d: d["x"].update(dtype="UNKNOWN"),
    lambda d: d["x"].update(shape=[True, 3]),
    lambda d: d["x"].update(shape=[2.0, 3]),
    lambda d: d["x"].update(shape=[-2, -3]),
    lambda d: d["x"].update(shape="2,3"),
    lambda d: d["x"].update(data_offsets=[0, 10]),
    lambda d: d["x"].update(data_offsets=[False, 12]),
    lambda d: d["x"].update(data_offsets=[0, 12, 12]),
    lambda d: d["y"].update(data_offsets=[8, 12]),
    lambda d: d["y"].update(data_offsets=[14, 18]),
    lambda d: d["y"].update(extra=True),
    lambda d: d.update(__metadata__={"format": True}),
])
def test_header_rejects_malformed_geometry(edit):
    d = tiny(); edit(d); raw = pack(d)
    with pytest.raises(ModelContractError):
        headers.decode_header(raw, len(raw) + 16)


@pytest.mark.parametrize("raw", [b"", b"12345678", b"\xff"*16,
    (2).to_bytes(8,"little")+b"{}x", (2).to_bytes(8,"little")+b"[]",
    (13).to_bytes(8,"little")+b'{"x":1,"x":2}',
    (9).to_bytes(8,"little")+b'{"x":NaN}',
    (3).to_bytes(8,"little")+b'{\xff}'])
def test_header_rejects_truncation_duplicates_nonfinite_invalid_utf8(raw):
    with pytest.raises(ModelContractError):
        headers.decode_header(raw, 100)


@pytest.mark.parametrize("delta", [-1, 1])
def test_header_rejects_file_bounds_and_trailing_bytes(delta):
    raw = pack(tiny())
    with pytest.raises(ModelContractError):
        headers.decode_header(raw, len(raw) + 16 + delta)


@pytest.fixture
def copied(tmp_path):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    return tmp_path


@pytest.mark.parametrize("path", ["config/qwen2_1p5b_target_shape.json", "config/model_profiles/qwen3_5_35b_a3b.json",
                                   "config/model_profiles/qwen3_5_0p8b.json"])
def test_runtime_profile_drift_rejected_even_if_model_id_same(copied, path):
    p = copied/path; d = load_json(p)
    if "shape" in d: d["shape"]["hidden_size"] = 1
    else: d["vocab_size"] = 1
    p.write_text(json.dumps(d))
    with pytest.raises(ModelContractError, match="artifact"):
        workloads.validate_preparation(copied)


@pytest.mark.parametrize("suffix", ["model.safetensors.header.bin", "model_api.json", "modeling_qwen2.py", "manifest.json"])
def test_frozen_source_or_header_tamper_rejected(copied, suffix):
    p=copied / headers.BUNDLE_ROOT / "qwen2_1p5b" / suffix
    p.write_bytes(p.read_bytes()+b" ")
    with pytest.raises(ModelContractError):
        headers.verify_bundle(copied,"qwen2_1p5b")


@pytest.mark.parametrize("name", ["../outside", "/etc/passwd", "config\\bad", "missing"])
def test_file_record_traversal_missing_and_absolute_rejected(name):
    with pytest.raises(ModelContractError):
        headers.read_record(ROOT, {"path": name, "sha256":"0"*64,"bytes":0})


class FakeResponse:
    def __init__(self, status=206, content_range="bytes 0-7/100", length="8", encoding="identity", data=b"12345678"):
        self.status=status
        self.headers={"Content-Range":content_range,"Content-Length":length,"Content-Encoding":encoding}
        self.data=data; self.read_called=False
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,n):
        self.read_called=True
        assert n == 9
        return self.data


@pytest.mark.parametrize("params", [{"status":200},{"content_range":"bytes 0-8/100"},
    {"content_range":"bytes 0-7/101"},{"length":"100"},{"encoding":"gzip"}])
def test_range_response_rejected_before_reading_payload(params):
    response=FakeResponse(**params)
    with pytest.raises(ModelContractError):
        collector.fetch_range("https://huggingface.co/example",7,100,opener=lambda *a,**k:response)
    assert response.read_called is False


def test_range_fetch_checks_exact_response_bytes():
    response=FakeResponse()
    data,receipt=collector.fetch_range("https://huggingface.co/example",7,100,opener=lambda *a,**k:response)
    assert data==b"12345678" and receipt["file_total_bytes"]==100
    with pytest.raises(ModelContractError):
        collector.fetch_range("https://huggingface.co/example",7,100,opener=lambda *a,**k:FakeResponse(data=b"123456789"))


def test_reacquisition_refuses_stale_output_before_network(tmp_path, monkeypatch):
    (tmp_path / "result.json").write_text('{"status":"PASS_PINNED_HEADERS_REACQUIRED_ONLY"}')
    called=[]
    monkeypatch.setattr(collector,"fetch_range",lambda *args,**kwargs:called.append(True))
    with pytest.raises(ModelContractError,match="fresh or empty"):
        collector.collect(ROOT,tmp_path,["qwen2_1p5b"])
    assert called == []


def reanchor_json(root, key, path, edit, monkeypatch):
    """Exercise semantic checks independently of the outer byte-integrity lock."""
    target=root/path
    data=load_json(target);edit(data);target.write_text(json.dumps(data))
    replacement={"bytes":target.stat().st_size,"sha256":headers.sha256(target.read_bytes())}
    manifest_path=root/headers.BUNDLE_ROOT/key/"manifest.json"
    bundle=load_json(manifest_path)
    def update(node):
        if isinstance(node,dict):
            if node.get("path")==str(path):node.update(replacement)
            for value in node.values():update(value)
        elif isinstance(node,list):
            for value in node:update(value)
    update(bundle)
    manifest_path.write_text(json.dumps(bundle))
    monkeypatch.setitem(headers.BUNDLE_SHA256,key,headers.sha256(manifest_path.read_bytes()))


@pytest.mark.parametrize("file_kind,edit", [
    ("api",lambda d:d.update(sha="0"*40)),
    ("api",lambda d:d.update(id="Qwen/Wrong")),
    ("config",lambda d:d["text_config"].update(hidden_size=1)),
    ("index",lambda d:d["weight_map"].pop(next(iter(d["weight_map"])))),
    ("index",lambda d:d["metadata"].update(total_size=1)),
    ("receipt",lambda d:d.update(status=200)),
    ("receipt",lambda d:d.update(content_range="bytes 0-7/100")),
    ("receipt",lambda d:d.update(file_total_bytes=True)),
    ("receipt",lambda d:d.update(body_sha256="0"*64)),
])
def test_semantic_source_checks_survive_reanchored_corruption(copied,monkeypatch,file_kind,edit):
    key="qwen3_5_0p8b"
    bundle=load_json(copied/headers.BUNDLE_ROOT/key/"manifest.json")
    record=bundle["shards"][0]["http_receipt"] if file_kind=="receipt" else bundle[file_kind]
    reanchor_json(copied,key,Path(record["path"]),edit,monkeypatch)
    with pytest.raises(ModelContractError):
        headers.verify_bundle(copied,key)
