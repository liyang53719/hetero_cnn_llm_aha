#!/usr/bin/env python3
"""Run the seven preserved checker sources against a caller-supplied source view.

All seven sources and all original test methods remain byte-for-byte unchanged.
Sources are hash-checked and copied into a private temporary test package first.
A fresh sibling compatibility view is built from the supplied view, so original
fixture-relative paths work without any pre-existing cloud freeze directory.
Synthetic tests establish rejection behavior, never actual execution evidence.
"""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).absolute().parent


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


B = load(HERE / 'build_source_view.py', 'portable_source_builder')


def run(freeze):
    pins, _, _ = B.load_pins(HERE)
    package_fd = B.open_directory(HERE)
    try:
        checked = {}
        for name, digest in pins['preserved_files'].items():
            raw, _ = B.read_checked(package_fd, name)
            B.need(B.sha(raw) == digest, 'PRESERVED_SOURCE_PIN')
            if name.endswith('.py'):
                checked[name] = raw
        B.need(len(checked) == 7, 'PRESERVED_SOURCE_COUNT')
    finally:
        os.close(package_fd)
    with tempfile.TemporaryDirectory(prefix='offline-verifier-tests-') as temporary:
        root = Path(temporary) / 'preserved_tests'
        root.mkdir(mode=0o700)
        compatibility = Path(temporary) / 'same_host_m128_replay_identity_20261017_freeze_cded2ae5'
        B.build(Path(freeze) / 'source', compatibility)
        root_fd = B.open_directory(root)
        try:
            for name, raw in checked.items():
                B.write_exclusive(root_fd, name, raw)
        finally:
            os.close(root_fd)
        verifier = load(root / 'verify_artifact.py', 'verify_artifact')
        verifier.load_sources(freeze)
        load(root / 'identity_schema.py', 'identity_schema')
        load(root / 'test_fixture.py', 'test_fixture')
        suite = unittest.TestSuite()
        for name in ('test_verify_artifact', 'test_identity_schema', 'test_cli'):
            module = load(root / (name + '.py'), name)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        B.need(not list(root.rglob('*.pyc')), 'UNEXPECTED_BYTECODE')
        return result.wasSuccessful()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, required=True)
    args = parser.parse_args()
    try:
        ok = run(args.freeze)
    except (B.SourceViewError, OSError) as error:
        parser.exit(2, f'original tests rejected: {error}\n')
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
