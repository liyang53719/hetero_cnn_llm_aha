"""Fast admission checks for the isolated, bounded production-top diagnostic."""
from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ".github/workflows/attention-top-profile.yml"
SOURCE_SHA = "6959810545203d5f9508075b311dba52f1bee0c9"
DIAGNOSTIC_ROOT = "work/attention_profile_diagnostic"
COMPACT_ROOT = "work/full_top_profile/compact"


def read_workflow(path: Path) -> dict:
    # BaseLoader preserves GitHub's YAML 1.2 `on` key without interpreting it as
    # the YAML 1.1 boolean True. These tests intentionally compare scalar text.
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


WORKFLOW = read_workflow(ROOT / WORKFLOW_PATH)
JOB = WORKFLOW["jobs"]["bounded-attention-top-profile"]
STEPS = JOB["steps"]


def step_named(name: str) -> dict:
    return next(step for step in STEPS if step.get("name") == name)


def test_only_main_diagnostic_paths_or_manual_dispatch_can_trigger():
    assert set(WORKFLOW["on"]) == {"push", "workflow_dispatch"}
    assert WORKFLOW["on"]["push"] == {
        "branches": ["main"],
        "paths": [WORKFLOW_PATH, "tools/attention_profile/**"],
    }
    assert WORKFLOW["permissions"] == {"contents": "read"}


def test_one_bounded_serial_job_and_exact_commit_concurrency():
    assert len(WORKFLOW["jobs"]) == 1
    assert JOB["runs-on"] == "ubuntu-24.04"
    assert JOB["timeout-minutes"] == "40"
    assert "strategy" not in JOB
    assert WORKFLOW["concurrency"] == {
        "group": "attention-top-profile-${{ github.sha }}",
        "cancel-in-progress": "false",
    }
    assert JOB["env"]["BUILD_JOBS"] == "1"
    assert JOB["env"]["BUILD_RESERVE_BYTES"] == "1073741824"
    assert JOB["env"]["MAKEFLAGS"].startswith("-j1 VM_PARALLEL_BUILDS=0 ")


def test_frozen_source_and_diagnostic_are_separate_verified_checkouts():
    checkouts = [step for step in STEPS if step.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) == 2
    assert checkouts[0]["with"] == {
        "ref": SOURCE_SHA, "fetch-depth": "1", "persist-credentials": "false",
    }
    assert checkouts[1]["with"] == {
        "ref": "${{ github.sha }}", "path": DIAGNOSTIC_ROOT,
        "fetch-depth": "1", "persist-credentials": "false",
    }
    assert JOB["env"]["SOURCE_SHA"] == SOURCE_SHA
    assert "defaults" not in WORKFLOW
    assert "defaults" not in JOB
    verify = step_named("Verify both exact revisions and separate repository roots")["run"]
    assert 'source_root=$(realpath "$GITHUB_WORKSPACE")' in verify
    assert f'diagnostic_root=$(realpath "$GITHUB_WORKSPACE/{DIAGNOSTIC_ROOT}")' in verify
    assert 'test "$diagnostic_root" != "$source_root"' in verify
    for root, revision in (("diagnostic_root", "GITHUB_SHA"), ("source_root", "SOURCE_SHA")):
        assert f'git -C "${root}" rev-parse --show-toplevel' in verify
        assert f'test "$(git -C "${root}" rev-parse HEAD)" = "${revision}"' in verify
        assert f'git -C "${root}" diff --exit-code HEAD --' in verify
    assert STEPS.index(step_named("Verify both exact revisions and separate repository roots")) < next(
        i for i, step in enumerate(STEPS) if "pip install" in step.get("run", "")
    )


def test_original_pinned_dependencies_are_installed_from_the_source_root():
    setup = step_named("Prepare the frozen source runtime, pinned tools and upstream iDMA")
    assert "working-directory" not in setup
    run = setup["run"]
    assert 'python -m pip install -e "$GITHUB_WORKSPACE"' in run
    for pin in (
        "torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu",
        "PyYAML==6.0.3", "numpy==2.3.5", "uv==0.12.19",
        "huggingface-hub==1.33.0", "tokenizers==0.23.2", "safetensors==0.8.0",
        "https://github.com/huggingface/transformers/archive/14e738b5d0cc69aa27a95dde272aea41fde44f2f.zip"
        "#sha256=15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d",
    ):
        assert pin in run
    assert 'prepare_host_ci_tools.sh "$GITHUB_WORKSPACE/work/attention_profile_ci_tools"' in run
    assert "prepare_pinned_idma_sources.py --output work/attention_profile_ci_idma" in run
    assert 'IDMA_EXPORT=$GITHUB_WORKSPACE/work/attention_profile_ci_idma/idma_export' in run
    assert JOB["env"]["HARDFLOAT_SOURCE"] == (
        "${{ github.workspace }}/work/upstream/hardfloat_continuous"
    )


def test_tests_are_fast_diagnostic_only_and_payload_guards_cover_both_roots():
    check = step_named("Check only the diagnostic tests and Git payload boundary")
    assert check["working-directory"] == DIAGNOSTIC_ROOT
    assert check["env"]["ATTENTION_PROFILE_SOURCE_ROOT"] == "${{ github.workspace }}"
    run = check["run"]
    assert '(cd "$GITHUB_WORKSPACE" && python scripts/check_git_payloads.py)\n' in run
    assert "python scripts/check_git_payloads.py\n" in run
    assert "python -m pytest -o addopts='' -q tools/attention_profile\n" in run
    assert "python -O -m pytest -o addopts='' -q tools/attention_profile\n" in run
    all_runs = "\n".join(step.get("run", "") for step in STEPS)
    assert "sbt -batch" not in all_runs
    assert "testOnly" not in all_runs
    assert "run_host_bf16_attention_core_fresh_gate.py" not in all_runs
    assert "chisel/continuous_prefill/tests/" not in all_runs
    assert "--max-cycles" not in all_runs  # The fixed cap belongs to the runner.


def test_codegen_performs_no_payload_collection_or_model_execution():
    all_runs = "\n".join(step.get("run", "") for step in STEPS)
    assert "collect_qwen35" not in all_runs
    assert "run_profile.py" not in all_runs
    profile = step_named("Generate exact frozen SV and concat callers without C++ build or model execution")
    assert "working-directory" not in profile
    assert profile["env"] == {"HF_HUB_OFFLINE": "1"}
    assert profile["run"].splitlines() == [
        "set -euo pipefail",
        f'python "$GITHUB_WORKSPACE/{DIAGNOSTIC_ROOT}/tools/attention_profile/run_codegen.py" '
        '--source-root "$GITHUB_WORKSPACE" '
        '--output "$GITHUB_WORKSPACE/work/full_top_profile"',
    ]


def test_upload_allowlist_is_compact_and_selected_pure_source_even_on_failure():
    uploads = [step for step in STEPS if step.get("uses", "").startswith("actions/upload-artifact@")]
    assert len(uploads) == 1
    assert uploads[0]["if"] == "always()"
    assert uploads[0]["with"]["path"].splitlines() == [
        f"{COMPACT_ROOT}/summary.json", f"{COMPACT_ROOT}/source_input_hashes.json",
        "work/full_top_profile/selected-source/",
    ]
    assert "${{ github.sha }}" in uploads[0]["with"]["name"]
    assert "${{ github.run_attempt }}" in uploads[0]["with"]["name"]


def test_diagnostic_boundary_does_not_claim_acceptance_or_speedup():
    assert "bounded" in WORKFLOW["name"]
    assert "diagnostic" in WORKFLOW["name"]
    boundary = step_named("State the diagnostic boundary even on timeout or failure")
    assert boundary["if"] == "always()"
    for statement in (
        SOURCE_SHA, "numerical_acceptance=false", "1200-second process-tree budget",
        "stop immediately after hier_verilation and before any C++ compilation",
        "No model downloads, fresh model execution, reference arithmetic, ELF build, DUT simulation",
        "caller attribution requires the generated call sites and active conditions",
        "pure generated caller/header/runtime source", "No speedup",
    ):
        assert statement in boundary["run"]


def _may_match_paths(name: str, patterns: list[str]) -> bool:
    """Conservatively model GitHub inclusion filters for these known paths.

    fnmatch permits '*' across '/', a superset of GitHub's single '*'. A match
    here therefore errs toward rejecting isolation, never hiding heavy CI.
    Exclusions are deliberately ignored, for the same conservative guarantee.
    """
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns if not pattern.startswith("!"))


def test_diagnostic_paths_do_not_trigger_any_existing_heavy_push_workflow():
    paths = {WORKFLOW_PATH, "tools/attention_profile/future/nested_diagnostic.py"}
    paths.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tools/attention_profile").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    triggered = set()
    for path in (ROOT / ".github/workflows").glob("*.y*ml"):
        if path.relative_to(ROOT).as_posix() == WORKFLOW_PATH:
            continue
        events = read_workflow(path).get("on", {})
        if isinstance(events, dict):
            if "push" not in events:
                continue
            push = events["push"] or {}
        else:
            if "push" not in ([events] if isinstance(events, str) else events):
                continue
            push = {}
        include = push.get("paths", ["**"])
        if any(_may_match_paths(name, include) for name in paths):
            triggered.add(path.name)
    # This small guard intentionally runs on every push; all other workflows
    # must remain excluded by the diagnostic-only file set.
    assert triggered == {"git-payload-guard.yml"}, sorted(triggered)
