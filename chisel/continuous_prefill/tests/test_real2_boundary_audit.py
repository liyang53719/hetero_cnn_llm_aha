#!/usr/bin/env python3
"""Tests of the independent evidence audit, NOT a hardware simulation.

Test directories are intentionally preserved. No old evidence is overwritten.
"""
import copy
import json
import math
import os
from pathlib import Path
import struct
import sys
import unittest
import uuid
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_real2_boundary import audit, bf16_rne, ordered_input_norm, WORDS, PEER_SOURCE


def scalar32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def scalarbf(x):
    u=struct.unpack('<I',struct.pack('<f',x))[0]
    return struct.unpack('<f',struct.pack('<I',((u+0x7fff+((u>>16)&1))&0xffff0000)&0xffffffff))[0]


class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ.get('OWNER_TEST_ARTIFACTS','work/real2_boundary_tests'))/uuid.uuid4().hex
        cls.root.mkdir(parents=True)
        cls.x=(np.arange(16*1536,dtype=np.float32).reshape(16,1536)%101-50)/np.float32(64)

    def fixture(self):
        root=self.root/uuid.uuid4().hex;peer=root/'peer';out=root/'candidate'
        for p in (peer,out):
            (p/'tensors').mkdir(parents=True);(p/'fixture').mkdir()
            (p/'gate.exit').write_text('0\n');(p/'simulation.exit').write_text('0\n')
            (p/'tensors/input_x.f32le').write_bytes(self.x.astype('<f4').tobytes())
        (peer/'source_base_commit.txt').write_text(PEER_SOURCE+'\n')
        m={'tokens':16,'layers':2,'shape':{'H':1536,'F':8960},'allocations':['l0_y'],
           'tensors':{'l0_y':{'address':0x23400000},'l1_x':{'address':0x23400000,'readonly':False}}}
        (out/'fixture/manifest.json').write_text(json.dumps(m))
        for name,words in WORDS.items():
            value=(np.arange(words,dtype=np.float32)%79-39)/np.float32(32)
            raw=value.astype('<f4').tobytes()
            (peer/f'tensors/{name}_actual.f32le').write_bytes(raw)
            (out/f'tensors/l0_{name}_actual.f32le').write_bytes(raw)
        y=(out/'tensors/l0_y_actual.f32le').read_bytes()
        (out/'tensors/l1_n0_actual.f32le').write_bytes(ordered_input_norm(y))
        return out,peer

    def test_reference_matches_scalar_order(self):
        actual=np.frombuffer(ordered_input_norm(self.x.astype('<f4').tobytes()),dtype='<f4').reshape(16,1536)
        for row in (0,5,15):
            acc=0.0
            for v in self.x[row]:acc=scalar32(acc+scalar32(float(v)*float(v)))
            variance=scalar32(scalar32(acc*scalar32(1/1536))+scalar32(1e-6))
            inv=scalar32(1/scalar32(math.sqrt(variance)))
            expected=np.array([scalarbf(scalar32(scalar32(float(v)*inv)*scalarbf(scalar32(scalar32(.9)+(i%11)*.015625)))) for i,v in enumerate(self.x[row])],dtype='<f4')
            self.assertEqual(actual[row].tobytes(),expected.tobytes())

    def test_bf16_ties_even_signed_zero(self):
        words=np.array([0x3f808000,0x3f818000,0xbf808000,0xbf818000,0,0x80000000],dtype='<u4')
        got=bf16_rne(words.view('<f4')).view('<u4').tolist()
        self.assertEqual(got,[0x3f800000,0x3f820000,0xbf800000,0xbf820000,0,0x80000000])

    def test_nonfinite_or_overflow(self):
        for v in [float('nan'),float('inf'),-float('inf'),np.finfo(np.float32).max]:
            with self.assertRaises(ValueError):bf16_rne(np.array([v],dtype=np.float32))

    def test_short_hidden(self):
        with self.assertRaises(ValueError):ordered_input_norm(b'\0'*16)

    def test_valid_supplementary_evidence(self):
        o,p=self.fixture();r=audit(o,p)
        self.assertEqual(r['peer_compared_fp32'],704512)
        self.assertEqual(r['boundary_norm_recomputed_fp32'],24576)
        self.assertFalse(r['rtl_rerun'])

    def test_changed_first_layer(self):
        o,p=self.fixture();f=o/'tensors/l0_down_actual.f32le';b=bytearray(f.read_bytes());b[0]^=1;f.write_bytes(b)
        with self.assertRaisesRegex(ValueError,'cross-run drift'):audit(o,p)

    def test_consumer_uses_original_x(self):
        o,p=self.fixture();(o/'tensors/l1_n0_actual.f32le').write_bytes(ordered_input_norm(self.x.astype('<f4').tobytes()))
        with self.assertRaisesRegex(ValueError,'previous Y'):audit(o,p)

    def test_missing_consumer(self):
        o,p=self.fixture();f=o/'tensors/l1_n0_actual.f32le';f.rename(f.with_suffix('.preserved'))
        with self.assertRaisesRegex(ValueError,'missing'):audit(o,p)

    def test_failed_gate_and_wrong_source(self):
        for name in ('gate.exit','simulation.exit','source_base_commit.txt'):
            o,p=self.fixture();(p/name).write_text('1\n')
            with self.assertRaises(ValueError):audit(o,p)

    def test_boundary_alias_or_host_allocation(self):
        for change in ('address','allocation','readonly'):
            o,p=self.fixture();f=o/'fixture/manifest.json';m=json.loads(f.read_text())
            if change=='address':m['tensors']['l1_x']['address']+=64
            elif change=='allocation':m['allocations'].append('l1_x')
            else:m['tensors']['l1_x']['readonly']=True
            f.write_text(json.dumps(m))
            with self.assertRaises(ValueError):audit(o,p)

    def test_nonfinite_tensor(self):
        o,p=self.fixture();f=o/'tensors/l1_n0_actual.f32le';b=bytearray(f.read_bytes());b[:4]=struct.pack('<I',0x7fc00001);f.write_bytes(b)
        with self.assertRaisesRegex(ValueError,'nonfinite'):audit(o,p)

    def test_wrong_geometry(self):
        o,p=self.fixture();f=o/'fixture/manifest.json';m=json.loads(f.read_text());m['tokens']=17;f.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'geometry'):audit(o,p)


if __name__=='__main__':unittest.main(verbosity=2)
