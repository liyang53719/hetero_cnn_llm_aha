"""Pure description tests. No tool invocation, output directory or native loading."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

D = Path(__file__).resolve().parent
SOURCE = (D / 'recipe.py').read_bytes()
recipe = types.ModuleType('native_recipe_verified_tests')
recipe.__file__ = str(D / 'recipe.py')
exec(compile(SOURCE, recipe.__file__, 'exec', dont_inherit=True, optimize=0), recipe.__dict__)
MODULES, FRAGMENTS, TEST_SOURCES = recipe.load_fragments()


class DescriptionOnly(unittest.TestCase):
    def reject(self, change):
        for original in FRAGMENTS:
            value = copy.deepcopy(original)
            change(value)
            with self.assertRaises((ValueError, KeyError, TypeError)):
                recipe.validate_fragment(value)

    def test_fixed_complete_contracts(self):
        result = recipe.describe(FRAGMENTS)
        self.assertEqual([v['component'] for v in result['components']], ['matrix_icg', 'idma'])
        self.assertFalse(result['execution_authority'])
        self.assertFalse(result['portable_build_executed'])
        self.assertEqual(sum(len(v['stages']) for v in FRAGMENTS), 223)
        self.assertTrue(all(v['unresolved_prerequisites'] for v in FRAGMENTS))

    def test_render_preserves_order_tokens_and_inputs(self):
        before = copy.deepcopy(FRAGMENTS)
        rows = recipe.render(FRAGMENTS)['stages']
        expected = [dict(component=v['component'], **s) for v in FRAGMENTS for s in v['stages']]
        self.assertEqual(rows, expected)
        self.assertEqual(FRAGMENTS, before)
        self.assertTrue(any('$ORIGIN/../lib' in token for row in rows for token in row['argv']))

    def test_source_output_rejected(self):
        self.reject(lambda v: v['stages'][0]['argv'].extend(['-o', '{repo}/oops.o']))

    def test_escaped_output_rejected(self):
        self.reject(lambda v: v['stages'][0]['argv'].extend(['-o', '{build}/../../oops.o']))

    def test_absolute_input_rejected(self):
        self.reject(lambda v: v['stages'][0]['argv'].append('/unreviewed/input.sv'))

    def test_bad_placeholder_rejected(self):
        self.reject(lambda v: v['stages'][0]['argv'].append('{tool:cxx'))

    def test_unknown_role_rejected(self):
        self.reject(lambda v: v['stages'][0]['inputs'].append('unknown.input'))

    def test_forward_role_rejected(self):
        self.reject(lambda v: v['stages'][0]['inputs'].append(v['stages'][-1]['outputs'][0]))

    def test_duplicate_output_rejected(self):
        self.reject(lambda v: v['stages'][1]['outputs'].append(v['stages'][0]['outputs'][0]))

    def test_empty_preconditions_rejected(self):
        self.reject(lambda v: v['stages'][0].update(preconditions=[]))

    def test_removed_tool_provenance_rejected(self):
        self.reject(lambda v: v['tools'][0].pop('prior_binary_sha256', None))

    def test_removed_unresolved_blockers_rejected(self):
        self.reject(lambda v: v.update(unresolved_prerequisites=[]))

    def test_asserted_authority_and_bool_int_rejected(self):
        for value in (True, 0):
            self.reject(lambda v: v.update(execution_authority=value))

    def test_unreviewed_field_rejected(self):
        self.reject(lambda v: v.update(extra='not part of the fixed description'))

    def test_missing_and_duplicate_components_rejected(self):
        for values in ([], FRAGMENTS[:1], FRAGMENTS + FRAGMENTS[:1]):
            with self.assertRaises(ValueError):
                recipe.describe(values)

    def test_changed_manifest_rejected_before_module_exec(self):
        real_read = Path.read_bytes
        def altered(path):
            if path == D / 'FRAGMENTS.json':
                return b'{"schema":"UNRUN_NATIVE_RECIPE_SOURCES_V1","fragments":[]}'
            return real_read(path)
        with mock.patch.object(Path, 'read_bytes', altered), mock.patch.object(recipe.types, 'ModuleType', side_effect=AssertionError('module created before manifest verification')):
            with self.assertRaisesRegex(ValueError, 'stable exact source buffer'):
                recipe.load_fragments()

    def test_changed_fragment_rejected_before_module_exec(self):
        real_read = Path.read_bytes
        def altered(path):
            if path == D / 'matrix_icg.py':
                return b'raise RuntimeError("must never execute")\n'
            return real_read(path)
        with mock.patch.object(Path, 'read_bytes', altered), mock.patch.object(recipe.types, 'ModuleType', side_effect=AssertionError('unverified module executed')):
            with self.assertRaisesRegex(ValueError, 'stable exact source buffer'):
                recipe.load_fragments()

    def test_describe_and_render_have_no_io(self):
        with mock.patch('builtins.open', side_effect=AssertionError('unexpected IO')), mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('unexpected read')), mock.patch.object(Path, 'write_bytes', side_effect=AssertionError('unexpected write')):
            recipe.describe(FRAGMENTS)
            recipe.render(FRAGMENTS)

    def test_no_execution_or_mutating_api_in_shared_source(self):
        tree = ast.parse(SOURCE)
        forbidden_imports = {'os', 'subprocess', 'socket', 'urllib', 'requests', 'ctypes', 'shutil'}
        forbidden_calls = {'Popen', 'system', 'check_call', 'check_output', 'run', 'write_bytes', 'write_text', 'mkdir', 'unlink', 'rmdir', 'rename', 'replace'}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name.split('.')[0] for a in node.names] if isinstance(node, ast.Import) else [node.module.split('.')[0]]
                self.assertTrue(forbidden_imports.isdisjoint(names))
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                self.assertNotIn(name, forbidden_calls)


def component_tests():
    # Execute only the exact pinned test buffers. Their top-level imports/reads
    # receive the same verified module/catalog buffers, without sys.path changes.
    manifest = json.loads(recipe.checked_bytes(D / 'FRAGMENTS.json', {'sha256': recipe.FRAGMENTS_SHA256}))
    cached = {}
    for row in manifest['fragments']:
        for key in ('module', 'catalog'):
            if key in row:
                pin = row[key]
                path = D / recipe.relative(pin['path'])
                cached[path] = recipe.checked_bytes(path, pin)
    tests = unittest.TestSuite()
    def exact_read(path):
        if path not in cached:
            raise AssertionError('test attempted an undeclared read: ' + str(path))
        return cached[path]
    with mock.patch.dict(sys.modules, MODULES), mock.patch.object(Path, 'read_bytes', exact_read):
        for index, (filename, raw) in enumerate(TEST_SOURCES):
            mod = types.ModuleType('native_recipe_component_tests_' + str(index))
            mod.__file__ = filename
            exec(compile(raw, filename, 'exec', dont_inherit=True, optimize=0), mod.__dict__)
            tests.addTests(unittest.defaultTestLoader.loadTestsFromModule(mod))
    return tests


if __name__ == '__main__':
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(DescriptionOnly), component_tests()])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
