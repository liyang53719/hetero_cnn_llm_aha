"""Source contract/mutation checks only. No Scala/Chisel/RTL/DUT execution."""
from pathlib import Path
import hashlib,json,re,difflib
C=Path(__file__).resolve().parent
B=C.parent/'host_runtime_kvappend/source/HostBlockCommandsV4.scala'
P=C/'source/HostBlockCommandsV4.scala'
s=P.read_text();base=B.read_text();checks=0

def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
def block(s,a,b):return s.split(a,1)[1].split(b,1)[0]
required=[
'enableRuntimeGqa:Boolean=false',
'require(!enableRuntimeGqa || enableRuntimeKvAppend',
'val runtimeGqaCommand=enableRuntimeGqa.B && runtimeAttentionProfile && (opcode===0x23.U || isSoftmax || opcode===0x24.U)',
') || runtimeKvAppendCommand || runtimeGqaCommand',
'((bf16AttentionCore.B || runtimeGqaCommand) && group=/=0.U) || waitEvent===previousSignal)',
'if(bf16AttentionCore||enableRuntimeKvAppend||enableRuntimeGqa)',
'val runtimeGqaContext= !runtimeGqaCommand || (attentionOp>=1.U && attentionOp<=3.U &&',
'attentionCapacity===128.U && attentionCold && attentionExpectedLength===0.U',
'attentionExpectedGeneration===0.U && attentionQueryStart===0.U',
'attentionBase===0.U && attentionCount===128.U && qkRows(0)===128.U',
'txCold && txGeneration===0.U && !attentionCacheValid',
'val attentionHeads=Mux(runtimeGqaCommand,runtimeProfile.attentionHeads.pad(16),8.U(16.W))',
'val attentionWidth=attentionHeads<<8',
'(!bf16AttentionBlock.B || blockWindow) && runtimeAppendContext && runtimeGqaContext',
'shape2(a,rows,attentionWidth) && cacheB',
'shape3(d,attentionHeads,attentionCount,attentionNewLength) && matrix(attentionCount,attentionNewLength,256.U,true.B)',
'shape3(a,attentionHeads,attentionCount,attentionNewLength) && shape3(d,attentionHeads,attentionCount,attentionNewLength) && program(1)',
'shape3(a,attentionHeads,attentionCount,attentionNewLength) && cacheB && shape2(d,rows,attentionWidth)',
'val runtimeGqa=runtimeGqaCommand && (attentionQk || attentionSoft || attentionPv)',
'runtimeQkNorm || runtimeRope || runtimeKvAppend || runtimeGqa',
'(runtimeKvAppend || runtimeGqa) && !attentionDistinct',
'(runtimeKvAppend || runtimeGqa) && !attentionLive',
'(runtimeKvAppend || runtimeGqa) && !attentionFresh',
'val queryWidth=Mux(runtimeGqa,runtimeProfile.attentionHeads.pad(16)<<8,2048.U(16.W))',
'val queryOffset=(attentionBase.pad(80)*queryWidth.pad(80))<<1',
'val outputBytes=(attentionCount.pad(80)*queryWidth.pad(80))<<1',
'bound.m:=attentionCount;bound.n:=Mux(attentionAppend,512.U,queryWidth);bound.k:=256.U',
'when(runtimeGqa){bound.qkNormPolicy:=1.U;bound.qkRole:=0.U}',
'bound.cacheCapacity:=attentionCapacity;bound.cacheLength:=Mux(attentionAppend,attentionExpectedLength,pendingAttentionLength)',
'bound.expectedCacheLength:=attentionExpectedLength;bound.queryStart:=attentionQueryStart',
'bound.currentGeneration:=Mux(attentionCacheValid,attentionGeneration,0.U);bound.expectedGeneration:=attentionExpectedGeneration;bound.cold:=attentionCold',
'bound.writeBytes:=Mux(attentionAppend,attentionCount.pad(64)<<11,outputBytes(63,0))',
'mainPublishBytes:=Mux(attentionAppend,0.U,outputBytes(63,0))',
'val runtimeGqaMacsWide=(bound.m.pad(96)*bound.cacheLength.pad(96)*bound.n.pad(96))<<1',
'val runtimeGqaAck=boundRuntimePrefix && bound.kind===QwenOwnerKind.Attention.U',
'(runtimeGqaMacsWide(runtimeGqaMacsWide.getWidth-1,64).orR || r.usefulMacs=/=runtimeGqaMacsWide(63,0))',
'.elsewhen(r.writeBytes=/=bound.writeBytes || badRuntimeGqaMacs(r)){fail(Status.Protocol.U)}',
'events(completionCommand(55,40)(log2Ceil(eventSlots)-1,0)):=true.B;completed:=completed+1.U',
'previousSignal:=completionCommand(55,40)',
'when(completingGroup && completionIndex<2.U){completionIndex:=completionIndex+1.U}',
'.elsewhen(bound.kind===QwenOwnerKind.Attention.U){',
'pendingGqaValid:=true.B;pendingAttentionContext:=tensors(2)',
'.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))',
'when(state===issue && !boundRuntimePrefix && io.resident.get.resetRequired){fail(Status.Protocol.U)}'
]
def contract(v):
 for x in required:
  if x not in v:raise ValueError('missing '+x)
 pub=block(v,'.elsewhen(boundRuntimePrefix){','.elsewhen(boundMoePhase){')
 for x in ('attentionCacheValid:=','attentionCache:=','attentionContext:=','attentionLength:=','attentionGeneration:=','stateValid:=','currentGeneration:=','currentStateAddress:=','currentHistoryAddress:='):
  if x in pub:raise ValueError('premature global publication '+x)
 if pub.index('when(io.runtimeAuthority.currentFault)')>pub.index('pendingGqaValid:=true.B'):raise ValueError('late fault bypass')
 if pub.index('when(completingGroup && completionIndex<2.U)')>pub.index('producedValid(out):=true.B'):raise ValueError('premature output publication')
 if pub.count('completed:=completed+1.U')!=1:raise ValueError('fused duplicate/missing completed counter')
 if pub.count('pendingGqaValid:=true.B')!=1:raise ValueError('fused duplicated staged success')
 if 'events(signalEvent' in pub:raise ValueError('PV event used for all fusion completions')
 if v.count('badRuntimeGqaMacs(r)){fail(Status.Protocol.U)}')!=2:raise ValueError('both done paths must check useful MACs')
contract(s)
need(hashlib.sha256(B.read_bytes()).hexdigest()=='bfe7b170b1174ef3c42326b3f1e55cdd8f8011b06ed9af37339f22fa33380334','frozen base pin')
for x in required:need(x in s,x)
# Exact unchanged common/legacy paths. Pure byte preservation, not simulation.
for a,b in [
 ('  val runtimeAttentionProfile=','  val pc='),
 ('    when(!headerOK)','  when(state===fetch'),
 ('    .elsewhen(attentionCommandPolicy){','    .elsewhen(qkCommandPolicy){'),
 ('    .elsewhen(qkCommandPolicy){','    .elsewhen(runtimeProjectionCommand){'),
 ('    val nativeQkNorm=','    val attentionAppend='),
 ('      val trusted=','      if(bf16AttentionBlock){'),
 ('    val runtimeNorm=','    val runtimeQkNorm='),
 ('    val supportedOrdinary=','    val initialValidation='),
 ('    .elsewhen(boundMoePhase){','  if(enableResidentFfn){when(state===complete'),
 ('  io.runtimeAuthority.accepted:=','  when(io.result.fire)'),
 ('    val nativeWeight=','    val nativeQkNorm='),
 ('      when(rope){','    if(enableTransposedDown){')]:
 need(block(s,a,b)==block(base,a,b),'preserved '+a)
need(s.count('Module(new')==base.count('Module(new'),'same actual metadata hardware instances')
# Original three public reader/typed paths are the only issuer, not a new shell.
need(s.count('val reader=Module(new Record128Reader)')==1,'one original reader')
need(s.count('val tensor=Module(new TypedTensorReader)')==1,'one original typed reader')
for k in ('0x23.U','0x33.U','0x24.U','0x41.U'):need(k in s,'original opcode '+k)
# Structural delimiter check strips comments/literals; not a compiler substitute.
clean=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S)
stack=[];pairs={')':'(',']':'[','}':'{'}
for c in clean:
 if c in '([{':stack.append(c)
 elif c in ')]}':
  need(bool(stack) and stack.pop()==pairs[c],'balanced Scala delimiters')
need(not stack,'closed Scala delimiters')
mutations=[
 ('enableRuntimeGqa.B && runtimeAttentionProfile','enableRuntimeGqa.B'),
 ('runtimeGqaCommand) && group=/=0.U','false.B) && group=/=0.U'),
 ('attentionCount===128.U && qkRows(0)===128.U','attentionCount>0.U'),
 ('runtimeAppendContext && runtimeGqaContext','runtimeAppendContext'),
 ('runtimeProfile.attentionHeads.pad(16),8.U(16.W)','8.U(16.W),8.U(16.W)'),
 ('shape3(a,attentionHeads,attentionCount,attentionNewLength) && cacheB','shape3(a,8.U,attentionCount,attentionNewLength) && cacheB'),
 ('runtimeKvAppend || runtimeGqa) && !attentionLive','runtimeKvAppend) && !attentionLive'),
 ('when(runtimeGqa){bound.qkNormPolicy:=1.U','when(runtimeGqa){bound.qkNormPolicy:=cp(108)'),
 ('*bound.n.pad(96))<<1',')<<12'),
 ('runtimeGqaMacsWide(runtimeGqaMacsWide.getWidth-1,64).orR','false.B'),
 (' || badRuntimeGqaMacs(r)',''),
 ('when(completingGroup && completionIndex<2.U){completionIndex:=completionIndex+1.U}','when(false.B){completionIndex:=completionIndex+1.U}'),
 ('pendingGqaValid:=true.B;pendingAttentionContext:=tensors(2)','attentionCacheValid:=true.B;pendingGqaValid:=true.B;pendingAttentionContext:=tensors(2)'),
 ('when(state===issue && !boundRuntimePrefix && io.resident.get.resetRequired)','when(state===issue && io.resident.get.resetRequired)'),
 ('.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))','.elsewhen(false.B)')]
for a,b in mutations:
 need(a in s,'mutation location '+a)
 try:contract(s.replace(a,b))
 except ValueError:continue
 raise ValueError('escaped mutation '+a)
result=dict(status='SOURCE_CONTRACT_ONLY_NOT_SCALA_OR_DUT',checks=checks,mutations_rejected=len(mutations),source_sha256=hashlib.sha256(P.read_bytes()).hexdigest(),base_sha256=hashlib.sha256(B.read_bytes()).hexdigest(),new_metadata_modules=0,launch_seal_preserved=True,full_m128_passes=0,rtl_five_profile_passes=0)
print(json.dumps(result,indent=2))
