"""Source/lexical and small geometry checks; explicitly not Scala, RTL or DUT."""
from pathlib import Path
import hashlib,json,re
C=Path(__file__).resolve().parent
P=C/'source/HostBlockCommandsV4.scala'
BASE=C.parent/'host_runtime_gatednorm/source/HostBlockCommandsV4.scala'
required=[
 'enableRuntimeQkNorm:Boolean=false',
 'runtimeAttentionProfile=enableRuntimeQkNorm.B && runtimeProfileKnown && (cfg.profileId===2.U || cfg.profileId===4.U)',
 'val runtimeQkNormCommand=runtimeAttentionProfile && opcode===0x32.U',
 'val runtimeProjectionCommand=runtimeNormProfile && (runtimeGdnProfile || runtimeAttentionProfile) && opcode===0x20.U',
 'if(bf16QkNormRope||enableRuntimeQkNorm){when(qkCommandPolicy && slot===3.U){tensor.io.request.bits.root:=policy(2)(79,56)}}',
 '(qkCommandPolicy && slot===3.U)',
 'if(bf16QkNormRope||enableRuntimeQkNorm){qkProjectedValid:=',
 'val rdAttentionWidth=Mux(rdRole===0.U,(runtimeProfile.attentionHeads.pad(16)<<9),512.U(16.W))',
 'val rdWidth=Mux(runtimeGdnProfile,rdGdnWidth,rdAttentionWidth)',
 'val rdOrder=Mux(runtimeGdnProfile,rdGdnOrder,rdAttentionOrder)',
 'txInputValid && txInputNormValid && sameAllocation(a,runtimeInputNormTensor)',
 'rdRole<=2.U',
 'when(runtimeAttentionProfile){bound.qkRole:=rdRole}',
 'bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B',
 'qkProjectedTensor(role):=tensors(2);qkRows(role):=bound.m',
 'qkWindowBase(role):=0.U;qkWindowCount(role):=bound.m',
 'Mux(runtimeAttentionProfile,runtimeProfile.attentionHeads.pad(16),8.U(16.W))',
 'val qkBytes=(qkCount.pad(64)*qkHeads.pad(64)<<9)(63,0)',
 'qkBase===0.U && qkCount===m && txCold && txGeneration===0.U && !attentionCacheValid',
 'Mux(runtimeQkNormCommand,ap(115,108)==="hc1".U || ap(115,108)==="hc2".U',
 'shape2(a,m,Mux(qkRole===0.U,qkWidth<<1,qkWidth))',
 'shape2(gate,m,qkWidth)',
 '(!(bf16AttentionCore.B || runtimeAttentionProfile) || sameAllocation(a,qkProjectedTensor(qkRole)))',
 'qkProjectedValid.asUInt.andR && !qkNormalizedValid(qkRole)',
 'Mux(qkRole===0.U,!qkNormalizedValid(1),qkNormalizedValid(0))',
 'qkLive:=(!(bf16AttentionCore.B || runtimeAttentionProfile) || (coreOrder && corePosition))',
 'val runtimeQkNorm=runtimeQkNormCommand && nativeQkNorm',
 'runtimeChunk || runtimeGatedNorm || runtimeQkNorm',
 'runtimeQkNorm && !qkDistinct','runtimeQkNorm && !qkLive','runtimeQkNorm && !qkFresh',
 'when(runtimeQkNorm){bound.qkNormPolicy:=ap(115,108);bound.cold:=true.B}',
 'bound.writeBytes:=Mux(nativeQkNorm && qkRole===0.U,qkBytes<<1,qkBytes);mainPublishBytes:=qkBytes',
 'qkNormalizedTensor(bound.qkRole):=tensors(2);rememberSource(tensors(1),4.U+bound.qkRole)',
 'starts(gateIndex):=bound.c;ends(gateIndex):=bound.c+mainPublishBytes',
 'attentionBlockValues(1):=tensors(3);attentionBlockValid(1):=true.B',
 '.elsewhen(r.tag=/=bound.tag){fail(Status.Protocol.U)}',
 '.elsewhen(r.writeBytes=/=bound.writeBytes){fail(Status.Protocol.U)}',
 'when(io.runtimeAuthority.currentFault){status:=Status.Protocol.U;poison:=true.B;state:=finish}',
 '.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))',
 'val tensorSlots=5',
 'val producedCapacity=if(bf16Gdn||bf16QkNormRope)2*maxCommands else maxCommands',
 'producedCount+&publicationSlots>producedCapacity.U',
]
checks=0
def need(b,msg):
 global checks
 checks+=1
 if not b: raise ValueError(msg)
def contract(s):
 for t in required:
  if t not in s: raise ValueError('missing '+t)
 pub=s.split('.elsewhen(boundRuntimePrefix){',1)[1].split('.elsewhen(boundMoePhase){',1)[0]
 for t in ('stateValid:=','currentGeneration:=','currentStateAddress:=','currentHistoryAddress:=','attentionCacheValid:=','attentionGeneration:='):
  if t in pub: raise ValueError('premature commit '+t)
 if pub.index('when(io.runtimeAuthority.currentFault)')>pub.index('qkNormalizedValid(bound.qkRole):=true.B'):
  raise ValueError('publication before fault veto')
s=P.read_text();base=BASE.read_text();contract(s)
for t in required:need(t in s,t)
need(hashlib.sha256(BASE.read_bytes()).hexdigest()=='5b44ddfa9e866823a4146eb91c21ed3748bfef6273075374f7af288e181117df','pinned GatedNorm ancestry')
need(s.count('Module(new')==base.count('Module(new'),'same arithmetic/module constructors')
seal=lambda x:x.split('    when(!headerOK)',1)[1].split('  when(state===fetch',1)[0]
need(seal(s)==seal(base),'unchanged complete-launch seal')
# Original profile0 numeric storage/official policy blocks remain byte-identical.
for a,b in [('    val nativeWeight=','    val nativeQkNorm='),('    val officialRoleOK=','    val nativeQkNorm=')]:
 need(s.split(a,1)[1].split(b,1)[0]==base.split(a,1)[1].split(b,1)[0],'unchanged profile0 '+a)
mutations=[
 ('val qkBytes=(qkCount.pad(64)*qkHeads.pad(64)<<9)(63,0)','val qkBytes=qkCount.pad(64)<<12'),
 ('when(runtimeAttentionProfile){bound.qkRole:=rdRole}','when(runtimeAttentionProfile){bound.qkRole:=0.U}'),
 ('qkBase===0.U && qkCount===m','true.B'),
 ('sameAllocation(a,qkProjectedTensor(qkRole))','true.B'),
 ('qkProjectedValid.asUInt.andR && !qkNormalizedValid(qkRole)','true.B'),
 ('runtimeQkNorm && !qkDistinct','false.B'),('runtimeQkNorm && !qkLive','false.B'),('runtimeQkNorm && !qkFresh','false.B'),
 ('when(runtimeQkNorm){bound.qkNormPolicy:=ap(115,108);bound.cold:=true.B}','when(runtimeQkNorm){bound.qkNormPolicy:="hc1".U}'),
 ('qkNormalizedTensor(bound.qkRole):=tensors(2);rememberSource(tensors(1),4.U+bound.qkRole)','attentionCacheValid:=true.B'),
 ('when(io.runtimeAuthority.currentFault){status:=Status.Protocol.U;poison:=true.B;state:=finish}','when(false.B){status:=Status.Protocol.U;poison:=true.B;state:=finish}'),
 ('.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))','.elsewhen(false.B)'),
]
for a,b in mutations:
 need(a in s,'mutation target')
 try:contract(s.replace(a,b,1))
 except ValueError:need(True,'rejected')
 else:raise ValueError('surviving mutation '+a)
lex=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S)
stack=[];pairs={')':'(',']':'[','}':'{'}
for c in lex:
 if c in '([{':stack.append(c)
 elif c in pairs:need(bool(stack) and stack.pop()==pairs[c],'balanced lexical delimiter')
need(not stack,'closed delimiters')
# Geometry only. Exact scalar counts bind future physical lease checks, NOT measured performance.
cases=[]
for profile,qh,h in [(2,8,1024),(4,16,2048)]:
 for m in (1,16,128):
  for role in (0,1):
   heads=qh if role==0 else 2
   output=m*heads*256*2;input_bytes=output*(2 if role==0 else 1)
   need(input_bytes==m*(qh*512 if role==0 else 512)*2,'input projected allocation')
   need(output%64==0,'aligned output')
   for policy,count in [('c1',1290),('c2',1316)]:
    scalar=m*heads*count
    need(0<scalar<=128*16*1316,'scalar domain')
    cases.append(dict(profile=profile,m=m,role=role,policy=policy,heads=heads,scalar=scalar,input_bytes=input_bytes,ack_bytes=output*(2 if role==0 else 1)))
print(json.dumps(dict(status='PASS_SOURCE_LEXICAL_GEOMETRY_ONLY_NOT_SCALA_RTL_DUT',checks=checks,rejected_mutations=len(mutations),geometry_cases=len(cases),source_sha256=hashlib.sha256(P.read_bytes()).hexdigest(),q16_m128_c2_scalar=128*16*1316,new_arithmetic_modules=0,capacity_delta='Existing produced allocation table unchanged; Q publishes two entries only if capacity check accepts; no new numerical payload'),indent=2))
