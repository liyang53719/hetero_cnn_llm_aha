#!/usr/bin/env python3
"""Cold stdlib-only tests. Run: python -B -m unittest -v test_check_publication.py"""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check_publication as checker


COMMIT = "1" * 40


def object_id(kind, data):
    # Independent fixture implementation, not the checker's hashing helper.
    header = (kind + " " + str(len(data))).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data).hexdigest()


def fixtures(files):
    """Build genuine Git Merkle trees from {path: (bytes, Git mode)}."""
    trie = {}
    for path, value in files.items():
        node = trie
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    flat = []
    trees = {}

    def visit(node, prefix):
        immediate = []
        for name, value in node.items():
            full = prefix + name
            if isinstance(value, dict):
                oid = visit(value, full + "/")
                row = {"path": name, "mode": "040000", "type": "tree", "sha": oid}
            else:
                raw, mode = value
                row = {"path": name, "mode": mode, "type": "blob",
                       "sha": object_id("blob", raw), "size": len(raw)}
            immediate.append(row)
            flat.append({**row, "path": full})
        immediate.sort(key=lambda row: (row["path"] +
                       ("/" if row["type"] == "tree" else "\0")).encode("utf-8"))
        raw = b"".join((row["mode"].lstrip("0") + " " + row["path"]).encode("utf-8")
                       + bytes([0]) + bytes.fromhex(row["sha"]) for row in immediate)
        oid = object_id("tree", raw)
        trees[oid] = {"sha": oid, "tree": immediate, "truncated": False}
        return oid

    root = visit(trie, "")
    return ({"sha": COMMIT, "tree": {"sha": root}},
            {"sha": root, "tree": sorted(flat, key=lambda row: row["path"]), "truncated": False},
            {"schema": 1, "profile": "github-required-prefix-tree-proof-v1",
             "root_sha": root, "trees": trees})


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="publication-check-cold-")
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.files = {
            "alpha/a.py": (b"print('a')\n", "100644"),
            "alpha/nested/b.txt": (b"b", "100644"),
            "alpha.c": (b"sort-before-directory", "100644"),
            "z.txt": (b"", "100644"),
            "unicode/é.txt": (b"unicode-name", "100644"),
        }
        self.expected = {}
        for path, (raw, mode) in self.files.items():
            target = self.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o755 if mode == "100755" else 0o644)
            self.expected[path] = hashlib.sha256(raw).hexdigest()
        self.commit, self.recursive, self.proof = fixtures(self.files)

    def tearDown(self):
        self.temp.cleanup()

    def run_audit(self, tree=None, commit=None, expected=None, source=None, pin_tree=None):
        commit = self.commit if commit is None else commit
        tree = self.proof if tree is None else tree
        return checker.audit(self.source if source is None else source,
                             self.expected if expected is None else expected,
                             commit, tree, expected_commit=COMMIT,
                             expected_tree=pin_tree or self.commit["tree"]["sha"])

    def assert_error(self, report, code):
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(code, [item["code"] for item in report["errors"]])

    def file_record(self, report, path):
        return next(item for item in report["files"] if item["path"] == path)

    def subprocess_args(self, tree=None, commit=None, expected=None):
        for name, data in (("tree", self.proof if tree is None else tree),
                           ("commit", self.commit if commit is None else commit),
                           ("expected", self.expected if expected is None else expected)):
            (self.base / (name + ".json")).write_text(json.dumps(data), encoding="utf-8")
        return [sys.executable, "-B", str(Path(checker.__file__).resolve()),
                "--source-root", str(self.source),
                "--expected-map", str(self.base / "expected.json"),
                "--commit-json", str(self.base / "commit.json"),
                "--tree-json", str(self.base / "tree.json"),
                "--expected-commit", COMMIT,
                "--expected-tree", self.commit["tree"]["sha"],
                "--out", str(self.base / "report.json")]

    def test_pass_both_profiles_and_known_blob_vector(self):
        self.assertEqual(checker.git_hash("blob", b""),
                         "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
        for tree in (self.proof, self.recursive):
            with self.subTest(profile="proof" if "trees" in tree else "recursive"):
                report = self.run_audit(tree=tree)
                self.assertEqual(report["status"], "PASS", report["errors"])
                self.assertEqual(report["counts"]["present"], 5)
                self.assertEqual(report["reconstructed_tree_sha"], self.commit["tree"]["sha"])
                self.assertTrue(report["tree_integrity_verified"])

    def test_rest_commit_shape(self):
        report = self.run_audit(commit={"sha": COMMIT, "commit": {"tree": self.commit["tree"]}})
        self.assertEqual(report["status"], "PASS")

    def test_collect_multiple_missing_without_early_stop(self):
        remote = {k: v for k, v in self.files.items() if k not in ("alpha/a.py", "z.txt")}
        commit, recursive, proof = fixtures(remote)
        for tree in (recursive, proof):
            report = self.run_audit(tree=tree, commit=commit, pin_tree=commit["tree"]["sha"])
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["missing"], ["alpha/a.py", "z.txt"])
            self.assertEqual(report["counts"]["present"], 3)
            self.assertEqual(report["audited_file_count"], 5)
            self.assertEqual(report["errors"], [])

    def test_missing_whole_directory_proves_all_descendants_missing(self):
        remote = {k: v for k, v in self.files.items() if not k.startswith("alpha/")}
        commit, _, proof = fixtures(remote)
        report = self.run_audit(tree=proof, commit=commit, pin_tree=commit["tree"]["sha"])
        self.assertEqual(report["missing"], ["alpha/a.py", "alpha/nested/b.txt"])
        self.assertEqual(report["incomplete"], [])

    def test_authentic_remote_hash_and_mode_mismatch(self):
        remote = dict(self.files)
        remote["alpha/a.py"] = (b"wrong", "100644")
        remote["z.txt"] = (b"", "100755")
        commit, _, proof = fixtures(remote)
        report = self.run_audit(tree=proof, commit=commit, pin_tree=commit["tree"]["sha"])
        self.assertEqual(report["mismatch"], ["alpha/a.py", "z.txt"])
        self.assertIn("remote_blob_sha1_mismatch", self.file_record(report, "alpha/a.py")["issues"])
        self.assertIn("remote_mode_mismatch", self.file_record(report, "z.txt")["issues"])
        self.assertEqual(report["errors"], [])

    def test_size_wrong_missing_and_boolean(self):
        root = self.proof["trees"][self.proof["root_sha"]]
        row = next(row for row in root["tree"] if row["path"] == "z.txt")
        for value in (1, None, False):
            with self.subTest(size=value):
                row["size"] = value
                report = self.run_audit()
                self.assertEqual(report["status"], "FAIL")
                if value == 1:
                    self.assertIn("remote_size_mismatch", self.file_record(report, "z.txt")["issues"])
                else:
                    self.assert_error(report, "tree_entry_size_invalid")
        del row["size"]
        report = self.run_audit()
        self.assertIn("remote_size_mismatch", self.file_record(report, "z.txt")["issues"])

    def test_local_digest_and_remote_blob_both_checked(self):
        (self.source / "z.txt").write_bytes(b"changed")
        report = self.run_audit()
        issues = self.file_record(report, "z.txt")["issues"]
        self.assertIn("local_sha256_mismatch", issues)
        self.assertIn("remote_blob_sha1_mismatch", issues)

    def test_local_file_symlink_rejected(self):
        target = self.source / "z.txt"
        target.unlink()
        target.symlink_to(self.source / "alpha/a.py")
        report = self.run_audit()
        self.assertIn("local_file_invalid", self.file_record(report, "z.txt")["issues"])

    def test_local_intermediate_symlink_rejected(self):
        (self.source / "alpha").rename(self.base / "relocated")
        (self.source / "alpha").symlink_to(self.base / "relocated", target_is_directory=True)
        report = self.run_audit()
        self.assertEqual(report["counts"]["local_invalid"], 2)

    def test_source_root_and_ancestor_symlink_rejected(self):
        alias = self.base / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        self.assert_error(self.run_audit(source=alias), "source_root_invalid")
        parent_alias = self.base / "parent-alias"
        parent_alias.symlink_to(self.base, target_is_directory=True)
        self.assert_error(self.run_audit(source=parent_alias / "source"), "source_root_invalid")

    def test_source_root_parent_traversal_is_opened_without_aliases(self):
        report = self.run_audit(source=self.source / "alpha" / "..")
        self.assertEqual(report["status"], "PASS")
        alias = self.base / "alias"
        alias.symlink_to(self.source / "alpha", target_is_directory=True)
        self.assert_error(self.run_audit(source=alias / ".."), "source_root_invalid")

    def test_hardlink_alias_rejected(self):
        os.link(self.source / "z.txt", self.base / "hardlink")
        report = self.run_audit()
        self.assertIn("local_file_invalid", self.file_record(report, "z.txt")["issues"])

    def test_nonregular_fifo_does_not_block(self):
        target = self.source / "z.txt"
        target.unlink()
        os.mkfifo(target)
        report = self.run_audit()
        self.assertIn("local_file_invalid", self.file_record(report, "z.txt")["issues"])

    def test_all_unsafe_expected_paths_rejected(self):
        for path in ("../escape", "/absolute", "a//b", "a/./b", "a/../b", "a\\b",
                     "C:/file", "a/", ".git/config", "nul\0file", "line\nfile"):
            with self.subTest(path=path):
                self.assert_error(self.run_audit(expected={path: "0" * 64}), "expected_path_unsafe")

    def test_invalid_expected_digests(self):
        for digest in (True, None, 123, "f" * 63, "F" * 64, "g" * 64):
            with self.subTest(digest=digest):
                self.assert_error(self.run_audit(expected={"z.txt": digest}), "expected_digest_invalid")

    def test_empty_map_and_expected_path_collision(self):
        self.assert_error(self.run_audit(expected={}), "expected_map_not_nonempty_object")
        expected = {**self.expected, "alpha": "0" * 64}
        self.assert_error(self.run_audit(expected=expected), "expected_directory_file_collision")

    def test_truncated_must_be_boolean_false(self):
        for value in (True, 0, 1, None, "false"):
            with self.subTest(value=value):
                proof = copy.deepcopy(self.proof)
                proof["trees"][proof["root_sha"]]["truncated"] = value
                self.assert_error(self.run_audit(tree=proof), "tree_not_explicitly_untruncated")
                recursive = copy.deepcopy(self.recursive)
                recursive["truncated"] = value
                self.assert_error(self.run_audit(tree=recursive), "tree_not_explicitly_untruncated")
        recursive = copy.deepcopy(self.recursive)
        del recursive["truncated"]
        self.assert_error(self.run_audit(tree=recursive), "tree_not_explicitly_untruncated")

    def test_duplicate_remote_paths(self):
        recursive = copy.deepcopy(self.recursive)
        recursive["tree"].append(copy.deepcopy(recursive["tree"][0]))
        self.assert_error(self.run_audit(tree=recursive), "tree_path_duplicate")
        proof = copy.deepcopy(self.proof)
        root = proof["trees"][proof["root_sha"]]
        root["tree"].append(copy.deepcopy(root["tree"][0]))
        self.assert_error(self.run_audit(tree=proof), "tree_path_duplicate")

    def test_wrong_commit_and_tree_binding(self):
        commit = copy.deepcopy(self.commit)
        commit["sha"] = "2" * 40
        self.assert_error(self.run_audit(commit=commit), "commit_sha_mismatch")
        commit["sha"] = COMMIT
        commit["tree"]["sha"] = "2" * 40
        self.assert_error(self.run_audit(commit=commit), "commit_tree_binding_mismatch")
        commit = {**self.commit, "commit": {"tree": {"sha": "2" * 40}}}
        self.assert_error(self.run_audit(commit=commit), "commit_tree_ambiguous")

    def test_invalid_sha_values(self):
        for value in (True, None, "x" * 40, "f" * 39, "F" * 40):
            with self.subTest(value=value):
                commit = copy.deepcopy(self.commit)
                commit["sha"] = value
                self.assert_error(self.run_audit(commit=commit), "commit_sha_invalid")

    def test_recursive_missing_parent_topology(self):
        recursive = copy.deepcopy(self.recursive)
        recursive["tree"] = [row for row in recursive["tree"] if row["path"] != "alpha"]
        self.assert_error(self.run_audit(tree=recursive), "tree_parent_missing")

    def test_recursive_file_directory_collision(self):
        recursive = copy.deepcopy(self.recursive)
        row = next(row for row in recursive["tree"] if row["path"] == "alpha")
        row.update(type="blob", mode="100644", size=0,
                   sha=object_id("blob", b""))
        self.assert_error(self.run_audit(tree=recursive), "tree_directory_file_collision")

    def test_recursive_incomplete_snapshot_hash_rejected(self):
        recursive = copy.deepcopy(self.recursive)
        recursive["tree"] = [row for row in recursive["tree"] if row["path"] != "alpha/a.py"]
        report = self.run_audit(tree=recursive)
        self.assert_error(report, "tree_object_hash_mismatch")
        self.assertIn("alpha/a.py", report["incomplete"])
        self.assertNotIn("alpha/a.py", report["missing"])

    def test_proof_required_subtree_absent_is_incomplete_not_missing(self):
        proof = copy.deepcopy(self.proof)
        alpha = next(row for row in proof["trees"][proof["root_sha"]]["tree"]
                     if row["path"] == "alpha")
        del proof["trees"][alpha["sha"]]
        report = self.run_audit(tree=proof)
        self.assert_error(report, "tree_required_evidence_unavailable")
        self.assertEqual(report["incomplete"], ["alpha/a.py", "alpha/nested/b.txt"])
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["counts"]["present"], 3)

    def test_tampered_root_cannot_prove_missing(self):
        proof = copy.deepcopy(self.proof)
        root = proof["trees"][proof["root_sha"]]
        root["tree"] = [row for row in root["tree"] if row["path"] != "z.txt"]
        report = self.run_audit(tree=proof)
        self.assert_error(report, "tree_object_hash_mismatch")
        self.assertEqual(report["counts"]["incomplete"], 5)
        self.assertEqual(report["missing"], [])

    def test_unrelated_opaque_subtree_is_allowed(self):
        commit, _, proof = fixtures({**self.files, "opaque/unused/deep.txt": (b"x", "100644")})
        needed = {proof["root_sha"]}
        for path in self.expected:
            oid = proof["root_sha"]
            for component in path.split("/")[:-1]:
                row = next(row for row in proof["trees"][oid]["tree"] if row["path"] == component)
                oid = row["sha"]
                needed.add(oid)
        proof["trees"] = {oid: raw for oid, raw in proof["trees"].items() if oid in needed}
        report = self.run_audit(tree=proof, commit=commit, pin_tree=commit["tree"]["sha"])
        self.assertEqual(report["status"], "PASS", report["errors"])

    def test_remote_parent_is_file_is_mismatch(self):
        remote = {k: v for k, v in self.files.items() if not k.startswith("alpha/")}
        remote["alpha"] = (b"file", "100644")
        commit, _, proof = fixtures(remote)
        report = self.run_audit(tree=proof, commit=commit, pin_tree=commit["tree"]["sha"])
        self.assertEqual(report["mismatch"], ["alpha/a.py", "alpha/nested/b.txt"])
        self.assertEqual(report["missing"], [])

    def test_proof_flat_entry_names_only(self):
        for name in ("a/b", "..", "/absolute", "back\\slash"):
            with self.subTest(name=name):
                proof = copy.deepcopy(self.proof)
                proof["trees"][proof["root_sha"]]["tree"][0]["path"] = name
                self.assert_error(self.run_audit(tree=proof), "tree_proof_name_unsafe")

    def test_bad_mode_type_and_schema(self):
        for mode, kind, code in ((100644, "blob", "tree_mode_invalid"),
                                 ("100644", "tree", "tree_mode_type_mismatch")):
            proof = copy.deepcopy(self.proof)
            row = proof["trees"][proof["root_sha"]]["tree"][0]
            row.update(mode=mode, type=kind)
            self.assert_error(self.run_audit(tree=proof), code)
        proof = copy.deepcopy(self.proof)
        proof["schema"] = True
        self.assert_error(self.run_audit(tree=proof), "tree_proof_schema_invalid")

    def test_duplicate_json_keys_are_rejected(self):
        path = self.base / "duplicate.json"
        path.write_text('{"path": 1, "path": 2}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            checker.load_json(path)

    def test_nonfinite_json_is_rejected(self):
        path = self.base / "nonfinite.json"
        path.write_text('{"size": NaN}')
        with self.assertRaisesRegex(ValueError, "non-finite"):
            checker.load_json(path)

    def test_cli_pin_override_and_deterministic_json(self):
        args = self.subprocess_args()
        first = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        saved = (self.base / "report.json").read_bytes()
        second = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(saved, (self.base / "report.json").read_bytes())
        self.assertEqual(first.stdout, second.stdout)

    def test_cli_wrong_commit_exit_nonzero(self):
        commit = {**self.commit, "sha": "2" * 40}
        result = subprocess.run(self.subprocess_args(commit=commit), capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads((self.base / "report.json").read_text())["status"], "FAIL")

    def test_cli_malformed_json_fails_with_report(self):
        args = self.subprocess_args()
        (self.base / "tree.json").write_text('{"sha":')
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        report = json.loads((self.base / "report.json").read_text())
        self.assert_error(report, "input_json_invalid")

    def test_cli_refuses_output_source_and_hardlink(self):
        args = self.subprocess_args()
        args[-1] = str(self.source / "z.txt")
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.source / "z.txt").read_bytes(), b"")
        alias = self.base / "alias-out"
        os.link(self.source / "z.txt", alias)
        args[-1] = str(alias)
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.source / "z.txt").read_bytes(), b"")

    def test_fixed_actual_96b0548_proof_regression(self):
        here = Path(__file__).resolve().parent
        freeze = here.parent / "same_host_m16_combined_20261017_freeze_4ce98ed5"
        needed = [here / "commit.json", here / "tree-proof.json", freeze / "FULL_SOURCE_HASHES.json"]
        if not all(path.is_file() for path in needed):
            self.skipTest("saved original evidence is not installed beside the standalone test")
        report = checker.audit(freeze / "reconstructed_cold_check",
                               checker.load_json(needed[2]), checker.load_json(needed[0]),
                               checker.load_json(needed[1]))
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["expected_file_count"], 379)
        self.assertEqual(report["counts"]["present"], 378)
        self.assertEqual(report["missing"],
                         ["candidates/qwen2_resident_matrix/portable_official_producer/gate.py"])
        self.assertEqual(report["mismatch"], [])
        self.assertEqual(report["incomplete"], [])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["verified_tree_response_count"], 84)
        self.assertTrue(report["tree_integrity_verified"])


if __name__ == "__main__":
    unittest.main()
