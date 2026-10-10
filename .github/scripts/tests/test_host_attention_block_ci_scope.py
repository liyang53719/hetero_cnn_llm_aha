"""Exact-tree scope control tests: no compiler, EDA, DUT or numerical runs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "host_attention_block_ci_scope.py"
SPEC = importlib.util.spec_from_file_location("host_attention_block_ci_scope", SCRIPT)
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)

RUNNER = scope.PROJECT + "scripts/run_host_bf16_attention_block_fresh_gate.py"
TIMEOUT_LINE = "    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 3600, 'bounded actual timeout required')\n"
LIVE_SOURCE = (
    "def run_case(*, timeout_seconds=3600):\n" + TIMEOUT_LINE
    + "    require(original_operator_gate_pass, 'unchanged numerical threshold')\n"
)


class Repository:
    def __init__(self, path):
        self.path = path
        self.git("init", "-q")
        self.git("config", "user.name", "CI scope control tests")
        self.git("config", "user.email", "scope-tests@example.invalid")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.path, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()

    def write(self, path, content):
        target = self.path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-qm", "Control fixture")
        return self.git("rev-parse", "HEAD")

    def classify(self, base, head):
        return scope.classify(self.path, base, head)


@pytest.fixture
def repo(tmp_path):
    return Repository(tmp_path)


def workflow(path):
    text = "name: numerical control fixture\non: [push, workflow_dispatch]\njobs:\n"
    for job in scope.WORKFLOW_ROOTS[path]:
        text += (
            "  " + job + ":\n"
            "    runs-on: ubuntu-24.04\n"
            "    timeout-minutes: 240\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - run: python numerical_gate.py --threshold 0.01\n"
        )
    if path in scope.WORKFLOW_ACCEPTANCE:
        text += (
            "  canonical-pass:\n"
            "    needs: build\n"
            "    runs-on: ubuntu-24.04\n"
            "    steps:\n"
            "      - run: python numerical_case.py\n"
            "  " + scope.WORKFLOW_ACCEPTANCE[path] + ":\n"
            "    needs: [build, canonical-pass]\n"
            "    if: always()\n"
            "    runs-on: ubuntu-24.04\n"
            "    steps:\n"
            "      - run: python numerical_acceptance.py\n"
        )
    return text


def add_wiring(path, text):
    text = text.replace("jobs:\n", "jobs:\n" + scope.SCOPE_JOB_BLOCK, 1)
    for job in scope.WORKFLOW_ROOTS[path]:
        text = text.replace("  " + job + ":\n", "  " + job + ":\n" + scope.ROOT_JOB_GUARD, 1)
    if path in scope.WORKFLOW_ACCEPTANCE:
        text = text.replace("    if: always()\n", scope.ACCEPTANCE_IF, 1)
    return text


@pytest.mark.parametrize("path", sorted(scope.ATTENTION_ONLY_PATHS))
def test_explicit_attention_orchestration_path_is_allowed(repo, path):
    repo.write(path, "old control content\n")
    base = repo.commit()
    repo.write(path, "new control content\n")
    head = repo.commit()
    assert repo.classify(base, head) == {
        "run_full": False, "base": base, "head": head, "changed_paths": [path],
        "reason": "only explicit Attention orchestration paths and exact scope wiring changed",
    }


@pytest.mark.parametrize("path", [
    "chisel/continuous_prefill/src/main/scala/HostBlockTop.scala",
    "chisel/continuous_prefill/src/test/scala/HostAttentionBlockCommandsSpec.scala",
    "chisel/continuous_prefill/tests/host_bf16_attention_block.cpp",
    scope.PROJECT + "scripts/host_bf16_attention_block_reference.py",
    scope.PROJECT + "scripts/host_bf16_attention_block_execution.py",
    scope.PROJECT + "scripts/host_bf16_attention_block_descriptor.py",
    scope.PROJECT + "scripts/host_bf16_attention_block_fixture.py",
    "chisel/p0_safety/src/main/scala/SharedFP.scala",
    "integration/gemmini/EmitHeteroBF16Fma.scala",
    "integration/gemmini/EmitHeteroFP32Alu.scala",
    "rtl/matrix/matrix.sv",
    "rtl/integration/idma.sv",
    "src/heteronpu/command.py",
    "scripts/collect_qwen35_layer0_payload.py",
    "config/upstream/qwen3_5_0p8b/weights.json",
    ".github/workflows/host-command-shared-idma.yml",
    ".github/scripts/another_scope.py",
    "unknown.txt",
])
def test_hardware_driver_oracle_shared_and_unknown_changes_run_full(repo, path):
    repo.write(RUNNER, "old orchestration\n")
    repo.write(path, "old source\n")
    base = repo.commit()
    repo.write(RUNNER, "new orchestration\n")
    repo.write(path, "changed source\n")
    head = repo.commit()
    result = repo.classify(base, head)
    assert result["run_full"] is True
    assert set(result["changed_paths"]) == {RUNNER, path}
    assert "outside Attention orchestration" in result["reason"]


def test_live_gate_only_exact_timeout_upper_bound_may_change(repo):
    repo.write(scope.LIVE_GATE, LIVE_SOURCE)
    base = repo.commit()
    repo.write(scope.LIVE_GATE, LIVE_SOURCE.replace("<= 3600", "<= 10800"))
    head = repo.commit()
    assert repo.classify(base, head)["run_full"] is False


@pytest.mark.parametrize("change", [
    lambda text: text.replace("<= 3600", "<= 10801"),
    lambda text: text.replace("timeout_seconds=3600", "timeout_seconds=10800"),
    lambda text: text.replace("original_operator_gate_pass", "True"),
    lambda text: text.replace("'unchanged numerical threshold'", "'different threshold'"),
    lambda text: text.replace("type(timeout_seconds) is int and ", ""),
    lambda text: text.replace(TIMEOUT_LINE, ""),
])
def test_live_gate_budget_does_not_hide_admission_or_default_changes(repo, change):
    repo.write(scope.LIVE_GATE, LIVE_SOURCE)
    base = repo.commit()
    repo.write(scope.LIVE_GATE, change(LIVE_SOURCE))
    assert repo.classify(base, repo.commit())["run_full"] is True


@pytest.mark.parametrize("path", sorted(scope.WORKFLOW_ROOTS))
def test_exact_workflow_wiring_bootstraps_without_changing_numerical_body(repo, path):
    original = workflow(path)
    repo.write(path, original)
    base = repo.commit()
    wired = add_wiring(path, original)
    repo.write(path, wired)
    assert scope.normalize_workflow(path, wired.encode()) == original.encode()
    assert repo.classify(base, repo.commit())["run_full"] is False


def test_complete_scope_bootstrap_is_attention_only(repo):
    for path in scope.WORKFLOW_ROOTS:
        repo.write(path, workflow(path))
    base = repo.commit()
    for path in scope.WORKFLOW_ROOTS:
        repo.write(path, add_wiring(path, workflow(path)))
    repo.write(".github/scripts/host_attention_block_ci_scope.py", SCRIPT.read_text())
    repo.write(RUNNER, "# New orchestration control fixture\n")
    report = repo.classify(base, repo.commit())
    assert report["run_full"] is False
    assert len(report["changed_paths"]) == 9


@pytest.mark.parametrize("change", [
    lambda text: text.replace("--threshold 0.01", "--threshold 0.02"),
    lambda text: text.replace("timeout-minutes: 240", "timeout-minutes: 300"),
    lambda text: text.replace("      - uses: actions/checkout@v4\n",
                              "      - uses: actions/checkout@v4\n        with: {ref: main}\n"),
    lambda text: text.replace("python3 .github/scripts/host_attention_block_ci_scope.py", "echo run_full=false #"),
    lambda text: text.replace("fetch-depth: 0", "fetch-depth: 1"),
    lambda text: text.replace("steps.classify.outputs.run_full", "false"),
    lambda text: text.replace("HEAD_SHA: ${{ github.sha }}", "HEAD_SHA: main"),
    lambda text: text.replace("needs.host-attention-scope.result != 'success' || ", ""),
    lambda text: text.replace("    timeout-minutes: 5\n", "    timeout-minutes: 5\n    if: false\n"),
    lambda text: text.replace("  # END HOST_ATTENTION_BLOCK_CI_SCOPE\n",
                              "  evil-job:\n    steps:\n      - run: false\n  # END HOST_ATTENTION_BLOCK_CI_SCOPE\n"),
    lambda text: text + "  sneaky-job:\n    steps:\n      - run: false\n",
    lambda text: text.replace("on: [push, workflow_dispatch]", "on: [workflow_dispatch]"),
])
def test_workflow_semantic_edits_even_inside_guard_markers_run_full(repo, change):
    path = ".github/workflows/host-bf16-v.yml"
    original = workflow(path)
    repo.write(path, original)
    base = repo.commit()
    repo.write(path, change(add_wiring(path, original)))
    result = repo.classify(base, repo.commit())
    assert result["run_full"] is True


def test_numerical_edit_in_already_guarded_workflow_still_runs_full(repo):
    path = ".github/workflows/host-bf16-gdn-core.yml"
    wired = add_wiring(path, workflow(path))
    repo.write(path, wired)
    base = repo.commit()
    repo.write(path, wired.replace("python numerical_case.py", "python other_case.py"))
    assert repo.classify(base, repo.commit())["run_full"] is True


@pytest.mark.parametrize("change", [
    lambda text: text.replace(scope.ROOT_JOB_GUARD, "", 1),
    lambda text: text.replace(scope.ACCEPTANCE_IF, "    if: always()\n", 1),
    lambda text: text.replace(scope.ACCEPTANCE_IF, "    if: false\n", 1),
    lambda text: text.replace("jobs:\n" + scope.SCOPE_JOB_BLOCK, "jobs:\n"),
    lambda text: text.replace("jobs:\n", "jobs:\n  # unexpected leading text\n", 1),
])
def test_incomplete_or_unrecognized_workflow_wiring_runs_full(repo, change):
    path = ".github/workflows/host-bf16-gdn-core.yml"
    original = workflow(path)
    repo.write(path, original)
    base = repo.commit()
    repo.write(path, change(add_wiring(path, original)))
    assert repo.classify(base, repo.commit())["run_full"] is True


@pytest.mark.parametrize("bad", ["", None, "0" * 40, "0" * 64, "a" * 40, "HEAD", "HEAD~1", "abc1234", "--all", "../HEAD", "f" * 39, "a" * 40 + "\n"])
@pytest.mark.parametrize("which", ["base", "head"])
def test_bad_missing_zero_or_unavailable_commit_runs_full(repo, bad, which):
    repo.write(RUNNER, "old\n")
    base = repo.commit()
    repo.write(RUNNER, "new\n")
    head = repo.commit()
    args = {"base": base, "head": head, which: bad}
    assert repo.classify(**args)["run_full"] is True


def test_blob_id_is_not_a_commit(repo):
    repo.write(RUNNER, "old\n")
    head = repo.commit()
    blob = repo.git("rev-parse", "HEAD:" + RUNNER)
    assert repo.classify(blob, head)["run_full"] is True


def test_empty_diff_does_not_grant_skip(repo):
    repo.write(RUNNER, "old\n")
    head = repo.commit()
    assert repo.classify(head, head)["run_full"] is True


def test_diff_uses_requested_commits_and_ignores_dirty_worktree(repo):
    repo.write(RUNNER, "old\n")
    repo.write("rtl/matrix/control.sv", "old hardware\n")
    base = repo.commit()
    repo.write(RUNNER, "new\n")
    safe_head = repo.commit()
    repo.write("rtl/matrix/control.sv", "new hardware\n")
    unsafe_head = repo.commit()
    repo.write(RUNNER, "uncommitted runner\n")
    assert repo.classify(base, safe_head)["run_full"] is False
    assert repo.classify(base, unsafe_head)["run_full"] is True


@pytest.mark.parametrize("kind", ["delete", "rename", "symlink", "executable-mode"])
def test_deleted_renamed_or_nonregular_allowlisted_path_runs_full(repo, kind):
    repo.write(RUNNER, "old\n")
    base = repo.commit()
    target = repo.path / RUNNER
    if kind == "delete":
        target.unlink()
    elif kind == "rename":
        target.rename(target.with_name("unknown_runner.py"))
    elif kind == "symlink":
        target.unlink()
        target.symlink_to("unknown_runner.py")
    else:
        target.chmod(0o755)
    assert repo.classify(base, repo.commit())["run_full"] is True


@pytest.mark.parametrize("raw", [b"M\0missing-final-null", b"\0", b":100644 100644 nope nope M\0path\0", b":100644 100644 " + b"a" * 40 + b" " + b"b" * 40 + b" M\0bad\npath\0"])
def test_malformed_git_output_fails_closed(monkeypatch, raw):
    monkeypatch.setattr(scope, "validate_commit", lambda *args: None)
    monkeypatch.setattr(scope, "git", lambda *args: raw)
    assert scope.classify(Path.cwd(), "a" * 40, "b" * 40)["run_full"] is True


@pytest.mark.parametrize("extra", [[], ["--unknown"], ["--base"], ["--base", "HEAD", "--base", "HEAD"], ["--bas", "HEAD"]])
def test_cli_malformed_inputs_emit_run_full_true(tmp_path, extra):
    output = tmp_path / "github-output"
    process = subprocess.run([sys.executable, str(SCRIPT), "--github-output", str(output), *extra],
                             cwd=tmp_path, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert output.read_text() == "run_full=true\n"
    assert json.loads(process.stdout)["run_full"] is True


def test_cli_logs_exact_commits_paths_and_explicit_skip(repo):
    repo.write(RUNNER, "old\n")
    base = repo.commit()
    repo.write(RUNNER, "new\n")
    head = repo.commit()
    output = repo.path / "github-output"
    process = subprocess.run([sys.executable, str(SCRIPT), "--base", base, "--head", head,
                              "--github-output", str(output)], cwd=repo.path, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert output.read_text() == "run_full=false\n"
    report = json.loads(process.stdout)
    assert (report["base"], report["head"], report["changed_paths"]) == (base, head, [RUNNER])


def test_dispatch_guard_has_no_base_and_guard_failure_cannot_suppress_roots():
    assert "github.event_name == 'push' && github.event.before || ''" in scope.SCOPE_JOB_BLOCK
    assert "ref: '${{ github.sha }}'" in scope.SCOPE_JOB_BLOCK
    assert "fetch-depth: 0" in scope.SCOPE_JOB_BLOCK
    assert "always()" in scope.ROOT_JOB_GUARD
    assert "needs.host-attention-scope.result != 'success'" in scope.ROOT_JOB_GUARD
    assert "needs.host-attention-scope.outputs.run_full != 'false'" in scope.ROOT_JOB_GUARD


def test_output_write_failure_reports_full_and_fails_the_guard(tmp_path):
    process = subprocess.run([sys.executable, str(SCRIPT), "--github-output", str(tmp_path)],
                             cwd=tmp_path, capture_output=True, text=True,
                             env={key: value for key, value in os.environ.items() if key != "GITHUB_OUTPUT"})
    assert process.returncode != 0
    assert json.loads(process.stdout)["run_full"] is True
