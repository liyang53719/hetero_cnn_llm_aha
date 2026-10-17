#!/usr/bin/env python3
"""Offline publication-closure proof for the pinned 96b0548 commit.

No network, Git executable, packages, imports from audited sources, or execution
of audited code is used. The expected map is {repository_path: sha256}. Local
regular-file bytes and executable bits supply the expected Git blob and mode.
Every recursive tree node is rebuilt using Git's byte ordering and object format.

The commit/tree pins are independent audit inputs fixed below. This validates
saved GitHub evidence against those pins; it does not authenticate the transport
that originally retrieved that evidence, or claim the map is a dependency graph.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


EXPECTED_COMMIT = "96b0548f7241b4a4c98c44601ccdcc62fe9e9989"
EXPECTED_TREE = "6a3670c95bc7ba85162eb20f72d714afa110ff2f"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MODE_TYPES = {
    "040000": "tree", "100644": "blob", "100755": "blob",
    "120000": "blob", "160000": "commit",
}


def git_hash(kind, raw):
    return hashlib.sha1(kind.encode("ascii") + b" " + str(len(raw)).encode("ascii")
                        + b"\0" + raw).hexdigest()


def safe_path(value):
    """Accept unambiguous relative POSIX paths with UTF-8 Git names."""
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        return False
    if any(p in ("", ".", "..", ".git") for p in value.split("/")):
        return False
    if re.match(r"^[A-Za-z]:", value):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def is_sha(value, pattern=HEX40):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key: " + repr(key))
        result[key] = value
    return result


def load_json(path):
    def reject_constant(value):
        raise ValueError("non-finite JSON number: " + value)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=_unique_pairs,
                         parse_constant=reject_constant)


def add_error(errors, code, path=None, **details):
    item = {"code": code}
    if path is not None:
        item["path"] = path
    item.update(details)
    errors.append(item)


def canonical_errors(errors):
    return sorted(errors, key=lambda item: json.dumps(item, sort_keys=True,
                                                     ensure_ascii=True))


def open_source_root(root):
    """Open every root component without following aliases, including ancestors."""
    absolute = Path(root).absolute()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def read_local_file(root_fd, path, seen_inodes):
    """Read via directory descriptors; reject symlinks, hardlinks and races."""
    parent_fd = os.dup(root_fd)
    file_fd = None
    try:
        parts = path.split("/")
        for component in parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child
        # lstat first prevents opening FIFOs/devices, which may block or have effects.
        initial = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("source is not a regular file (symlinks are forbidden)")
        if initial.st_nlink != 1:
            raise ValueError("source has hard-link aliases")
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=parent_fd)
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ValueError("opened source is nonregular or has hard-link aliases")
        inode = (opened.st_dev, opened.st_ino)
        if inode != (initial.st_dev, initial.st_ino):
            raise ValueError("source changed while opening")
        if inode in seen_inodes:
            raise ValueError("source aliases another expected path: " + seen_inodes[inode])
        seen_inodes[inode] = path
        chunks = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        final = os.fstat(file_fd)
        linked = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size,
                              s.st_nlink, s.st_mtime_ns, s.st_ctime_ns)
        if identity(opened) != identity(final) or identity(final) != identity(linked):
            raise ValueError("source changed while reading")
        if len(raw) != final.st_size:
            raise ValueError("source length changed while reading")
        return {"sha256": hashlib.sha256(raw).hexdigest(),
                "blob_sha1": git_hash("blob", raw), "size": len(raw),
                "mode": "100755" if final.st_mode & 0o111 else "100644"}
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(parent_fd)


def validate_commit(commit, expected_commit, expected_tree, errors):
    observed_commit = None
    commit_tree = None
    if not isinstance(commit, dict):
        add_error(errors, "commit_not_object")
        return observed_commit, commit_tree
    observed_commit = commit.get("sha")
    if not is_sha(observed_commit):
        add_error(errors, "commit_sha_invalid")
    elif observed_commit != expected_commit:
        add_error(errors, "commit_sha_mismatch", expected=expected_commit,
                  observed=observed_commit)
    candidates = []
    if "tree" in commit:
        candidates.append(commit["tree"])
    if "commit" in commit:
        if not isinstance(commit["commit"], dict):
            add_error(errors, "rest_commit_not_object")
        else:
            candidates.append(commit["commit"].get("tree"))
    if not candidates:
        add_error(errors, "commit_tree_missing")
    trees = []
    for candidate in candidates:
        value = candidate.get("sha") if isinstance(candidate, dict) else None
        if not is_sha(value):
            add_error(errors, "commit_tree_sha_invalid")
        else:
            trees.append(value)
    if trees:
        commit_tree = trees[0]
        if len(set(trees)) != 1:
            add_error(errors, "commit_tree_ambiguous")
        for tree in sorted(set(trees)):
            if tree != expected_tree:
                add_error(errors, "commit_tree_pin_mismatch", expected=expected_tree,
                          observed=tree)
    return observed_commit, commit_tree


def validate_tree(tree, commit_tree, expected_tree, errors):
    entries = {}
    root_sha = None
    reconstructed = None
    if not isinstance(tree, dict):
        add_error(errors, "tree_not_object")
        return entries, root_sha, reconstructed
    root_sha = tree.get("sha")
    if not is_sha(root_sha):
        add_error(errors, "tree_sha_invalid")
    if root_sha != expected_tree:
        add_error(errors, "tree_pin_mismatch", expected=expected_tree, observed=root_sha)
    if root_sha != commit_tree or not is_sha(commit_tree):
        add_error(errors, "commit_tree_binding_mismatch")
    if tree.get("truncated") is not False:
        add_error(errors, "tree_not_explicitly_untruncated")
    rows = tree.get("tree")
    if not isinstance(rows, list):
        add_error(errors, "tree_entries_not_array")
        return entries, root_sha, reconstructed
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            add_error(errors, "tree_entry_not_object", index=index)
            continue
        path = row.get("path")
        if not safe_path(path):
            add_error(errors, "tree_path_unsafe", index=index, observed=path)
            continue
        if path in entries:
            add_error(errors, "tree_path_duplicate", path=path)
            continue
        entries[path] = row
        mode = row.get("mode")
        if not isinstance(mode, str) or mode not in MODE_TYPES:
            add_error(errors, "tree_mode_invalid", path=path)
        elif row.get("type") != MODE_TYPES[mode]:
            add_error(errors, "tree_mode_type_mismatch", path=path)
        if not is_sha(row.get("sha")):
            add_error(errors, "tree_entry_sha_invalid", path=path)
        if "size" in row and (type(row["size"]) is not int or row["size"] < 0):
            add_error(errors, "tree_entry_size_invalid", path=path)
    children = {"": []}
    for path, entry in entries.items():
        parent = path.rpartition("/")[0]
        children.setdefault(parent, []).append((path, entry))
        if entry.get("type") == "tree":
            children.setdefault(path, [])
        if parent and parent not in entries:
            add_error(errors, "tree_parent_missing", path=path, parent=parent)
        elif parent and entries[parent].get("type") != "tree":
            add_error(errors, "tree_directory_file_collision", path=path, parent=parent)
    computed = {}
    directories = {""} | {p for p, v in entries.items() if v.get("type") == "tree"}
    for directory in sorted(directories, key=lambda p: (-p.count("/"), -len(p), p)):
        ordered = sorted(children.get(directory, []), key=lambda item:
                         item[0].rsplit("/", 1)[-1].encode("utf-8")
                         + (b"/" if item[1].get("type") == "tree" else b"\0"))
        payload = []
        valid = True
        for path, entry in ordered:
            mode = entry.get("mode")
            oid = computed.get(path) if entry.get("type") == "tree" else entry.get("sha")
            if (not isinstance(mode, str) or mode not in MODE_TYPES
                    or entry.get("type") != MODE_TYPES.get(mode) or not is_sha(oid)):
                valid = False
                continue
            name = path.rsplit("/", 1)[-1].encode("utf-8")
            payload.append(mode.lstrip("0").encode("ascii") + b" " + name + b"\0"
                           + bytes.fromhex(oid))
        if valid:
            computed[directory] = git_hash("tree", b"".join(payload))
            declared = root_sha if directory == "" else entries[directory].get("sha")
            if computed[directory] != declared:
                add_error(errors, "tree_object_hash_mismatch", path=directory,
                          expected=declared, computed=computed[directory])
    reconstructed = computed.get("")
    if reconstructed is None:
        add_error(errors, "tree_root_not_reconstructable")
    return entries, root_sha, reconstructed


def validate_tree_proof(bundle, paths, commit_tree, expected_tree, errors):
    """Verify complete immediate-child trees, then prove each required path.

    Tree IDs of irrelevant subdirectories are opaque Merkle commitments. A
    required subtree with no complete authenticated response is never interpreted
    as a missing file. All supplied responses are validated, including extras.
    """
    tables = {}
    computed = {}
    entries = {}
    evidence = {}
    root_sha = bundle.get("root_sha")
    if type(bundle.get("schema")) is not int or bundle.get("schema") != 1:
        add_error(errors, "tree_proof_schema_invalid")
    if bundle.get("profile") != "github-required-prefix-tree-proof-v1":
        add_error(errors, "tree_proof_profile_invalid")
    if not is_sha(root_sha):
        add_error(errors, "tree_sha_invalid")
    if root_sha != expected_tree:
        add_error(errors, "tree_pin_mismatch", expected=expected_tree, observed=root_sha)
    if root_sha != commit_tree or not is_sha(commit_tree):
        add_error(errors, "commit_tree_binding_mismatch")
    trees = bundle.get("trees")
    if not isinstance(trees, dict) or not trees:
        add_error(errors, "tree_proof_trees_not_nonempty_object")
        trees = {}
    for oid, response in sorted(trees.items()):
        before = len(errors)
        if not is_sha(oid):
            add_error(errors, "tree_proof_key_invalid", observed=oid)
            continue
        if not isinstance(response, dict):
            add_error(errors, "tree_proof_response_not_object", tree_sha=oid)
            continue
        if response.get("sha") != oid:
            add_error(errors, "tree_proof_response_sha_mismatch", tree_sha=oid)
        if response.get("truncated") is not False:
            add_error(errors, "tree_not_explicitly_untruncated", tree_sha=oid)
        rows = response.get("tree")
        if not isinstance(rows, list):
            add_error(errors, "tree_entries_not_array", tree_sha=oid)
            continue
        table = {}
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                add_error(errors, "tree_entry_not_object", tree_sha=oid, index=index)
                continue
            path = row.get("path")
            if not safe_path(path) or "/" in path:
                add_error(errors, "tree_proof_name_unsafe", tree_sha=oid,
                          index=index, observed=path)
                continue
            if path in table:
                add_error(errors, "tree_path_duplicate", tree_sha=oid, path=path)
                continue
            table[path] = row
            mode = row.get("mode")
            if not isinstance(mode, str) or mode not in MODE_TYPES:
                add_error(errors, "tree_mode_invalid", tree_sha=oid, path=path)
            elif row.get("type") != MODE_TYPES[mode]:
                add_error(errors, "tree_mode_type_mismatch", tree_sha=oid, path=path)
            if not is_sha(row.get("sha")):
                add_error(errors, "tree_entry_sha_invalid", tree_sha=oid, path=path)
            if "size" in row and (type(row["size"]) is not int or row["size"] < 0):
                add_error(errors, "tree_entry_size_invalid", tree_sha=oid, path=path)
        if len(errors) == before:
            ordered = sorted(table.values(), key=lambda row: row["path"].encode("utf-8")
                             + (b"/" if row["type"] == "tree" else b"\0"))
            payload = b"".join(row["mode"].lstrip("0").encode("ascii") + b" "
                               + row["path"].encode("utf-8") + b"\0"
                               + bytes.fromhex(row["sha"]) for row in ordered)
            computed[oid] = git_hash("tree", payload)
            if computed[oid] != oid:
                add_error(errors, "tree_object_hash_mismatch", tree_sha=oid,
                          expected=oid, computed=computed[oid])
            else:
                tables[oid] = table
    for path in sorted(paths):
        current = root_sha
        parts = path.split("/")
        for index, component in enumerate(parts):
            if not is_sha(current) or current not in tables:
                evidence[path] = {"status": "incomplete", "required_tree_sha": current,
                                  "at_component": "/".join(parts[:index])}
                break
            entry = tables[current].get(component)
            if entry is None:
                evidence[path] = {"status": "missing", "verified_parent_tree_sha": current,
                                  "absent_component": "/".join(parts[:index + 1])}
                break
            if index == len(parts) - 1:
                entries[path] = entry
                evidence[path] = {"status": "present", "verified_parent_tree_sha": current}
                break
            if entry["type"] != "tree":
                evidence[path] = {"status": "mismatch", "verified_parent_tree_sha": current,
                                  "blocking_component": "/".join(parts[:index + 1]),
                                  "blocking_type": entry["type"]}
                break
            current = entry["sha"]
    missing_trees = sorted({item["required_tree_sha"] for item in evidence.values()
                            if item["status"] == "incomplete" and
                            isinstance(item["required_tree_sha"], str)})
    for oid in missing_trees:
        add_error(errors, "tree_required_evidence_unavailable", tree_sha=oid)
    return (entries, root_sha, computed.get(root_sha) if is_sha(root_sha) else None,
            evidence, len(tables))


def audit(source_root, expected_map, commit, tree, *,
          expected_commit=EXPECTED_COMMIT, expected_tree=EXPECTED_TREE,
          input_errors=None):
    errors = list(input_errors or [])
    if not is_sha(expected_commit) or not is_sha(expected_tree):
        add_error(errors, "expected_identity_invalid")
    observed_commit, commit_tree = validate_commit(commit, expected_commit,
                                                   expected_tree, errors)
    safe_expected = {}
    if not isinstance(expected_map, dict) or not expected_map:
        add_error(errors, "expected_map_not_nonempty_object")
    else:
        for path, digest in expected_map.items():
            if not safe_path(path):
                add_error(errors, "expected_path_unsafe", observed=path)
                continue
            safe_expected[path] = digest
            if not is_sha(digest, HEX64):
                add_error(errors, "expected_digest_invalid", path=path)
        for path in sorted(safe_expected):
            parts = path.split("/")
            for i in range(1, len(parts)):
                parent = "/".join(parts[:i])
                if parent in safe_expected:
                    add_error(errors, "expected_directory_file_collision", path=path,
                              parent=parent)
    path_evidence = {}
    verified_response_count = None
    proof = isinstance(tree, dict) and ("profile" in tree or "trees" in tree)
    if proof:
        entries, root_sha, reconstructed, path_evidence, verified_response_count = validate_tree_proof(
            tree, safe_expected, commit_tree, expected_tree, errors)
    else:
        entries, root_sha, reconstructed = validate_tree(tree, commit_tree,
                                                         expected_tree, errors)
        if any(e["code"].startswith("tree_") for e in errors):
            path_evidence = {path: {"status": "incomplete"} for path in safe_expected
                             if path not in entries}
    root_fd = None
    try:
        root_fd = open_source_root(source_root)
    except (OSError, ValueError) as exc:
        add_error(errors, "source_root_invalid", reason=type(exc).__name__)
    files = []
    seen_inodes = {}
    try:
        for path in sorted(safe_expected):
            digest = safe_expected[path]
            record = {"path": path, "expected_sha256": digest, "issues": []}
            local = None
            if root_fd is None:
                record["issues"].append("local_root_unavailable")
            else:
                try:
                    local = read_local_file(root_fd, path, seen_inodes)
                    record["local"] = local
                    if local["sha256"] != digest:
                        record["issues"].append("local_sha256_mismatch")
                except (OSError, ValueError) as exc:
                    record["issues"].append("local_file_invalid")
                    record["local_error"] = (str(exc) if isinstance(exc, ValueError)
                                             else type(exc).__name__)
            remote = entries.get(path)
            evidence = path_evidence.get(path, {})
            if evidence:
                record["publication_evidence"] = evidence
            if evidence.get("status") == "incomplete":
                record["issues"].append("remote_evidence_incomplete")
            elif evidence.get("status") == "mismatch":
                record["issues"].append("remote_parent_not_tree")
            elif remote is None:
                record["issues"].append("remote_missing")
            else:
                record["remote"] = {key: remote[key] for key in ("type", "mode", "sha", "size")
                                    if key in remote}
                if remote.get("type") != "blob":
                    record["issues"].append("remote_not_blob")
                if local is not None:
                    for remote_key, local_key, code in (
                            ("mode", "mode", "remote_mode_mismatch"),
                            ("sha", "blob_sha1", "remote_blob_sha1_mismatch"),
                            ("size", "size", "remote_size_mismatch")):
                        value = remote.get(remote_key)
                        if value != local[local_key] or (remote_key == "size"
                                                       and type(value) is not int):
                            record["issues"].append(code)
            if not is_sha(digest, HEX64):
                record["issues"].append("expected_digest_invalid")
            record["issues"].sort()
            record["status"] = ("incomplete" if evidence.get("status") == "incomplete" else
                                "mismatch" if evidence.get("status") == "mismatch" else
                                "missing" if remote is None else
                                "mismatch" if record["issues"] else "present")
            files.append(record)
    finally:
        if root_fd is not None:
            os.close(root_fd)
    groups = {status: [item["path"] for item in files if item["status"] == status]
              for status in ("present", "missing", "mismatch", "incomplete")}
    passed = not errors and len(groups["present"]) == len(files) and bool(files)
    return {
        "schema_version": 1, "status": "PASS" if passed else "FAIL",
        "expected_commit_sha": expected_commit, "observed_commit_sha": observed_commit,
        "expected_tree_sha": expected_tree, "commit_tree_sha": commit_tree,
        "recursive_tree_sha": root_sha, "reconstructed_tree_sha": reconstructed,
        "tree_evidence_profile": ("github-required-prefix-tree-proof-v1" if proof else
                                  "github-recursive-tree-v1"),
        "verified_tree_response_count": verified_response_count,
        "tree_integrity_verified": not any(e["code"].startswith(("tree_", "commit_", "rest_commit_"))
                                           or e["code"] == "expected_identity_invalid" for e in errors),
        "expected_file_count": len(expected_map) if isinstance(expected_map, dict) else 0,
        "audited_file_count": len(files), "remote_entry_count": len(entries),
        "counts": {**{key: len(value) for key, value in groups.items()},
                   "remote_present": sum("remote" in item for item in files),
                   "local_invalid": sum("local" not in item for item in files),
                   "global_errors": len(errors)},
        **groups, "errors": canonical_errors(errors), "files": files,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--expected-map", required=True, type=Path)
    parser.add_argument("--commit-json", required=True, type=Path)
    parser.add_argument("--tree-json", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-commit", default=EXPECTED_COMMIT,
                        help="explicit independently verified commit SHA pin")
    parser.add_argument("--expected-tree", default=EXPECTED_TREE,
                        help="explicit independently verified root tree SHA pin")
    args = parser.parse_args(argv)
    # Never overwrite inputs, audited files, or files reached through symlinks.
    resolved_out = args.out.resolve()
    protected = {p.resolve() for p in (args.expected_map, args.commit_json, args.tree_json)}
    source = args.source_root.resolve()
    if resolved_out in protected or resolved_out == source or source in resolved_out.parents:
        parser.error("--out must be outside the source root and distinct from input files")
    if args.out.is_symlink():
        parser.error("--out must not be a symlink")
    if args.out.exists():
        output_stat = args.out.stat()
        if not stat.S_ISREG(output_stat.st_mode) or output_stat.st_nlink != 1:
            parser.error("--out must be a regular file without hard-link aliases")
    inputs = {}
    errors = []
    for name in ("expected_map", "commit_json", "tree_json"):
        try:
            inputs[name] = load_json(getattr(args, name))
        except (OSError, ValueError, UnicodeError) as exc:
            inputs[name] = None
            add_error(errors, "input_json_invalid", input=name, reason=type(exc).__name__)
    report = audit(args.source_root, inputs["expected_map"], inputs["commit_json"],
                   inputs["tree_json"], expected_commit=args.expected_commit,
                   expected_tree=args.expected_tree, input_errors=errors)
    encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    temporary = None
    try:
        # Atomic replacement avoids truncating an aliased file even if a link is
        # introduced after validation. A failed write never leaves a partial report.
        fd, temporary = tempfile.mkstemp(prefix="." + args.out.name + ".", dir=args.out.parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(encoded)
        os.replace(temporary, args.out)
        temporary = None
    except OSError as exc:
        print("publication audit output error: " + type(exc).__name__, file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            os.unlink(temporary)
    print(json.dumps({"status": report["status"], "expected_file_count":
                      report["expected_file_count"], "counts": report["counts"]}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
