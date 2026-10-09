"""Small public GDN ABI, alias, dependency and malformed-chain rejection tests."""
import dataclasses as dc
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_bf16_gdn_descriptor import *


class HostGdnDescriptorTests(unittest.TestCase):
    def dense(self, **kw):
        return HostGdnDenseBinding(**(dict(tokens=1,activation_ddr=0x10000,weight_ddr=0x1000000,output_ddr=0x2000000)|kw))
    def conv(self, **kw):
        return HostGdnConvBinding(**(dict(tokens=1,activation_ddr=0x2000000,weight_ddr=0x3000000,output_ddr=0x4000000,
                                         history_input_ddr=0x5000000,history_output_ddr=0x6000000,cold=True)|kw))
    def test_public_roundtrip_all_supported_token_extents(self):
        for tokens in (1,2,15,16,17,128):
            for binding in (self.dense(tokens=tokens),self.conv(tokens=tokens),self.conv(tokens=tokens,cold=False,expected_generation=19)):
                c,r=build_host_gdn_descriptor(binding,first_index=37,event_wait=2,event_signal=9)
                self.assertEqual(binding,parse_host_gdn_descriptor(c.pack(),{i:x.pack() for i,x in r.items()}))
    def chain(self):
        return [self.dense(),self.conv(),self.dense(activation_ddr=0x80000,output_ddr=0x7000000),
                self.conv(activation_ddr=0x7000000,output_ddr=0x8000000,history_input_ddr=0x6000000,history_output_ddr=0x9000000,cold=False,expected_generation=1)]
    def test_true_four_command_chain(self):
        bs=self.chain(); cs,rs=build_gdn_commands(bs)
        self.assertEqual(len(rs),60)
        self.assertEqual([c.src0 for c in cs],[0,12,30,42])
        self.assertEqual([(c.event_wait,c.event_signal) for c in cs],[(0,1),(1,2),(2,3),(3,4)])
        self.assertEqual([parse_host_gdn_descriptor(c,rs) for c in cs],bs)
    def test_invalid_tensor_alias_context_generation(self):
        for kw in ({'tokens':0},{'tokens':129},{'context':1},{'cold':True,'expected_generation':1},
                   {'history_input_ddr':0x2000000},{'history_output_ddr':0x4000000},{'output_ddr':0x4000020}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):self.conv(**kw)
        with self.assertRaises(ValueError): self.dense(weight_ddr=0x10000)
    def test_policy_and_history_root_rejections(self):
        for binding,index in ((self.dense(),5),(self.conv(),4)):
            c,r=build_host_gdn_descriptor(binding)
            for bit_index in ((0,8,16,24,25,32,64) if index==5 else (0,8,16,25,64)):
                mutated=dc.replace(r[index],payload=r[index].payload^(1<<bit_index))
                with self.subTest(bit=bit_index),self.assertRaises(ValueError):parse_host_gdn_descriptor(c,r|{index:mutated})
        c,r=build_host_gdn_descriptor(self.conv())
        for state in (r[5].payload|(1<<48),12|(12<<24),0|(15<<24),0xffffff|(15<<24)):
            with self.assertRaises(ValueError):parse_host_gdn_descriptor(c,r|{5:dc.replace(r[5],payload=state)})
        with self.assertRaises(ValueError):parse_host_gdn_descriptor(c,r|{8:dc.replace(r[8],next_index=9)})
    def test_chain_requires_actual_prior_dma_addresses(self):
        for index,changed in ((1,self.conv(activation_ddr=0xa000000)),(3,self.conv(cold=False,expected_generation=1)),
                              (2,self.dense(activation_ddr=0x80000,output_ddr=0x4000000))):
            bs=self.chain(); bs[index]=changed
            with self.assertRaises(ValueError):build_gdn_commands(bs)

if __name__=='__main__':unittest.main()
