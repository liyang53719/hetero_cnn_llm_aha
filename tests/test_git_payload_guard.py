import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def loader():
    spec = importlib.util.spec_from_file_location("git_payload_guard_test", ROOT / "scripts/check_git_payloads.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def stage(repo, name, raw=b"payload"):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    subprocess.run(["git", "-C", str(repo), "add", "-f", "--", name], check=True)
    return path


@pytest.mark.parametrize("name", [
    "tests/fixtures/qk_norm256/local.npz", "tests/fixtures/qk_norm256/remote.npz",
    "tests/fixtures/qk_norm256/converted.npy",
    "tests/fixtures/rope_rounding/local.npz", "tests/fixtures/rope_rounding/remote.npz",
    "tests/fixtures/rope_rounding/historical_arithmetic.npy", "tests/fixtures/rope_rounding/subdir/renamed.npz",
    "models/config.json", "weights/q.bin", "checkpoints/latest.npy", "work/generated/anything.dat",
    "artifacts/corpus.zip", "elsewhere/model.safetensors", "elsewhere/model-00001-of-00004.bin",
    "converted/q_norm_weight.npy", "elsewhere/weights.npz", "elsewhere/model.pt",
    "elsewhere/model.pth", "elsewhere/model.gguf", "elsewhere/pytorch_model.bin",
])
def test_forced_staging_is_rejected(repo, name):
    stage(repo, name)
    assert loader().check_index(repo)


@pytest.mark.parametrize("name", [
    "tests/fixtures/tiny_golden.npz", "tests/fixtures/tiny_golden.npy",
    "reports/execution/small/host_commands.bin", "reports/execution/small/host_descriptors.bin",
    "tests/fixtures/rope_rounding/provenance.json", "tb/models/axi_ddr.sv",
    "config/upstream/weight_headers/model/manifest.json",
])
def test_scoped_policy_preserves_small_fixtures_and_metadata(repo, name):
    stage(repo, name)
    assert loader().check_index(repo) == []


def header():
    raw = json.dumps({"layer.weight": {"dtype": "BF16", "shape": [16], "data_offsets": [0, 32]}}).encode()
    return len(raw).to_bytes(8, "little") + raw


def test_exact_header_only_evidence_allowed(repo):
    stage(repo, "config/upstream/weight_headers/model/model.safetensors.header.bin", header())
    assert loader().check_index(repo) == []


def test_header_exception_reads_staged_blob_not_corrected_worktree(repo):
    path = stage(repo, "config/upstream/weight_headers/model/model.safetensors.header.bin", header() + b"actual weights")
    path.write_bytes(header())
    assert "trailing tensor" in loader().check_index(repo)[0]


def test_unstaged_payload_cannot_change_index_verdict(repo):
    path = stage(repo, "config/upstream/weight_headers/model/model.safetensors.header.bin", header())
    path.write_bytes(header() + b"unstaged weights")
    assert loader().check_index(repo) == []


@pytest.mark.parametrize("raw", [b"", b"abc", b"\x02\0\0\0\0\0\0\0{}", header()[:-1]])
def test_invalid_header_rejected(repo, raw):
    stage(repo, "config/upstream/weight_headers/model/model.safetensors.header.bin", raw)
    assert loader().check_index(repo)


def test_header_exception_does_not_cover_arbitrary_directory(repo):
    stage(repo, "elsewhere/model.safetensors.header.bin", header())
    assert loader().check_index(repo)


def test_frozen_blob_identity_rejected_even_after_rename():
    m = loader()
    for blob in m.FROZEN_BLOBS:
        assert "renamed" in m.forbidden_reason("tests/fixtures/innocent.dat", blob)


def test_git_error_fails_closed(tmp_path):
    process = subprocess.run([sys.executable, str(ROOT / "scripts/check_git_payloads.py"), "--root", str(tmp_path)],
                             capture_output=True, text=True)
    assert process.returncode == 2
    assert "GIT_PAYLOAD_CHECK_REJECTED" in process.stderr


def test_optimized_mode_still_rejects_forced_staging(repo):
    stage(repo, "tests/fixtures/rope_rounding/local.npz")
    process = subprocess.run([sys.executable, "-O", str(ROOT / "scripts/check_git_payloads.py"), "--root", str(repo)],
                             capture_output=True, text=True)
    assert process.returncode == 1
    assert "transient RoPE/QK corpus" in process.stderr
