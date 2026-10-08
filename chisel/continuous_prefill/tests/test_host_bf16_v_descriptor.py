# SPDX-License-Identifier: Apache-2.0
import dataclasses
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from host_bf16_v_descriptor import HostVBinding,build_host_v_descriptor,parse_host_v_descriptor

class HostVDescriptorTests(unittest.TestCase):
    def binding(self,**kw):
        d=dict(rows=128,token_base=47,token_count=81,activation_ddr=0x100000,weight_ddr=0x200000,output_ddr=0x400000)
        return HostVBinding(**(d|kw))
    def test_roundtrip_native_windows(self):
        for m in (1,15,16,17,80,81,128):
            for base in (0,m-1):
                b=self.binding(rows=m,token_base=base,token_count=m-base)
                c,r=build_host_v_descriptor(b,first_index=32,event_signal=4)
                self.assertEqual(parse_host_v_descriptor(c.pack(),{i:x.pack() for i,x in r.items()}),b)
                self.assertEqual(b.job['writeBytes'],(m-base)*1024)
                self.assertEqual(b.job['a'],b.activation_ddr+base*2048)
    def test_invalid_windows_and_bounds(self):
        for kw in ({'rows':0},{'rows':129},{'token_count':0},{'token_count':129},{'token_base':48},
                   {'activation_ddr':0x100002},{'weight_ddr':0x200002},{'output_ddr':0x400002},
                   {'output_ddr':0x100000},{'activation_ddr':(1<<56)-64}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):self.binding(**kw)
    def test_reject_candidate_version_modes_and_local_addresses(self):
        c,r=build_host_v_descriptor(self.binding())
        for payload in (r[5].payload^3,r[5].payload^(1<<8),r[5].payload^(2<<8),r[5].payload^(1<<10),r[5].payload|(0xc1<<52),r[5].payload|(1<<71)):
            mutated=r|{5:dataclasses.replace(r[5],payload=payload)}
            with self.subTest(payload=payload),self.assertRaises(ValueError):parse_host_v_descriptor(c,mutated)
        for i in range(6,15):
            for payload in (r[i].payload|64,r[i].payload|(1<<64),r[i].payload^(1<<56)):
                with self.subTest(i=i,payload=payload),self.assertRaises(ValueError):parse_host_v_descriptor(c,r|{i:dataclasses.replace(r[i],payload=payload)})
    def test_reject_cycles_short_chains_aliases_reserved_and_aux(self):
        c,r=build_host_v_descriptor(self.binding())
        for i,next_index in ((5,5),(8,6),(14,15),(4,0xffffff),(7,0xffffff),(3,99)):
            with self.subTest(i=i,next_index=next_index),self.assertRaises(ValueError):
                parse_host_v_descriptor(c,r|{i:dataclasses.replace(r[i],next_index=next_index)})
        for i in range(21):
            with self.subTest(i=i),self.assertRaises(ValueError):parse_host_v_descriptor(c,r|{i:dataclasses.replace(r[i],flags=1)})
        with self.assertRaises(ValueError):parse_host_v_descriptor(dataclasses.replace(c,src1=c.src0),r)
        with self.assertRaises(ValueError):parse_host_v_descriptor(c,r|{4:dataclasses.replace(r[4],payload=r[4].payload|(1<<26))})

if __name__=='__main__':unittest.main()
