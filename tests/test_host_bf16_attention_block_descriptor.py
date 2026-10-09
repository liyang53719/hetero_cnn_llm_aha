"""Public wire/topology checks only; these do not execute owners or model data."""
from dataclasses import replace
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'chisel/continuous_prefill/scripts'))
sys.path.insert(0, str(ROOT / 'chisel/continuous_prefill/tests'))
from heteronpu.descriptor_chain import DescriptorRecord, NULL_INDEX, validate_descriptor_chain
from host_bf16_qkv_descriptor import HostQkvBinding
from host_bf16_qk_rope_descriptor import HostQkNormBinding, HostPartialRopeBinding
from host_bf16_attention_core_descriptor import AttentionContext, AttentionTensor, HostAttentionCoreBinding, build_host_attention_core_commands, validate_host_attention_core_commands
from host_bf16_attention_block_descriptor import (
    HostAttentionBlockBinding as B, AttentionBlockOperation as Op,
    BLOCK_SEQUENCE, BLOCK_COMMAND_INDICES, CHAIN_RECORDS, OWNER_JOBS,
    build_host_attention_block_commands as build, build_host_attention_block_descriptor,
    parse_host_attention_block_descriptor, validate_host_attention_block_commands as validate,
    validate_carried_attention_block_commands as carried,
)


from host_attention_block_control_vectors import fixture


@pytest.mark.parametrize('old,generation,capacity',[(0,0,1),(0,0,256),(1,1,256),(255,7,256)])
def test_full_block_roundtrip_and_exact_inventory(old,generation,capacity):
    args=fixture(old=old,generation=generation,capacity=capacity)
    commands,records=build(*args)
    assert len(commands)==22 and len(records)==CHAIN_RECORDS==296 and OWNER_JOBS==19
    assert set(records)==set(range(296))
    assert validate([c.pack() for c in commands],{i:r.pack() for i,r in records.items()})==args
    assert [c.src0 for c in commands]==[0,12,33,54,75,90,102,114,126,137,150,159,172,184,197,209,221,234,247,259,272,284]
    assert [c.opcode for c in commands]==[0x30,0x20,0x20,0x20,0x32,0x32,0x34,0x34,0x41,0x23,0x33,0x24,0x30,0x20,0x30,0x30,0x20,0x20,0x30,0x20,0x30,0x30]
    assert [(c.event_wait,c.event_signal) for c in commands]==[(i,i+1) for i in range(22)]
    assert sum(b.job is not None for b in args[-1])==10
    assert args[-1][1].job['gdnElementwiseOp']==2
    assert args[-1][1].job['a']==args[1][0].gate_output_ddr
    assert args[-1][1].job['b']==args[3].output_ddr
    assert args[-1][7].job['gdnElementwiseOp']==1
    assert args[-1][2].job['k']==2048 and args[-1][8].job['k']==3584


@pytest.mark.parametrize('which',range(11))
def test_new_policy_bits_and_exact_program(which):
    binding=fixture()[-1][which]
    command,records=build_host_attention_block_descriptor(binding,first_index=33,event_wait=20,event_signal=21)
    assert parse_host_attention_block_descriptor(command,records)==binding
    policy=next(r for r in records.values() if r.record_type==0x24)
    full=policy.pack()
    assert full>>56 & 255==3
    assert full>>64 & 15==binding.operation
    assert full>>68 & 0xFFFFFFFF==0
    assert full>>100 & 255==1
    assert full>>108 & 255==0
    assert full>>116 & 7==binding.role
    assert full>>119==0
    assert policy.payload>>63==0
    for bit in (63,64,71):
        bad=dict(records)
        i=next(i for i,r in records.items() if r.record_type==0x24)
        bad[i]=replace(records[i],payload=records[i].payload | 1<<bit)
        with pytest.raises(ValueError): parse_host_attention_block_descriptor(command,bad)


def test_all_producer_roots_are_actual_not_preloaded_lookalikes():
    args=fixture(); block=args[-1]
    # Mutation remains independently well shaped and non-overlapping but breaks
    # each real producer edge, including raw hidden and the final fence.
    changes=[(0,'d'),(1,'a'),(1,'b'),(2,'a'),(3,'a'),(3,'b'),(4,'a'),(5,'a'),(6,'a'),
             (7,'a'),(7,'b'),(8,'a'),(9,'a'),(9,'b'),(10,'a'),(10,'b'),(10,'d')]
    for index,field in changes:
        tensor=getattr(block[index],field)
        bad=list(block);bad[index]=replace(block[index],**{field:replace(tensor,address=0x3500000)})
        with pytest.raises(ValueError,match='binding'):
            build(*args[:-1],bad)


def test_global_aliases_are_full_physical_allocations():
    args=fixture(); block=list(args[-1])
    # Valid within input command, unsafe against a future FFN weight.
    block[0]=replace(block[0],a=replace(block[0].a,address=block[5].b.address+64))
    block[3]=replace(block[3],a=block[0].a);block[-1]=replace(block[-1],b=block[0].a)
    with pytest.raises(ValueError,match='overlap'): build(*args[:-1],block)
    # Readonly parameter roles cannot alias each other either.
    block=list(args[-1]);block[6]=replace(block[6],b=block[5].b)
    with pytest.raises(ValueError,match='overlap'): build(*args[:-1],block)


def test_context_role_m1_stride_and_event_mutations_reject():
    args=fixture(); commands,records=build(*args)
    for pc in BLOCK_COMMAND_INDICES:
        chain=validate_descriptor_chain(commands[pc].src0,records)
        policy_index=chain[-2][0];context_index=chain[-1][0]
        for index,bit in ((policy_index,12),(policy_index,44),(policy_index,52),(policy_index,63),(context_index,26),(context_index,35)):
            bad=dict(records);bad[index]=replace(records[index],payload=records[index].payload^(1<<bit))
            with pytest.raises(ValueError): validate(commands,bad)
        for root in (commands[pc].src0,commands[pc].src1,commands[pc].dst):
            bad=dict(records);bad[root+2]=replace(records[root+2],payload=records[root+2].payload^1)
            with pytest.raises(ValueError): validate(commands,bad)
    bad=list(commands);bad[12]=replace(commands[12],event_wait=8)
    with pytest.raises(ValueError,match='events'): validate(bad,records)
    bad=list(args[-1]);bad[0]=replace(bad[0],context=AttentionContext(256,1,1,1,False))
    with pytest.raises(ValueError,match='context'): build(*args[:-1],bad)
    for shape in ((128,1024),(1,2048)):
        with pytest.raises(ValueError,match='M1'): replace(args[-1][0],a=AttentionTensor(0x3500000,shape))


def test_old_core_fence_is_absent_and_cannot_commit_full_block():
    args=fixture(); commands,records=build(*args)
    policies=[r.payload for r in records.values() if r.record_type==0x24]
    assert not any(p&255==2 and (p>>8)&15==4 for p in policies)
    old_commands,old_records=build_host_attention_core_commands(*args[:-1])
    assert validate_host_attention_core_commands(old_commands,old_records)==args[3]
    with pytest.raises(ValueError): validate(old_commands,old_records)
    with pytest.raises(ValueError): validate_host_attention_core_commands(commands,records)


def test_carried_launch_protects_final_cache_and_all_parameters_but_reuses_scratch():
    previous=build(*fixture())
    # All scratch is reused, including the prior PV context. Final output gets
    # another allocation and the cache remains at the identical allocation.
    current=build(*fixture(old=1,generation=1,final=0x3001000))
    assert carried(*previous,*current)[3].expected_length==1
    for kwargs in ({'final':0x3000000}, {'final':0x3001000,'old':2,'generation':1},
                   {'final':0x3001000,'old':1,'generation':2}):
        config=dict(old=1,generation=1);config.update(kwargs)
        with pytest.raises(ValueError): carried(*previous,*build(*fixture(**config)))
    args=fixture(old=1,generation=1,final=0x3001000)
    for index in (0,2,4,5,6,8):
        block=list(args[-1]);block[index]=replace(block[index],b=replace(block[index].b,address=0x3800000))
        with pytest.raises(ValueError,match='identities'): carried(*previous,*build(*args[:-1],block))
    # The old final remains protected even if declared as current raw hidden.
    block=list(args[-1]);new_hidden=AttentionTensor(0x3000000,(1,1024))
    block[0]=replace(block[0],a=new_hidden);block[3]=replace(block[3],a=new_hidden);block[-1]=replace(block[-1],b=new_hidden)
    with pytest.raises(ValueError,match='overlap'): carried(*previous,*build(*args[:-1],block))


def test_sigmoid_reversed_operand_roots_reject_even_with_matching_geometry():
    args=fixture();block=list(args[-1]);gate=block[1]
    block[1]=replace(gate,a=gate.b,b=gate.a)
    with pytest.raises(ValueError,match='binding'): build(*args[:-1],block)
    from host_attention_block_control_vectors import program
    wrong=program(mode='reversed_sigmoid')
    with pytest.raises(ValueError,match='binding'):
        validate([int(x) for x in wrong['commands']],{i:int(x) for i,x in enumerate(wrong['records'])})
