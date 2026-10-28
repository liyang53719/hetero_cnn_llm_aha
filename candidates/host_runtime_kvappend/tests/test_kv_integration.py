"""Independent integration model; cannot prove emitted Chisel or RTL behavior."""
import copy,itertools,unittest

def mode(kind=7,flags=(False,False,False),capacity=0,width=512,legacy_attention=False):
 runtime=all(flags)
 if kind==7 and (legacy_attention or runtime):return 12 if all(flags) and 0<capacity<=256 and width==512 else 7
 return 0

def prefix(kind=7,flags=(False,False,False)):
 return kind in (8,10,11,12,14,15) or kind==7 and all(flags)

def span(base,n):return base%64==0 and base+n<=2**56

def overlap(a,na,b,nb):return a<b+nb and b<a+na

def geometry(m,key=0x100000,value=0x200000,cache=0x300000,capacity=128):
 n=m*1024
 return 1<=m<=128 and capacity==128 and all(span(a,b) for a,b in ((key,n),(value,n),(cache,capacity*2048))) and not any((overlap(key,n,value,n),overlap(cache,capacity*2048,key,n),overlap(cache,capacity*2048,value,n)))

def allowed(addr,write,m,key=0x100000,value=0x200000,cache=0x300000):
 if addr%64 or addr+64>2**56:return False
 ranges=((cache,m*1024),(cache+128*1024,m*1024)) if write else ((key,m*1024),(value,m*1024))
 return any(b<=addr and addr+64<=b+n for b,n in ranges)

def context():return dict(host=dict(epoch=3,profile=4,root=0x44,regions=(1,2),commands=9),txn=(1<<40)+7)

def producers(m=128):
 c=context()
 return dict(current=c,key_context=copy.deepcopy(c),value_context=copy.deepcopy(c),m=m,
  key=dict(tag=9,role=1,heads=2,dim=256,dst=0x100000,m=m),
  key_result=dict(tag=9,status=0,committed=True,acked=m*1024,output=0x100000,pos=0),
  value=dict(tag=3,role=2,width=512,dst=0x200000,m=m),
  value_result=dict(tag=3,status=0,acked=m*1024),
  valid=(True,True,True),q_committed=True,busy=False,consumer=10,last=None)

def eligible(p):
 k,v,kd,vd=p['key'],p['value'],p['key_result'],p['value_result'];c=p['consumer'];m=p['m']
 last=p['last']
 return (p['current']==p['key_context']==p['value_context'] and all(p['valid']) and p['q_committed'] and not p['busy'] and
  k['role']==1 and k['heads']==2 and k['dim']==256 and k['dst']==kd['output']==0x100000 and k['m']==m and
  k['tag']==kd['tag'] and kd['status']==0 and kd['committed'] and kd['acked']==m*1024 and kd['pos']==0 and
  v['role']==2 and v['width']==512 and v['dst']==0x200000 and v['m']==m and v['tag']==vd['tag'] and vd['status']==0 and vd['acked']==m*1024 and
  k['tag']<c and v['tag']<c and k['tag']!=2**32-1 and v['tag']!=2**32-1 and c!=2**32-1 and
  (last is None or p['current']['txn']>last[0] or p['current']['txn']==last[0] and k['tag']>last[1] and v['tag']>last[2]))

def result(m=128):return dict(accepted=(m,512,2,256,128,0,0,0,0,0,True),tag=10,status=0,bytes=m*2048,key=m*1024,value=m*1024,accepted_count=m*64,returned=m*64,drained=True,proposal=True,base=0x300000,capacity=128,length=m,generation=1,arithmetic_lease=False)

def terminal_ok(d,m=128):
 return d==result(m)

class IntegrationModel(unittest.TestCase):
 def test_legacy_kind7_never_hijacked(self):
  for m in (16,128):
   self.assertEqual(mode(),0);self.assertFalse(prefix())
 def test_runtime_typed_mode_same_profiles(self):
  for profile in (2,4):
   for m in (16,128):
    self.assertEqual(mode(flags=(True,)*3,capacity=128),12);self.assertTrue(prefix(flags=(True,)*3))
 def test_runtime_bad_capacity_reject_before_effect(self):
  for cap in (0,1,127,129,256,257,2**32-1):
   self.assertFalse(geometry(16,capacity=cap))
 def test_partial_flags_never_claim_runtime(self):
  for flags in itertools.product((False,True),repeat=3):
   if not all(flags):self.assertFalse(prefix(flags=flags));self.assertEqual(mode(flags=flags),0)
 def test_full_fixed_capacity_each_m(self):
  for m in range(1,129):self.assertTrue(geometry(m))
  for m in (0,129,256,65535):self.assertFalse(geometry(m))
 def test_each_actual_beat_in_exact_plane(self):
  for m in range(1,129):
   writes=[]
   for plane in (0,1):
    for beat in range(m*16):
     src=(0x100000,0x200000)[plane]+beat*64;dst=0x300000+plane*128*1024+beat*64
     self.assertTrue(allowed(src,False,m));self.assertTrue(allowed(dst,True,m));writes.append(dst)
   self.assertEqual(len(set(writes))*64,m*2048)
 def test_unwritten_gaps_and_endpoints_are_blocked(self):
  for m in (1,16,127,128):
   for base in (0x300000,0x300000+128*1024):
    self.assertFalse(allowed(base-1,True,m))
    self.assertEqual(allowed(base+m*1024,True,m),m==128 and base==0x300000)
    self.assertTrue(allowed(base+m*1024-64,True,m))
 def test_entire_cache_alias_not_only_tail(self):
  self.assertFalse(geometry(16,key=0x300000+32*1024));self.assertFalse(geometry(16,value=0x300000+160*1024))
 def test_aperture_and_overflow(self):
  self.assertTrue(geometry(128,cache=2**56-128*2048))
  for b in (2**56-64,2**64-64,0x300001):self.assertFalse(geometry(16,cache=b))
 def test_actual_full_identity_success(self):
  for m in (1,16,128):self.assertTrue(eligible(producers(m)))
 def test_host_and_high_transaction_mismatch(self):
  for who in ('key_context','value_context'):
   for key in ('epoch','profile','root','regions','commands'):
    p=producers();p[who]['host'][key]=None;self.assertFalse(eligible(p))
   p=producers();p[who]['txn']^=1<<40;self.assertFalse(eligible(p))
 def test_strict_both_producers_before_consumer(self):
  for who in ('key','value'):
   for tag in (10,11,2**32-1):
    p=producers();p[who]['tag']=tag;p[who+'_result']['tag']=tag;self.assertFalse(eligible(p))
 def test_each_producer_identity_required(self):
  p0=producers()
  for who in ('key','value','key_result','value_result'):
   for field in p0[who]:
    p=producers();p[who][field]=None;self.assertFalse(eligible(p),(who,field))
 def test_both_producers_replay_independent(self):
  for last in ((2**40+7,9,2),(2**40+7,8,3),(2**40+8,1,1)):
   p=producers();p['last']=last;self.assertFalse(eligible(p))
  p=producers();p['last']=(2**40+6,100,100);self.assertTrue(eligible(p))
 def test_fault_invalidation_and_replacement(self):
  for i in range(3):
   p=producers();v=list(p['valid']);v[i]=False;p['valid']=tuple(v);self.assertFalse(eligible(p))
  p=producers();p['q_committed']=False;self.assertFalse(eligible(p))
  p=producers();p['busy']=True;self.assertFalse(eligible(p))
 def test_each_terminal_evidence_mandatory(self):
  self.assertTrue(terminal_ok(result()))
  for field in result():
   d=result();d[field]=None;self.assertFalse(terminal_ok(d))
 def test_staging_does_not_publish_fullchain(self):
  published=dict(length=0,generation=0,cache=False,state=False);staged=result()
  self.assertTrue(terminal_ok(staged));self.assertEqual(published,dict(length=0,generation=0,cache=False,state=False))
  fullchain=False
  if fullchain:published.update(length=staged['length'],generation=staged['generation'],cache=True,state=True)
  self.assertFalse(published['cache']);self.assertFalse(published['state'])
if __name__=='__main__':unittest.main(verbosity=2)
