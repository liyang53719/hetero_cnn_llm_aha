#!/usr/bin/env python3
"""Frozen Down composition, actual full-source typecheck, bounded Host CHIRRTL.

Only actual HostBlockCommands and its metadata readers are elaborated. The
complete actual HostBlockTop/Collection and QwenOwnerKernel are typechecked.
No complete top elaboration, RTL, simulator, EDA, download or arithmetic claim.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, re, subprocess, sys, time

sys.dont_write_bytecode = True
TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
DOWN = TASK.parent / "transposed_down"
COMMIT = "825caff3a6c618419c49c7da452e009ce86ae8b5"
PREFIX = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
PATCH = "candidates/qwen2_resident_matrix/transposed_host/host_workspace.patch"
HARDFLOAT = "c1105e6ac6a0dd90fc80893efc4830ab609005d3"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def frozen(path):
    return subprocess.check_output(["git", "show", COMMIT + ":" + path], cwd=ROOT)


def compose(out):
    down = module("host_down_compose", DOWN / "check_frontend.py")
    paths, pins = down.compose(out)
    if pins != json.loads((DOWN / "source_pins.json").read_text()):
        raise ValueError("unchanged Down composition identity drift")
    data = (ROOT / PATCH).read_bytes()
    patch = out / "patch_host.patch"
    patch.write_bytes(data)
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=out, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=out, check=True)
    pins["patches"][PATCH] = sha(data)
    pins["patched_sources"] = {p: sha((out / p).read_bytes()) for p in paths}
    pins["composition_helpers"] = {
        str(p.relative_to(ROOT)): sha(p.read_bytes())
        for p in (DOWN / "check_frontend.py", DOWN / "source_pins.json",
                  TASK.parent / "transposed_seed/check_frontend.py",
                  TASK.parent / "transposed_seed/source_pins.json")}
    return paths, pins


def make_baseline(source):
    # Same actual frozen parser, same desiredName; only the Scala class name
    # differs to compile it alongside the candidate in one bounded javac slot.
    original = frozen(PREFIX + "HostBlockCommands.scala").decode()
    if original.count("class HostBlockCommands(") != 1:
        raise ValueError("baseline declaration drift")
    original = original.replace("class HostBlockCommands(", "class HostBlockCommandsBaseline(", 1)
    marker = ") extends Module {\n"
    if original.count(marker) != 1:
        raise ValueError("baseline module body drift")
    original = original.replace(marker, marker + '  override def desiredName = "HostBlockCommands"\n', 1)
    path = source / "baseline/HostBlockCommandsBaseline.scala"
    path.parent.mkdir(parents=True)
    path.write_text(original)
    return path


def register_inventory(fir):
    """Count exact nested FIRRTL register types, including Vecs of bundles."""
    def bits(typ):
        tokens = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|\d+|[<>{}\[\]:,]", typ)
        index = 0

        def parse():
            nonlocal index
            if tokens[index] == "{":
                index += 1
                total = 0
                while tokens[index] != "}":
                    if tokens[index] == "flip":
                        index += 1
                    index += 1  # field name
                    if tokens[index] != ":":
                        raise ValueError("malformed register field")
                    index += 1
                    total += parse()
                    if tokens[index] == ",":
                        index += 1
                index += 1
            else:
                kind = tokens[index]
                index += 1
                if kind in ("UInt", "SInt"):
                    if tokens[index] != "<" or tokens[index + 2] != ">":
                        raise ValueError("unknown register width")
                    total = int(tokens[index + 1])
                    index += 3
                elif kind in ("Clock", "Reset", "AsyncReset"):
                    total = 1
                else:
                    raise ValueError("unsupported register type: " + kind)
            while index < len(tokens) and tokens[index] == "[":
                if tokens[index + 2] != "]":
                    raise ValueError("malformed register vector")
                total *= int(tokens[index + 1])
                index += 3
            return total

        result = parse()
        if index != len(tokens):
            raise ValueError("trailing register type tokens")
        return result

    modules = re.finditer(r"^  module (\w+) :.*?(?=^  (?:extmodule|module) |\Z)", fir, re.M | re.S)
    return {m.group(1): {name: {"bits": bits(typ), "type": typ}
                        for name, typ in re.findall(r"^\s*reg(?:reset)? (\w+) : (.*?), clock", m.group(0), re.M)}
            for m in modules}


def audit(directory, helper):
    report = {"default_off_ir": {}, "host_launch_bits": 833,
              "enabled_workspace_bits": 173, "public_launch_extended": False,
              "top_elaborated": False, "rtl_generated": False,
              "hardware_arithmetic_executed": False, "generated_chirrtl": {},
              "commands_register_inventory": {},
              "added_combinational_logic": {
                  "commands": "workspace address subtract/add/compare, M/N/K and extent admission, permission masks and lease validity",
                  "host_top_source_only": "composite cmd/owner/hub/DMA poison OR plus valid/ready gates; top not elaborated",
                  "area_timing_measured": False, "zero_register_delta_is_not_zero_area": True}}
    for profile in ("ordinary", "qkv"):
        before = helper.normalized_chirrtl((directory / (profile + "_baseline.fir")).read_text())
        after = helper.normalized_chirrtl((directory / (profile + "_disabled.fir")).read_text())
        if before != after:
            raise ValueError("default-off normalized CHIRRTL drift: " + profile)
        report["default_off_ir"][profile] = {"equal": True, "sha256": sha(after.encode())}
        enabled = helper.normalized_chirrtl((directory / (profile + "_enabled.fir")).read_text())
        if "prefixWorkspace : { valid : UInt<1>, base : UInt<64>, extent : UInt<64>, generation : UInt<32>, splitK : UInt<12>}" not in enabled:
            raise ValueError("exact enabled typed workspace ABI missing")
        if "prefixWorkspace" in after:
            raise ValueError("default-off workspace IO leakage")
        if re.search(r"^\s*(?:s|c)mem ", enabled, re.M):
            raise ValueError("unexpected memory allocation in bounded Host parser")
        if "inst owner of" in enabled or "inst dma of" in enabled:
            raise ValueError("complete owner or DMA was elaborated")
        before_regs = register_inventory(after)
        after_regs = register_inventory(enabled)
        if before_regs != after_regs:
            raise ValueError("enabled Commands register inventory drift: " + profile)
        if after_regs["HostBlockCommands"]["cfg"]["bits"] != 833:
            raise ValueError("launch snapshot register ABI drift")
        report["commands_register_inventory"][profile] = {
            "enabled_equals_disabled": True, "added_registers": 0, "added_register_bits": 0,
            "cfg_reused_bits": 833,
            "by_module": {name: {"register_count": len(regs),
                                  "total_bits": sum(r["bits"] for r in regs.values()),
                                  "registers": regs} for name, regs in after_regs.items()}}
    for path in sorted(directory.glob("*.fir")):
        report["generated_chirrtl"][path.name] = {"sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}
    return report


def audit_existing(previous, out):
    if out.exists():
        raise ValueError("use a new evidence directory")
    original = json.loads((previous / "summary.json").read_text())
    if len(original["commands"]) != 2 or any(c["exit_code"] != 0 for c in original["commands"]):
        raise ValueError("both full-source compilation and bounded emission must have succeeded")
    if not original["full_host_top_typechecked"] or not original["full_qwen_owner_kernel_typechecked"]:
        raise ValueError("actual full-source typecheck incomplete")
    if original["source_pins"] != json.loads((TASK / "source_pins.json").read_text()):
        raise ValueError("source pins changed after compilation")
    for path, digest in original["source_sha256"].items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError("compiled source changed: " + path)
    for path, digest in original["source_pins"]["patches"].items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError("composed patch changed: " + path)
    for name, identity in original["generated_chirrtl"].items():
        if sha((previous / "chirrtl" / name).read_bytes()) != identity["sha256"]:
            raise ValueError("generated CHIRRTL changed: " + name)
    helper = module("host_reaudit_helper", ROOT / "scripts/check_matrix_interface_candidate.py")
    report = audit(previous / "chirrtl", helper)
    report.update(status="PASS_REAUDIT_HOST_WORKSPACE_FRONTEND", original_evidence=str(previous.relative_to(ROOT)),
                  original_summary_sha256=sha((previous / "summary.json").read_bytes()),
                  original_compiled_source_sha256=original["source_sha256"],
                  source_pins=original["source_pins"], auditor_sha256=sha(Path(__file__).read_bytes()),
                  full_host_top_typechecked=True, full_qwen_owner_kernel_typechecked=True,
                  commands_reexecuted=[])
    out.mkdir(parents=True)
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def run(out, cache, hardfloat, validate_only=False):
    if out.exists():
        raise ValueError("use a new evidence directory")
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {"status": "STARTED", "source_commit": COMMIT, "commands": [],
              "full_host_top_typechecked": False, "full_qwen_owner_kernel_typechecked": False,
              "top_elaborated": False, "rtl_generated": False, "hardware_arithmetic_executed": False,
              "java_budget": {"active_processors": 1, "heap_mib": 1024, "timeout_seconds_per_command": 180}}

    def save():
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")

    def command(argv, name):
        t = time.monotonic()
        entry = {"argv": argv, "log": name, "exit_code": None, "status": "RUNNING"}
        report["commands"].append(entry)
        save()
        with (out / name).open("w") as log:
            result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        entry.update(exit_code=result.returncode, wall_seconds=time.monotonic() - t, status="FINISHED")
        save()
        if result.returncode:
            raise RuntimeError("command failed: " + name)

    try:
        source = out / "source"
        source.mkdir()
        paths, pins = compose(source)
        if pins != json.loads((TASK / "source_pins.json").read_text()):
            raise ValueError("frozen source/patch/postimage identity drift")
        report["source_pins"] = pins
        route = json.loads(frozen("candidates/qwen2_resident_matrix/transposed_route/manifest.json"))
        helper = module("host_frontend_helper", ROOT / "scripts/check_matrix_interface_candidate.py")
        if sha((ROOT / "scripts/check_matrix_interface_candidate.py").read_bytes()) != route["dependencies"]["scripts/check_matrix_interface_candidate.py"]:
            raise ValueError("dependency helper drift")
        lock_path = ROOT / "chisel/rope_hardware_oracle/maven-lock.json"
        if sha(lock_path.read_bytes()) != route["maven_lock_sha256"]:
            raise ValueError("Maven lock drift")
        dependencies = helper.dependency_paths(json.loads(lock_path.read_text())["artifacts"])
        if len(dependencies) != 87:
            raise ValueError("dependency count drift")
        # Validate the entire cache before calling its preparer; no download.
        for path, digest in dependencies.items():
            if sha((cache / path).read_bytes()) != digest:
                raise ValueError("cache dependency identity drift: " + str(path))
        cp, plugin, receipt = helper.prepare_dependencies(ROOT, cache, route)
        (out / "dependency_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        report["dependency_receipt_sha256"] = sha((out / "dependency_receipt.json").read_bytes())
        if subprocess.check_output(["git", "-C", str(hardfloat), "rev-parse", "HEAD"], text=True).strip() != HARDFLOAT:
            raise ValueError("HardFloat head drift")
        hpaths = subprocess.check_output(["git", "-C", str(hardfloat), "ls-tree", "-r", "--name-only", HARDFLOAT,
                                          "--", "hardfloat/src/main/scala"], text=True).splitlines()
        hpaths = [p for p in hpaths if p.endswith(".scala")]
        if len(hpaths) != 20:
            raise ValueError("HardFloat source count drift")
        sources = [source / p for p in paths if p.endswith(".scala")]
        for path in hpaths:
            dest = source / "pinned_hardfloat" / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(subprocess.check_output(["git", "-C", str(hardfloat), "show", HARDFLOAT + ":" + path]))
            sources.append(dest)
        sources += [make_baseline(source), TASK / "HostWorkspaceElaboration.scala"]
        report["source_sha256"] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sources}
        report["task_source_sha256"] = {p.name: sha(p.read_bytes()) for p in TASK.iterdir() if p.is_file()}
        report["hardfloat_commit"] = HARDFLOAT
        report["typechecked_source_count"] = len(sources)
        if validate_only:
            report["status"] = "PASS_SOURCE_AND_CACHE_VALIDATION_ONLY"
            save()
            return report
        java = ["java", "-Xmx1024m", "-XX:ActiveProcessorCount=1"]
        classes = out / "classes"
        classes.mkdir()
        command(java + ["-cp", cp, "scala.tools.nsc.Main", "-classpath", cp, "-Xplugin:" + str(plugin),
                        "-d", str(classes)] + list(map(str, sources)), "compile.log")
        report["full_host_top_typechecked"] = True
        report["full_qwen_owner_kernel_typechecked"] = True
        command(java + ["-cp", str(classes) + ":" + cp, "heteronpu.continuous.HostWorkspaceElaboration", str(out / "chirrtl")], "elaboration.log")
        report.update(audit(out / "chirrtl", helper))
        for path in sources:
            if sha(path.read_bytes()) != report["source_sha256"][str(path.relative_to(ROOT))]:
                raise ValueError("source changed during compile")
        report["status"] = "PASS_HOST_WORKSPACE_FULL_TYPECHECK_AND_FRONTEND_ONLY"
        report["wall_seconds"] = time.monotonic() - start
        save()
        return report
    except Exception as error:
        report.update(status="FAILED", error=str(error), wall_seconds=time.monotonic() - start)
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--hardfloat", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--audit-existing", type=Path)
    args = parser.parse_args()
    if args.audit_existing:
        result = audit_existing(args.audit_existing.resolve(), args.out.resolve())
    else:
        if args.cache is None or args.hardfloat is None:
            parser.error("--cache and --hardfloat required for source/typecheck mode")
        result = run(args.out.resolve(), args.cache.resolve(), args.hardfloat.resolve(), args.validate_only)
    print(json.dumps({"status": result["status"]}))
