"""Reassemble exact published project sources; never invokes a compiler or model."""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
MISSING = {
    "host_memory.hpp": "PROJECT_SOURCE_MISSING",
    "host_ports.hpp": "PROJECT_SOURCE_MISSING",
    "sink_stream_bridge.hpp": "PROJECT_SOURCE_MISSING",
    "VHostBlockTop.h": "GENERATED_MODEL_NOT_INCLUDED",
    "VHostBlockTop__Dpi.h": "GENERATED_MODEL_NOT_INCLUDED",
    "VHostBlockTop__Syms.h": "GENERATED_MODEL_NOT_INCLUDED",
    "VHostBlockTop___024root.h": "GENERATED_MODEL_NOT_INCLUDED",
    "svdpi.h": "EXTERNAL_RUNTIME_NOT_INCLUDED",
    "verilated_sym_props.h": "EXTERNAL_RUNTIME_NOT_INCLUDED",
}
QUOTED = re.compile(r'^\s*#\s*include\s*"([^"\n]+)"', re.MULTILINE)


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def relative(name):
    path = PurePosixPath(name)
    need(bool(name) and not path.is_absolute() and
         all(part not in (".", "..") for part in path.parts) and
         str(path) == name and "\\" not in name, "unsafe relative source name")
    return path


def digest(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def pin():
    data = json.loads((HERE / "SOURCE_PIN.json").read_text(encoding="utf-8"))
    need(data["scope"] == "PROJECT_SOURCE_SUBSET_ONLY", "unexpected source scope")
    targets = []
    for record in data["copied_sources"]:
        relative(record["repository_path"])
        relative(record["assembled_path"])
        targets.append(record["assembled_path"])
    need(len(targets) == len(set(targets)) == 22, "unexpected source set")
    return data


def read_source(root, name):
    path = root
    for part in relative(name).parts:
        path = path / part
        need(not path.is_symlink(), "symlink rejected: " + name)
    need(path.is_file(), "source absent: " + name)
    return path.read_bytes()


def verify(source):
    records = pin()["copied_sources"]
    expected = {record["assembled_path"] for record in records}
    need(source.is_dir() and not source.is_symlink(), "source directory absent or symlink")
    entries = list(source.rglob("*"))
    need(not any(path.is_symlink() for path in entries), "source symlink rejected")
    actual = {path.relative_to(source).as_posix() for path in entries if path.is_file()}
    need(actual == expected, "source file set differs from pin")
    for record in records:
        name = record["assembled_path"]
        need(digest(read_source(source, name)) ==
             {key: record[key] for key in ("bytes", "sha256")},
             "source bytes differ: " + name)
    return {"status": "EXACT_PROJECT_SOURCE_SUBSET", "files": len(records),
            "cpp_compiled": False, "full_host_ready": False}


def assemble(repository, output):
    # Validate every input before creating a new destination. Never overwrite.
    need(repository.is_dir(), "repository directory absent")
    repository = repository.resolve()
    output = output.absolute()
    need(not output.exists() and not output.is_symlink(), "destination already exists")
    need(output.parent.is_dir(), "destination parent absent")
    destination = output.parent.resolve() / output.name
    need(not destination.is_relative_to(repository), "destination must be outside repository")
    buffers = []
    for record in pin()["copied_sources"]:
        raw = read_source(repository, record["repository_path"])
        need(digest(raw) == {key: record[key] for key in ("bytes", "sha256")},
             "repository source differs: " + record["repository_path"])
        buffers.append((record["assembled_path"], raw))
    destination.mkdir(exist_ok=False)
    for name, raw in buffers:
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    return verify(destination)


def closure(source):
    verify(source)
    edges = []
    names = {record["assembled_path"] for record in pin()["copied_sources"]}
    for name in sorted(names):
        if not name.endswith((".hpp", ".cpp")):
            continue
        content = read_source(source, name).decode("utf-8")
        for match in QUOTED.finditer(content):
            header = match.group(1)
            relative(header)
            candidates = [(PurePosixPath(name).parent / header).as_posix(),
                          (PurePosixPath("include") / header).as_posix()]
            target = next((candidate for candidate in candidates if candidate in names), None)
            edge = {"source": name, "header": header}
            if target is not None:
                edge.update(status="RECOVERED_PROJECT_SOURCE", target=target)
            else:
                need(header in MISSING, "unclassified include: " + header)
                edge.update(status=MISSING[header])
            edges.append(edge)
    return {"scope": "LITERAL_QUOTED_INCLUDE_SOURCE_AUDIT_ONLY", "full_host_ready": False,
            "missing": {name: MISSING[name] for name in sorted({edge["header"] for edge in edges
                        if edge["status"] != "RECOVERED_PROJECT_SOURCE"})},
            "edges": edges}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("assemble", help="copy pinned sources to a NEW directory")
    build.add_argument("--repo", required=True, type=Path)
    build.add_argument("--out", required=True, type=Path)
    for name in ("verify", "closure"):
        check = commands.add_parser(name)
        check.add_argument("--source", type=Path, default=HERE / "source")
    args = parser.parse_args()
    try:
        if args.command == "assemble":
            result = assemble(args.repo, args.out)
        elif args.command == "verify":
            result = verify(args.source)
        else:
            result = closure(args.source)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, "SOURCE RECOVERY FAILED: " + str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
