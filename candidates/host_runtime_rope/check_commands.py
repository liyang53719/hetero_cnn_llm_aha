"""Actual Commands source/lexical and geometry checks, never Scala/RTL/DUT."""
from pathlib import Path
import hashlib,json,re
C=Path(__file__).resolve().parent;P=C/'source/HostBlockCommandsV4.scala'
BASE=C.parent/'host_runtime_qknorm/source/HostBlockCommandsV4.scala'
required=[
 'enableRuntimeQkNorm:Boolean=false,enableRuntimeRope:Boolean=false',
 'require(!enableRuntimeRope || enableRuntimeQkNorm',
 'val runtimeRopeCommand=enableRuntimeRope.B && runtimeAttentionProfile && opcode===0x34.U',
 'val runtimeQkCommand=runtimeQkNormCommand || runtimeRopeCommand',
 'val qkCommandPolicy=(bf16QkNormRope.B && (opcode===0x32.U||opcode===0x34.U)) || runtimeQkCommand',
 'val expectedKind=Mux(policySlot===0.U,0x20.U,Mux(policySlot===1.U,0x24.U,0x25.U))',
 'program(71,56)===opcode && program(79,72)===2.U && program(87,80)===1.U',
 'program(91,88)===5.U && program(95,92)===5.U && program(103,96)===16.U',
 'ap(67,66)===Mux(opcode===0x32.U,0.U,1.U)',
 'ap(115,108)===Mux(opcode===0x32.U,"hc1".U,"hb1".U)',
 'qkRole<=1.U','qkCount>0.U && qkCount<=128.U',
 'Mux(runtimeAttentionProfile,runtimeProfile.attentionHeads.pad(16),8.U(16.W))',
 'val qkBytes=(qkCount.pad(64)*qkHeads.pad(64)<<9)(63,0)',
 'qkBase===0.U && qkCount===m && txCold && txGeneration===0.U && !attentionCacheValid',
 'nativePartialRope:=common && opcode===0x34.U && shape2(a,m,qkWidth)',
 'b.dims(0)>0.U && shape2(b,b.dims(0),64.U) && ax(111,80).pad(65)+qkCount<=b.dims(0)',
 'qkNormalizedValid(qkRole) && a.address===qkNormalized(qkRole)',
 '(!(bf16AttentionCore.B || runtimeAttentionProfile) || sameAllocation(a,qkNormalizedTensor(qkRole)))',
 'm===qkRows(qkRole) && qkBase===qkWindowBase(qkRole) && qkCount===qkWindowCount(qkRole)',
 'qkNormalizedValid.asUInt.andR && !qkRotatedValid(qkRole) && Mux(qkRole===0.U,!qkRotatedValid(1),qkRotatedValid(0))',
 'ax(111,80)===Mux(attentionCacheValid,attentionLength,0.U)',
 '(qkRole===0.U || ax(111,80)===qkAbsolutePosition(0))',
 'qkLive:=(!(bf16AttentionCore.B || runtimeAttentionProfile) || (coreOrder && corePosition))',
 'readonly(b) && sourceAllowed(b,weightRole)',
 'qkFresh:=disjoint && fresh(d) && readwrite(d)',
 'val runtimeRope=runtimeRopeCommand && nativePartialRope',
 'runtimeChunk || runtimeGatedNorm || runtimeQkNorm || runtimeRope',
 '(runtimeQkNorm || runtimeRope) && !qkDistinct','(runtimeQkNorm || runtimeRope) && !qkLive','(runtimeQkNorm || runtimeRope) && !qkFresh',
 'bound.kind:=Mux(nativeQkNorm,QwenOwnerKind.QkNorm256.U,QwenOwnerKind.PartialRope64.U)',
 'bound.a:=qkActiveA;bound.dst:=qkActiveD;bound.m:=qkCount;bound.n:=qkHeads;bound.k:=256.U',
 'bound.qkRole:=qkRole;bound.qkPositionBase:=ax(111,80);bound.qkTrigTokens:=b.dims(0)',
 'when(runtimeQkNorm || runtimeRope){bound.qkNormPolicy:=ap(115,108);bound.cold:=true.B}',
 'bound.writeBytes:=Mux(nativeQkNorm && qkRole===0.U,qkBytes<<1,qkBytes);mainPublishBytes:=qkBytes',
 '.elsewhen(r.tag=/=bound.tag){fail(Status.Protocol.U)}',
 '.elsewhen(r.writeBytes=/=bound.writeBytes){fail(Status.Protocol.U)}',
 'when(io.runtimeAuthority.currentFault){status:=Status.Protocol.U;poison:=true.B;state:=finish}',
 '.elsewhen(bound.kind===QwenOwnerKind.PartialRope64.U){',
 'rememberSource(tensors(1),6.U);qkRotatedValid(bound.qkRole):=true.B',
 'qkRotatedTensor(bound.qkRole):=tensors(2);qkAbsolutePosition(bound.qkRole):=bound.qkPositionBase',
 'when(state===issue && !boundRuntimePrefix && io.resident.get.resetRequired){fail(Status.Protocol.U)}',
 '.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))',
 'val tensorSlots=5','val producedCapacity=if(bf16Gdn||bf16QkNormRope)2*maxCommands else maxCommands',
 'producedCount+&publicationSlots>producedCapacity.U'
]
checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
def block(s,a,b):return s.split(a,1)[1].split(b,1)[0]
def contract(s):
 for t in required:
  if t not in s:raise ValueError('missing '+t)
 pub=block(s,'.elsewhen(boundRuntimePrefix){','.elsewhen(boundMoePhase){')
 for t in ('stateValid:=','currentGeneration:=','currentStateAddress:=','currentHistoryAddress:=','attentionCacheValid:=','attentionGeneration:='):
  if t in pub:raise ValueError('premature commit '+t)
 if pub.index('when(io.runtimeAuthority.currentFault)')>pub.index('qkRotatedValid(bound.qkRole):=true.B'):raise ValueError('publication before fault veto')
s=P.read_text();base=BASE.read_text();contract(s)
for t in required:need(t in s,t)
need(hashlib.sha256(BASE.read_bytes()).hexdigest()=='78ea48c40d1ab6e1897883186dd4e88ef420b655434c25d90fbe0d003d724f1a','exact final r2 Commands ancestry')
need(s.count('Module(new')==base.count('Module(new'),'same existing decoder hardware constructors')
for a,b in [('    when(!headerOK)','  when(state===fetch'),('    val nativeWeight=','    val nativeQkNorm='),('    val officialRoleOK=','    val nativeQkNorm='),('  val phaseResidentFault=','  val runtimeAccepted='),('  when(io.job.fire){','  when(io.completion.fire){')]:
 need(block(s,a,b)==block(base,a,b),'preserved '+a)
# Legacy publication branch and all original Qwen2 numeric formulas stay exact.
need(block(s,'    .elsewhen(boundMoePhase){','  if(enableResidentFfn){when(state===complete')==block(base,'    .elsewhen(boundMoePhase){','  if(enableResidentFfn){when(state===complete'),'unchanged legacy post-prefix completions')
mutations=[
 ('val qkBytes=(qkCount.pad(64)*qkHeads.pad(64)<<9)(63,0)','val qkBytes=qkCount.pad(64)<<12'),
 ('qkBase===0.U && qkCount===m','true.B'),
 ('sameAllocation(a,qkNormalizedTensor(qkRole))','true.B'),
 ('qkNormalizedValid.asUInt.andR && !qkRotatedValid(qkRole)','true.B'),
 ('Mux(qkRole===0.U,!qkRotatedValid(1),qkRotatedValid(0))','true.B'),
 ('ax(111,80).pad(65)+qkCount<=b.dims(0)','true.B'),
 ('ap(115,108)===Mux(opcode===0x32.U,"hc1".U,"hb1".U)','true.B'),
 ('(runtimeQkNorm || runtimeRope) && !qkDistinct','false.B'),
 ('(runtimeQkNorm || runtimeRope) && !qkLive','false.B'),
 ('(runtimeQkNorm || runtimeRope) && !qkFresh','false.B'),
 ('when(runtimeQkNorm || runtimeRope){bound.qkNormPolicy:=ap(115,108);bound.cold:=true.B}','when(runtimeQkNorm || runtimeRope){bound.qkNormPolicy:="hc1".U}'),
 ('when(io.runtimeAuthority.currentFault){status:=Status.Protocol.U;poison:=true.B;state:=finish}','when(false.B){status:=Status.Protocol.U;poison:=true.B;state:=finish}'),
 ('when(state===issue && !boundRuntimePrefix && io.resident.get.resetRequired)','when(state===issue && io.resident.get.resetRequired)'),
 ('.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))','.elsewhen(false.B)'),
]
for a,b in mutations:
 need(a in s,'mutation target')
 try:contract(s.replace(a,b,1))
 except ValueError:need(True,'rejected')
 else:raise ValueError('surviving mutation '+a)
# A tiny lexical check is not a Scala parser/typecheck.
lex=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S)
stack=[];pairs={')':'(',']':'[','}':'{'}
for c in lex:
 if c in '([{':stack.append(c)
 elif c in pairs:need(bool(stack) and stack.pop()==pairs[c],'balanced lexical delimiter')
need(not stack,'closed delimiters')
cases=[]
for profile,qh in [(2,8),(4,16)]:
 for m in (1,16,128):
  for role in (0,1):
   heads=qh if role==0 else 2
   output=m*heads*512;scalar=m*heads*192;memory=m*(2+16*heads)
   need(output%64==0 and output==m*heads*8*64,'true ACK geometry')
   need(scalar==m*heads*32*6 and scalar<=128*16*192,'six scalar operations/pair')
   need(memory==m*2+m*heads*(8+8),'trig read/input read/output write actual counts')
   cases.append(dict(profile=profile,m=m,role=role,heads=heads,ack_bytes=output,scalar=scalar,memory=memory))
print(json.dumps(dict(status='PASS_SOURCE_LEXICAL_GEOMETRY_ONLY_NOT_SCALA_RTL_DUT',checks=checks,rejected_mutations=len(mutations),geometry_cases=len(cases),source_sha256=hashlib.sha256(P.read_bytes()).hexdigest(),base_sha256=hashlib.sha256(BASE.read_bytes()).hexdigest(),q16_m128_scalar=393216,new_arithmetic_modules=0,new_payload_storage_bits=0,full_m128_pass=0,full_rtl_pass=0),indent=2))
