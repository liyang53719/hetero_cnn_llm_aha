"""Host-only preservation proof and fail-closed inverse mutation coverage."""
import ast
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import selected_host_preservation as preservation

D = Path(__file__).resolve().parent


class SelectedHostPreservation(unittest.TestCase):
    def source(self, relative):
        return ast.parse((D / relative).read_text())

    def test_exact_inverse_restores_frozen_pre_selection_ast_without_mutating_input(self):
        for relative in preservation.FIXTURES:
            with self.subTest(relative=relative):
                tree = self.source(relative)
                before = ast.dump(tree, include_attributes=True)
                restored = preservation.undo_selected_host(self, tree, relative)
                self.assertEqual(ast.dump(tree, include_attributes=True), before)
                self.assertEqual(ast.dump(restored), ast.dump(preservation.frozen_source(self, relative)))
                self.assertEqual(preservation.fingerprint(restored.body), preservation.PRE_SELECTION_AST_SHA256[relative])

    def test_every_reviewed_fragment_missing_mutated_duplicated_is_rejected(self):
        for relative, rows in preservation.reviewed_delta(self).items():
            for row in rows:
                wanted = ast.parse(row['new_source']).body
                for case in ('missing', 'mutated', 'duplicate'):
                    with self.subTest(relative=relative, fragment=row['new_sha256'], case=case):
                        tree = self.source(relative)
                        matches = preservation.fragment_matches(tree, wanted)
                        self.assertEqual(len(matches), 1)
                        container, index = matches[0]
                        if case == 'missing':
                            del container[index:index + len(wanted)]
                        elif case == 'duplicate':
                            container[index:index] = copy.deepcopy(wanted)
                        else:
                            names = [node for statement in container[index:index + len(wanted)]
                                     for node in ast.walk(statement) if isinstance(node, ast.Name)]
                            self.assertTrue(names)
                            names[0].id = 'UNREVIEWED_SELECTED_HOST_MUTATION'
                        with self.assertRaisesRegex(AssertionError, 'one exact selected-host fragment: ' + row['new_sha256']):
                            preservation.undo_selected_host(self, tree, relative)

    def test_frozen_sources_and_reviewed_delta_reject_byte_mutation(self):
        files = ['reviewed_delta.json'] + [row['fixture'] for row in preservation.FIXTURES.values()]
        for changed in files:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                for name in files:
                    raw = (preservation.FIXTURE_DIR / name).read_bytes()
                    (root / name).write_bytes(raw + (b'\n' if name == changed else b''))
                relative = next((key for key, row in preservation.FIXTURES.items() if row['fixture'] == changed),
                                'controller/cloud_flow.py')
                with patch.object(preservation, 'FIXTURE_DIR', root), self.assertRaisesRegex(AssertionError, 'frozen'):
                    preservation.undo_selected_host(self, self.source(relative), relative)

    def test_fragment_and_replacement_hashes_are_independently_checked(self):
        for field in ('new_source', 'old_source'):
            rows = preservation.reviewed_delta(self)
            rows['controller/cloud_flow.py'][-1][field] += '\nUNREVIEWED_INVERSE = 1'
            with self.subTest(field=field), patch.object(preservation, 'reviewed_delta', return_value=rows):
                with self.assertRaisesRegex(AssertionError, 'fixed'):
                    preservation.undo_selected_host(self, self.source('controller/cloud_flow.py'), 'controller/cloud_flow.py')

    def test_unknown_top_level_and_nested_statements_reach_original_historical_hash(self):
        import test_stage_return_retention as historical
        for relative in preservation.FIXTURES:
            for location in ('module', 'run'):
                with self.subTest(relative=relative, location=location):
                    tree = self.source(relative)
                    body = tree.body if location == 'module' else next(
                        node.body for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
                    body.extend(ast.parse('UNREVIEWED_SELECTED_HOST_LEFTOVER = 1').body)
                    restored = preservation.undo_selected_host(self, tree, relative)
                    self.assertIn('UNREVIEWED_SELECTED_HOST_LEFTOVER', ast.unparse(restored))
                    self.assertNotEqual(preservation.fingerprint(restored.body), preservation.PRE_SELECTION_AST_SHA256[relative])
                    restored = historical.undo_reviewed_aggregate_cap_delta(self, restored, relative)
                    restored = historical.undo_reviewed_finite_log_delta(self, restored, relative)
                    restored = historical.undo_reviewed_v3_delta(self, restored, relative)
                    with self.assertRaises(AssertionError) as caught:
                        historical.Test().check_original_ast(relative, restored)
                    self.assertIn(historical.BASE_AST[relative], str(caught.exception))

    def test_selected_inverse_is_not_a_baseline_or_partial_delta_fallback(self):
        for relative in preservation.FIXTURES:
            with self.subTest(relative=relative), self.assertRaisesRegex(AssertionError, 'one exact selected-host fragment'):
                preservation.undo_selected_host(self, preservation.frozen_source(self, relative), relative)

    def test_unrelated_source_is_returned_unchanged_as_copy(self):
        tree = ast.parse('UNRELATED = 1')
        restored = preservation.undo_selected_host(self, tree, 'controller/flow.py')
        self.assertIsNot(tree, restored)
        self.assertEqual(ast.dump(tree), ast.dump(restored))


if __name__ == '__main__':
    unittest.main()
