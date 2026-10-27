"""Pure synthetic packaging controls: no Scala, JVM, class, model or arithmetic run."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

S = Path(__file__).with_name("assemble_sources.py")
spec = importlib.util.spec_from_file_location("source_assembly", S)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.rec = self.root / "reconstructed"
        self.repo.mkdir()
        self.rec.mkdir()
        self.out = self.root / "out"
        self.manifest = {"schema": 1}
        for stage, count in [("production19", 19), ("dependency_sources8", 8)]:
            rows = []
            for i in range(count):
                kind = "reconstructed" if i == 0 else "repository"
                name = f"Fixture{stage}{i}.scala"
                body = ("// synthetic source fixture " + name + "\n").encode()
                ((self.rec if i == 0 else self.repo) / name).write_bytes(body)
                rows.append({"name": name, "kind": kind, "path": name,
                             "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
            self.manifest[stage] = rows

    def run_assembly(self):
        return m.assemble(self.manifest, self.repo, self.rec, self.out)

    def rejected(self):
        with self.assertRaises((ValueError, KeyError)):
            self.run_assembly()
        self.assertFalse(self.out.exists())

    def test_exact(self):
        receipt = self.run_assembly()
        self.assertEqual([len(receipt['stages'][k]) for k in ('production19', 'dependency_sources8')], [19, 8])
        for stage in receipt['stages']:
            for r in receipt['stages'][stage]:
                self.assertEqual(hashlib.sha256((self.out / stage / r['name']).read_bytes()).hexdigest(), r['sha256'])

    def test_hash(self):
        self.manifest['production19'][0]['sha256'] = '0' * 64
        self.rejected()

    def test_size(self):
        self.manifest['production19'][0]['bytes'] += 1
        self.rejected()

    def test_count(self):
        self.manifest['production19'].pop()
        self.rejected()

    def test_duplicate(self):
        self.manifest['production19'][1] = copy.deepcopy(self.manifest['production19'][0])
        self.rejected()

    def test_traversal(self):
        self.manifest['production19'][0]['path'] = '../outside.scala'
        self.rejected()

    def test_absolute(self):
        self.manifest['production19'][0]['path'] = str(self.root / 'absolute.scala')
        self.rejected()

    def test_source_symlink(self):
        r = self.manifest['production19'][0]
        (self.rec / 'alias.scala').symlink_to(self.rec / r['path'])
        r['path'] = 'alias.scala'
        self.rejected()

    def test_input_root_symlink(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.repo, target_is_directory=True)
        self.repo = alias
        self.rejected()

    def test_overlap(self):
        self.out = self.repo / 'out'
        self.rejected()

    def test_existing_output(self):
        self.out.mkdir()
        with self.assertRaises(ValueError):
            self.run_assembly()
        self.assertEqual(list(self.out.iterdir()), [])

    def test_kind(self):
        self.manifest['production19'][0]['kind'] = 'opaque_class_cache'
        self.rejected()

    def test_non_scala(self):
        self.manifest['production19'][0]['name'] = 'Fixture.class'
        self.rejected()

    def test_schema(self):
        self.manifest['schema'] = 2
        self.rejected()


if __name__ == '__main__':
    unittest.main()
