# SPDX-License-Identifier: Apache-2.0
"""Validation-tool negative tests. These fixtures are not DUT execution proof."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/"scripts/verify_production_chain.py"
spec=importlib.util.spec_from_file_location("production_verifier",path)
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

def receipt():
    # Deterministic parser fixture; real DUT evidence is stored independently.
    counts,macs,physical=v.counts('tiny',16)
    lines=[]
    for i,(name,n) in enumerate(zip(v.NAMES,counts)):
        lines += [f'STAGE_CHECK phase={i} name={name} values={n} max_abs=0 rel_l2=0 bit_diffs=0 cycle={(i+1)*20000}',
                  f'STAGE_MEMORY phase={i} reads=100 write_acks={n//16} visible_bytes={n*4}']
    writes=sum(counts)//16
    lines += [f'PINNED_IDMA_BLOCK transfers={1500+writes} external_read_beats=1500 external_write_beats={writes} full_backend=1',
              f'DDR_GUARD_PASS visible_write_bytes={sum(counts)*4} host_intermediate_writes=0',
              f'CONTINUOUS_QWEN2_BLOCK_PASS tokens=16 hidden=64 ffn=128 heads=2 kv_heads=1 phases=15 checked_fp32={sum(counts)} bit_diffs=0 max_abs=0 cycles=299994 macs={macs} read_bytes=96000 write_bytes={sum(counts)*4} request_stalls=2 response_delay_cycles=7 hash=0 host_intermediate_writes=0 full_model=0 canonical_512_array=1 executed_macs={physical}']
    return '\n'.join(lines)+'\n'

class EvidenceTest(unittest.TestCase):
    def test_valid_scoped_fixture(self): self.assertEqual(v.parse_log(receipt(),'tiny',16)['final']['checked_fp32'],'16896')
    def test_real_shape_formula(self):
        c,m,p=v.counts('real',16);self.assertEqual(sum(c),663552);self.assertEqual(m,749101056);self.assertGreater(p,m)
    def test_wrong_profile(self):
        with self.assertRaises(ValueError):v.parse_log(receipt(),'real',16)
    def test_wrong_runtime_length(self):
        with self.assertRaises(ValueError):v.parse_log(receipt(),'tiny',17)
    def test_reject_fields(self):
        for old,new in [('canonical_512_array=1','canonical_512_array=0'),('full_backend=1','full_backend=0'),('max_abs=0','max_abs=nan'),('bit_diffs=0','bit_diffs=1'),('host_intermediate_writes=0','host_intermediate_writes=1'),('full_model=0','full_model=1'),('request_stalls=2','request_stalls=0'),('response_delay_cycles=7','response_delay_cycles=0'),('cycles=299994','cycles=1'),('macs=607232','macs=1'),('executed_macs=1146880','executed_macs=1'),('ffn=128','ffn=80'),('write_acks=64','write_acks=63'),('visible_bytes=4096','visible_bytes=4032'),('transfers=2556','transfers=1'),('external_read_beats=1500','external_read_beats=1499')]:
            with self.subTest(field=old):
                self.assertIn(old,receipt())
                with self.assertRaises((ValueError,KeyError)):v.parse_log(receipt().replace(old,new),'tiny',16)
    def test_missing_phase(self):
        text='\n'.join(x for x in receipt().splitlines() if not x.startswith('STAGE_CHECK phase=7 '))
        with self.assertRaises(ValueError):v.parse_log(text,'tiny',16)
    def test_duplicate_phase(self):
        with self.assertRaises(ValueError):v.parse_log(receipt().replace('phase=7 ','phase=6 '),'tiny',16)
    def test_phase_name_swap(self):
        with self.assertRaises(ValueError):v.parse_log(receipt().replace('name=o ','name=r '),'tiny',16)
    def test_missing_ack_coverage(self):
        with self.assertRaises(ValueError):v.parse_log(receipt().replace('STAGE_MEMORY phase=7','INCOMPLETE phase=7'),'tiny',16)
    def test_duplicate_completion(self):
        with self.assertRaises(ValueError):v.parse_log(receipt()+receipt().splitlines()[-1]+'\n','tiny',16)
    def test_fatal(self):
        for text in ['BLOCK_FAIL: wrong','%Error','Fatal','Assertion failed']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):v.parse_log(receipt()+text,'tiny',16)
    def test_duplicate_key(self):
        with self.assertRaises(ValueError):v.parse_log(receipt().replace('ffn=128','ffn=128 ffn=128'),'tiny',16)
    def test_invalid_tokens(self):
        for t in [0,-1,1025,True,16.0]:
            with self.subTest(t=t):
                with self.assertRaises(ValueError):v.counts('tiny',t)
if __name__=='__main__':unittest.main()
