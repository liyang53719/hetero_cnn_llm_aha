"""No network, model execution, or optional skipping in recovery regression tests."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def loader():
    spec = importlib.util.spec_from_file_location("rope_materializer_test", ROOT / "scripts/materialize_rope_rounding_corpora.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def recovery(monkeypatch):
    module = loader()
    raw = {name: ("test bytes for " + name).encode() for name in module.FIXTURE_PINS}
    monkeypatch.setattr(module, "FIXTURE_BYTES", {name: len(value) for name, value in raw.items()})
    monkeypatch.setattr(module, "FIXTURE_PINS", {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()})
    monkeypatch.setattr(module, "fetch", lambda name: raw[name])
    return module, raw


def test_source_is_full_immutable_commit_and_independent_pins_match():
    m = loader()
    assert m.SOURCE_COMMIT == "27542342d546eae3e283463c25cc31211817bf16"
    assert "/" + m.SOURCE_COMMIT + "/" in m.SOURCE_BASE
    spec = importlib.util.spec_from_file_location("rope_runner_pins", ROOT / "scripts/run_rope_rounding_ablation.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert m.FIXTURE_PINS == runner.FIXTURE_PINS
    assert set(m.FIXTURE_BYTES) == set(m.FIXTURE_PINS)


def test_materialize_all_validate_and_reuse_without_download(tmp_path, recovery, monkeypatch):
    m, raw = recovery
    result = m.materialize(tmp_path)
    assert set(result["materialized_files"]) == set(raw)
    assert result["model_native_expectations_regenerated"] is False
    assert result["arithmetic_recomputed"] is False
    for name, data in raw.items():
        assert (tmp_path / name).read_bytes() == data
    monkeypatch.setattr(m, "fetch", lambda _: pytest.fail("unnecessary network"))
    assert m.materialize(tmp_path)["materialized_files"] == []
    assert m.materialize(tmp_path, verify_only=True)["materialized_files"] == []


def test_missing_verify_only_fails_without_network(tmp_path, recovery, monkeypatch):
    m, _ = recovery
    monkeypatch.setattr(m, "fetch", lambda _: pytest.fail("verify-only downloaded"))
    with pytest.raises(ValueError, match="missing historical fixtures"):
        m.materialize(tmp_path, verify_only=True)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("name", ["local.npz", "remote.npz", "provenance.json", "historical_arithmetic.npy"])
def test_existing_corruption_is_never_replaced(tmp_path, recovery, monkeypatch, name):
    m, raw = recovery
    bad = b"!" * len(raw[name])
    (tmp_path / name).write_bytes(bad)
    monkeypatch.setattr(m, "fetch", lambda _: pytest.fail("corruption silently repaired"))
    with pytest.raises(ValueError, match="digest drift"):
        m.materialize(tmp_path)
    assert (tmp_path / name).read_bytes() == bad


@pytest.mark.parametrize("bad", [b"", b"oversized untrusted download" * 100, b"!" * 24])
def test_bad_download_never_publishes_partial_corpus(tmp_path, recovery, monkeypatch, bad):
    m, raw = recovery
    monkeypatch.setattr(m, "fetch", lambda name: bad if name == "remote.npz" else raw[name])
    with pytest.raises(ValueError, match="drift"):
        m.materialize(tmp_path)
    assert not list(tmp_path.iterdir())


def test_download_failure_preserves_existing_metadata(tmp_path, recovery, monkeypatch):
    m, raw = recovery
    (tmp_path / "provenance.json").write_bytes(raw["provenance.json"])
    def fail(name):
        if name == "remote.npz":
            raise OSError("offline")
        return raw[name]
    monkeypatch.setattr(m, "fetch", fail)
    with pytest.raises(OSError, match="offline"):
        m.materialize(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["provenance.json"]


def test_local_git_extraction_is_explicit_and_has_no_network_fallback(tmp_path, recovery, monkeypatch):
    m, raw = recovery
    monkeypatch.setattr(m, "fetch", lambda _: pytest.fail("offline extraction downloaded"))
    monkeypatch.setattr(m, "extract_git", lambda name: raw[name])
    assert m.materialize(tmp_path, from_git=True)["materialized_files"]


def test_git_command_binds_immutable_commit_and_path(monkeypatch):
    m = loader()
    calls = []
    def read(command, **kwargs):
        calls.append(command)
        return b"bad historical data"
    monkeypatch.setattr(m.subprocess, "check_output", read)
    with pytest.raises(ValueError, match="drift"):
        m.extract_git("local.npz")
    assert calls == [["git", "-C", str(m.ROOT), "show",
                      m.SOURCE_COMMIT + ":tests/fixtures/rope_rounding/local.npz"]]


def test_symlinks_rejected_without_reading_target(tmp_path, recovery):
    m, _ = recovery
    (tmp_path / "local.npz").symlink_to(tmp_path / "missing-target")
    with pytest.raises(ValueError, match="symlink refused"):
        m.materialize(tmp_path)


@pytest.mark.parametrize("status,encoding,data", [
    (404, "identity", b"bad"), (200, "gzip", b"bad"),
    (200, "identity", b"bad"), (200, "identity", b"!" * 24),
])
def test_fetch_status_encoding_length_and_digest_are_fail_closed(monkeypatch, recovery, status, encoding, data):
    # Use the real fetch implementation rather than the fixture's replacement.
    m = loader()
    m.FIXTURE_BYTES = {"local.npz": 24}
    m.FIXTURE_PINS = {"local.npz": hashlib.sha256(b"a" * 24).hexdigest()}
    class Response:
        headers = {"Content-Encoding": encoding}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size):
            assert size == 25
            return data
    response = Response()
    response.status = status
    monkeypatch.setattr(m.urllib.request, "urlopen", lambda *a, **k: response)
    with pytest.raises(ValueError):
        m.fetch("local.npz")


def test_optimized_mode_still_rejects_corruption(tmp_path):
    (tmp_path / "local.npz").write_bytes(b"not a corpus")
    process = subprocess.run([sys.executable, "-O", str(ROOT / "scripts/materialize_rope_rounding_corpora.py"),
                              "--output", str(tmp_path), "--verify-only"], capture_output=True, text=True)
    assert process.returncode == 2
    assert "HISTORICAL_FIXTURE_RECOVERY_REJECTED" in process.stderr
