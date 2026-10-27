"""Restore exact small Scala source selections only. Never compile or import them."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json


def need(condition, message):
    if not condition:
        raise ValueError(message)


def no_symlinks(path):
    path = Path(path).absolute()
    need(not any(p.is_symlink() for p in [path, *path.parents]), "symlink path")
    return path


def relative(value):
    need(isinstance(value, str) and "\\" not in value, "relative string required")
    p = PurePosixPath(value)
    need(not p.is_absolute() and str(p) == value and value not in ("", ".")
         and ".." not in p.parts, "unsafe relative path")
    return p


def assemble(manifest, repository, reconstructed, output):
    roots = {"repository": no_symlinks(repository).resolve(),
             "reconstructed": no_symlinks(reconstructed).resolve()}
    need(all(p.is_dir() for p in roots.values()), "missing source root")
    out = no_symlinks(output)
    need(not out.exists(), "output must not exist")
    need(out.parent.is_dir(), "output parent must exist")
    out = out.resolve()
    need(all(out != p and out not in p.parents and p not in out.parents
             for p in roots.values()), "output overlaps inputs")
    need(manifest.get("schema") == 1, "schema")
    staged = []
    for stage, count in [("production19", 19), ("dependency_sources8", 8)]:
        rows = manifest.get(stage)
        need(isinstance(rows, list) and len(rows) == count, "stage count")
        names = set()
        for row in rows:
            name = relative(row["name"])
            need(len(name.parts) == 1 and name.suffix == ".scala", "Scala basename")
            need(str(name) not in names, "duplicate source name")
            names.add(str(name))
            kind = row["kind"]
            need(kind in roots, "source kind")
            p = no_symlinks(roots[kind] / relative(row["path"]))
            need(p.is_file() and p.resolve().is_relative_to(roots[kind]), "source missing")
            need(isinstance(row["bytes"], int) and 0 < row["bytes"] <= 131072,
                 "small source size")
            need(p.stat().st_size == row["bytes"], "source size")
            data = p.read_bytes()
            need(hashlib.sha256(data).hexdigest() == row["sha256"], "source hash")
            text = data.decode("utf-8")
            need("\0" not in text, "binary source")
            staged.append((stage, str(name), data, row["sha256"]))
    # All source identities and paths validated before creating the new directory.
    out.mkdir()
    receipt = {"status": "SOURCE_RESTORED_ONLY_NO_TYPECHECK_OR_EXECUTION", "stages": {}}
    for stage, name, data, sha in staged:
        (out / stage).mkdir(exist_ok=True)
        (out / stage / name).write_bytes(data)
        receipt["stages"].setdefault(stage, []).append(
            {"name": name, "bytes": len(data), "sha256": sha})
    (out / "SOURCE_RESTORE.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=Path(__file__).with_name("SOURCE_SELECTIONS.json"))
    ap.add_argument("--repository", type=Path, required=True)
    ap.add_argument("--reconstructed", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(assemble(json.loads(args.manifest.read_text()), args.repository,
                              args.reconstructed, args.output), indent=2))


if __name__ == "__main__":
    main()
