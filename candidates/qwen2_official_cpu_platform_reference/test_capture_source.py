"""Cold source derivation and validator tests; never invoke the capture body."""
import ast
from pathlib import Path
import unittest
from . import capture_source as S
from . import policy as P
from . import validator as V

class SourceTests(unittest.TestCase):
    def source(self):return S.derive((V.ROOT/S.CAPTURE).read_bytes(),(V.ROOT/S.RECIPE).read_bytes())

    def test_exact_reversible_math_source_and_ast(self):
        result=self.source();proof=result['proof']
        self.assertTrue(proof['original_capture_byte_reconstruction']);self.assertTrue(proof['original_capture_ast_reconstruction'])
        self.assertFalse(proof['official_math_rewritten']);self.assertEqual(proof['legacy_gate_replacements'],2)
        original=(V.ROOT/S.CAPTURE).read_text();derived=result['capture_source']
        # Original AST execution calls, semantic checks and resource/write gates
        # all survive verbatim; only the enumerated new policy edits are allowed.
        for line in original.splitlines():
            if any(marker in line for marker in ('execute(','semantic check','alias equality','exact exported mask',
                'BF16 residual','BF16 product','BF16 final','payload bytes','per-capture cap','69 MiB pair cap')):
                self.assertIn(line,derived)
        self.assertNotIn("'prior18_fresh_hash_matches':True",derived)
        self.assertIn('LEGACY_CONTRACT_DIFFERENT',derived)
        self.assertIn('LEGACY_CONTRACT_EQUAL',derived)

    def test_drift_refused(self):
        capture=(V.ROOT/S.CAPTURE).read_bytes();recipe=(V.ROOT/S.RECIPE).read_bytes()
        for a,b in ((capture+b'\n',recipe),(capture,recipe+b'\n')):
            with self.assertRaises(ValueError):S.derive(a,b)

    def test_real_cold_load_requires_capability_and_new_contract(self):
        capture,validate,proof=S.load(V.ROOT)
        self.assertTrue(callable(capture));self.assertTrue(callable(validate))
        with self.assertRaisesRegex(RuntimeError,'capability'):capture(V.ROOT,{},Path('/unused'))
        self.assertTrue(proof['original_capture_ast_reconstruction'])

    def test_new_validator_removes_only_legacy_hash_gate(self):
        source=self.source()['validation_source']
        self.assertNotIn("pins['prior18_expectations']",source)
        for marker in ('exact29 observations','fixed export name','non-placeholder observed hash',
                       'observed stride','observed storage','cold K equality','cold V fixed layout',
                       'PV fixed layout','exact mask hashes'):
            self.assertIn(marker,source)
        tree=ast.parse(source)
        self.assertEqual(tree.body[0].name,'validate_new_observations')

if __name__=='__main__':unittest.main()
