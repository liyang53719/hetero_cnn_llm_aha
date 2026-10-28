#!/usr/bin/env python3
"""Source-delta and small authority-contract tests, NOT Chisel/DUT simulation."""
from pathlib import Path
import hashlib,json
W=Path(__file__).resolve().parents[2]
C=Path(__file__).resolve().parents[1]
B=W/'host_runtime_qknorm/source'
BASE_PINS={'UnifiedMoeSharedArithmeticAdapterV5.scala':'4ec49bd01eaefa92e708b3f22f85d7f9afad30313550f0704b270dbd7761c49a',
'UnifiedMoeSharedArithmeticProtocolV5.scala':'062da912b7f5f78ad428eaa9a7e3a89c5e492a65039ba1ccb8ba9649041b0235'}
checks=0
def need(v,m):
 global checks
 checks+=1
 if not v: raise ValueError(m)
def replace1(s,a,b):
 need(s.count(a)==1,'unique replacement: '+a)
 return s.replace(a,b)
def expected(name,s):
 if name.endswith('ProtocolV5.scala'):
  s=replace1(s,'  val OrdinaryQkNormMaximumOperations=2695168\n','  val OrdinaryQkNormMaximumOperations=2695168\n  val OrdinaryRopeScalar=8\n  val OrdinaryRopeStage=75\n  // Separate RoPE bound: M128 * Q16 * 32 pairs * six FP32 operations.\n  // Exact job count is M * heads * 192; this bound is not completion evidence.\n  val OrdinaryRopeMaximumOperations=393216\n')
  s=replace1(s,'val OrdinaryQkNorm=6\n','val OrdinaryQkNorm=6;val OrdinaryRope=7\n')
  s=replace1(s,'  * have separate bounds. No ordinary operation fabricates a MoE allocation.','  * have separate bounds. QKNorm kind6/stage74 and RoPE kind7/stage75 use\n  * Scalar8 ONLY, never Format9 or Vector10; neither widens another bound.\n  * No ordinary operation fabricates a MoE allocation.')
 else:
  s=replace1(s,'      k===UnifiedArithmeticAuthorityKindV5.OrdinaryQkNorm.U\n','      k===UnifiedArithmeticAuthorityKindV5.OrdinaryQkNorm.U ||\n      k===UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U\n')
  s=replace1(s,'    val ordinaryQkNorm=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryQkNorm.U\n','    val ordinaryQkNorm=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryQkNorm.U\n    val ordinaryRope=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U\n')
  s=replace1(s,'else if(i==9) ordinaryKind(a.authorityKind) && !ordinaryChunk && !ordinaryQkNorm\n','else if(i==9) ordinaryKind(a.authorityKind) && !ordinaryChunk && !ordinaryQkNorm && !ordinaryRope\n')
  s=replace1(s,'      else Mux(ordinaryQkNorm,UnifiedMoeArithmeticClientV5.OrdinaryQkNormStage.U,','      else Mux(ordinaryRope,UnifiedMoeArithmeticClientV5.OrdinaryRopeStage.U,\n        Mux(ordinaryQkNorm,UnifiedMoeArithmeticClientV5.OrdinaryQkNormStage.U,')
  s=replace1(s,'UnifiedMoeArithmeticClientV5.Stages(i).U)))))','UnifiedMoeArithmeticClientV5.Stages(i).U))))))')
  s=replace1(s,"    // Do not enlarge Norm, Conv, RawPrep or any MoE operation's count domain.",'    // Do not enlarge Norm, Conv, RawPrep, QKNorm or any other count domain.')
  s=replace1(s,'      else Mux(ordinaryQkNorm,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryQkNormMaximumOperations.U else 0.U),','      else Mux(ordinaryRope,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryRopeMaximumOperations.U else 0.U),\n        Mux(ordinaryQkNorm,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryQkNormMaximumOperations.U else 0.U),')
  s=replace1(s,'UnifiedMoeArithmeticClientV5.MaximumOperations(i).U)))))','UnifiedMoeArithmeticClientV5.MaximumOperations(i).U))))))')
 return s
actual={n:(C/'source'/n).read_text() for n in BASE_PINS}
expected_sources={}
for name,sha in BASE_PINS.items():
 b=(B/name).read_bytes();need(hashlib.sha256(b).hexdigest()==sha,'baseline pin '+name)
 expected_sources[name]=expected(name,b.decode());need(actual[name]==expected_sources[name],'exact reviewed delta '+name)
 # Scala delimiters outside comments/string literals: targeted new nested Muxs.
 s=actual[name]
 need(s.count('(')==s.count(')'),'parentheses '+name)
 need(s.count('{')==s.count('}'),'braces '+name)
mutations=[
('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryRopeScalar=8','val OrdinaryRopeScalar=9'),
('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryRopeStage=75','val OrdinaryRopeStage=74'),
('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryRopeMaximumOperations=393216','val OrdinaryRopeMaximumOperations=2695168'),
('UnifiedMoeSharedArithmeticProtocolV5.scala','val OrdinaryRope=7','val OrdinaryRope=6'),
('UnifiedMoeSharedArithmeticProtocolV5.scala','val Count=11','val Count=12'),
('UnifiedMoeSharedArithmeticProtocolV5.scala','val authorityKind=UInt(3.W)','val authorityKind=UInt(2.W)'),
('UnifiedMoeSharedArithmeticProtocolV5.scala','val ScalarClients=Seq(0,1,2,8)','val ScalarClients=Seq(0,1,2,8,11)'),
('UnifiedMoeSharedArithmeticAdapterV5.scala',' && !ordinaryRope\n','\n'),
('UnifiedMoeSharedArithmeticAdapterV5.scala','else if(i==10) ordinaryChunk','else if(i==10) ordinaryChunk || ordinaryRope'),
('UnifiedMoeSharedArithmeticAdapterV5.scala','val scalarIdentity=io.coreScalar.result.bits.identity.asUInt===sPacket.identity.asUInt','val scalarIdentity=true.B'),
('UnifiedMoeSharedArithmeticAdapterV5.scala','io.coreScalar.request.valid:=sOffer','io.coreScalar.request.valid:=sOffer && !poison'),
('UnifiedMoeSharedArithmeticAdapterV5.scala','id.transactionId===previous.lease.identity.transactionId','id.transactionId(31,0)===previous.lease.identity.transactionId(31,0)'),
('UnifiedMoeSharedArithmeticAdapterV5.scala','a.hostEpoch===previous.hostEpoch','true.B'),
('UnifiedMoeSharedArithmeticAdapterV5.scala','io.retire(i).bits.lease.asUInt===leases(i).asUInt','true.B'),
]
for n,a,b in mutations:
 need(actual[n].count(a)==1,'unique mutation '+a)
 need(actual[n].replace(a,b)!=expected_sources[n],'reject mutation '+a)
# Deliberately small independent authority-contract model; no arithmetic or HDL claims.
stages=[64,65,66,64,65,66,67,68,69,69,72]
resources=[2,2,2,1,1,1,1,1,2,1,1]
caps=[133120,393216,512,1024,131072,128,294912,16384,1332736,262144,42506240]
ordinary_caps={2:[13631488,2097152],3:[3731456,4096],4:[194624,0],5:[5259264,1048576],6:[2695168,0],7:[393216,0]}
def allowed(slot,kind,stage,resource,count,allocated=False,allocation=0,new=True):
 ordinary=lambda k:1<=k<=(7 if new else 6)
 if slot<8: domain=kind==0 and allocated and allocation!=0
 else: domain=(ordinary(kind) if slot==8 else ordinary(kind) and kind not in (4,6,7) if slot==9 else kind==4) and not allocated and allocation==0
 exstage=stages[slot] if slot<8 or kind==1 else 68+kind
 maxops=caps[slot] if slot<8 or kind==1 else caps[10] if slot==10 else ordinary_caps.get(kind,[0,0])[slot-8]
 return domain and stage==exstage and resource==resources[slot] and 0<count<=maxops
# Existing kind0..6 domains and bounds remain identical for every slot/stage/resource/count boundary.
for i in range(11):
 for k in range(7):
  for stage in range(64,77):
   for resource in (1,2):
    for count in (0,1,393216,393217,2695168,2695169,42506240,42506241):
     need(allowed(i,k,stage,resource,count,i<8,1 if i<8 else 0)==allowed(i,k,stage,resource,count,i<8,1 if i<8 else 0,new=False),'legacy domain unchanged')
for i in range(11):
 for stage in range(64,77):
  for resource in (1,2):
   for count in (0,1,191,192,128*16*192,128*16*192+1):
    need(allowed(i,7,stage,resource,count)==(i==8 and stage==75 and resource==2 and 0<count<=393216),'Rope exclusive slot/stage/cap')
for m in (1,16,128):
 for h in (2,8,16):
  exact=m*h*32*6
  need(exact==m*h*192 and allowed(8,7,75,2,exact),'exact arithmetic count in separate cap')
need(not allowed(8,7,75,2,192,True,1),'Rope never MoE allocation')
need(not allowed(8,7,75,2,192,False,1),'ordinary allocation sequence zero')
def fresh(tx,owner,epoch,ptx,powner,pepoch):
 return tx>ptx or tx==ptx and owner>powner and epoch==pepoch
need(not fresh(0x200000001,8,3,0x200000001,8,3),'equal owner replay')
need(not fresh(0x100000001,9,3,0x200000001,8,3),'txn high32 rollback')
need(fresh(0x200000001,9,3,0x200000001,8,3),'strict later owner')
need(not fresh(0x200000001,9,4,0x200000001,8,3),'same txn wrong epoch')
need(fresh(0x300000001,0,4,0x200000001,8,3),'new full txn')
result={'status':'PASS_SOURCE_DELTA_AND_SMALL_AUTHORITY_MODEL_NOT_DUT','checks':checks,'mutations_rejected':len(mutations),'source_pins':[{'path':str(C/'source'/n),'bytes':len(v.encode()),'sha256':hashlib.sha256(v.encode()).hexdigest()} for n,v in actual.items()], 'scope':'Only kind7/stage75 Scalar8 domain added; unchanged transport/held/identity/debt text. No compile/elaboration/numeric proof.'}
print(json.dumps(result,indent=2))
