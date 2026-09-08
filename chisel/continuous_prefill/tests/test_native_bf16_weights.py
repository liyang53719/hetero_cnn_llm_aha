#!/usr/bin/env python3
"""Packing and descriptor tests. These are not numerical RTL results."""
import copy, hashlib, json, os, struct, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pack_owner_bf16_weights import convert, pack_words
from pack_owner_multilayer_fixture import pack_layers
from heteronpu.descriptor_chain import DescriptorRecord

class NativeWeightsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(tempfile.mkdtemp(prefix='native_weights_',dir=os.environ.get('TEST_OUTPUT_ROOT')))
        cls.shape=dict(H=1536,F=8960,HEADS=12,KVHEADS=2,HD=128,MAX_TOKENS=1024)
        cls.old=cls.root/'fp32';cls.base=pack_layers(cls.shape,16,2,cls.old,0)
    def test_rne_ties_and_sign(self):
        xs=[0,0x80000000,0x3f808000,0x3f818000,0xbf808000,0x00008000]
        expected=[0,0x8000,0x3f80,0x3f82,0xbf80,0]
        self.assertEqual(list(struct.unpack('<6H',pack_words(struct.pack('<6I',*xs)))),expected)
    def test_reject_nonfinite_overflow_and_truncation(self):
        for u in [0x7f800000,0xff800000,0x7fc00001,0x7f7fffff,0xff7fffff]:
            with self.subTest(u=u),self.assertRaises(ValueError):pack_words(struct.pack('<I',u))
        with self.assertRaises(ValueError):pack_words(b'123')
    def test_public_descriptor_and_graph_preserved(self):
        dst=self.root/'bf16';m=convert(self.old,dst)
        self.assertEqual((dst/'host_commands.bin').read_bytes(),(self.old/'host_commands.bin').read_bytes())
        self.assertEqual(m['schedule'],self.base['schedule'])
        self.assertEqual(m['weight_contract']['weights'].__len__(),14)
        self.assertEqual(sum(t['bytes'] for t in m['weight_contract']['weights'].values()),187170816)
        for n,t in self.base['tensors'].items():
            self.assertEqual(m['tensors'][n]['address'],t['address'])
        raw=(dst/'host_descriptors.bin').read_bytes();old=(self.old/'host_descriptors.bin').read_bytes()
        roots={o['roots'][1] for o in m['schedule'] if o['opcode']=='MATRIX_GEMM'}
        changed=set()
        for i in range(m['descriptors']):
            a=int.from_bytes(old[16*i:16*i+16],'little');b=int.from_bytes(raw[16*i:16*i+16],'little')
            if a!=b:
                changed.add(i);self.assertEqual(a^b,2 << (56+52))
        self.assertEqual(changed,roots)
        self.assertEqual(m['tensors']['l1_x']['address'],m['tensors']['l0_y']['address'])
        with self.assertRaises(ValueError):convert(self.old,dst)
    def test_reject_missing_table_bytes(self):
        bad=self.root/'bad';bad.mkdir()
        (bad/'manifest.json').write_text(json.dumps(self.base))
        (bad/'host_descriptors.bin').write_bytes(b'\0'*16)
        (bad/'host_commands.bin').write_bytes((self.old/'host_commands.bin').read_bytes())
        with self.assertRaises(ValueError):convert(bad,self.root/'must_not_exist')
        self.assertFalse((self.root/'must_not_exist').exists())
    def test_reject_changed_command(self):
        import shutil
        bad=self.root/'bad_cmd';shutil.copytree(self.old,bad)
        raw=bytearray((bad/'host_commands.bin').read_bytes());raw[0]^=1;(bad/'host_commands.bin').write_bytes(raw)
        with self.assertRaises(ValueError):convert(bad,self.root/'reject_command')
        self.assertFalse((self.root/'reject_command').exists())

if __name__=='__main__':unittest.main(verbosity=2)
