import pytest
from heteronpu.sequence_state_transactions import *
def addr(domain=StateDomain.KV,page=0,word=0):return StateAddress(PageKey(domain,0,0,page),word)
def test_cow():
 s=SequenceStateStore(16);s.create_sequence(1);s.write_committed(1,addr(),10);s.share_prefix(1,2,[addr().key]);s.write_committed(2,addr(),20);assert s.read_committed(1,addr())==10 and s.read_committed(2,addr())==20;s.validate()
def test_partial():
 s=SequenceStateStore(16);s.create_sequence(3);t=s.begin(3,max_steps=4)
 for step in range(4):t.write(step,addr(page=step//2,word=step),100+step)
 s.commit(t,2);assert s.read_committed(3,addr(word=0))==100 and s.read_committed(3,addr(page=1,word=2))==0
def test_stale():
 s=SequenceStateStore();s.create_sequence(4);old=s.begin(4,max_steps=1);new=s.begin(4,max_steps=1);s.commit(new,0)
 with pytest.raises(RuntimeError):s.commit(old,0)
def test_stress():
 r=transaction_stress_report(200);assert r['status']=='PASS' and r['counters']['copy_on_write']>0
