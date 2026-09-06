#!/usr/bin/env python3
"""Public-ABI auditor tests. Mutations are in memory; no DUT/file replacement."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'chisel/continuous_prefill/scripts'))
import audit_host_public_abi as audit_module
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import DescriptorRecord, RecordType, SfuProgram, TensorDType


class PublicAbiTests(unittest.TestCase):
    def setUp(self):
        self.evidence=Path('/virtual/evidence')
        self.c=self.evidence/'tensors/host_commands.bin'
        self.d=self.evidence/'tensors/host_descriptors.bin'
        self.h=self.evidence/'generated/block_layout.h'
        base=0x100000000;span=16*1536*4;null=0xffffff
        self.header='H=1536; F=8960; HEADS=12; KVHEADS=2; HD=128; OFF_Y=1048576ULL; OFF_X=0ULL; ARENA_BYTES=2097152ULL;'
        commands=bytearray(64);descriptors=bytearray(512)
        for pc in range(3):
            root=pc*10;output=base+2097152+4096
            command=Command128(Opcode.SFU_VECTOR,Engine.SFU_CGRA,event_wait=pc,event_signal=pc+1,src0=root,src1=root+4,dst=root+7)
            commands[pc*16:pc*16+16]=command.to_bytes()
            addresses=[base+1048576 if pc==0 else output+(pc-1)*span,base,output+pc*span]
            for operand,(index,address) in enumerate(zip((root,root+4,root+7),addresses)):
                payload=(address&((1<<48)-1)) | (7<<52) | (2<<60) | ((address>>48)<<64)
                recs=[DescriptorRecord(RecordType.TENSOR_BASE,0,0,index+1,payload),
                      DescriptorRecord(RecordType.SHAPE4,0,0,index+2,16 | (1536<<18) | (1<<36) | (1<<54)),
                      DescriptorRecord(RecordType.STRIDE3,0,0,index+3 if operand==0 else null,1536 | (1<<24) | (1<<48))]
                if operand==0:recs.append(SfuProgram(48,2,1,TensorDType.FP32,TensorDType.FP32).to_record())
                for off,rec in enumerate(recs):descriptors[(index+off)*16:(index+off+1)*16]=rec.pack().to_bytes(16,'little')
        self.raw={self.c:bytes(commands),self.d:bytes(descriptors)}

    def run_audit(self, mutation=None):
        read_bytes=Path.read_bytes;read_text=Path.read_text
        values=dict(self.raw)
        if mutation:values.update(mutation)
        def rb(path):return values[path] if path in values else read_bytes(path)
        def rt(path,*args,**kwargs):return self.header if path==self.h else read_text(path,*args,**kwargs)
        with patch.object(Path,'read_bytes',rb),patch.object(Path,'read_text',rt):
            return audit_module.audit(ROOT,self.evidence)

    def test_frozen_writer_and_reader_roundtrip(self):
        r=self.run_audit()
        self.assertEqual(r['commands'],3);self.assertEqual(r['descriptor_records'],30)
        self.assertTrue(r['descriptor_roundtrip']);self.assertTrue(r['command128_roundtrip'])

    def test_mutations_rejected(self):
        cases=[]
        for bit in (0,8,11,24,40,56,80,104):cases.append((self.c,0,bit))
        for record,bit in [(0,0),(0,8),(0,16),(0,32),(0,56),(0,104),(0,108),(0,112),(0,116),
                           (1,56),(2,56),(3,56),(3,72),(3,80),(3,88),(3,96),(3,104),(3,112),(3,120)]:
            cases.append((self.d,record,bit))
        for path,record,bit in cases:
            data=bytearray(self.raw[path]);data[16*record+bit//8]^=1<<(bit%8)
            with self.subTest(table=path.name,record=record,bit=bit),self.assertRaises((ValueError,KeyError)):
                self.run_audit({path:bytes(data)})
        for path in (self.c,self.d):
            with self.subTest(short_table=path.name),self.assertRaises(ValueError):self.run_audit({path:self.raw[path][:-1]})

if __name__=='__main__':unittest.main()
