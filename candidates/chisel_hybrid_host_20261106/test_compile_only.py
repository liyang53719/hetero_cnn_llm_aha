"""Read-only source/build contract tests. Never run Java or download inputs."""
from pathlib import Path
import hashlib
import json
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

D = Path(__file__).resolve().parent
SOURCE = D / 'compile_only.py'
MODULE = {'__file__': str(SOURCE), '__name__': 'source_compile_contract'}
exec(compile(SOURCE.read_bytes(), str(SOURCE), 'exec'), MODULE)


class SourceContract(unittest.TestCase):
    def test_complete_selection_without_execution(self):
        with patch('subprocess.run', side_effect=AssertionError('no process')), patch('urllib.request.urlopen', side_effect=AssertionError('no network')):
            sources, jars = MODULE['selection']()
        self.assertEqual(len(sources), 204)
        self.assertEqual(len(jars), 107)
        self.assertEqual(len({r['maven_path'] for r in jars}), 106)

    def test_source_identity_mismatch(self):
        row = json.loads((D / 'SOURCES.json').read_bytes())['sources'][0]
        changed = dict(row, sha256='0' * 64)
        with self.assertRaises(ValueError):
            MODULE['exact'](MODULE['REPO'] / row['path'], changed)

    def test_noncanonical_paths(self):
        for value in ('../escape.scala', '/absolute.scala', 'a/../b.scala', './a.scala'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE['relative'](value)

    def test_no_test_main_or_artifact_execution_in_compiler(self):
        source = SOURCE.read_text()
        self.assertIn("'scala.tools.nsc.Main'", source)
        self.assertEqual(source.count('subprocess.run('), 2)
        self.assertIn("[str(java), '-version']", source)
        self.assertNotIn('shell=True', source)
        self.assertNotIn('upload-artifact', source)

    def test_child_limits_are_not_called_in_parent(self):
        class ObservedCompilerCall(Exception):
            pass
        calls = []
        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[-1] == '-version':
                return SimpleNamespace(stdout=b'openjdk version "21.0.1"', returncode=0)
            self.assertIs(kwargs['preexec_fn'], MODULE['child_limits'])
            raise ObservedCompilerCall()
        rows, jars = MODULE['selection']()
        fake_inputs = [(row, '/not-executed/' + row['maven_path']) for row in jars]
        with tempfile.TemporaryDirectory(prefix='source-contract-') as output:
            with patch('subprocess.run', side_effect=fake_run), patch('resource.setrlimit', side_effect=AssertionError('parent limits must not change')), patch.dict(MODULE, fetch_jars=lambda *_: fake_inputs):
                with self.assertRaises(ObservedCompilerCall):
                    MODULE['compile_sources'](rows, jars, Path(output), Path('/usr/bin/true'))
        self.assertEqual(len(calls), 2)

    def test_helpers_are_exactly_the_selected_thirty(self):
        rows = json.loads((D / 'SOURCES.json').read_bytes())['sources']
        selected = {r['path'].split('/')[-1]: r for r in rows if r['phase'] == 'helpers'}
        actual = {p.name: p for p in (D / 'scala').glob('*.scala')}
        self.assertEqual(set(selected), set(actual))
        self.assertEqual(len(actual), 30)
        for name, path in actual.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), selected[name]['sha256'])


if __name__ == '__main__':
    unittest.main()
