import importlib.util
import pathlib
import unittest
p=pathlib.Path(__file__).with_name('consumer_owned.py')
spec=importlib.util.spec_from_file_location('candidate',p)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class Coverage(unittest.TestCase):
    def result(self, mismatch=0):
        return {'comparisons': {'final': {'byte_mismatches': mismatch}},
                'router': {k: {'byte_mismatches':0} for k in
                           ('ids','normalized_bf16_weights','bf16_dense_logits')}}
    def test_moe_matched_subset_is_incomplete(self):
        r=self.result();c.classify_observed_profile(r,True)
        self.assertEqual(r['status'],'INCOMPLETE')
        self.assertEqual(r['observed_subset_status'],'BITWISE_MATCH_DIAGNOSTIC')
        self.assertFalse(r['numerical_pass'])
    def test_moe_mismatch_remains_visible(self):
        r=self.result(1);c.classify_observed_profile(r,True)
        self.assertEqual(r['status'],'INCOMPLETE')
        self.assertEqual(r['observed_subset_status'],'BITWISE_MISMATCH_DIAGNOSTIC')
        self.assertEqual(r['comparisons']['final']['byte_mismatches'],1)
    def test_claimed_marker_cannot_enable_missing_reader(self):
        r=self.result();r['router']['raw_fp32_selection_scores']={'coverage':'COMPLETE','byte_mismatches':0}
        c.classify_observed_profile(r,True);self.assertEqual(r['status'],'INCOMPLETE')
    def test_non_moe_keeps_diagnostic(self):
        for n,status in ((0,'BITWISE_MATCH_DIAGNOSTIC'),(1,'BITWISE_MISMATCH_DIAGNOSTIC')):
            r=self.result(n);c.classify_observed_profile(r,False);self.assertEqual(r['status'],status)
    def test_real_main_calls_guard_and_never_exits_success(self):
        import ast
        tree=ast.parse(p.read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        self.assertEqual(sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='classify_observed_profile' for n in ast.walk(main)),1)
        self.assertTrue(any(isinstance(n,ast.Raise) and isinstance(n.exc,ast.Call) and isinstance(n.exc.func,ast.Name) and n.exc.func.id=='SystemExit' and n.exc.args[0].value==2 for n in ast.walk(main)))
if __name__=='__main__':unittest.main()
