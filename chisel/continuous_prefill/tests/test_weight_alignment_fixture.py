#!/usr/bin/env python3
"""Public descriptor/alias checks; not numerical hardware simulation."""
import copy,json,os,re,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from align_owner_weight_fixture import transform
from pack_owner_multilayer_fixture import pack_layers
from heteronpu.descriptor_chain import DescriptorRecord,RecordType,validate_descriptor_chain

class AlignmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(tempfile.mkdtemp(prefix='weight_alignment_',dir=os.environ.get('OWNER_TEST_ARTIFACTS')))
    def fixture(self,real=False):
        root=Path(tempfile.mkdtemp(prefix='case_',dir=self.root));s=dict(H=1536,F=8960,HEADS=12,KVHEADS=2,HD=128,MAX_TOKENS=1024) if real else dict(H=64,F=128,HEADS=2,KVHEADS=1,HD=32,MAX_TOKENS=1024)
        pack_layers(s,16,2,root/'src',9467985920);return root
    def check_alignment(self,real):
        d=self.fixture(real);old=json.loads((d/'src/manifest.json').read_text());new=transform(d/'src',d/'aligned')
        self.assertEqual((d/'src/host_commands.bin').read_bytes(),(d/'aligned/host_commands.bin').read_bytes())
        weights={o['b'] for o in old['schedule'] if o['opcode']=='MATRIX_GEMM'}
        self.assertEqual(len(weights),14)
        for name in weights:self.assertEqual(new['tensors'][name]['address']%1024,0)
        self.assertEqual(new['schedule'],old['schedule'])
        self.assertEqual(new['tensors']['l1_x']['address'],new['tensors']['l0_y']['address'])
        self.assertNotIn('l1_x',new['allocations'])
        last=new['metadataLimit']
        for name in new['allocations']:
            t=new['tensors'][name];self.assertGreaterEqual(t['address'],last+64);last=t['address']+t['words']*4
        raw=(d/'aligned/host_descriptors.bin').read_bytes();records={i:DescriptorRecord.unpack(int.from_bytes(raw[16*i:16*i+16],'little')) for i in range(430)}
        for op in new['schedule']:
            for name,root in zip((op['a'],op['b'],op['dst']),op['roots']):
                if name is None:continue
                ch=validate_descriptor_chain(root,records);r=ch[0][1];a=new['tensors'][name]['address']
                self.assertEqual((r.payload&((1<<48)-1))|(((r.payload>>64)&255)<<48),a)
        # Every numeric allocation address in the generated C++ header was rebound.
        header=(d/'aligned/owner_fixture.h').read_text()
        for name in new['allocations']:
            self.assertIn('{"'+name+'",'+str(new['tensors'][name]['address'])+'ULL',header)
    def test_tiny2_descriptor_and_guards(self):self.check_alignment(False)
    def test_real2_descriptor_and_guards(self):self.check_alignment(True)
    def test_64_byte_mode_is_identical(self):
        d=self.fixture();transform(d/'src',d/'again',64)
        for n in ('host_commands.bin','host_descriptors.bin','owner_fixture.h'):self.assertEqual((d/'src'/n).read_bytes(),(d/'again'/n).read_bytes())
    def test_reject_existing_output(self):
        d=self.fixture();(d/'old').mkdir()
        with self.assertRaises(ValueError):transform(d/'src',d/'old')
    def test_reject_unapproved_alignment(self):
        for n in (0,1,128,True,2048):
            d=self.fixture()
            with self.assertRaises(ValueError):transform(d/'src',d/'new',n)
if __name__=='__main__':unittest.main(verbosity=2)
