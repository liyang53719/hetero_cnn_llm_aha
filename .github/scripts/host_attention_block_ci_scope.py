#!/usr/bin/env python3
"""Fail closed unless an exact commit diff is Attention orchestration only.

This is deliberately a narrow exception, not a general CI path policy. In the
seven unrelated Host workflows only the literal guard below and known job
conditions may differ; removing that wiring must leave identical bytes. The
normal hardware, driver, oracle and upstream-source triggers remain intact.
The report in stdout records both commit IDs and every changed path, including
when the answer is to run the full suite. No worktree content is classified.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


PROJECT = "chisel/continuous_prefill/"
LIVE_GATE = PROJECT + "scripts/host_bf16_attention_block_live_gate.py"
ATTENTION_ONLY_PATHS = frozenset({
    PROJECT + "scripts/run_host_bf16_attention_block_fresh_gate.py",
    PROJECT + "scripts/host_bf16_attention_block_build_artifact.py",
    PROJECT + "tests/test_host_bf16_attention_block_fresh_gate.py",
    PROJECT + "tests/test_host_bf16_attention_block_build_artifact.py",
    PROJECT + "tests/test_host_bf16_attention_block_live_gate.py",
    PROJECT + "tests/test_host_bf16_attention_block_ci.py",
    PROJECT + "tests/test_host_bf16_attention_block_split_ci.py",
    PROJECT + "tests/test_host_bf16_gdn_block_ci.py",
    PROJECT + "tests/test_host_bf16_gdn_fresh_gate.py",
    ".github/workflows/host-bf16-attention-block.yml",
    ".github/scripts/host_attention_block_ci_scope.py",
    ".github/scripts/tests/test_host_attention_block_ci_scope.py",
    ".github/scripts/verify_attention_block_split.py",
    ".github/scripts/tests/test_attention_block_split_acceptance.py",
    "doc/U00_2_HOST_ATTENTION_SPLIT_CI_20261010_CN.md",
    "doc/block_checklist.yaml",
    "reports/execution/U00_2_HOST_ATTENTION_SPLIT_CI_20261010/summary.json",
})

# These literals are also the insertion contract for the workflow editor. Do
# not accept arbitrary text merely because it is between the marker comments.
SCOPE_JOB_BLOCK = """  # BEGIN HOST_ATTENTION_BLOCK_CI_SCOPE
  host-attention-scope:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    outputs:
      run_full: ${{ steps.classify.outputs.run_full }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: '${{ github.sha }}'
          fetch-depth: 0
      - name: Classify exact Attention orchestration diff
        id: classify
        env:
          BASE_SHA: ${{ github.event_name == 'push' && github.event.before || '' }}
          HEAD_SHA: ${{ github.sha }}
        run: |
          python3 .github/scripts/host_attention_block_ci_scope.py --base "$BASE_SHA" --head "$HEAD_SHA" --github-output "$GITHUB_OUTPUT"
  # END HOST_ATTENTION_BLOCK_CI_SCOPE
"""
ROOT_JOB_GUARD = """    needs: host-attention-scope
    if: ${{ always() && (needs.host-attention-scope.result != 'success' || needs.host-attention-scope.outputs.run_full != 'false') }}
"""
ACCEPTANCE_IF = "    if: ${{ always() && needs.build.result != 'skipped' }}\n"

# Only dependency-free roots need the new guard. Their existing descendants
# skip normally, except the three acceptance jobs whose original always()
# conditions need the single exact replacement above.
WORKFLOW_ROOTS = {
    ".github/workflows/host-bf16-v.yml": (
        "fresh-official-actual-Host-V", "legacy-real2-build",
        "fresh-official-actual-Host-QKV-representative",
    ),
    ".github/workflows/host-bf16-qkv-rope.yml": ("representative-chain",),
    ".github/workflows/host-bf16-attention-core.yml": ("representative-attention-core",),
    ".github/workflows/host-bf16-gdn.yml": ("build",),
    ".github/workflows/host-bf16-gdn-core.yml": ("build",),
    ".github/workflows/host-bf16-gdn-block.yml": ("build",),
    ".github/workflows/chisel-continuous-prefill.yml": ("continuous",),
}
WORKFLOW_ACCEPTANCE = {
    ".github/workflows/host-bf16-gdn.yml": "dense-conv-v1-acceptance",
    ".github/workflows/host-bf16-gdn-core.yml": "core-only-acceptance",
    ".github/workflows/host-bf16-gdn-block.yml": "block-acceptance",
}


class ScopeError(ValueError):
    """An input cannot prove that the narrow skip exception applies."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScopeError(message)


def normalize_workflow(path: str, content: bytes) -> bytes:
    """Remove only the complete literal wiring; preserve everything else."""
    text = content.decode("utf-8")
    require(text.count("\njobs:\n") == 1, "unknown workflow jobs layout: " + path)
    before, jobs = text.split("\njobs:\n", 1)
    guarded = jobs.startswith(SCOPE_JOB_BLOCK)
    if guarded:
        jobs = jobs[len(SCOPE_JOB_BLOCK):]
    require("HOST_ATTENTION_BLOCK_CI_SCOPE" not in before + jobs,
            "nonliteral or misplaced workflow guard: " + path)
    headers = list(re.finditer(r"(?m)^  ([A-Za-z0-9_-]+):\n", jobs))
    names = [match.group(1) for match in headers]
    require(len(names) == len(set(names)), "duplicate workflow jobs: " + path)
    require(all(name in names for name in WORKFLOW_ROOTS[path]),
            "missing known workflow root: " + path)
    acceptance = WORKFLOW_ACCEPTANCE.get(path)
    require(acceptance is None or acceptance in names, "missing workflow acceptance: " + path)
    pieces = [jobs[:headers[0].start()]]
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(jobs)
        block = jobs[header.start():end]
        name = header.group(1)
        title = header.group(0)
        if name in WORKFLOW_ROOTS[path] and guarded:
            require(block.startswith(title + ROOT_JOB_GUARD), "nonliteral root guard: " + name)
            block = title + block[len(title + ROOT_JOB_GUARD):]
        if name == acceptance and guarded:
            require(block.count(ACCEPTANCE_IF) == 1, "nonliteral acceptance guard: " + name)
            block = block.replace(ACCEPTANCE_IF, "    if: always()\n", 1)
        pieces.append(block)
    restored = before + "\njobs:\n" + "".join(pieces)
    require("host-attention-scope" not in restored and ACCEPTANCE_IF not in restored,
            "unexpected workflow scope wiring: " + path)
    return restored.encode("utf-8")


def normalize_live_gate(content: bytes) -> bytes:
    """Only the agreed 3600 -> 10800 process budget line may differ."""
    lines = [
        ("    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= "
         + str(limit) + ", 'bounded actual timeout required')\n").encode("ascii")
        for limit in (3600, 10800)
    ]
    require(sum(content.count(line) for line in lines) == 1, "unrecognized live-gate timeout API")
    return content.replace(lines[1], lines[0])


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True,
        timeout=30, env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0"},
    )
    require(result.returncode == 0, "git could not read the exact commit diff")
    return result.stdout


def validate_commit(repo: Path, value: str, label: str) -> None:
    require(isinstance(value, str) and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value)
            and set(value) != {"0"}, label + " must be a nonzero full commit SHA")
    require(git(repo, "rev-parse", "--verify", value + "^{commit}").decode("ascii").strip() == value,
            label + " is not an available exact commit")


def changed_files(repo: Path, base: str, head: str) -> list[tuple[str, str, str, str]]:
    raw = git(repo, "diff", "--raw", "-z", "--no-abbrev", "--no-renames", "--no-ext-diff", "--no-textconv",
              base, head, "--")
    if not raw:
        return []
    fields = raw.split(b"\0")
    require(fields[-1] == b"" and len(fields) % 2 == 1, "malformed git path list")
    changes = []
    for index in range(0, len(fields) - 1, 2):
        metadata = fields[index].decode("ascii").split()
        require(len(metadata) == 5 and re.fullmatch(r":[0-7]{6}", metadata[0])
                and re.fullmatch(r"[0-7]{6}", metadata[1])
                and all(re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value)
                        for value in metadata[2:4]), "malformed git change metadata")
        path = fields[index + 1].decode("utf-8")
        require(path and not any(ord(char) < 32 or ord(char) == 127 for char in path),
                "malformed git changed path")
        changes.append((path, metadata[4], metadata[0][1:], metadata[1]))
    require(len(changes) == len({row[0] for row in changes}), "duplicate git changed paths")
    return changes


def classify(repo: Path, base: str, head: str) -> dict:
    report = {"run_full": True, "base": base, "head": head, "changed_paths": [], "reason": "unclassified"}
    try:
        validate_commit(repo, base, "base")
        validate_commit(repo, head, "head")
        changes = changed_files(repo, base, head)
        report["changed_paths"] = [row[0] for row in changes]
        require(changes, "empty diff does not establish Attention-only work")
        for path, status, old_mode, new_mode in changes:
            require(status in {"A", "M"} and new_mode in {"100644", "100755"}
                    and (old_mode == "000000" if status == "A" else old_mode == new_mode),
                    "deletion, rename, mode or file-type change: " + path)
            if path in ATTENTION_ONLY_PATHS:
                continue
            require(status == "M", "unknown added path: " + path)
            require(path in WORKFLOW_ROOTS or path == LIVE_GATE, "outside Attention orchestration: " + path)
            old = git(repo, "show", base + ":" + path)
            new = git(repo, "show", head + ":" + path)
            if path in WORKFLOW_ROOTS:
                require(normalize_workflow(path, old) == normalize_workflow(path, new),
                        "unrelated workflow body changed: " + path)
            else:
                require(normalize_live_gate(old) == normalize_live_gate(new),
                        "live admission changed beyond timeout API: " + path)
        report.update(run_full=False, reason="only explicit Attention orchestration paths and exact scope wiring changed")
    except Exception as error:
        report["reason"] = str(error) or type(error).__name__
    return report


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ScopeError("malformed CLI: " + message)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    output = os.environ.get("GITHUB_OUTPUT")
    # Preserve a valid output destination even if a different argument is bad.
    if argv.count("--github-output") == 1:
        index = argv.index("--github-output")
        if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            output = argv[index + 1]
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--github-output", default=output)
    try:
        names = [arg.split("=", 1)[0] for arg in argv if arg.startswith("--")]
        require(len(names) == len(set(names)), "malformed CLI: duplicate option")
        args = parser.parse_args(argv)
        output = args.github_output
        report = classify(Path.cwd(), args.base, args.head)
    except Exception as error:
        report = {"run_full": True, "base": None, "head": None, "changed_paths": [], "reason": str(error)}
    status = 0
    if output:
        try:
            with Path(output).open("a", encoding="utf-8") as stream:
                stream.write("run_full=" + str(report["run_full"]).lower() + "\n")
        except OSError as error:
            report.update(run_full=True, reason="cannot write GitHub output: " + str(error))
            status = 1
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
