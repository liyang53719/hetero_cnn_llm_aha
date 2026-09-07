#!/usr/bin/env python3
"""Public ABI, physical arena and reject-path tests, not hardware simulation."""
from pathlib import Path
import tempfile, unittest, sys, os
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'scripts'))
from pack_owner_block_fixture import pack, Command128, DescriptorRecord, RecordType, NULL_INDEX, validate_descriptor_chain, EXPECTED_LAYER0
class FixtureTest(unittest.TestCase):
    def make(self,shape=None,tokens=16,relocate=0):
        root=Path(os.environ.get('OWNER_TEST_ARTIFACTS','work/owner_fixture_tests'));root.mkdir(parents=True,exist_ok=True)
        out=Path(tempfile.mkdtemp(prefix='case_',dir=root))/'fixture'
        s=shape or dict(H=64,F=128,HEADS=2,KVHEADS=1,HD=32,MAX_TOKENS=1024)
        return out,pack(s,tokens,out,relocate)
    def test_exact_21_existing_opcodes_and_public_roundtrip(self):
        out,m=self.make();raw=(out/'host_commands.bin').read_bytes();db=(out/'host_descriptors.bin').read_bytes()
        records={i:DescriptorRecord.unpack(int.from_bytes(db[i*16:i*16+16],'little')) for i in range(m['descriptors'])}
        self.assertEqual(m['commands'],21);self.assertEqual(m['descriptors'],215)
        self.assertEqual([x['opcode'].lower() for x in m['schedule']],[x.opcode for x in EXPECTED_LAYER0])
        for i in range(21):
            c=Command128.from_bytes(raw[i*16:i*16+16]);self.assertEqual(c.to_bytes(),raw[i*16:i*16+16]);self.assertEqual((c.event_wait,c.event_signal),(i,i+1))
            for root in (c.src0,c.src1,c.dst):
                if root!=NULL_INDEX:
                    for idx,r in validate_descriptor_chain(root,records):self.assertEqual(r.pack().to_bytes(16,'little'),db[idx*16:idx*16+16])
    def test_full_model_dimensions_and_output_counts(self):
        for H,F,G,J,D in [(64,128,2,1,32),(1536,8960,12,2,128)]:
            with self.subTest(H=H):
                _,m=self.make(dict(H=H,F=F,HEADS=G,KVHEADS=J,HD=D,MAX_TOKENS=1024))
                words=sum(m['tensors'][n]['words'] for op in m['schedule'] for n in op['outputs'])
                self.assertEqual(words,16*(10*H+7*J*D+3*F))
                self.assertEqual(m['schedule'][10]['outputs'],[]);self.assertEqual(m['schedule'][11]['outputs'],[])
                self.assertEqual(m['schedule'][9]['outputs'],['cache_k','cache_v'])
    def test_every_destination_has_distinct_storage_and_guards(self):
        for t in [1,15,16,17,33,1024]:
            with self.subTest(tokens=t):
                _,m=self.make(tokens=t);prev=m['metadataLimit']
                for n in m['allocations']:
                    x=m['tensors'][n];self.assertGreaterEqual(x['address']-prev,64);self.assertEqual(x['address']%64,0);prev=x['address']+4*x['words']
                self.assertGreaterEqual(m['limit']-prev,64)
                k,v=m['tensors']['cache_k'],m['tensors']['cache_v'];self.assertEqual(v['address'],k['address']+4*k['words'])
    def test_relocated_descriptor_addresses_not_hardware_constants(self):
        a,ma=self.make();b,mb=self.make(relocate=0x234560000)
        self.assertEqual((a/'host_commands.bin').read_bytes(),(b/'host_commands.bin').read_bytes())
        self.assertNotEqual((a/'host_descriptors.bin').read_bytes(),(b/'host_descriptors.bin').read_bytes())
        for n,x in ma['tensors'].items():self.assertEqual(mb['tensors'][n]['address']-x['address'],0x234560000)
    def test_token_admission(self):
        for t in [0,-1,1025]:
            with self.subTest(tokens=t):
                with self.assertRaises(ValueError):self.make(tokens=t)
    def test_refuse_overwrite(self):
        out,m=self.make()
        with self.assertRaises(ValueError):pack(m['shape'],16,out)
    def test_matrix_dimension_contracts(self):
        out,m=self.make();db=(out/'host_descriptors.bin').read_bytes();records={i:DescriptorRecord.unpack(int.from_bytes(db[i*16:i*16+16],'little')) for i in range(m['descriptors'])}
        for i in [1,4,7,10,12,13,16,17,19]:
            op=m['schedule'][i];c=validate_descriptor_chain(op['roots'][0],records)
            self.assertEqual([r.record_type for _,r in c], [RecordType.TENSOR_BASE,RecordType.SHAPE4,RecordType.STRIDE3,RecordType.MATRIX_OP,RecordType.MATRIX_AUX])
            self.assertEqual(c[-1][1].payload,0x4000040024ffffff)
    def test_no_full_score_materialization_claim(self):
        _,m=self.make();self.assertEqual(m['attention_fusion'],[10,11,12])
        self.assertTrue(m['tensors']['scores']['virtual']);self.assertTrue(m['tensors']['probabilities']['virtual'])
        self.assertFalse(m['scope']['gguf_descriptor_image']);self.assertFalse(m['scope']['paged_kv']);self.assertFalse(m['scope']['full_model'])
if __name__=='__main__':unittest.main()
