"""Read-only byte, JSON, AST and in-memory compile validation of this excerpt.

Never imports or executes excerpt code, writes bytecode/output, or runs a child.
Only optional upstream files explicitly supplied on the command line are read.
The package manifest's trusted SHA-256 is necessarily supplied out of band.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys

MANIFEST = "PUBLIC_MANIFEST.json"
ALLOWLIST = "PACKAGE_ALLOWLIST.txt"
PROVENANCE = "SOURCE_PINS.json"
SOURCE_SHA256 = "e0269e0b7c1b13217f51f1263ec3b605bd15c1da234fa4409111e2b167b41add"
REVIEW_SHA256 = "25fa02dd7523bcff1f3312fbe0fa2592da04beb44c1558fae5dc2b240656436b"
COPIED = (
    "overlay/admission.py",
    "overlay/capture/wholeblock.py",
    "overlay/contract/FRAME_ROUTING_POLICY.json",
    "overlay/contract/OP_EVIDENCE_POLICY.json",
    "overlay/fullblock_runtime.py",
    "overlay/integration/interface.py",
    "overlay/integration/runner.py",
    "overlay/observation/fullblock_attention.py",
    "overlay/supervision/SUPPORT_PINS.json",
    "overlay/supervision/ci_support_v3_long.py",
    "overlay/supervision/gate.py",
    "overlay/supervision/supervisor_adapter.py",
    "patches/integration__runner.py.diff",
    "prepare_fullblock.py",
    "source_controls.py",
)
GENERATED = (MANIFEST, ALLOWLIST, PROVENANCE, "README.md", "SUMMARY.json", "static_check.py")
EXPECTED = tuple(sorted(COPIED + GENERATED))
# Construct generic absolute-looking tokens without embedding private locations.
SEP = chr(47)
GENERIC_LITERALS = {
    SEP, SEP + "proc", SEP + "proc" + SEP,
    SEP + "proc" + SEP + "self" + SEP + "maps", SEP + "stat",
    SEP + "root", SEP + "root" + SEP,
    SEP + "usr" + SEP + "bin:" + SEP + "bin",
}
MACHINE_PATH = re.compile(r"/(?:workspace|home|tmp|opt|mnt|Users|private|var/tmp)/|[A-Za-z]:\\")
ROOT_TOKEN = SEP + "root"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def parse_json(raw):
    return json.loads(raw, object_pairs_hook=strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def identity(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def relative_name(name):
    require(type(name) is str and name and "\\" not in name, "invalid relative filename")
    parts = PurePosixPath(name).parts
    require(not name.startswith(SEP) and all(p not in ("", ".", "..") for p in parts)
            and str(PurePosixPath(name)) == name, "noncanonical relative filename")
    return name


def regular_file(path):
    require(stat.S_ISREG(path.lstat().st_mode), "nonregular file")
    require(not path.is_symlink(), "symlink file")
    raw = path.read_bytes()
    require(len(raw) <= 1024 * 1024, "file exceeds static excerpt bound")
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--review-file", type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            "run with isolated, no-site and no-bytecode flags")
    require(sys.version_info[:3] == (3, 12, 14), "use target CPython 3.12.14")
    root = Path(__file__).resolve().parent
    discovered = []
    for path in root.rglob("*"):
        mode = path.lstat().st_mode
        require(not stat.S_ISLNK(mode), "symlink in excerpt")
        if stat.S_ISDIR(mode):
            continue
        require(stat.S_ISREG(mode), "special file in excerpt")
        discovered.append(path.relative_to(root).as_posix())
    require(tuple(sorted(discovered)) == EXPECTED, "exact excerpt inventory mismatch")
    raw = {name: regular_file(root / relative_name(name)) for name in EXPECTED}
    require(sum(map(len, raw.values())) < 1024 * 1024, "excerpt exceeds one MiB")
    require(raw[ALLOWLIST].decode("utf-8").splitlines() == list(EXPECTED), "allowlist mismatch")
    manifest = parse_json(raw[MANIFEST])
    require(manifest["schema"] == "fixed93-public-source-excerpt-manifest-v1", "manifest schema")
    require(manifest["scope"] == "SOURCE excerpt only; no actual authorization", "manifest scope")
    require(set(manifest["files"]) == set(EXPECTED) - {MANIFEST}, "manifest coverage mismatch")
    for name, pin in manifest["files"].items():
        require(pin == identity(raw[name]), "manifest hash mismatch: " + name)
    for name, content in raw.items():
        text = content.decode("utf-8")
        require(not MACHINE_PATH.search(text), "private machine path found: " + name)
        if name.endswith(".json"):
            parse_json(content)
    pins = parse_json(raw[PROVENANCE])
    require(pins["upstream_source_manifest"]["sha256"] == SOURCE_SHA256, "upstream source fingerprint")
    require(pins["upstream_independent_source_materialization_review"]["sha256"] == REVIEW_SHA256,
            "upstream review fingerprint")
    require(set(pins["files"]) == set(COPIED), "copied-file pins coverage")
    for name in COPIED:
        require(pins["files"][name] == identity(raw[name]), "original-byte identity mismatch: " + name)
    python_names = [name for name in EXPECTED if name.endswith(".py")]
    for name in python_names:
        tree = ast.parse(raw[name], filename=name)
        compile(tree, name, "exec", dont_inherit=True, optimize=0)
        if name in COPIED:
            literals = [node.value for node in ast.walk(tree)
                        if isinstance(node, ast.Constant) and type(node.value) is str]
            require(all(not value.startswith(SEP) or value in GENERIC_LITERALS for value in literals),
                    "unexpected absolute-looking source literal: " + name)
            if name in ("overlay/admission.py", "overlay/supervision/gate.py"):
                counts = Counter(literals)
                require(counts[ROOT_TOKEN] == 1 and counts[ROOT_TOKEN + SEP] == 1,
                        "logical reviewer/root authority tokens changed")
                require(counts["audit_attention_schedule_correspondence"] == 1,
                        "author-task exclusion changed")
                prefix_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                                and isinstance(node.func, ast.Attribute)
                                and isinstance(node.func.value, ast.Name)
                                and node.func.value.id == "reviewer" and node.func.attr == "startswith"
                                and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                                and node.args[0].value == ROOT_TOKEN + SEP]
                require(len(prefix_calls) == 1, "logical reviewer namespace use changed")
    policy = parse_json(raw["overlay/contract/FRAME_ROUTING_POLICY.json"])
    summary = parse_json(raw["SUMMARY.json"])
    require(policy["actual_execution_authorized"] is False and summary["actual_execution_authorized"] is False,
            "source excerpt cannot authorize actual work")
    require(policy["transient_frame_ownership_detection_equivalent"] is False
            and policy["transient_locals_detection_equivalent"] is False
            and summary["reduced_transient_integrity_sampling"] is True, "integrity caveat missing")
    require(summary["fullblock_pass_claimed"] is False and summary["numerical_pass_claimed"] is False,
            "invalid pass claim")
    budget = summary["budget_proposal"]
    require(budget["total_seconds"] == 43200 == budget["shared_work_seconds"]
            + budget["cleanup_seconds"] + budget["final_supervisor_seconds"], "budget arithmetic")
    require((budget["shared_work_seconds"], budget["cleanup_seconds"], budget["final_supervisor_seconds"])
            == (43185, 5, 10), "budget split")
    require(budget["fresh_free_space_gate_bytes"] == 22715767588 == budget["owned_reservation_bytes"]
            + budget["separate_margin_bytes"], "free-space arithmetic")
    require(budget["one_cpu"] is True and budget["process_address_space_bytes"] == 2147483648
            and budget["completion_guaranteed"] is False, "resource/guarantee caveat")
    source_verified = False
    if args.source_root is not None:
        source_root = args.source_root.resolve()
        source_raw = regular_file(source_root / "SOURCE_MANIFEST.json")
        require(identity(source_raw) == {"bytes": 8464, "sha256": SOURCE_SHA256}, "upstream source manifest hash")
        source_manifest = parse_json(source_raw)
        for name in COPIED:
            require(source_manifest["files"][name] == pins["files"][name], "upstream manifest pin mismatch")
            require(regular_file(source_root / name) == raw[name], "upstream copy differs: " + name)
        source_verified = True
    review_verified = False
    if args.review_file is not None:
        require(identity(regular_file(args.review_file))["sha256"] == REVIEW_SHA256, "review fingerprint differs")
        review_verified = True
    print(json.dumps({
        "schema": "fixed93-public-source-excerpt-static-check-v1",
        "status": "PASS_STATIC_ONLY",
        "files": len(EXPECTED), "bytes": sum(map(len, raw.values())),
        "copied_original_files": len(COPIED), "python_ast_compile_checks": len(python_names),
        "public_manifest_sha256": identity(raw[MANIFEST])["sha256"],
        "allowlist_sha256": identity(raw[ALLOWLIST])["sha256"],
        "upstream_original_copies_verified": source_verified,
        "upstream_review_fingerprint_verified": review_verified,
        "source_code_executed": False, "original_tests_rerun": False,
        "builder_preflight_dut_native_model_run": False,
        "actual_execution_authorized": False,
        "scope": "Hashes, exact allowlist, strict JSON, AST and in-memory compile only"
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
