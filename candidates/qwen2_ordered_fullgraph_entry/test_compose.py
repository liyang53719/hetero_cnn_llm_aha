"""Bounded source-only cold tests. No target imports, tensors, native code, or RTL.

python -B test_compose.py --source-root PINNED_BASE/source
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
# Resolve this one sibling explicitly: -I intentionally removes the script
# directory from sys.path. Never use cwd or rewrite the target source prelude.
import importlib.util
_COMPOSER_PATH = Path(__file__).resolve().with_name("compose.py")
_COMPOSER_SPEC = importlib.util.spec_from_file_location("_source_only_composer_under_test", _COMPOSER_PATH)
composer = importlib.util.module_from_spec(_COMPOSER_SPEC)
sys.modules[_COMPOSER_SPEC.name] = composer
_COMPOSER_SPEC.loader.exec_module(composer)
if Path(composer.__file__).resolve() != _COMPOSER_PATH:
    raise RuntimeError("foreign composer import origin")

SOURCE_ROOT = None


class ComposerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="qwen2-source-compose-tests-")
        cls.root = Path(cls.temp.name)
        cls.pins, cls.raw_pins = composer.load_pins(composer.HERE / "SOURCE_PINS.json")
        cls.patch = (composer.HERE / "suffix_dispatch.patch").read_bytes()
        cls.baseline = cls.root / "baseline"
        cls.receipt = composer.compose(SOURCE_ROOT, cls.baseline)
        cls.source = cls.root / "source-fixture"
        shutil.copytree(SOURCE_ROOT, cls.source)
        cls.before = (cls.source / composer.SUFFIX).read_bytes()
        cls.after = (cls.baseline / "source" / composer.SUFFIX).read_bytes()
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        # Only test-owned temporary copies are removed. No baseline-source edits.
        cls.temp.cleanup()

    def fresh(self, label="output"):
        type(self).counter += 1
        return self.root / (label + "-" + str(type(self).counter))

    def reject(self, *, source=None, output=None, pins_path=None, patch_path=None,
               message=None):
        target = output if output is not None else self.fresh()
        was_present = os.path.lexists(target)
        with self.assertRaises((composer.ComposeError, OSError)) as caught:
            composer.compose(source if source is not None else self.source, target,
                             pins_path=pins_path, patch_path=patch_path)
        if message:
            self.assertIn(message, str(caught.exception))
        if not was_present:
            self.assertFalse(os.path.lexists(target), "validation failure created an output")

    def pin_copy(self, edit):
        pins = json.loads(self.raw_pins)
        edit(pins)
        path = self.fresh("pins")
        path.write_bytes(composer.json_bytes(pins))
        return path

    def patch_copy(self, data):
        path = self.fresh("patch")
        path.write_bytes(data)
        return path

    @contextmanager
    def replace_file(self, name, new_bytes):
        path = self.source / name
        original = path.read_bytes()
        try:
            path.write_bytes(new_bytes)
            yield
        finally:
            path.write_bytes(original)

    def test_full_316_file_manifest(self):
        manifest_bytes = (self.baseline / "SOURCE_MANIFEST.json").read_bytes()
        self.assertEqual(composer.digest(manifest_bytes), self.receipt["source_manifest_sha256"])
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["source_file_count"], 316)
        self.assertEqual(set(manifest["source_files"]), set(self.pins["source_files"]))
        self.assertEqual(manifest["changed_relative_paths"], [composer.SUFFIX])
        self.assertEqual(set(path.name for path in self.baseline.iterdir()),
                         {"source", "SOURCE_MANIFEST.json", "COMPOSE_RECEIPT.json"})
        for name, entry in manifest["source_files"].items():
            data = (self.baseline / "source" / name).read_bytes()
            self.assertEqual(entry, {"bytes": len(data), "sha256": composer.digest(data)})
            if name != composer.SUFFIX:
                self.assertEqual(entry, self.pins["source_files"][name])
        self.assertEqual(composer.digest(self.before), self.pins["suffix_pre_sha256"])
        self.assertEqual(composer.digest(self.after), self.pins["suffix_post_sha256"])

    def test_exact_forward_reverse_roundtrip(self):
        self.assertEqual(composer.apply_patch_exact(self.before, self.patch), self.after)
        reverse = []
        for index, line in enumerate(self.patch.splitlines(keepends=True)):
            if index < 2:
                reverse.append(line)
            elif line.startswith(b"@@"):
                old_start, old_count, new_start, new_count = composer.HUNK.fullmatch(line).groups()
                reverse.append(b"@@ -" + new_start + b"," + (new_count or b"1") +
                               b" +" + old_start + b"," + (old_count or b"1") + b" @@\n")
            elif line.startswith(b"-"):
                reverse.append(b"+" + line[1:])
            elif line.startswith(b"+"):
                reverse.append(b"-" + line[1:])
            else:
                reverse.append(line)
        self.assertEqual(composer.apply_patch_exact(self.after, b"".join(reverse)), self.before)

    def test_default_none_signature_without_target_import(self):
        tree = ast.parse(self.after)
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and
                    node.name == "execute_public_suffix")
        defaults = dict(zip((arg.arg for arg in node.args.kwonlyargs), node.args.kw_defaults))
        self.assertIsInstance(defaults["attention_dispatch"], ast.Constant)
        self.assertIsNone(defaults["attention_dispatch"].value)
        self.assertIs(defaults["enable_raw_kv"].value, False)

    def test_no_runtime_or_acceptance_inheritance(self):
        self.assertEqual(self.receipt["composition_status"], "SOURCE_ONLY_COMPOSED")
        self.assertEqual(self.receipt["full_numeric_status"], "TEMP_NOT_EXECUTED")
        self.assertIs(self.receipt["default_enabled"], False)
        self.assertIs(self.receipt["inherited_runtime_pass"], False)
        self.assertTrue(all(value is False for value in self.receipt["execution"].values()))
        self.assertFalse(any(name == "numpy" or name.startswith("numpy.") for name in sys.modules))
        self.assertFalse(any(name.startswith("candidates.") for name in sys.modules))
        self.assertFalse(list(self.baseline.rglob("__pycache__")))

    def test_cold_cli_in_fresh_bounded_interpreter(self):
        target = self.fresh("cold-cli")
        result = subprocess.run([sys.executable, "-B", str(composer.HERE / "compose.py"),
                                 "--source-root", str(SOURCE_ROOT), "--output", str(target)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10, check=False,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        report = json.loads(result.stdout)
        self.assertEqual(report["source_manifest_sha256"], self.receipt["source_manifest_sha256"])
        self.assertEqual((target / "SOURCE_MANIFEST.json").read_bytes(),
                         (self.baseline / "SOURCE_MANIFEST.json").read_bytes())
        self.assertFalse(list(target.rglob("__pycache__")))

    def test_cli_has_no_run_option(self):
        result = subprocess.run([sys.executable, "-B", str(composer.HERE / "compose.py"),
                                 "--source-root", str(SOURCE_ROOT), "--output", str(self.fresh()), "--run"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"unrecognized arguments: --run", result.stderr)

    def test_same_path_rejected(self):
        self.reject(output=self.source, message="must not overlap")

    def test_output_descendant_rejected(self):
        self.reject(output=self.source / "new-child", message="must not overlap")

    def test_output_ancestor_rejected(self):
        self.reject(output=self.root, message="must not overlap")

    def test_output_existing_is_unchanged(self):
        output = self.fresh()
        output.mkdir()
        marker = output / "sentinel"
        marker.write_bytes(b"keep")
        self.reject(output=output, message="refusing overwrite")
        self.assertEqual(marker.read_bytes(), b"keep")
        self.assertEqual(list(output.iterdir()), [marker])

    def test_duplicate_apply_output_rejected(self):
        self.reject(output=self.baseline, message="refusing overwrite")

    def test_already_patched_source_rejected(self):
        self.reject(source=self.baseline / "source", message="byte-count mismatch")

    def test_extra_source_file_rejected(self):
        path = self.source / "unexpected.py"
        try:
            path.write_text("# extra\n")
            self.reject(message="file-set bounds")
        finally:
            path.unlink()

    def test_extra_empty_directory_rejected(self):
        path = self.source / "unexpected-empty-directory"
        try:
            path.mkdir()
            self.reject(message="source directories")
        finally:
            path.rmdir()

    def test_missing_source_rejected(self):
        path = self.source / "LOCAL_SOURCE_POLICY.json"
        saved = path.read_bytes()
        try:
            path.unlink()
            self.reject(message="file-set mismatch")
        finally:
            path.write_bytes(saved)

    def test_same_length_source_corruption_rejected(self):
        name = "LOCAL_SOURCE_POLICY.json"
        before = (self.source / name).read_bytes()
        changed = bytes([before[0] ^ 1]) + before[1:]
        with self.replace_file(name, changed):
            self.reject(message="source hash mismatch")

    def test_wrong_source_file_hash_pin_rejected(self):
        pins_path = self.pin_copy(lambda pins: pins["source_files"]["LOCAL_SOURCE_POLICY.json"].update(
            sha256="0" * 64))
        self.reject(pins_path=pins_path, message="source hash mismatch")

    def test_wrong_source_file_size_pin_rejected(self):
        pins_path = self.pin_copy(lambda pins: pins["source_files"]["LOCAL_SOURCE_POLICY.json"].update(bytes=1))
        self.reject(pins_path=pins_path, message="byte-count mismatch")

    def test_wrong_preimage_pin_rejected(self):
        pins_path = self.pin_copy(lambda pins: pins.update(suffix_pre_sha256="0" * 64))
        self.reject(pins_path=pins_path, message="preimage pin is inconsistent")

    def test_wrong_postimage_pin_rejected(self):
        pins_path = self.pin_copy(lambda pins: pins.update(suffix_post_sha256="0" * 64))
        self.reject(pins_path=pins_path, message="postimage hash mismatch")

    def test_wrong_patch_pin_rejected(self):
        pins_path = self.pin_copy(lambda pins: pins.update(patch_sha256="0" * 64))
        self.reject(pins_path=pins_path, message="patch hash mismatch")

    def test_missing_patch_pin_rejected(self):
        pins_path = self.pin_copy(lambda pins: pins.pop("patch_sha256"))
        self.reject(pins_path=pins_path, message="patch_sha256")

    def test_patch_byte_corruption_rejected(self):
        self.reject(patch_path=self.patch_copy(self.patch + b"\n"), message="patch hash mismatch")

    def test_rebound_wrong_patch_target_rejected(self):
        patch = self.patch.replace(composer.SUFFIX.encode(), b"other.py", 2)
        pins_path = self.pin_copy(lambda pins: pins.update(patch_sha256=composer.digest(patch)))
        self.reject(pins_path=pins_path, patch_path=self.patch_copy(patch), message="only the pinned suffix")

    def test_wrong_hunk_context_rejected(self):
        patch = self.patch.replace(b"     reports = []\n", b"     reports = ()\n")
        self.assertNotEqual(patch, self.patch)
        with self.assertRaisesRegex(composer.ComposeError, "context mismatch"):
            composer.apply_patch_exact(self.before, patch)

    def test_wrong_hunk_count_rejected(self):
        patch = self.patch.replace(b"@@ -180,7 +180,8 @@", b"@@ -180,8 +180,8 @@")
        with self.assertRaisesRegex(composer.ComposeError, "line-count mismatch"):
            composer.apply_patch_exact(self.before, patch)

    def test_wrong_hunk_offset_rejected(self):
        patch = self.patch.replace(b"@@ -180,7 +180,8 @@", b"@@ -180,7 +181,8 @@")
        with self.assertRaisesRegex(composer.ComposeError, "line offset mismatch"):
            composer.apply_patch_exact(self.before, patch)

    def test_patch_second_file_rejected(self):
        with self.assertRaises(composer.ComposeError):
            composer.apply_patch_exact(self.before, self.patch + b"--- a/other.py\n+++ b/other.py\n")

    def test_noncanonical_paths_rejected(self):
        for bad in ("../outside", "/absolute", "a/../b", "a//b", "./a", "a\\b", "bad\npath"):
            with self.subTest(path=bad), self.assertRaises(composer.ComposeError):
                composer._canonical_relative(bad)

    def test_unsafe_pin_path_rejected(self):
        def change(pins):
            pins["source_files"]["../outside"] = pins["source_files"].pop("LOCAL_SOURCE_POLICY.json")
        self.reject(pins_path=self.pin_copy(change), message="relative source path")

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(composer.ComposeError, "duplicate JSON key"):
            composer.read_json(b'{"a": 1, "a": 2}')

    def test_symlink_source_file_rejected(self):
        path = self.source / "LOCAL_SOURCE_POLICY.json"
        saved = path.read_bytes()
        try:
            path.unlink()
            path.symlink_to(Path(SOURCE_ROOT) / "LOCAL_SOURCE_POLICY.json")
            self.reject(message="symlink is forbidden")
        finally:
            path.unlink()
            path.write_bytes(saved)

    def test_symlink_source_root_rejected(self):
        alias = self.fresh("source-link")
        alias.symlink_to(self.source, target_is_directory=True)
        self.reject(source=alias, message="symlink path aliases")

    def test_symlink_output_parent_rejected(self):
        alias = self.fresh("output-parent-link")
        alias.symlink_to(self.root, target_is_directory=True)
        self.reject(output=alias / "new-child", message="symlink path aliases")

    def test_fifo_rejected_without_blocking(self):
        path = self.source / "LOCAL_SOURCE_POLICY.json"
        saved = path.read_bytes()
        try:
            path.unlink()
            os.mkfifo(path)
            self.reject(message="special source file")
        finally:
            path.unlink()
            path.write_bytes(saved)

    def test_header_only_has_no_tensor_payload(self):
        data = (self.source / composer.HEADER_ONLY).read_bytes()
        composer._check_source_content(composer.HEADER_ONLY, data)
        self.assertEqual(len(data), 8 + int.from_bytes(data[:8], "little"))
        with self.assertRaisesRegex(composer.ComposeError, "header-only"):
            composer._check_source_content(composer.HEADER_ONLY, data + b"TENSOR")

    def test_binary_payloads_rejected(self):
        for path, data in (("example.py", b"\x7fELFblah"), ("example.bin", b"text"),
                           ("example.py", b"\xff"), ("example.py", b"\x00"),
                           ("example.npy", b"text")):
            with self.subTest(path=path, data=data), self.assertRaises(composer.ComposeError):
                composer._check_source_content(path, data)

    def test_resource_caps_active(self):
        import resource
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_AS)[0], 256 * 1024 * 1024)
        self.assertLessEqual(resource.getrlimit(resource.RLIMIT_CPU)[0], 20)
        if hasattr(os, "sched_getaffinity"):
            self.assertEqual(len(os.sched_getaffinity(0)), 1)
        self.assertTrue(sys.dont_write_bytecode)

    def test_original_source_still_matches_all_pins(self):
        composer._check_file_set(Path(SOURCE_ROOT), self.pins["source_files"])
        for name, pin in self.pins["source_files"].items():
            data = (Path(SOURCE_ROOT) / name).read_bytes()
            self.assertEqual(len(data), pin["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin["sha256"])


def main():
    global SOURCE_ROOT
    composer.set_resource_limits()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()
    SOURCE_ROOT = args.source_root.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ComposerTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"test_status": "PASS" if result.wasSuccessful() else "FAIL",
                      "tests_run": result.testsRun,
                      "full_numeric_status": "TEMP_NOT_EXECUTED",
                      "source_files": 316,
                      "scope": "source-only composition, exact patch roundtrip, and fail-closed negatives",
                      "resource_limits": {"cpus": 1, "address_space_mib": 256,
                                          "cpu_seconds": 20, "wall_seconds": 25}}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
