"""Test-only exact selected-preparation inverse, before frozen historical proofs.

Every new and old statement sequence is independently hash-pinned. Only exact,
unique reviewed fragments are replaced. Unknown changes are left in the tree
for the unchanged historical hashes to reject; callers are never mutated.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / 'acceptance_tests/fixtures/selected_host'
FIXTURES = {'controller/cloud_flow.py': {'fixture': 'controller_cloud_flow.py.txt', 'sha256': '167492d0814fbd74e4a32f7911bf6db081ff25842feba0457048d436ef8917b9'}, 'numeric/numeric_tail.py': {'fixture': 'numeric_numeric_tail.py.txt', 'sha256': '00324b9f753f0f2b9031177afb49315602e399452650ab2d5307a7819fce9354'}}
PRE_SELECTION_AST_SHA256 = {'controller/cloud_flow.py': '5df0e4e5dda592102500c1243fa1e7a8a5403e4a13aa25d420903d79ac5a4199', 'numeric/numeric_tail.py': 'cb548659f7c78feeea42e820456b216f9126cb9fc61aa70ac01519dd98fff0b4'}
DELTA_SHA256 = 'd610b5c1f895d9aeec28f6ceedb0db944ba685d27616b2d5c0bece0ad9884c09'


def fingerprint(body):
    return hashlib.sha256(ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False).encode()).hexdigest()


def reviewed_delta(test):
    raw = (FIXTURE_DIR / 'reviewed_delta.json').read_bytes()
    test.assertEqual(hashlib.sha256(raw).hexdigest(), DELTA_SHA256, 'frozen selected-host reviewed delta')
    return json.loads(raw)


def frozen_source(test, relative):
    fixture = FIXTURES[relative]
    raw = (FIXTURE_DIR / fixture['fixture']).read_bytes()
    test.assertEqual(hashlib.sha256(raw).hexdigest(), fixture['sha256'], 'frozen pre-selection source: ' + relative)
    return ast.parse(raw)


def fragment_matches(tree, wanted):
    wanted_dump = [ast.dump(node, include_attributes=False) for node in wanted]
    matches = []
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if not isinstance(value, list) or not value or not all(isinstance(node, ast.stmt) for node in value):
                continue
            dumps = [ast.dump(node, include_attributes=False) for node in value]
            for index in range(len(value) - len(wanted) + 1):
                if dumps[index:index + len(wanted)] == wanted_dump:
                    matches.append((value, index))
    return matches


def undo_selected_host(test, tree, relative):
    tree = copy.deepcopy(tree)
    if relative not in FIXTURES:
        return tree
    frozen_source(test, relative)
    for row in reversed(reviewed_delta(test)[relative]):
        wanted = ast.parse(row['new_source']).body
        replacement = ast.parse(row['old_source']).body
        test.assertEqual(fingerprint(wanted), row['new_sha256'], 'fixed selected-host fragment')
        test.assertEqual(fingerprint(replacement), row['old_sha256'], 'fixed pre-selection replacement')
        matches = fragment_matches(tree, wanted)
        test.assertEqual(len(matches), 1, 'one exact selected-host fragment: ' + row['new_sha256'])
        container, index = matches[0]
        container[index:index + len(wanted)] = copy.deepcopy(replacement)
    return tree


def selected_host_tree(test, path, relative):
    return undo_selected_host(test, ast.parse(path.read_text()), relative)
