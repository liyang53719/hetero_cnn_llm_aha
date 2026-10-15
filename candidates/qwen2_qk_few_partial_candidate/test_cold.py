import json
from pathlib import Path
import sys
import unittest
from candidates.qwen2_qk_few_partial_candidate import model
class ColdTests(unittest.TestCase):
    def test_registered_two_graphs_six_cases(self):
        c=model.CONFIG;self.assertEqual(c['partials'],[2,4]);self.assertEqual(len(c['cases']),3)
        self.assertEqual(len(set(v['seed'] for v in c['cases'])),3)
    def test_one_total_budget(self):
        self.assertEqual(model.CONFIG['limits']['total_cpu_seconds'],120)
        self.assertEqual(model.CONFIG['limits']['total_output_bytes'],64<<20)
    def test_pilot_and_stop_are_total(self):
        s=(model.HERE/'probe.py').read_text()
        self.assertIn('if projected<=95',s)
        self.assertIn('if cpu_used()>110',s)
        self.assertIn('resource.setrlimit(resource.RLIMIT_CPU,(120,120))',s)
        self.assertIn('594432/(16*128)',s)
        self.assertIn('INCOMPLETE_PROBABILITY_BUDGET',s)
    def test_cold(self):
        self.assertIsNone(model.compile_library('/tmp/not-created'))
        self.assertNotIn('numpy',sys.modules);self.assertNotIn('torch',sys.modules)
    def test_rng_fixed(self):
        self.assertEqual(model.splitmix64(0),(0x9e3779b97f4a7c15,0xe220a8397b1dcdaf))
    def test_order_and_capacity(self):
        s=(model.HERE/'kernel.cpp').read_text()
        self.assertIn('float partial[128]',s);self.assertIn('int k=P*t+p',s)
        self.assertIn('exact_fma(from(uint32_t(w[k*width+base+c])<<16),a,partial[c*P+p])',s)
        self.assertIn('float dot=partial[c*P]+0.0f',s)
    def test_no_dynamic_selection(self):
        c=model.CONFIG;self.assertEqual(c['selection'],'REPORT_ALL_SIX_CASES_WITHOUT_GRAPH_OR_SEED_SELECTION')
        self.assertEqual(c['ordered_graph']['window_boundary_clear'],'FORBIDDEN')
if __name__=='__main__':unittest.main()
