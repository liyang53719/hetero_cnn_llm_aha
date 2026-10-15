import copy
import unittest
from . import public_summary as p

def fixture():
    comparisons=[dict(case=n,**dict(zip(p.COMPARE_KEYS,v))) for n,v in zip(('M1','M2'),((0,0,10,18432,8192,12288,2048),(0,0,10,49152,16384,36864,4096)))]
    cases=[]
    for name in p.POSITIVE+p.NEGATIVE:
        if name in p.NEGATIVE:
            cases.append(dict(name=name,injected=True,terminal=dict(status='Memory' if name=='memory_error' else 'Protocol')));continue
        rows=1 if name.startswith('M1') else 2;hits=160 if rows==1 else 512;fills=rows*32;acks=fills+hits;stalled=name.endswith('STALLED')
        cache=dict(capacity_bytes=704512,kv_reserved_bytes=262144,valid_metadata_bytes=512,local_packet_bytes=64,outstanding_limit=1,
          bank_word_bits=256,banks_per_packet=2,minimum_response_edges=1,outstanding=0,valid_lines=0,
          counts=dict(fill_requests=fills,fill_commits=fills,read_requests=hits,bank_write_accesses=2*fills,bank_read_accesses=2*hits,
                      consume_acks=acks,response_latency_edges=acks*(3 if stalled else 1)))
        cases.append(dict(name=name,terminal=dict(status=None,executed_macs=73728 if rows==1 else 221184),
          owner=dict(accepted=dict(matrix_requests=144 if rows==1 else 432),resident_cache=cache),write_ack_bytes=rows*6144,local_hold_edges=1152 if stalled else 0))
    return dict(status='PASS_SMALL_SYNTHETIC_RESIDENT_EQUIVALENCE',full_m128_executed=False,fullblock_executed=False,
                rtl_executed=False,ci_executed=False,comparisons=comparisons,cases=cases)

class Public(unittest.TestCase):
    def test_valid(self):self.assertEqual(p.sanitize(fixture())['negative_cases_passed'],9)
    def test_exact_numbers(self):
        for bad in ('private/path',{},[],True,None,-1,float('nan'),float('inf'),1.0):
            r=fixture();r['comparisons'][0]['observed_fields']=bad
            with self.assertRaises(ValueError):p.sanitize(r)
    def test_missing_or_reordered_cases(self):
        r=fixture();r['cases']=r['cases'][:-1]
        with self.assertRaises(ValueError):p.sanitize(r)
        r=fixture();r['comparisons'].reverse()
        with self.assertRaises(ValueError):p.sanitize(r)
    def test_failed_negative_and_live_claim(self):
        for key,val in [('injected',False),('injected','private/path')]:
            r=fixture();r['cases'][-1][key]=val
            with self.assertRaises(ValueError):p.sanitize(r)
        r=fixture();r['full_m128_executed']=True
        with self.assertRaises(ValueError):p.sanitize(r)
    def test_new_fields_do_not_leak(self):
        import json
        r=fixture();r['private']='private/path';r['cases'][0]['secret']={'path':'private/path'}
        self.assertNotIn('private',json.dumps(p.sanitize(r)))
if __name__=='__main__':unittest.main()
