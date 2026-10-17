#!/usr/bin/env python3
"""Adapter-only deterministic stdlib tests; requires the fixed source checkout.

The supplied checkout is never modified. Each mutation uses a private fixture
copy of only the 465 pinned files. No model, Git, network or native program runs.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).absolute().parent


def load(name):
    path = HERE / (name + '.py')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


B = load('build_source_view')
V = load('verify_artifact')
CHECKOUT = None


class SourceViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.full, cls.map_raw = B.load_pins()
        root_fd = B.open_directory(CHECKOUT)
        try:
            cls.fixture = {}
            for name, digest in cls.full.items():
                raw, _ = B.read_checked(root_fd, name)
                B.need(B.sha(raw) == digest, 'TEST_CHECKOUT_PIN')
                cls.fixture[name] = raw
        finally:
            os.close(root_fd)
        cls.selected = next(n for n in sorted(cls.full) if n != B.CONTRACT)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='source-view-adapter-')
        self.root = Path(self.temp.name)
        self.checkout = self.root / 'checkout'
        self.checkout.mkdir(mode=0o700)
        self.output = self.root / 'view'
        for name, raw in self.fixture.items():
            path = self.checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(raw)

    def tearDown(self):
        self.temp.cleanup()

    def reject(self, code=None, checkout=None, output=None, package=HERE):
        context = self.assertRaisesRegex(B.SourceViewError, code) if code else self.assertRaises((B.SourceViewError, OSError))
        with context:
            B.build(checkout or self.checkout, output or self.output, package)
        self.assertFalse((self.output / 'FULL_SOURCE_HASHES.json').exists())

    def test_01_complete465_exact_private_view(self):
        result = B.build(self.checkout, self.output)
        self.assertEqual(result['source_files'], 465)
        self.assertEqual(result['source_map_sha256'], B.MAP_SHA)
        self.assertFalse(result['git_head_authenticated'])
        self.assertFalse(result['runtime_executed'])
        self.assertEqual((self.output / 'FULL_SOURCE_HASHES.json').read_bytes(), self.map_raw)
        self.assertEqual(set(p.name for p in self.output.iterdir()), {'source', 'FULL_SOURCE_HASHES.json'})
        self.assertEqual(V.load_sources(self.output)[0], self.full)
        for path in [self.output, *self.output.rglob('*')]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)
        for name in self.full:
            original = (self.checkout / name).stat()
            copied = (self.output / 'source' / name).stat()
            self.assertNotEqual((original.st_dev, original.st_ino), (copied.st_dev, copied.st_ino))
            self.assertEqual(copied.st_nlink, 1)

    def test_02_missing_file(self):
        (self.checkout / self.selected).unlink()
        self.reject()

    def test_03_changed_bytes(self):
        (self.checkout / self.selected).write_bytes(b'mutated')
        self.reject('SOURCE_HASH')

    def test_04_oversize_source(self):
        with (self.checkout / self.selected).open('wb') as stream:
            stream.truncate(B.MAX_FILE + 1)
        self.reject('FILE_TYPE_SIZE')

    def test_05_hardlink_source(self):
        os.link(self.checkout / self.selected, self.root / 'alias')
        self.reject('FILE_TYPE_SIZE')

    def test_06_file_symlink(self):
        path = self.checkout / self.selected
        target = self.root / 'target'
        path.rename(target)
        path.symlink_to(target)
        self.reject()

    def test_07_directory_symlink(self):
        path = self.checkout / self.selected.split('/')[0]
        target = self.root / 'target'
        path.rename(target)
        path.symlink_to(target, target_is_directory=True)
        self.reject()

    def test_08_checkout_symlink(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.checkout, target_is_directory=True)
        self.reject(checkout=alias)

    def test_09_checkout_ancestor_symlink(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.reject(checkout=alias / 'checkout')

    def test_10_output_inside_checkout(self):
        self.reject('OUTPUT_CHECKOUT_OVERLAP', output=self.checkout / 'view')

    def test_11_output_equals_checkout(self):
        self.reject('OUTPUT_CHECKOUT_OVERLAP', output=self.checkout)

    def test_12_output_ancestor_checkout(self):
        self.reject('OUTPUT_CHECKOUT_OVERLAP', output=self.root)

    def test_13_existing_directory(self):
        self.output.mkdir()
        (self.output / 'preserve').write_bytes(b'KEEP')
        self.reject('OUTPUT_EXISTS')
        self.assertEqual((self.output / 'preserve').read_bytes(), b'KEEP')

    def test_14_existing_file(self):
        self.output.write_bytes(b'KEEP')
        self.reject('OUTPUT_EXISTS')
        self.assertEqual(self.output.read_bytes(), b'KEEP')

    def test_15_output_dangling_symlink(self):
        self.output.symlink_to(self.root / 'absent')
        self.reject('OUTPUT_EXISTS')
        self.assertTrue(self.output.is_symlink())

    def test_16_output_ancestor_symlink(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.reject(output=alias / 'view')

    def test_17_contract_malformed(self):
        for raw in (b'{}', b'{"inputs":{},"inputs":{}}', b'\xff', b'{"x":NaN}'):
            with self.subTest(raw=raw):
                (self.checkout / B.CONTRACT).write_bytes(raw)
                self.reject('INPUT_CONTRACT_PIN')

    def test_18_contract_repin_mutation_rejected(self):
        contract = json.loads(self.fixture[B.CONTRACT])
        contract['inputs'][self.selected] = B.sha(b'mutated')
        (self.checkout / B.CONTRACT).write_bytes(B.encoded(contract))
        (self.checkout / self.selected).write_bytes(b'mutated')
        self.reject('INPUT_CONTRACT_PIN')

    def test_19_wrong_published_map(self):
        package = self.root / 'package'
        shutil.copytree(HERE, package, copy_function=shutil.copyfile)
        (package / 'FULL_SOURCE_HASHES.json').write_bytes(b'{}\n')
        self.reject('PACKAGE_MAP_PIN', package=package)

    def test_20_wrong_pins(self):
        package = self.root / 'package'
        shutil.copytree(HERE, package, copy_function=shutil.copyfile)
        pins = json.loads((package / 'pins.json').read_bytes())
        pins['commit'] = '0' * 40
        (package / 'pins.json').write_bytes(B.encoded(pins))
        self.reject('PACKAGE_PINS', package=package)

    def test_21_unlisted_extras_and_stale_bytecode_not_copied(self):
        for name in ('unlisted.py', '__pycache__/verify_artifact.cpython-313.pyc', 'verify_artifact.pyc'):
            path = self.checkout / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'raise RuntimeError("must never execute")\n')
        B.build(self.checkout, self.output)
        self.assertEqual({p.relative_to(self.output / 'source').as_posix() for p in (self.output / 'source').rglob('*') if p.is_file()}, set(self.full))
        self.assertFalse(list(self.output.rglob('*.pyc')))
        self.assertFalse((self.output / 'source/unlisted.py').exists())

    def test_22_fifo_rejected_without_blocking(self):
        path = self.checkout / self.selected
        path.unlink()
        os.mkfifo(path)
        self.reject('FILE_TYPE_SIZE')

    def test_23_same_bytes_replacement_after_preflight(self):
        original = B.write_exclusive
        replaced = False
        def replace(root_fd, name, raw):
            nonlocal replaced
            original(root_fd, name, raw)
            if not replaced:
                path = self.checkout / self.selected
                temporary = path.with_name(path.name + '.replacement')
                temporary.write_bytes(self.fixture[self.selected])
                temporary.replace(path)
                replaced = True
        with mock.patch.object(B, 'write_exclusive', replace):
            self.reject('SOURCE_DRIFT')

    def test_24_in_place_drift_after_copy(self):
        original = B.write_exclusive
        changed = False
        def change(root_fd, name, raw):
            nonlocal changed
            original(root_fd, name, raw)
            if not changed:
                (self.checkout / self.selected).write_bytes(b'changed after copy')
                changed = True
        with mock.patch.object(B, 'write_exclusive', change):
            self.reject('SOURCE_DRIFT')

    def test_25_strict_json(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'\xff', b'[' * 1100):
            with self.subTest(raw=raw[:30]), self.assertRaises(B.SourceViewError):
                B.strict(raw)

    def test_26_relative_path_rejections(self):
        for name in ('', '/', '/a', '../a', './a', 'a//b', 'a/../b', 'a/./b', 'a/', 'a\\b', 'a\x00b', 'C:/a', 'a:b', 'a b'):
            with self.subTest(name=name), self.assertRaises(B.SourceViewError):
                B.source_map({name: '0' * 64}, 1)

    def test_27_map_collision_digest_and_count(self):
        for value, count in (({'a': '0'*64, 'a/b': '1'*64}, 2), ({'a': 'x'*64}, 1), ({'a': '0'*64}, 2), ({'a': True}, 1), ([], 0)):
            with self.subTest(value=value), self.assertRaises(B.SourceViewError):
                B.source_map(value, count)

    def test_28_preserved_checker_pins(self):
        pins, _, _ = B.load_pins()
        self.assertEqual(len([n for n in pins['preserved_files'] if n.endswith('.py')]), 7)
        for name, digest in pins['preserved_files'].items():
            self.assertEqual(B.sha((HERE / name).read_bytes()), digest)
        self.assertEqual(V.MAP_SHA, B.MAP_SHA)
        self.assertEqual(V.COMMIT, B.COMMIT)

    def test_29_input_byte_drift_during_read(self):
        path = self.checkout / self.selected
        root_fd = B.open_directory(self.checkout)
        original = B.os.read
        changed = False
        def change(fd, size):
            nonlocal changed
            raw = original(fd, size)
            if not changed:
                with path.open('ab') as stream:
                    stream.write(b'x')
                changed = True
            return raw
        try:
            with mock.patch.object(B.os, 'read', change), self.assertRaises(B.SourceViewError):
                B.read_checked(root_fd, self.selected)
        finally:
            os.close(root_fd)

    def test_30_size_limit_and_traversal_root(self):
        with self.assertRaisesRegex(B.SourceViewError, 'JSON_SIZE'):
            B.strict(b' ' * (B.MAX_FILE + 1))
        with self.assertRaisesRegex(B.SourceViewError, 'ROOT_PATH'):
            B.absolute(str(self.checkout) + '/../checkout')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True)
    args, remainder = parser.parse_known_args()
    CHECKOUT = args.checkout
    unittest.main(argv=[sys.argv[0], *remainder], verbosity=2)
