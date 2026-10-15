import ctypes as C
from pathlib import Path
import subprocess

import pytest

from candidates.qwen2_exact_tree_scheduler import arithmetic as exact
from candidates.qwen2_rectangular_qk_payload.model import Scratch, configure, payload, run_tile
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import bf, finite
from scripts.qwen2_rectangular_attention_model import scratch_address


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    target = tmp_path_factory.mktemp('rectangular-qk')/'kernel.so'
    subprocess.run(['/usr/bin/g++','-std=c++17','-O2','-shared','-fPIC',
                    '-fno-fast-math','-ffp-contract=off','-frounding-math','-fno-tree-vectorize',
                    str(Path(__file__).with_name('kernel.cpp')),'-o',str(target)],
                   check=True,capture_output=True,timeout=30)
    return configure(C.CDLL(str(target)))


def multiply(a,b):
    x,ex = exact.decode(a); y,ey = exact.decode(b)
    return exact.round_rne(x*y,ex+ey,bool((a^b)>>31))


def reference(q,k):
    partials=[]
    for stripe in range(16):
        value=0
        for t in range(8):
            j=stripe+16*t
            value=exact.fma(bf(q[j]),bf(k[j]),value)
        partials.append(value)
    total=0
    for part in partials:
        total=exact.add(total,part)
    dot=bf(total); scaled=multiply(dot,0x3db504f3)
    return partials,(total,dot,scaled,bf(scaled))


def compare(native,q,k,qbase=0):
    seen={}
    s,stats=run_tile(native,q,k,qbase=qbase,debug=lambda kind,index,data:seen.__setitem__((kind,index),data))
    for r,row in enumerate(q):
        for key in range(qbase+r+1):
            partials,finished=reference(row,k[key])
            for stripe,part in enumerate(partials):
                assert seen[('partial',(r,key,stripe))] == (part,)
            assert seen[('dot_score',(r,key))] == finished
            assert s.get('score',r,key) == finished[-1]
    pairs=sum(qbase+r+1 for r in range(len(q)))
    assert len(seen)==pairs*17
    assert stats['wide_issues']==128 and stats['useful_fmas']==pairs*128
    assert stats['fixed_4096_lane_issue_capacity']==128*4096
    assert stats['ordered_scalar_adds']==pairs*16 and stats['scalar_scale_muls']==pairs
    return s,stats,seen


def test_same_a_b_capacities_and_nonoverlapping_original_addresses():
    s=Scratch(128)
    assert len(s.a)==704512 and len(s.b)==81920
    assert s.layout['used_a_bytes']==84*1024 and s.layout['used_b_bytes']==80*1024
    used=set()
    for obj in s.layout['objects']:
        for row in range(obj['rows']):
            for col in range(obj['columns']):
                group,bank,word,byte=scratch_address(s.layout,obj['name'],row,col)
                assert 0<=bank<16 and 0<=word<(1376 if group=='A' else 160)
                for offset in range(obj['bytes_per_element']):
                    identity=(group,bank,word,byte+offset)
                    assert identity not in used
                    used.add(identity)


def test_payload_uses_stored_words_and_pads_only_nonexistent_rows_keys():
    s=Scratch(17)
    for j in range(128):
        s.put('q',0,j,0x3f800000+(j<<16))
        for key in range(17):s.put('k',key,j,0x3f000000+(key<<16))
    a,b,valid=payload(s,16,1,7,3,32,17)
    assert a==(0x3f80+55,)+(0,)*15
    assert b[:17]==tuple(0x3f00+key for key in range(17)) and b[17:]==(0,)*239
    assert valid==(17,)+(0,)*15
    assert scratch_address(s.layout,'q',0,55)==('A',0,3,14)
    assert scratch_address(s.layout,'k',16,55)==('A',0,19,14)


def test_signed_zero_partial_bits_and_explicit_positive_zero_fold(native):
    # Negative tiny product rounds to -0 in each stripe. Remaining -0 FMAs
    # retain that bit; the required fold starts at +0 and yields +0.
    q=[[0x00010000]*16+[0x80000000]*112]
    k=[[0x80010000]*16+[0x3f800000]*112]
    _,_,seen=compare(native,q,k)
    assert all(seen[('partial',(0,0,s))]==(0x80000000,) for s in range(16))
    assert seen[('dot_score',(0,0))]==(0,0,0,0)


def test_cancellation_partial_dot_score_are_bit_equal(native):
    q=[[0x3f800000 if j<64 else 0xbf800000 for j in range(128)] for _ in range(3)]
    k=[[0x40000000]*128,[0xc0000000]*128,[0x3f800000]*128]
    compare(native,q,k)


def test_both_original_bf16_boundaries_not_old_fp32_score(native):
    q=[[0]*128];k=[[0]*128]
    q[0][0],q[0][1]=0x3f800000,0x3b800000
    k[0][0]=k[0][1]=0x3f800000
    _,_,seen=compare(native,q,k)
    total,dot,scaled,score=seen[('dot_score',(0,0))]
    assert total==0x3f808000 and dot==0x3f800000
    assert score!=bf(multiply(total,0x3db504f3)) and score==bf(scaled)


def test_tail_query_and_causal_prefix_include_all_eight_steps(native):
    q=[[0x3f000000+((j%7)<<16) for j in range(128)]]
    k=[[0x3e800000+(((key+j)%9)<<16) for j in range(128)] for key in range(17)]
    _,stats,_=compare(native,q,k,qbase=16)
    assert stats['physical_fmas']==128*16*32
    assert stats['useful_fmas']==17*128


def test_noncausal_physical_nonfinite_does_not_poison_selected_lanes(native):
    q=[[0]*128 for _ in range(16)]
    k=[[0]*128 for _ in range(16)]+[[0x7f800000]*128]
    s,_,_=compare(native,q,k)
    assert not finite(s.get('partial_or_pv_capture',0,16))
    # The same actual key becomes selected in the tail tile and must fail.
    with pytest.raises(ValueError,match='selected QK lane finite'):
        run_tile(native,[[0]*128],k,qbase=16)


def test_selected_fma_overflow_and_original_scalar_exception_policy(native):
    q=[[0]*128];k=[[0]*128]
    q[0][0],k[0][0]=0x7f7f0000,0x3f800000
    compare(native,q,k)  # largest finite BF16 dot remains a finite scaled score
    k[0][0]=0x40000000
    with pytest.raises(ValueError,match='selected QK lane finite'):
        run_tile(native,q,k)
    post=(C.c_uint32*3)()
    assert native.post_dot(0x00010000,post)==-2  # scale inexact-underflow is fatal
    folded=C.c_uint32()
    assert native.scalar_add(0x7f7fffff,0x7f7fffff,C.byref(folded))==-2


def test_native_partial_progress_cannot_skip_steps_or_reuse_early(native):
    assert native.reset()==0 and native.begin(5)==0
    a,b,valid,out=(C.c_uint16*16)(),(C.c_uint16*256)(),(C.c_uint32*16)(),(C.c_uint32*4096)()
    assert native.step(0,1,32,a,b,valid,out)==-1
    assert native.step(0,0,32,a,b,valid,out)==0
    assert native.begin(1)==-1
    assert native.step(0,0,32,a,b,valid,out)==-1
    assert native.reset()==0
