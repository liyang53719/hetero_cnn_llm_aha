import ast,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import prepare
class PrepareTests(unittest.TestCase):
    def test_zero_fuzz_original_profiles_and_accumulator_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'composed';result=prepare.compose(root)
            self.assertEqual(result['status'],'PASS_SOURCE_COMPOSITION')
            from .check_native import load_service
            identity=load_service(root).source_identity()
            self.assertEqual(identity['accumulator_banks'],5)
            old=(prepare.ROOT/prepare.TARGETS[0]).read_text();new=(root/prepare.TARGETS[0]).read_text()
            import re
            for include in re.findall(r'#include \"([^\"]+)\"',new):
                dependency=(root/prepare.TARGETS[0]).parent/include
                self.assertTrue(dependency.is_file())
                self.assertIn(str(dependency.resolve().relative_to(root.resolve())),prepare.SOURCES)
            # Original profile1 and legacy arithmetic/control suffix is exact.
            suffix='  if(normalProfile==1){\n';self.assertEqual(old[old.index(suffix):],new[new.index(suffix):])
            begin='extern "C" int matrix_normal_group_v1'
            self.assertEqual(old[:old.index(begin)],new[:new.index(begin)])
            self.assertEqual(new.count('static float accum'),0)
            self.assertEqual(new.count('const unsigned columns=normalOpcode==0x23?256:128;'),1)
            self.assertIn('profile==2',new);self.assertIn('normalProfile==2',new)
            oldp=ast.parse((prepare.ROOT/prepare.TARGETS[1]).read_text());newp=ast.parse((root/prepare.TARGETS[1]).read_text())
            class Normalize(ast.NodeTransformer):
                def visit_Compare(self,n):
                    n=self.generic_visit(n)
                    if isinstance(n.left,ast.Attribute) and n.left.attr=='profile' and len(n.ops)==1 and isinstance(n.ops[0],ast.In) and ast.dump(n.comparators[0])==ast.dump(ast.Tuple(elts=[ast.Constant(1),ast.Constant(2)],ctx=ast.Load())):
                        n.ops=[ast.Eq()];n.comparators=[ast.Constant(1)]
                    return n
            self.assertEqual(ast.dump(oldp),ast.dump(Normalize().visit(newp)))
    def test_source_mutation_rejected(self):
        read=Path.read_bytes;target=prepare.ROOT/prepare.BACKEND[1]
        with patch.object(Path,'read_bytes',lambda p:read(p)+(b'\n' if p==target else b'')):
            with self.assertRaises(ValueError):prepare.check()
    def test_wrong_generated_identity_rejects(self):
        pins=prepare.check();pins['generated'][prepare.TARGETS[0]]='0'*64
        with tempfile.TemporaryDirectory() as d,patch.object(prepare,'check',return_value=pins):
            with self.assertRaisesRegex(ValueError,'generated source identity'):prepare.compose(Path(d)/'new')
    def test_existing_destination_rejected(self):
        # Ordinary composition is strict and refuses pre-existing targets.
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):prepare.compose(Path(d))
if __name__=='__main__':unittest.main()
