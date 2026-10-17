import unittest
from mapping import *
class Tests(unittest.TestCase):
    def test_q_all_addresses_and_distinct_local_storage(self):
        cells=set()
        for d in range(128):
            x=q_local(d);cells.add((x['bank'],x['word'],x['bank_fp32_lane']))
            self.assertEqual(x['line'],d//16)
        self.assertEqual(len(cells),128)
        for t in range(128):
            for h in range(12):
                for d in range(128):
                    x=ddr_word('q',4096,t,h,d)
                    self.assertEqual(x['byte_address'],4096+4*(1536*t+128*h+d))
                    self.assertEqual(x['fp32_lane'],d%16)
    def test_kv_all_words_and_causal_group_tails(self):
        for kind in ('k','v'):
            for t in range(128):
                for h in range(2):
                    for d in range(128):
                        x=ddr_word(kind,0,t,h,d)
                        self.assertEqual(x['beat_address']+4*x['fp32_lane'],4*(256*t+128*h+d))
        for query in range(128):
            covered=[]
            for start in range(0,query+1,16):
                active=min(16,query+1-start)
                covered.extend(start+j for j in range(active))
                self.assertTrue(all(start+j<=query for j in range(active)))
            self.assertEqual(covered,list(range(query+1)))
    def test_scratch_no_alias_all96lines_and_bank_conflicts(self):
        cells=set();lines=set()
        for kind in ('score','prob'):
            for h in range(6):
                for k in range(128):
                    x=scratch(kind,h,k);cell=(x['bank'],x['word'],x['bank_fp32_lane'])
                    self.assertNotIn(cell,cells);cells.add(cell);lines.add(x['line'])
        self.assertEqual(len(cells),1536);self.assertEqual(lines,set(range(4096,4192)))
        for k in range(128):
            self.assertEqual(len({scratch('prob',h,k)['bank'] for h in range(6)}),1)
            self.assertEqual(len({scratch('prob',h,k)['word'] for h in range(6)}),6)
    def test_qk_all_physical_diagonals(self):
        selected=set()
        for j in range(16):
            for r in range(16):
                x=qk_lane(j,r);selected.add((x['result_row'],x['result_col']))
                self.assertEqual(x['endpoint'],j//2)
                self.assertEqual(x['endpoint_col'],16*(j%2)+r)
                self.assertEqual(x['b_register'],16*j+r)
        self.assertEqual(len(selected),256)
    def test_panel_alias_and_pv_endpoints(self):
        self.assertEqual({panel(h,k)['word'] for h in range(6) for k in range(16)},set(range(96)))
        self.assertEqual({inverse(h)['word'] for h in range(6)},set(range(96,102)))
        selected=set()
        for h in range(6):
            for c in range(128):
                x=pv_lane(h,c);self.assertLess(x['endpoint'],4);selected.add((x['result_row'],x['result_col']))
        self.assertEqual(len(selected),768)
    def test_boundaries_fail_closed(self):
        for bad in (True,1.0,-1,128):
            with self.assertRaises(ValueError):q_local(bad)
        for call in (lambda:ddr_word('q',1,0,0,0),lambda:ddr_word('q',2**64-64,127,11,127),lambda:scratch('prob',6,0),lambda:qk_lane(16,0),lambda:panel(0,16),lambda:pv_lane(0,128)):
            with self.assertRaises(ValueError):call()
    def test_no_supply_or_timing_claim(self):
        s=scope()
        for key in ('can_supply','rtl_measured','numerical_execution','accepted_80','accepted_90'):self.assertFalse(s[key])
        self.assertNotIn('cycles',s);self.assertEqual(s['q_staging_heads_existing'],1)
if __name__=='__main__':unittest.main()
