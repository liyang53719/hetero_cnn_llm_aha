#!/usr/bin/env python3
"""Negative gates and public-ABI layout tests; retained artifacts are never deleted."""
from pathlib import Path
import copy,json,os,shutil,sys,unittest,uuid
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'chisel/continuous_prefill/scripts'))
from pack_owner_multilayer_fixture import pack_layers
from verify_host_block_gate import verify
from audit_owner_block_abi import audit
from run_owner_lifecycle_gate import fields
from heteronpu.command import Command128
ART=Path(os.environ.get('OWNER_TEST_ARTIFACTS',str(ROOT/'work/owner_extended_tests')))/uuid.uuid4().hex
ART.mkdir(parents=True)
SHAPE=dict(H=64,F=128,HEADS=2,KVHEADS=1,HD=32,MAX_TOKENS=1024)

class LayoutTests(unittest.TestCase):
    def test_two_and_three_layers_retain_public_commands_and_actual_producer_alias(self):
        for layers in (1,2,3):
            for tokens in (1,17,33):
                with self.subTest(layers=layers,tokens=tokens):
                    out=ART/f'layout_l{layers}_t{tokens}';m=pack_layers(SHAPE,tokens,layers,out,1<<48)
                    self.assertEqual(m['commands'],21*layers);self.assertEqual(m['descriptors'],215*layers)
                    raw=(out/'host_commands.bin').read_bytes()
                    for pc in range(21*layers):
                        c=Command128.from_bytes(raw[16*pc:16*pc+16]);self.assertEqual((c.event_wait,c.event_signal),(pc,pc+1))
                    for layer in range(1,layers):
                        a=m['tensors'][f'l{layer}_x'];b=m['tensors'][f'l{layer-1}_y']
                        self.assertEqual(a['address'],b['address']);self.assertFalse(a['readonly'])
                        self.assertNotIn(f'l{layer}_x',m['allocations'])
                    for layer in range(layers):
                        w=m['tensors'][f'l{layer}_wq'];self.assertTrue(w['readonly']);self.assertLess(w['address'],m['scratchBase'])
    def test_invalid_layer_capacity(self):
        for n in (0,4,28,True,1.5):
            with self.subTest(n=n),self.assertRaises(ValueError):pack_layers(SHAPE,17,n,ART/('invalid_l_'+str(n)))
    def test_invalid_token_capacity(self):
        for n in (0,1025,-1,True,1.5):
            with self.subTest(n=n),self.assertRaises(ValueError):pack_layers(SHAPE,n,2,ART/('invalid_t_'+str(n)))
    def test_invalid_address(self):
        for n in (-64,1,65,1<<56):
            with self.subTest(n=n),self.assertRaises(ValueError):pack_layers(SHAPE,17,2,ART/('invalid_a_'+str(n)),n)
    def test_no_overwrite(self):
        p=ART/'preserved';p.mkdir();(p/'marker').write_text('keep')
        with self.assertRaises(ValueError):pack_layers(SHAPE,17,2,p)
        self.assertEqual((p/'marker').read_text(),'keep')
    def test_duplicate_receipt_field_rejected(self):
        with self.assertRaises(ValueError):fields('X completed=0 completed=42')

EVIDENCE=os.environ.get('OWNER_STACK_EVIDENCE')
@unittest.skipUnless(EVIDENCE,'set OWNER_STACK_EVIDENCE to completed actual multi-layer proof')
class EvidenceTests(unittest.TestCase):
    def clone(self,name):
        p=ART/name;shutil.copytree(Path(EVIDENCE),p,ignore=shutil.ignore_patterns('obj','classes','VHostOwnerReplay'));return p
    def test_accept_actual_completed_multi_layer_proof(self):
        r=verify(Path(EVIDENCE),False);self.assertGreaterEqual(r['layers'],2);self.assertTrue(r['scope']['multilayer']);audit(Path(EVIDENCE))
    def test_missing_second_layer_output(self):
        p=self.clone('missing');f=p/'tensors/l1_y_actual.f32le';f.rename(f.with_suffix('.missing'))
        with self.assertRaises((ValueError,OSError)):verify(p,False)
    def test_short_output(self):
        p=self.clone('short');f=p/'tensors/l1_y_actual.f32le';f.write_bytes(f.read_bytes()[:-4])
        with self.assertRaises(ValueError):verify(p,False)
    def test_bit_flip_actual(self):
        p=self.clone('bitflip');f=p/'tensors/l1_y_actual.f32le';b=bytearray(f.read_bytes());b[0]^=1;f.write_bytes(b)
        with self.assertRaises(ValueError):verify(p,False)
    def test_both_outputs_nan(self):
        p=self.clone('nan')
        for side in ('actual','reference'):
            f=p/f'tensors/l1_y_{side}.f32le';b=bytearray(f.read_bytes());b[:4]=(0x7fc00001).to_bytes(4,'little');f.write_bytes(b)
        with self.assertRaises(ValueError):verify(p,False)
    def test_repeated_weight_identity(self):
        p=self.clone('repeat_weights');f=p/'run.log';lines=f.read_text().splitlines();ids=[i for i,s in enumerate(lines) if s.startswith('LAYER_WEIGHT_ID ')]
        self.assertGreaterEqual(len(ids),2)
        first=fields(lines[ids[0]]);second=fields(lines[ids[1]])
        for k in ('wq','wg','wd'):second[k]=first[k]
        lines[ids[1]]='LAYER_WEIGHT_ID '+' '.join(f'{k}={v}' for k,v in second.items());f.write_text('\n'.join(lines)+'\n')
        with self.assertRaises(ValueError):verify(p,False)
    def test_missing_completion(self):
        p=self.clone('completion');f=p/'run.log';f.write_text('\n'.join(x for x in f.read_text().splitlines() if not x.startswith('OWNER_COMPLETION pc=21 '))+'\n')
        with self.assertRaises(ValueError):verify(p,False)
    def test_reference_only_not_actual_handoff(self):
        p=self.clone('alias');f=p/'fixture/manifest.json';m=json.loads(f.read_text());m['tensors']['l1_x']['address']=m['tensors']['l0_x']['address'];f.write_text(json.dumps(m))
        with self.assertRaises(ValueError):verify(p,False)
    def test_corrupt_descriptor_padding(self):
        p=self.clone('padding')
        for n in ('fixture','tensors'):
            f=p/n/'host_descriptors.bin';b=bytearray(f.read_bytes());b[-1]=1;f.write_bytes(b)
        with self.assertRaises(ValueError):audit(p)

if __name__=='__main__':unittest.main(verbosity=2)
