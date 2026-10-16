#!/usr/bin/env python3
"""Bounded actual DownOwner frontend/Verilator unit, never full Matrix.

Invoking this runner DOES resolve dependencies, compile, elaborate and simulate.
Preparation and review alone must not invoke run(). Only hashes and compact
structural/test receipts are written to the four-file evidence allowlist.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.raw_kv.run_unit import run_group
from candidates.qwen2_resident_matrix.raw_kv_parent.prepare_unit import prepare


TOTAL_SECONDS = 600
STAGE_SECONDS = {"dependencies": 120, "compile": 120, "elaborate": 60,
                 "parent_rtl_unit": 240}
SCENARIOS = ("default_off_dense", "enabled_dense_drain", "retained_a_window",
             "raw_fault_retirement")
EVIDENCE_FILES = frozenset({"summary.json", "source-sha256.json",
                          "dependency-sha256.json", "rtl-sha256.json"})
DIAGNOSTIC_BYTES = 4096
DIAGNOSTIC_WINDOW_BYTES = 128 * 1024
CPP_BUILD_MAKEFLAGS = "-j2 VM_PARALLEL_BUILDS=1"
LOCK_PATH = "chisel/rope_hardware_oracle/maven-lock.json"
WORKFLOW_PATH = ".github/workflows/raw-kv-parent-unit.yml"
OWNER = "TransposedDenseDownOwner"
BANKS = "TransposedDownDenseBanks"
QUEUE_FIELDS = ("a:UInt<16>[16]", "b:UInt<16>[256]", "context:UInt<3>",
                "clear:UInt<1>", "last:UInt<1>", "finish:UInt<1>", "emit:UInt<1>")
BUILD_PROPERTIES = "sbt.version=1.10.2\n"
BUILD_SBT = '''ThisBuild / scalaVersion := "2.13.16"
libraryDependencies ++= Seq("org.chipsalliance" %% "chisel" % "6.7.0", "edu.berkeley.cs" %% "chiseltest" % "6.0.0" % Test, "org.scalatest" %% "scalatest" % "3.2.19" % Test)
addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full)
scalacOptions += "-language:reflectiveCalls"
Test / parallelExecution := false
lazy val writeDependencyPaths = taskKey[Unit]("Local dependency audit input, including compiler plugin")
writeDependencyPaths := {
  val jars = ((Test / externalDependencyClasspath).value.files ++ scalaInstance.value.allJars ++ update.value.allFiles).filter(_.getName.endsWith(".jar")).distinct
  IO.write(file("dependency-paths.txt"), jars.map(_.getAbsolutePath).sorted.mkString("\\n"))
}
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def _diagnostic_text(text, prefixes=(), limit=320):
    """Redact paths and large values before any failure text leaves the runner."""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = "".join(c if c.isprintable() else " " for c in text)
    if re.search(r"(?i)\b(?:raw[_ -]?tensor|weights?|payload|stimuli|trace|dump)\s*[:=]", text):
        return "[payload/dump diagnostic omitted]"
    if len(re.findall(r"\b(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?)\b", text)) > 12:
        return "[numeric bulk diagnostic omitted]"
    for prefix, label in sorted(prefixes, key=lambda item: len(str(item[0])), reverse=True):
        text = text.replace(str(prefix), label)
    text = re.sub(r"(?:https?|file)://[^\s]+", "<URL>", text)
    text = re.sub(r"(?i)\b(?:authorization|proxy-authorization)\s*[:=]\s*.*", "authorization=<REDACTED>", text)
    text = re.sub(r"(?i)\b(?:bearer|token|access[_-]?token|refresh[_-]?token|api[_-]?key|password|passwd|secret)\b[\"']?\s*(?:[:=]\s*|\s+)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)", "credential=<REDACTED>", text)
    text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]+|gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "<TOKEN>", text)
    # Keep source filenames/line numbers but suppress other absolute prefixes.
    text = re.sub(r"(?<![\w>])/(?:[^\s/:,()]+/)+([^\s/:,()]+)", r"<PATH>/\1", text)
    text = re.sub(r"\b\d+'[hHbBdD][0-9a-fA-F_xXzZ]+\b", "<VALUE>", text)
    text = re.sub(r"\b0[xX][0-9a-fA-F]+\b|\b[0-9a-fA-F]{16,}\b|\b\d{6,}\b", "<VALUE>", text)
    text = re.sub(r"(?<!\w)[A-Za-z0-9_+/=-]{40,}(?!\w)", "<LONG TOKEN>", text)
    # JSON/Scala collection formatting can otherwise expose payload vectors.
    text = re.sub(r"\b(?:Array|Vector|List|Seq|Vec)\s*\(.*", "<COLLECTION OMITTED>", text)
    return text.strip().encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def failure_diagnostics(log_path, *, prefixes=(), stage="runner", error=""):
    """At most 4 KiB of first/last selected errors; never raw log tails.

    Only bounded head/tail windows are read. Compiler source echoes, numeric
    bulk data, raw-tensor/weight/payload dumps and ordinary log lines are
    excluded. The unchanged full log remains local and is never an artifact.
    """
    lines = []
    if log_path is not None and Path(log_path).is_file():
        with Path(log_path).open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(0)
            first = stream.read(DIAGNOSTIC_WINDOW_BYTES)
            if size > DIAGNOSTIC_WINDOW_BYTES:
                first = first.rsplit(b"\n", 1)[0]
            windows = [first]
            if size > DIAGNOSTIC_WINDOW_BYTES:
                stream.seek(max(DIAGNOSTIC_WINDOW_BYTES, size - DIAGNOSTIC_WINDOW_BYTES))
                windows.append(stream.read(DIAGNOSTIC_WINDOW_BYTES).split(b"\n", 1)[-1])
        for window in windows:
            for raw in window.decode("utf-8", errors="replace").splitlines():
                # Skip giant lines, data collections and explicit dump labels,
                # even when a misleading error prefix has been added.
                if len(raw.encode("utf-8")) > 1024:
                    continue
                clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw).strip()
                if re.search(r"(?i)\b(?:raw[_ -]?tensor|weights?|payload|stimuli|trace|dump)\s*[:=]", clean):
                    continue
                if re.search(r"\b(?:Array|Vector|List|Seq|Vec)\s*\(", clean):
                    continue
                if len(re.findall(r"\b(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?)\b", clean)) > 12:
                    continue
                # Select diagnostic messages, not source lines printed by scalac.
                selected = (
                    re.match(r"\[error\]\s+.*\.scala:\d+(?::\d+)?:\s+\S", clean)
                    or re.match(r"\[(?:error|info)\]\s+.*(?:\*\*\* (?:FAILED|ABORTED) \*\*\*|Tests?:.*failed|TESTS? FAILED)", clean)
                    or re.match(r"\[error\]\s+\([^)]*\)\s+.*(?:failed|Exception|Error)", clean)
                    or re.match(r"(?:\[(?:error|info)\]\s+)?(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:Exception|Error):", clean)
                    or re.match(r"(?:\[(?:error|info)\]\s+)?(?:Assertion failed|assertion failed|.*(?:did not equal|was not equal to|timed out|Timeout))\b", clean)
                    or re.match(r"%Error(?:-[\w]+)?:", clean)
                )
                if selected:
                    sanitized = _diagnostic_text(clean, prefixes)
                    if sanitized and (not lines or sanitized != lines[-1]):
                        lines.append(sanitized)
    chosen = lines if len(lines) <= 10 else lines[:5] + ["[intermediate diagnostic lines omitted]"] + lines[-5:]
    header = "[parent-unit failure: " + _diagnostic_text(stage, prefixes, 64) + "]"
    message = _diagnostic_text(error, prefixes, 512)
    result = "\n".join([header, "[runner] " + message] + (chosen or ["[no selected compiler/test failure lines in bounded log windows]"]))
    return result.encode("utf-8")[:DIAGNOSTIC_BYTES].decode("utf-8", errors="ignore")


def progress_receipt(log_path):
    """Fixed markers only; no arbitrary log text, payloads or paths escape.

    A case_begin without sim_ready locates a timeout before the test callback
    (lowering, C++ build or simulator startup); it does not prove C++ was slow.
    Bounded head/tail sampling is disclosed, so absence is not proof of failure.
    """
    receipt = {"sampling": "first_last_128KiB", "events": [], "last_cycle": {}}
    path = Path(log_path)
    if not path.is_file():
        return receipt
    with path.open("rb") as stream:
        size = stream.seek(0, os.SEEK_END)
        stream.seek(0)
        windows = [stream.read(DIAGNOSTIC_WINDOW_BYTES)]
        if size > DIAGNOSTIC_WINDOW_BYTES:
            windows[0] = windows[0].rsplit(b"\n", 1)[0]
            stream.seek(max(DIAGNOSTIC_WINDOW_BYTES, size - DIAGNOSTIC_WINDOW_BYTES))
            windows.append(stream.read(DIAGNOSTIC_WINDOW_BYTES).split(b"\n", 1)[-1])
    for window in windows:
        for line in window.splitlines():
            if len(line) > 160:
                continue
            match = re.fullmatch(rb"(?:\[info\] )?PARENT_PROGRESS (case_begin|sim_ready|scenario_begin|scenario_done|cycle) ([a-z_]+) ([0-9]{1,5})", line)
            if not match:
                continue
            event, scenario, cycle = (part.decode("ascii") for part in match.groups())
            if scenario not in SCENARIOS or int(cycle) > 30000:
                continue
            if event == "cycle":
                if int(cycle) % 1024 == 0:
                    receipt["last_cycle"][scenario] = max(int(cycle), receipt["last_cycle"].get(scenario, 0))
            elif int(cycle) == 0:
                item = {"event": event, "scenario": scenario}
                if item not in receipt["events"]:
                    receipt["events"].append(item)
    return receipt


def build_inventory(project):
    """Counts only within the two known test directories; never read contents."""
    cases = {
        "raw_off": "the_actual_composed_TransposedDenseDownOwner_raw_KV_loan_should_complete_ordinary_Dense_with_the_raw_feature_absent",
        "raw_on": "the_actual_composed_TransposedDenseDownOwner_raw_KV_loan_should_retire_real_parent_work_before_loans_and_preserve_poisoned_raw_debt",
    }
    result = {}
    base = Path(project) / "test_run_dir"
    for label, directory in cases.items():
        root = base / directory
        counts = {"cpp": 0, "object": 0, "executable": 0}
        result[label] = counts
        if base.is_symlink() or root.is_symlink() or not root.is_dir():
            continue
        for current, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(current) / name).is_symlink()]
            for name in names:
                path = Path(current) / name
                if path.is_symlink() or not path.is_file():
                    continue
                if name.endswith(".cpp"):
                    counts["cpp"] += 1
                elif name.endswith(".o"):
                    counts["object"] += 1
                elif name == "VTransposedDenseDownOwner" and path.stat().st_mode & 0o111:
                    counts["executable"] += 1
    return result


def _modules(text):
    headers = list(re.finditer(r"^\s*(?:(?:public|private)\s+)?(module|extmodule|intmodule)\s+(\w+)\s*:", text, re.M))
    need(headers, "no CHIRRTL module declarations")
    result = {}
    for i, match in enumerate(headers):
        kind, name = match.groups()
        need(kind == "module", "external or intrinsic module outside parent unit scope")
        need(name not in result, "duplicate CHIRRTL module")
        result[name] = text[match.end():headers[i + 1].start() if i + 1 < len(headers) else len(text)]
    return result


def memory_audit_parent(text):
    """Allow the original 32 SRAMs and one exact existing operand Queue only.

    This is an audit of emitted CHIRRTL, not a synthesis/area claim. Matrix
    bundle names occur in IO types, but no Matrix/HardFloat arithmetic module
    or black box may be declared or instantiated.
    """
    modules = _modules(text)
    need(OWNER in modules and BANKS in modules, "actual parent/bank modules missing")
    queue_names = [n for n in modules if re.fullmatch(r"Queue(?:\d+_MatrixStreamStep)?(?:_\d+)?", n)]
    need(len(queue_names) == 1 and set(modules) == {OWNER, BANKS, queue_names[0]},
         "unexpected module: only actual DownOwner, banks and operand Queue allowed")
    queue = queue_names[0]
    instances = {name: re.findall(r"^\s*inst\s+(\w+)\s+of\s+(\w+)\b", body, re.M)
                 for name, body in modules.items()}
    need(sorted(instances[OWNER]) == sorted([("banks", BANKS), ("operands", queue)])
         and not instances[BANKS] and not instances[queue],
         "unexpected module instance or replicated bank/Queue")
    need(re.search(r"^\s*circuit\s+" + OWNER + r"\s*:", text, re.M),
         "actual DownOwner must be circuit top")

    declarations = []
    for module, body in modules.items():
        for line in body.splitlines():
            stripped = line.strip()
            if not re.match(r"(?:[sc]?mem)\b", stripped):
                continue
            match = re.fullmatch(r"(smem|cmem)\s+(\w+)\s*:\s*(.*?)\s*\[(\d+)\](?:\s*,\s*(?:undefined|old|new))?\s*(?:@\[.*\])?", stripped)
            need(match is not None, "unsupported memory declaration")
            kind, name, element, depth = match.groups()
            declarations.append((module, kind, name, re.sub(r"\s+", "", element), int(depth)))
    banks = [m for m in declarations if m[0] == BANKS]
    need(len(banks) == 32 and len({m[2] for m in banks}) == 32,
         "actual CHIRRTL bank count mismatch")
    need(all(m[1] == "smem" and m[3] == "UInt<256>" for m in banks)
         and sorted(m[4] for m in banks) == [160] * 16 + [1376] * 16,
         "actual CHIRRTL bank geometry mismatch")
    for _, _, name, _, _ in banks:
        ports = re.findall(r"^\s*(read|write|rdwr|infer)\s+mport\s+\w+\s*=\s*"
                           + re.escape(name) + r"\[", modules[BANKS], re.M)
        need(sorted(ports) == ["read", "write"], "actual CHIRRTL bank port mismatch")

    other = [m for m in declarations if m[0] != BANKS]
    need(len(other) == 1, "extra or missing operand FIFO memory")
    module, kind, name, element, depth = other[0]
    need(module == queue and kind == "cmem" and name == "ram" and depth == 4,
         "existing operand Queue memory identity/depth mismatch")
    need(element.startswith("{") and element.endswith("}"), "operand Queue must retain original bundle type")
    fields = tuple(element[1:-1].split(","))
    need(fields in (QUEUE_FIELDS, tuple(reversed(QUEUE_FIELDS))), "operand Queue element type mismatch")
    queue_ports = re.findall(r"^\s*(read|write|rdwr|infer)\s+mport\s+\w+\s*=\s*ram\[",
                             modules[queue], re.M)
    # Queue uses Mem.apply for both enqueue and dequeue in Chisel 6.7.0;
    # CHIRRTL may retain inferred directions until FIRRTL lowers those ports.
    need(sorted(queue_ports) in (["read", "write"], ["infer", "write"],
                                 ["infer", "read"], ["infer", "infer"]),
         "operand Queue memory port mismatch")
    return {"sram_memories": 32, "a_banks": 16, "a_depth": 1376, "b_banks": 16,
            "b_depth": 160, "width": 256, "read_ports_per_bank": 1,
            "write_ports_per_bank": 1, "operand_fifo": {"module": queue,
            "memory": "ram", "kind": "cmem", "depth": 4, "element_bits": 4359,
            "type": "MatrixStreamStep", "fields": list(QUEUE_FIELDS), "ports": queue_ports},
            "total_memory_declarations": 33, "module_names": sorted(modules),
            "matrix_or_hardfloat_instantiated": False}


def result_audit(log):
    """Require both ScalaTest cases and each completed behavioral scenario."""
    totals = re.findall(r"Total number of tests run:\s*(\d+)\b", log)
    need(totals == ["2"] and log.count("All tests passed") == 1,
         "missing exact two-test ScalaTest result")
    markers = re.findall(r"^\s*PARENT_SCENARIO_PASS\s+(\w+)\s*$", log, re.M)
    need(sorted(markers) == sorted(SCENARIOS), "missing, duplicate or unexpected parent scenario marker")
    return {"scala_tests": 2, "completed_scenarios": list(SCENARIOS)}


def dependency_audit(path, lock_path):
    """Verify known pinned jars before compile; disclose all other jar hashes.

    The existing lock does not include the prior unit's chiseltest/ScalaTest
    closure. Those unchanged versions are inventoried, never called locked.
    """
    artifacts = json.loads(lock_path.read_text())["artifacts"]
    locked = {}
    for coordinate, sha in artifacts.items():
        if coordinate.endswith(".jar"):
            name = Path(coordinate).name
            need(name not in locked or locked[name] == sha, "ambiguous dependency lock basename")
            locked[name] = sha
    lines = path.read_text().splitlines()
    need(lines and all(lines), "missing resolved dependency inventory")
    paths = sorted({Path(line).resolve() for line in lines})
    names = [p.name for p in paths]
    need(len(names) == len(set(names)), "duplicate resolved dependency basename")
    required = {"chisel_2.13-6.7.0.jar", "chisel-plugin_2.13.16-6.7.0.jar",
                "chiseltest_2.13-6.0.0.jar", "scalatest_2.13-3.2.19.jar",
                "scala-compiler-2.13.16.jar", "scala-library-2.13.16.jar"}
    need(required <= set(names), "required exact toolchain dependency missing from audit")
    hashes = {}
    evidence = []
    for p in paths:
        need(p.is_file() and p.suffix == ".jar", "invalid resolved dependency file")
        sha = digest(p)
        need(p.name not in locked or locked[p.name] == sha, "locked dependency digest mismatch: " + p.name)
        hashes[p] = sha
        evidence.append({"jar": p.name, "sha256": sha, "existing_lock_match": p.name in locked})
    return hashes, sorted(evidence, key=lambda item: item["jar"])


def run(out):
    out = Path(out).resolve()
    need(not out.exists(), "fresh output required")
    out.mkdir(parents=True)
    project = out / "project"
    project.mkdir()
    evidence = out / "evidence"
    evidence.mkdir()
    start = time.monotonic()
    summary = {"status": "STARTED", "scope": "actual DownOwner and existing banks only; external Matrix/DDR/seed test agents; no Matrix/HardFloat arithmetic",
               "stages": [], "total_budget_seconds": TOTAL_SECONDS,
               "stage_budgets_seconds": STAGE_SECONDS, "hardware_performance_measured": False,
               "cpp_build": {"parallel_translation_units": True, "jobs": 2, "optimization": "-O0"}}
    frozen = {}
    dependencies = {}
    original_source_names = set()
    original_parent_files = set()
    original_configuration_names = set()
    workflow_present = False

    def emit(name, value):
        need(name in EVIDENCE_FILES, "non-allowlisted evidence filename")
        data = json.dumps(value, indent=2, sort_keys=True) + "\n"
        need(len(data.encode()) <= 256 * 1024, "evidence file exceeds 256 KiB bound")
        (evidence / name).write_text(data)

    def save():
        emit("summary.json", summary)

    def parent_files():
        return {p for p in HERE.iterdir() if p.is_file() and p.suffix in {".py", ".scala", ".json", ".patch", ".md"}}

    def configuration_files():
        return ({p for p in project.glob("*.sbt") if p.is_file()}
                | {p for p in (project / "project").glob("*")
                   if p.is_file() and p.suffix in {".sbt", ".scala", ".properties"}}
                | {p for p in (project / ".jvmopts", project / ".sbtopts") if p.exists()})

    def assert_frozen():
        for p, sha in frozen.items():
            need(p.is_file() and digest(p) == sha, "frozen source/configuration changed: " + p.name)
        for p, sha in dependencies.items():
            need(p.is_file() and digest(p) == sha, "resolved dependency changed: " + p.name)
        if original_source_names:
            need({str(p.relative_to(project)) for p in (project / "src").rglob("*") if p.is_file()} == original_source_names,
                 "generated compile source set changed")
            need(parent_files() == original_parent_files, "parent candidate source set changed")
            need(configuration_files() == original_configuration_names, "generated build configuration set changed")
            need((ROOT / WORKFLOW_PATH).exists() == workflow_present, "workflow presence changed")

    env = dict(os.environ, MAKEFLAGS=CPP_BUILD_MAKEFLAGS,
               JVM_OPTS="-Xmx2G -Xss4M -XX:ActiveProcessorCount=2",
               SBT_OPTS="-Dsbt.supershell=false -Dsbt.color=false -Dsbt.task.cpus=2")

    def command(name, args):
        assert_frozen()
        # Reserve run_group's TERM grace inside the overall runner budget.
        remaining = TOTAL_SECONDS - (time.monotonic() - start) - 5
        need(remaining > 0, "total 600s runner budget exhausted")
        budget = min(STAGE_SECONDS[name], remaining)
        began = time.monotonic()
        entry = {"name": name, "budget_seconds": budget}
        summary["stages"].append(entry)
        save()
        with (out / (name + ".log")).open("w") as log:
            try:
                rc = run_group(args, cwd=project, env=env, log=log, timeout=budget)
            except BaseException as error:
                entry.update(status="TIMEOUT" if isinstance(error, subprocess.TimeoutExpired) else "INTERRUPTED",
                             seconds=time.monotonic() - began)
                save()
                raise
        entry.update(status="PASS" if rc == 0 else "FAIL", exit_code=rc,
                     seconds=time.monotonic() - began)
        save()
        need(rc == 0, name + " failed; local log retained (not uploaded)")
        assert_frozen()

    def rtl_evidence():
        paths = sorted((project / "test_run_dir").rglob("*.sv")) + sorted((project / "test_run_dir").rglob("*.v"))
        chirrtl = sorted((out / "chirrtl").glob("*.fir"))
        if paths or chirrtl:
            emit("rtl-sha256.json", {str(p.relative_to(out)): digest(p) for p in paths + chirrtl})
        return paths

    try:
        save()
        source = project / "src/main/scala"
        prepared = prepare(source)
        generated = {p.name: digest(p) for p in source.glob("*.scala")}
        need(generated and generated == prepared["generated"], "prepared compile-unit hashes mismatch")
        need(set(p.name for p in source.iterdir()) == set(generated), "unexpected prepared compile-source file")
        test = project / "src/test/scala"
        test.mkdir(parents=True)
        (test / "ParentKvUnit.scala").write_bytes((HERE / "ParentKvUnit.scala").read_bytes())
        (project / "project").mkdir()
        (project / "project/build.properties").write_text(BUILD_PROPERTIES)
        (project / "build.sbt").write_text(BUILD_SBT)

        inputs = prepared["inputs"]
        need(isinstance(inputs, dict) and bool(inputs), "missing prepared source provenance")
        source_hashes = {"repository_inputs": {}, "generated_sources": {}, "generated_configuration": {}}
        for relative, sha in inputs.items():
            p = ROOT / relative
            need(not Path(relative).is_absolute() and ".." not in Path(relative).parts
                 and p.resolve().is_relative_to(ROOT), "source input must be repository relative")
            need(re.fullmatch(r"[0-9a-f]{64}", sha) and p.is_file() and digest(p) == sha,
                 "prepared source input hash mismatch: " + relative)
            frozen[p] = sha
        original_parent_files = parent_files()
        for p in original_parent_files | {HERE.parent / "raw_kv/run_unit.py", ROOT / LOCK_PATH}:
            frozen[p] = digest(p)
        workflow = ROOT / WORKFLOW_PATH
        workflow_present = workflow.exists()
        if workflow_present:
            frozen[workflow] = digest(workflow)
        source_hashes["repository_inputs"] = {str(p.relative_to(ROOT)): sha for p, sha in frozen.items()}
        for p in sorted((project / "src").rglob("*")):
            if p.is_file():
                frozen[p] = digest(p)
                source_hashes["generated_sources"][str(p.relative_to(project))] = frozen[p]
        need(source_hashes["generated_sources"], "no generated compile units")
        original_source_names = set(source_hashes["generated_sources"])
        for p in (project / "build.sbt", project / "project/build.properties"):
            frozen[p] = digest(p)
            source_hashes["generated_configuration"][str(p.relative_to(project))] = frozen[p]
        original_configuration_names = configuration_files()
        # Slices are fingerprints only; never copy source text into evidence.
        if "slices" in prepared:
            slices = prepared["slices"]
            need(isinstance(slices, dict) and all(isinstance(k, str) and isinstance(v, str)
                 and re.fullmatch(r"[0-9a-f]{64}", v) for k, v in slices.items()), "invalid extracted slice hashes")
            source_hashes["extracted_slices"] = slices
        emit("source-sha256.json", source_hashes)
        summary["preparation"] = {"pinned_main_compile_units": len(generated),
                                  "exact_source_slices": len(prepared.get("slices", {})),
                                  "repository_inputs_hashed": len(source_hashes["repository_inputs"])}
        command("dependencies", ["sbt", "update", "writeDependencyPaths"])
        dependencies, dep_evidence = dependency_audit(project / "dependency-paths.txt", ROOT / LOCK_PATH)
        frozen[project / "dependency-paths.txt"] = digest(project / "dependency-paths.txt")
        emit("dependency-sha256.json", dep_evidence)
        summary["dependencies"] = {"jars": len(dep_evidence),
            "existing_lock_matches": sum(d["existing_lock_match"] for d in dep_evidence),
            "unlocked_jar_hashes_disclosed": sum(not d["existing_lock_match"] for d in dep_evidence)}
        command("compile", ["sbt", "Test / compile"])
        command("elaborate", ["sbt", "Test / runMain heteronpu.continuous.ParentKvElaborate " + str(out / "chirrtl")])
        summary["frontend"] = {}
        expected_fir = {"parent_raw0.fir", "parent_raw1.fir"}
        need({p.name for p in (out / "chirrtl").iterdir() if p.is_file()} == expected_fir,
             "unexpected frontend output set")
        for raw in (0, 1):
            name = "parent_raw" + str(raw)
            text = (out / "chirrtl" / (name + ".fir")).read_text()
            summary["frontend"][name] = memory_audit_parent(text)
            modules = _modules(text)
            for module in (OWNER, BANKS):
                need(bool(re.search(r"\brawKv\s*:", modules[module])) == bool(raw),
                     "optional raw port presence mismatch")
        rtl_evidence()
        save()
        command("parent_rtl_unit", ["sbt", "testOnly heteronpu.continuous.ParentKvUnit"])
        summary["tests"] = result_audit((out / "parent_rtl_unit.log").read_text())
        need(rtl_evidence(), "no generated RTL")
        assert_frozen()
        need(time.monotonic() - start <= TOTAL_SECONDS, "total 600s runner budget exhausted")
        summary.update(status="PASS_PARENT_UNIT_ONLY")
    except BaseException as error:
        prefixes = ((project, "<PROJECT>"), (out, "<OUT>"), (ROOT, "<REPO>"))
        stage = summary["stages"][-1]["name"] if summary["stages"] else "prepare"
        diagnostics = failure_diagnostics(out / (stage + ".log"), prefixes=prefixes,
                                          stage=stage, error=str(error))
        summary.update(status="FAIL", error=_diagnostic_text(str(error), prefixes, 512),
                       error_type=type(error).__name__, failure_diagnostics=diagnostics)
        print(diagnostics, flush=True)
        error._parent_unit_diagnostic_reported = True
        raise
    finally:
        summary["progress"] = progress_receipt(out / "parent_rtl_unit.log")
        summary["build_inventory"] = build_inventory(project)
        rtl_evidence()
        summary["wall_seconds"] = time.monotonic() - start
        save()
        need(set(p.name for p in evidence.iterdir()) <= EVIDENCE_FILES, "unexpected evidence artifact")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        print(json.dumps(run(arguments.out), indent=2))
    except (Exception, KeyboardInterrupt) as error:
        # run() already printed its bounded sanitized failure receipt. A raw
        # traceback would reintroduce absolute paths/exception command data.
        if not getattr(error, "_parent_unit_diagnostic_reported", False):
            print(failure_diagnostics(None, prefixes=((arguments.out.resolve(), "<OUT>"), (ROOT, "<REPO>")),
                                      stage="setup/receipt", error=str(error)), flush=True)
        sys.exit(1)
