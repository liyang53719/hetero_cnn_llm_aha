"""Default-off Host V version-2 descriptor serializer and independent preflight.

This is deliberately separate from the version-1 SharedL2 candidate serializer.
All extension addresses are checked zero sentinels for private owner staging.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from heteronpu.abi_validation import uint
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import DescriptorRecord, MatrixAux, NULL_INDEX, TensorDType, validate_descriptor_chain
from heteronpu.gemmini_descriptor_v2 import tensor_base_record, shape4_record, stride3_record, matrix_op_record

@dataclass(frozen=True)
class HostVBinding:
    rows: int
    token_base: int
    token_count: int
    activation_ddr: int
    weight_ddr: int
    output_ddr: int

    def __post_init__(self):
        for name, width in (("rows", 8), ("token_base", 32), ("token_count", 8),
                            ("activation_ddr", 56), ("weight_ddr", 56), ("output_ddr", 56)):
            object.__setattr__(self, name, uint(getattr(self, name), width, name))
        if not 1 <= self.rows <= 128 or not 1 <= self.token_count <= 128 or self.token_base + self.token_count > self.rows:
            raise ValueError("invalid full tensor or token window")
        spans = [(self.activation_ddr, self.rows * 2048), (self.weight_ddr, 1024 * 512 * 2), (self.output_ddr, self.rows * 1024)]
        for address, size in spans:
            if address % 64 or address + size > 1 << 56:
                raise ValueError("unaligned or overflowing DDR tensor")
        out, size = spans[2]
        for address, source_size in spans[:2]:
            if address < out + size and out < address + source_size:
                raise ValueError("output overlaps full input tensor")

    @property
    def job(self):
        return dict(m=self.token_count, n=512, k=1024,
                    a=self.activation_ddr + self.token_base * 2048, b=self.weight_ddr,
                    dst=self.output_ddr + self.token_base * 1024, writeBytes=self.token_count * 1024,
                    activationBf16=True, weightBf16=True, outputBf16=True)


def build_host_v_descriptor(binding: HostVBinding, *, first_index=0, event_wait=0, event_signal=1):
    binding.__post_init__()
    first_index = uint(first_index, 24, "first_index")
    if first_index + 21 > NULL_INDEX:
        raise ValueError("descriptor index aperture exhausted")
    if event_signal == 0 or event_signal == event_wait:
        raise ValueError("signal must be nonzero and distinct from wait")
    records = {}
    for slot, offset in enumerate((0, 15, 18)):
        root = first_index + offset
        rows, cols = ((binding.rows, 1024), (1024, 512), (binding.rows, 512))[slot]
        address = (binding.activation_ddr, binding.weight_ddr, binding.output_ddr)[slot]
        records[root] = tensor_base_record(address, dtype=TensorDType.BF16, rank=2, next_index=root+1)
        records[root+1] = shape4_record((rows, cols, 1, 1), next_index=root+2)
        records[root+2] = stride3_record((cols, 1, 1), next_index=root+3 if slot==0 else NULL_INDEX)
    records[first_index+3] = matrix_op_record(m=binding.rows,n=512,k=1024,dataflow=0,next_index=first_index+4)
    records[first_index+4] = MatrixAux().to_record(next_index=first_index+5)
    policy = 2 | 2<<8 | 3<<10 | binding.token_base<<12 | binding.token_count<<44
    records[first_index+5] = DescriptorRecord(0x1a,0,0,first_index+6,policy)
    for kind in range(9):
        index=first_index+6+kind
        records[index]=DescriptorRecord(0x1b,0,0,index+1 if kind<8 else NULL_INDEX,kind<<56)
    command=Command128(Opcode.MATRIX_GEMM,Engine.MATRIX,event_wait=event_wait,event_signal=event_signal,
                       src0=first_index,src1=first_index+15,dst=first_index+18)
    return command, records


def parse_host_v_descriptor(command, records):
    if isinstance(command,int): command=Command128.unpack(command)
    if command.opcode!=Opcode.MATRIX_GEMM or command.engine!=Engine.MATRIX or command.flags:
        raise ValueError("unsupported command envelope")
    chains=[validate_descriptor_chain(root,records) for root in (command.src0,command.src1,command.dst)]
    indices=[i for chain in chains for i,_ in chain]
    if len(indices)!=21 or len(set(indices))!=21:
        raise ValueError("chains must have 21 distinct records")
    addresses=[]; shapes=[]
    for slot,chain in enumerate(chains):
        expected=[1,2,3]+([0x10,0x12,0x1a]+[0x1b]*9 if slot==0 else [])
        if [int(r.record_type) for _,r in chain]!=expected:
            raise ValueError("unexpected record order")
        if any(r.subtype or r.flags for _,r in chain):
            raise ValueError("reserved common header")
        base,shape,stride=[r.payload for _,r in chain[:3]]
        if (base>>48)&0xffff!=0x2050:
            raise ValueError("not native contiguous BF16 rank2")
        addresses.append((base & ((1<<48)-1)) | (base>>64)<<48)
        dims=tuple((shape>>(18*i))&0x3ffff for i in range(4))
        if dims[2:]!=(1,1) or stride!=dims[1]|1<<24|1<<48:
            raise ValueError("invalid shape or element stride")
        shapes.append(dims[:2])
    policy=chains[0][5][1].payload
    if policy&0xff!=2 or (policy>>8)&3!=2 or (policy>>10)&3!=3 or policy>>52:
        raise ValueError("unsupported V owner-managed version/mode")
    for kind,(_,record) in enumerate(chains[0][6:]):
        if record.payload!=kind<<56: raise ValueError("owner-managed address sentinel required")
    result=HostVBinding(shapes[0][0],(policy>>12)&0xffffffff,(policy>>44)&0xff,*addresses)
    if shapes!=[(result.rows,1024),(1024,512),(result.rows,512)]:
        raise ValueError("invalid V shapes")
    if chains[0][3][1].payload!=result.rows|512<<16|1024<<32 or chains[0][4][1].payload!=MatrixAux().payload():
        raise ValueError("unsupported Matrix policy")
    return result
