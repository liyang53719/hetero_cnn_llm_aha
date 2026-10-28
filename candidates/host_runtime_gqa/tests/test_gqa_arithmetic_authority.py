#!/usr/bin/env python3
"""Exact source delta and independent contract model. NOT Chisel/DUT/RTL proof."""
from pathlib import Path
import hashlib, importlib.util, json, re
C=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gqa_arithmetic_delta',C/'arithmetic_delta.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
actual={}
for name,pin in p.PINS.items():
 b=(p.B/name).read_bytes();need(hashlib.sha256(b).hexdigest()==pin,'frozen exact input '+name)
 s=(C/'source'/name).read_text();actual[name]=s
 need(s==p.expected(name,b.decode()),'exact reviewed source delta '+name)
 need(s.count('(')==s.count(')'),'balanced parentheses '+name)
 need(s.count('{')==s.count('}'),'balanced braces '+name)
protocol=actual['UnifiedMoeSharedArithmeticProtocolV5.scala']
adapter=actual['UnifiedMoeSharedArithmeticAdapterV5.scala']
need('val authorityKind=UInt(4.W)' in protocol and 'authorityKind=UInt(3.W)' not in protocol,'global4-bit domain')
need('val Count=11' in protocol and 'val ScalarClients=Seq(0,1,2,8)' in protocol,'unchanged slots and four scalar borrowers')
need('val OrdinaryGqaScalar=8' in protocol and 'val OrdinaryGqaStage=76' in protocol and 'val OrdinaryGqaMaximumOperations=3145728' in protocol,'separate bounded GQA slot')
need('profileId' not in protocol+adapter,'arithmetic definitions are not profile-specialized')
need(adapter.count('Module(new UnifiedVectorElement32BankV4)')==1,'one existing numerical bank')
need('Module(new Scalar' not in adapter and 'Module(new Matrix' not in adapter,'no new Scalar/Matrix service')
# Compare every old domain boundary against a genuinely frozen0..7 table.
stages=(64,65,66,64,65,66,67,68,69,69,72)
resources=(2,2,2,1,1,1,1,1,2,1,1)
caps=(133120,393216,512,1024,131072,128,294912,16384,1332736,262144,42506240)
old_caps={1:(1332736,262144),2:(13631488,2097152),3:(3731456,4096),4:(194624,0),5:(5259264,1048576),6:(2695168,0),7:(393216,0)}
new_caps={**old_caps,8:(3145728,0)}
def allowed(slot,kind,stage,resource,count,allocated=False,allocation=0,extended=True):
 ordinary=1<=kind<=(8 if extended else 7)
 if slot<8:
  domain=kind==0 and allocated and allocation!=0;expected=stages[slot];bound=caps[slot]
 else:
  domain=(ordinary if slot==8 else ordinary and kind not in (4,6,7,8) if slot==9 else kind==4) and not allocated and allocation==0
  expected=stages[slot] if kind==1 else 68+kind
  bound=caps[10] if slot==10 else (new_caps if extended else old_caps).get(kind,(0,0))[slot-8]
 return domain and stage==expected and resource==resources[slot] and 0<count<=bound
counts=(0,1,393216,393217,1332736,1332737,2695168,2695169,3145728,3145729,13631488,13631489,42506240,42506241)
for i in range(11):
 for k in range(8):
  for st in range(64,78):
   for res in range(3):
    for count in counts:
     need(allowed(i,k,st,res,count,i<8,1 if i<8 else 0)==allowed(i,k,st,res,count,i<8,1 if i<8 else 0,False),'old domain unchanged')
for i in range(11):
 for k in range(8,16):
  for st in range(64,78):
   for res in range(3):
    for count in counts:
     want=k==8 and i==8 and st==76 and res==2 and 0<count<=3145728
     need(allowed(i,k,st,res,count)==want,'GQA exclusive; reserved kinds reject')
need(8 != (8 & 7),'3-bit narrowing would alias GQA to MoE: widening is essential')
for allocated,allocation in ((True,1),(True,0),(False,1)):
 need(not allowed(8,8,76,2,1,allocated,allocation),'GQA cannot fabricate MoE allocation')
for m in (1,16,128):
 for c in (1,128,256):
  for h in (8,16):
   exact=6*m*c*h
   need(allowed(8,8,76,2,exact),'all fixed runtime geometry counts fit separate cap')
need(6*128*256*16==3145728,'fixed owner maximum bound')
need(6*128*128*8==786432 and 6*128*128*16==1572864,'first cold C128 exact counts not cap')
# A source model of original freshness, intentionally full-width64 transaction and16 epoch.
def fresh(tx,owner,epoch,prev_tx,prev_owner,prev_epoch,kind=8,prev_kind=7,allocation=0,prev_allocation=0):
 continuity=1<=kind<=8 and 1<=prev_kind<=8
 return tx>prev_tx or (tx==prev_tx and owner>prev_owner and continuity and allocation==prev_allocation and epoch==prev_epoch)
for tx,owner,epoch,want in ((0x200000001,7,9,False),(0x200000001,8,9,True),(0x100000001,8,9,False),(0x200000001,8,10,False),(0x300000001,0,10,True)):
 need(fresh(tx,owner,epoch,0x200000001,7,9)==want,'full txn/epoch and strict owner freshness')
need(not fresh(0x200000001,8,9,0x200000001,7,9,kind=9),'reserved authority does not gain continuity')
# Retirement intent cannot erase accepted/pending/held work or accept a partial success.
def retire(accepted,issued,returned,expected,held=False,raw=False,quarantine=False,ok=True):
 drained=not held and not raw and not quarantine and accepted==issued==returned
 return drained and (not ok or returned==expected)
for n in (0,1,786431,786432):
 need(retire(n,n,n,786432)==(n==786432),'success requires exact genuine returns')
need(not retire(786432,786431,786431,786432),'unissued offer is debt')
need(not retire(786432,786432,786431,786432),'accepted return debt remains')
for flag in ('held','raw','quarantine'):
 need(not retire(786432,786432,786432,786432,**{flag:True}),'pending '+flag+' prevents retirement')
# Mutation checks are against the exact allowed-delta oracle, not Python assertions.
mutations=[
 ('UnifiedMoeSharedArithmeticProtocolV5.scala','val authorityKind=UInt(4.W)','val authorityKind=UInt(3.W)'),
 ('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryGqa=8','val OrdinaryGqa=7'),
 ('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryGqaScalar=8','val OrdinaryGqaScalar=9'),
 ('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryGqaStage=76','val OrdinaryGqaStage=75'),
 ('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryGqaMaximumOperations=3145728','val OrdinaryGqaMaximumOperations=13631488'),
 ('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryRopeMaximumOperations=393216','val OrdinaryRopeMaximumOperations=3145728'),
 ('UnifiedMoeSharedArithmeticProtocolV5.scala','val Count=11','val Count=12'),
 ('UnifiedMoeSharedArithmeticProtocolV5.scala','val ScalarClients=Seq(0,1,2,8)','val ScalarClients=Seq(0,1,2,8,11)'),
 ('UnifiedMoeSharedArithmeticAdapterV5.scala',' && !ordinaryGqa\n','\n'),
 ('UnifiedMoeSharedArithmeticAdapterV5.scala','else if(i==10) ordinaryChunk','else if(i==10) ordinaryChunk || ordinaryGqa'),
 ('UnifiedMoeSharedArithmeticAdapterV5.scala','val scalarIdentity=io.coreScalar.result.bits.identity.asUInt===sPacket.identity.asUInt','val scalarIdentity=true.B'),
 ('UnifiedMoeSharedArithmeticAdapterV5.scala','io.coreScalar.request.valid:=sOffer','io.coreScalar.request.valid:=sOffer && !poison'),
 ('UnifiedMoeSharedArithmeticAdapterV5.scala','id.transactionId===previous.lease.identity.transactionId','id.transactionId(31,0)===previous.lease.identity.transactionId(31,0)'),
 ('UnifiedMoeSharedArithmeticAdapterV5.scala','a.hostEpoch===previous.hostEpoch','true.B'),
 ('UnifiedMoeSharedArithmeticAdapterV5.scala','io.retire(i).bits.lease.asUInt===leases(i).asUInt','true.B'),
 ('UnifiedMoeSharedArithmeticAdapterV5.scala','issued(i)===returned(i)','true.B'),
]
for name,a,b in mutations:
 need(a in actual[name],'mutation exists '+a)
 need(actual[name].replace(a,b)!=p.expected(name,(p.B/name).read_text()),'mutation rejected '+a)
# ALL profiles instantiate this one common interface/resource definition, not different widths.
common={'authority_kind_bits':4,'client_slots':11,'scalar_raw_clients':4,'format_raw_clients':4,'vector_raw_clients':2,'ordinary_vector_raw_clients':1,'new_scalar_banks':0,'new_matrix_services':0,'new_dma':0,'existing_vector32_banks':1,'gqa_authority_kind':8,'gqa_scalar_slot':8,'gqa_stage':76,'gqa_max_operations':3145728,'source_declared_authority_register_delta_bits':23}
profiles={str(i):dict(common) for i in range(5)}
need(all(v==common for v in profiles.values()),'common width/resources for every profile')
result={'status':'PASS_EXACT_SOURCE_DELTA_AND_AUTHORITY_MODEL_NOT_DUT','checks':checks,'mutations_rejected':len(mutations),'source_pins':[{'path':str(C/'source'/n),'bytes':len(s.encode()),'sha256':hashlib.sha256(s.encode()).hexdigest()} for n,s in actual.items()], 'common_profiles':profiles,'scope':'One globally widened4-bit metadata domain; new kind8/stage76 Scalar8 only. All0..7 domains and transport/held/identity/debt text remain frozen. No compile/elaboration/RTL/numerical proof.'}
print(json.dumps(result,indent=2))
