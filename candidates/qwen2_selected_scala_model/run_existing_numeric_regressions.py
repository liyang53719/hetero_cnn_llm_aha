"""Run all 15 unchanged attention_matrix_batch numerical regression tests.

Required: --source-root RAW_CHECKOUT. Run with <=20 CPU seconds, <=256 MiB,
and one CPU. This runner reuses the pinned stdlib-only exact Fraction/RNE
backend from test_schedule_numeric; it does not load NumPy/native/bootstrap
module bodies. Original tests and the original behavioral model ASTs remain
unchanged. These are existing arithmetic/behavioral regressions, not native
MatrixService, full-block M128 numerical, RTL, physical, or timing acceptance.
"""
import ast
from collections import Counter
from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest

# Isolated python (-I) intentionally omits the script directory from sys.path.
# Load this candidate-local harness explicitly, without adding search paths.
_harness_path = Path(__file__).resolve().with_name('test_schedule_numeric.py')
_harness_spec = importlib.util.spec_from_file_location('test_schedule_numeric', _harness_path)
if _harness_spec is None or _harness_spec.loader is None:
    raise RuntimeError('candidate-local numeric harness could not be loaded')
harness = importlib.util.module_from_spec(_harness_spec)
sys.modules[_harness_spec.name] = harness
_harness_spec.loader.exec_module(harness)


# The shared loader consumes --source-root and verifies all raw definitions it
# needs before any AST execution, while preserving unittest's remaining argv.
model_path = harness.SOURCES / 'attention_matrix_batch/model.py'
model_pin = harness.INPUT_PINS['sources'][
    'candidates/qwen2_resident_matrix/attention_matrix_batch/model.py']
model_bytes = model_path.read_bytes()
harness.need(len(model_bytes) == model_pin['bytes'] and
             hashlib.sha256(model_bytes).hexdigest() == model_pin['sha256'],
             'existing behavioral model differs from fixed raw source pin')
model = ModuleType('reviewed_attention_matrix_batch_model')
model.__file__ = str(model_path)
model.__dict__.update(Counter=Counter, dataclass=dataclass)
sys.modules[model.__name__] = model
model_tree = ast.parse(model_bytes, filename=str(model_path))
model_body = [node for node in model_tree.body
              if isinstance(node, (ast.Assign, ast.ClassDef, ast.FunctionDef))]
exec(compile(ast.Module(body=model_body, type_ignores=[]), str(model_path), 'exec'),
     model.__dict__)

# Every helper and all test methods are copied as unchanged AST nodes. __file__
# is the original test's path because one unchanged test inspects its imports.
original_tests = ModuleType('reviewed_attention_matrix_batch_test_model')
original_tests.__dict__.update(harness.NS)
original_tests.__dict__.update(
    __name__='reviewed_attention_matrix_batch_test_model', candidate=model,
    unittest=unittest, Path=Path, __file__=str(harness.COLD_SOURCE))
sys.modules[original_tests.__name__] = original_tests
namespace = original_tests.__dict__
helpers = ('softmax', 'expected_qk', 'expected_pv', 'batched_attention')
classes = ('OriginalGeneratorEquivalenceTests', 'BatchedNumericalBoundaryTests',
           'MappingAndCountTests', 'DomainAndFaultTests')
harness.definitions(harness.COLD_SOURCE, helpers + classes, namespace)
for name in classes:
    globals()[name] = namespace[name]

if __name__ == '__main__':
    unittest.main()
