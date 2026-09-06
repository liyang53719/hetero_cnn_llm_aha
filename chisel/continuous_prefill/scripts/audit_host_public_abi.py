#!/usr/bin/env python3
"""Audit emitted Host command bytes using the retained public Python ISA parser.

Read-only audit. This does not simulate hardware or create replacement outputs.
The target is exactly the real16 block followed by three SFU_VECTOR additions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def audit(repo: Path, evidence: Path) -> dict:
    sys.path.insert(0, str(repo / 'src'))
    from heteronpu.command import Command128, Engine, Opcode
    from heteronpu.descriptor_chain import DescriptorRecord, RecordType, SfuProgram, TensorDType, validate_descriptor_chain

    def constant(name: str) -> int:
        matches = re.findall(r'\b' + re.escape(name) + r'\s*=\s*(\d+)(?:ULL)?\b', header)
        require(len(matches) == 1, 'missing/duplicate layout constant ' + name)
        return int(matches[0])

    header = (evidence / 'generated/block_layout.h').read_text()
    require(all(constant(k) == v for k, v in [('H',1536),('F',8960),('HEADS',12),('KVHEADS',2),('HD',128)]), 'not real Qwen2 geometry')
    command_path = evidence / 'tensors/host_commands.bin'
    descriptor_path = evidence / 'tensors/host_descriptors.bin'
    command_bytes, descriptor_bytes = command_path.read_bytes(), descriptor_path.read_bytes()
    require(len(command_bytes) == 64 and len(descriptor_bytes) == 512, 'bad padded table length')
    records = {i: DescriptorRecord.unpack(int.from_bytes(descriptor_bytes[16*i:16*i+16], 'little')) for i in range(30)}
    public = json.loads((repo / 'config/descriptor_public_encoding.json').read_text())
    require(public['approval_status'] == 'APPROVED', 'unapproved public descriptor encoding')
    require(public['tensor_base']['dtype_codes']['FP32'] == int(TensorDType.FP32) == 7, 'FP32 code mismatch')
    base, span = 0x100000000, 16*1536*4
    y, x, output = base+constant('OFF_Y'), base+constant('OFF_X'), base+constant('ARENA_BYTES')+4096
    used = set()
    decoded = []
    for pc in range(3):
        raw = command_bytes[16*pc:16*pc+16]
        cmd = Command128.from_bytes(raw)
        require(cmd.to_bytes() == raw, 'command roundtrip mismatch')
        require(cmd.opcode == Opcode.SFU_VECTOR and cmd.engine == Engine.SFU_CGRA and cmd.flags == 0, 'not enabled SFU_VECTOR envelope')
        require((cmd.event_wait, cmd.event_signal) == (pc,pc+1), 'event dependency mismatch')
        require((cmd.src0, cmd.src1, cmd.dst) == (10*pc,10*pc+4,10*pc+7), 'descriptor root mismatch')
        addresses = [y if pc==0 else output+(pc-1)*span, x, output+pc*span]
        for operand, (root, address) in enumerate(zip((cmd.src0,cmd.src1,cmd.dst),addresses)):
            chain = validate_descriptor_chain(root, records)
            expected = [RecordType.TENSOR_BASE,RecordType.SHAPE4,RecordType.STRIDE3]
            if operand == 0:
                expected += [RecordType.SFU_PROGRAM]
            require([r.record_type for _,r in chain] == expected, 'wrong tensor/policy chain')
            for index, record in chain:
                require(index not in used, 'aliased descriptor records')
                used.add(index)
                require(record.pack().to_bytes(16,'little') == descriptor_bytes[16*index:16*index+16], 'descriptor roundtrip mismatch')
            p=chain[0][1].payload
            expected_base=(address & ((1<<48)-1)) | (7<<52) | (2<<60) | ((address>>48)<<64)
            require(p==expected_base,'address/space/layout/dtype/rank mismatch')
            dims=tuple((chain[1][1].payload>>(18*i))&((1<<18)-1) for i in range(4))
            strides=tuple((chain[2][1].payload>>(24*i))&((1<<24)-1) for i in range(3))
            require(dims==(16,1536,1,1) and strides==(1536,1,1), 'shape or element stride mismatch')
            if operand==0:
                program=SfuProgram.from_record(chain[-1][1])
                require(program.program_id==int(Opcode.SFU_VECTOR) and program.input_count==2 and program.output_count==1,'wrong dedicated program')
                require(program.input_dtype==TensorDType.FP32 and program.output_dtype==TensorDType.FP32,'wrong SFU dtype')
                require(program.lane_width_bits==16 and program.vector_lanes==public['sfu_program']['dedicated_vector_lanes']==0 and program.program_flags==0,'wrong SFU lane/policy fields')
        decoded.append({'pc':pc,'opcode':cmd.opcode.name,'engine':cmd.engine.name,'wait':cmd.event_wait,'signal':cmd.event_signal,'a':hex(addresses[0]),'b':hex(addresses[1]),'dst':hex(addresses[2])})
    require(used==set(range(30)),'incomplete descriptor coverage')
    identity = ['src/heteronpu/command.py','src/heteronpu/descriptor_chain.py','config/descriptor_public_encoding.json']
    return {'status':'PASS_HOST_BYTES_WITH_RETAINED_PUBLIC_ISA_PARSERS','commands':3,'descriptor_records':30,'tensor_chains':9,'command128_roundtrip':True,'descriptor_roundtrip':True,'decoded_commands':decoded,'source_sha256':{p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in identity},'table_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [command_path,descriptor_path]},'scope':'Read-only interoperability audit, not a new hardware execution claim.'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=audit(args.repo.resolve(),args.evidence.resolve())
        with args.output.open('x') as stream:
            stream.write(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    except (ValueError,OSError,KeyError,TypeError) as error:
        raise SystemExit('PUBLIC_ABI_REJECTED: '+str(error))
