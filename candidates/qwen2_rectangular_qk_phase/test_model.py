from dataclasses import replace
import ctypes as C
from pathlib import Path
import subprocess

import pytest

from candidates.qwen2_rectangular_qk_payload.model import configure,run_tile
from candidates.qwen2_rectangular_qk_phase.model import Phase,fixture,drain


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    target=tmp_path_factory.mktemp('qk-phase')/'kernel.so'
    source=Path(__file__).parents[1]/'qwen2_rectangular_qk_payload'/'kernel.cpp'
    subprocess.run(['/usr/bin/g++','-std=c++17','-O2','-shared','-fPIC','-fno-fast-math',
                    '-ffp-contract=off','-frounding-math','-fno-tree-vectorize',str(source),'-o',str(target)],
                   check=True,capture_output=True,timeout=30)
    return configure(C.CDLL(str(target)))


def new(native,debug=None):
    q=[[0]*128];k=[[0]*128]
    q[0][0],q[0][1]=0x3f800000,0x3b800000;k[0][0]=k[0][1]=0x3f800000
    return Phase(native,fixture(q,k),enabled=True,old_owners_idle=True,debug=debug)


def until(e,kind):
    for _ in range(10000):
        request=e.offer()
        assert request is not None
        if request.tag.kind==kind:return request
        e.accept(request);e.complete(request.tag)
    raise AssertionError('event not reached')


def test_phase_payload_matches_frozen_partial_dot_score_with_ack(native):
    observed={}
    e=new(native,lambda kind,index,data:observed.__setitem__((kind,index),data))
    q=[[0]*128];k=[[0]*128]
    q[0][0],q[0][1]=0x3f800000,0x3b800000;k[0][0]=k[0][1]=0x3f800000
    drain(e)
    reference={}
    s,_=run_tile(native,q,k,debug=lambda kind,index,data:reference.__setitem__((kind,index),data))
    assert observed==reference and e.s.get('score',0,0)==s.get('score',0,0)
    assert e.stats['acked:matrix']==128 and e.stats['acked:scalar_add']==16
    assert e.stats['acked:scalar_scale']==1 and e.stats['acked:b_write']==16*16*32//8
    assert e.stats['acked:group_done']==4 and e.stats['acked:owner_done']==1
    assert e.stats['fixed_4096_lane_capacity']==4096*128
    assert all(x is None for x in e.slots+e.contexts) and e.done and e.drained


def test_default_off_and_one_accepted_credit(native):
    with pytest.raises(ValueError,match='default-off'):
        Phase(native,fixture([[0]*128],[[0]*128]))
    e=new(native);request=e.offer();e.accept(request)
    for _ in range(20):assert e.offer() is None and e.pending==request and not e.done
    with pytest.raises(ValueError,match='credit'):
        e.accept(request)
    e.complete(request.tag)


def test_missing_b_commit_ack_prevents_slot_publish_and_group_reuse(native):
    e=new(native);request=until(e,'b_write')
    before=bytes(e.s.b);e.accept(request)
    assert bytes(e.s.b)==before and e.slots[0] is None and e.contexts[0]==0
    for _ in range(10):assert e.offer() is None and not e.done
    e.complete(request.tag)
    assert bytes(e.s.b)!=before and e.slots[0] is None  # one word is not a full partial
    while e.offer().tag.kind=='b_write':
        r=e.offer();e.accept(r);e.complete(r.tag)
    assert e.slots[0]==0 and e.contexts[0] is None


def test_wrong_epoch_and_abort_drain_accepted_matrix_return(native):
    e=new(native);request=until(e,'matrix');e.accept(request)
    with pytest.raises(ValueError,match='identity'):
        e.complete(replace(request.tag,epoch=99))
    assert e.poisoned and not e.drained and e.pending==request
    e.complete(request.tag)
    assert e.drained and not e.done and e.offer() is None


def test_abort_does_not_cancel_accepted_write_commit_but_never_publishes(native):
    e=new(native);request=until(e,'b_write');before=bytes(e.s.b)
    e.accept(request);e.abort()
    assert e.pending==request and not e.drained and bytes(e.s.b)==before
    e.complete(request.tag)
    assert bytes(e.s.b)!=before and e.drained and not e.done
    assert all(x is None for x in e.slots)


def test_scalar_and_score_write_ack_are_not_completion(native):
    e=new(native);request=until(e,'scalar_add');e.accept(request)
    assert e.offer() is None and e.stats['acked:scalar_add']==0
    e.complete(request.tag)
    request=until(e,'a_write');before=bytes(e.s.a);e.accept(request)
    assert bytes(e.s.a)==before and not e.done
    e.complete(request.tag);assert bytes(e.s.a)!=before
    request=until(e,'owner_done');e.accept(request)
    assert not e.done
    e.complete(request.tag);assert e.done


def test_selected_numeric_fault_and_write_error_fail_closed(native):
    e=Phase(native,fixture([[0x7f7f0000]*128],[[0x40000000]*128]),enabled=True,old_owners_idle=True)
    request=until(e,'matrix');e.accept(request)
    assert not e.poisoned  # numerical return remains an accepted obligation
    e.complete(request.tag)
    assert e.poisoned and e.drained and not e.done
    e=new(native);request=until(e,'b_write');e.accept(request);e.complete(request.tag,error=True)
    assert e.poisoned and not e.done and e.slots[0] is None


def test_forged_address_rejected_without_mutating_offered_operation(native):
    e=new(native);request=until(e,'b_write')
    tag=replace(request.tag,address=('B',15,159,0))
    before=bytes(e.s.b)
    with pytest.raises(ValueError,match='admission'):
        e.accept(replace(request,tag=tag))
    assert e.offer()==request and e.pending is None and bytes(e.s.b)==before
