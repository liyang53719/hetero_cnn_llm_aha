"""Source/lexical checks only: no Scala compiler, elaborator, RTL or DUT."""
from pathlib import Path
import hashlib,json,re
C=Path(__file__).resolve().parent
P=C/'source/HostBlockCommandsV4.scala'
BASE=C.parent/'host_runtime_rope/source/HostBlockCommandsV4.scala'
checks=0

def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)

def block(s,a,b):return s.split(a,1)[1].split(b,1)[0]
required=[
 'enableRuntimeKvAppend:Boolean=false',
 'require(!enableRuntimeKvAppend || enableRuntimeRope',
 'val runtimeKvAppendCommand=enableRuntimeKvAppend.B && runtimeAttentionProfile && kv',
 'val isSoftmax=opcode===0x33.U;val kv=opcode===0x41.U',
 'val correctEngine=engine===Mux(isMatrix,2.U,Mux(kv,4.U,3.U))',
 ') || runtimeKvAppendCommand',
 'Mux(kv && !attentionCommandPolicy,validate,policyIssue)',
 'if(bf16AttentionCore||enableRuntimeKvAppend)',
 'val expectedKind=Mux(policySlot===attentionContextSlot,0x26.U,Mux(policySlot===attentionPolicySlot,0x24.U,',
 '(policySlot===attentionContextSlot)=/=(next===0xffffff.U)',
 'cp(63,56)===2.U','cp(115,108)===Mux(arithmetic,"ha1".U,0.U) && cp(127,116)===0.U',
 'finishRecord(cx,0x26.U) && cx(63,56)===2.U && cx(127,125)===0.U && cx(124)',
 'val runtimeAppendContext= !runtimeKvAppendCommand || (attentionOp===0.U && group===0.U &&',
 'attentionCapacity===128.U && attentionCold && attentionExpectedLength===0.U',
 'attentionExpectedGeneration===0.U && attentionQueryStart===0.U',
 'attentionBase===0.U && attentionCount===m && m>0.U && m<=128.U',
 'txCold && txGeneration===0.U && !attentionCacheValid',
 '(!bf16AttentionBlock.B || blockWindow) && runtimeAppendContext',
 'val cacheD=shape3(d,2.U,attentionCapacity,512.U)',
 'attentionAppend:=common && kv && attentionOp===0.U && shape2(a,rows,512.U) && shape2(b,rows,512.U) && cacheD',
 'qkProjectedValid.asUInt.andR && qkNormalizedValid.asUInt.andR && qkRotatedValid.asUInt.andR',
 'qkAbsolutePosition(0)===attentionQueryStart && qkAbsolutePosition(1)===attentionQueryStart',
 '(0 until 3).map(i=>qkRows(i)===rows && qkWindowBase(i)===attentionBase &&',
 'qkWindowCount(i)===attentionCount).reduce(_&&_)',
 'val appendLive=producers && !pendingAttentionValid && !pendingGqaValid && trusted',
 'sameAllocation(a,qkRotatedTensor(1)) && sameAllocation(b,qkProjectedTensor(2))',
 'liveSpan(a.address+(attentionBase.pad(64)<<10),a.address+((attentionBase.pad(64)+attentionCount)<<10))',
 'liveSpan(b.address+(attentionBase.pad(64)<<10),b.address+((attentionBase.pad(64)+attentionCount)<<10))',
 'val appendFresh=disjoint && readwrite(d) && Mux(attentionCacheValid,reusableAttentionCache(d),fresh(d))',
 'val attention=(bf16AttentionCore.B || runtimeAttentionProfile) && ((attentionCacheValid &&',
 '(pendingAttentionValid && overlap(address,end,pendingAttentionCache.address,pendingAttentionCache.paddedEnd))',
 'val runtimeKvAppend=runtimeKvAppendCommand && attentionAppend',
 'runtimeQkNorm || runtimeRope || runtimeKvAppend',
 'runtimeKvAppend && !attentionDistinct','runtimeKvAppend && !attentionLive','runtimeKvAppend && !attentionFresh',
 'boundRuntimePrefix:=runtimePrefix',
 'bound.m:=attentionCount;bound.n:=Mux(attentionAppend,512.U,2048.U);bound.k:=256.U',
 'bound.cacheCapacity:=attentionCapacity;bound.cacheLength:=Mux(attentionAppend,attentionExpectedLength,pendingAttentionLength)',
 'bound.expectedCacheLength:=attentionExpectedLength;bound.queryStart:=attentionQueryStart',
 'bound.writeBytes:=Mux(attentionAppend,attentionCount.pad(64)<<11,attentionCount.pad(64)<<12)',
 'mainPublishBytes:=Mux(attentionAppend,0.U,attentionCount.pad(64)<<12)',
 'val publicationSlots=Mux(coreFence||attentionFence||attentionAppend,0.U',
 'when(bound.kind=/=QwenOwnerKind.KvAppend.U){',
 '.elsewhen(bound.kind===QwenOwnerKind.KvAppend.U){',
 'pendingAttentionValid:=true.B;pendingAttentionCache:=tensors(2)',
 'pendingAttentionOldLength:=bound.cacheLength;pendingAttentionLength:=bound.cacheLength+bound.m',
 'pendingAttentionGeneration:=bound.expectedGeneration;pendingAttentionCold:=bound.cold',
 'pendingAttentionBase:=policy(attentionPolicySlot)(99,68);pendingAttentionCount:=bound.m',
 'when(state===issue && !boundRuntimePrefix && io.resident.get.resetRequired){fail(Status.Protocol.U)}',
 '.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))'
]
def contract(s):
 for r in required:
  if r not in s:raise ValueError('missing '+r)
 pub=block(s,'.elsewhen(boundRuntimePrefix){','.elsewhen(boundMoePhase){')
 for t in ('attentionCacheValid:=','attentionCache:=','attentionContext:=','attentionLength:=','attentionGeneration:=','stateValid:=','currentGeneration:=','currentStateAddress:=','currentHistoryAddress:='):
  if t in pub:raise ValueError('premature global commit '+t)
 kv=block(pub,'.elsewhen(bound.kind===QwenOwnerKind.KvAppend.U){','.elsewhen(bound.kind===QwenOwnerKind.Dense.U){')
 for t in ('producedValid','producedCount','pendingGqaValid:=true.B','state:=finish'):
  if t in kv:raise ValueError('KV staged receipt polluted '+t)
 if pub.index('when(io.runtimeAuthority.currentFault)')>pub.index('pendingAttentionValid:=true.B'):raise ValueError('fault after staged receipt')
 no_kv=block(pub,'when(bound.kind=/=QwenOwnerKind.KvAppend.U){','        when(bound.kind===QwenOwnerKind.GdnConv.U){')
 if 'producedValid(out):=true.B' not in no_kv:raise ValueError('no explicit exclusion from live producer table')

s=P.read_text();base=BASE.read_text();contract(s)
for r in required:need(r in s,r)
need(hashlib.sha256(BASE.read_bytes()).hexdigest()=='e6274123e393b4bc29879f7e9b4bfffa09042f6258d48193d83e98df2e5f822c','exact prior Commands baseline')
need(s.count('Module(new')==base.count('Module(new'),'same original metadata hardware')
for a,b in [
 ('    when(!headerOK)','  when(state===fetch'),
 ('    .elsewhen(attentionCommandPolicy){','    .elsewhen(qkCommandPolicy){'),
 ('    val nativeQkNorm=','    val attentionAppend='),
 ('  when(io.job.fire){','  when(io.completion.fire){'),
 ('    .elsewhen(boundMoePhase){','  if(enableResidentFfn){when(state===complete'),
 ('  val phaseResidentFault=','  val runtimeAccepted='),
 ('  io.runtimeAuthority.accepted:=','  when(io.result.fire)'),
 ('    val nativeWeight=','    val nativeQkNorm=')]:
 need(block(s,a,b)==block(base,a,b),'preserved '+a)
mutations=[
 ('attentionCapacity===128.U','attentionCapacity<=256.U'),
 ('attentionBase===0.U && attentionCount===m','true.B'),
 ('attentionExpectedGeneration===0.U && attentionQueryStart===0.U','true.B'),
 ('txCold && txGeneration===0.U && !attentionCacheValid','true.B'),
 ('sameAllocation(a,qkRotatedTensor(1)) && sameAllocation(b,qkProjectedTensor(2))','true.B'),
 ('qkRotatedValid.asUInt.andR','true.B'),
 ('qkAbsolutePosition(1)===attentionQueryStart','true.B'),
 ('qkWindowCount(i)===attentionCount','true.B'),
 ('runtimeKvAppend && !attentionLive','false.B'),
 ('runtimeKvAppend && !attentionFresh','false.B'),
 ('runtimeKvAppend && !attentionDistinct','false.B'),
 ('when(bound.kind=/=QwenOwnerKind.KvAppend.U){','when(true.B){'),
 ('mainPublishBytes:=Mux(attentionAppend,0.U,attentionCount.pad(64)<<12)','mainPublishBytes:=d.payloadBytes'),
 ('Mux(kv && !attentionCommandPolicy,validate,policyIssue)','Mux(kv,validate,policyIssue)'),
 ('pendingAttentionValid:=true.B;pendingAttentionCache:=tensors(2)','pendingAttentionValid:=true.B;attentionCacheValid:=true.B;pendingAttentionCache:=tensors(2)'),
 ('when(state===issue && !boundRuntimePrefix && io.resident.get.resetRequired)','when(state===issue && io.resident.get.resetRequired)'),
 ('.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))','.elsewhen(false.B)')
]
for old,new in mutations:
 need(old in s,'mutation target '+old)
 try:contract(s.replace(old,new))
 except ValueError:need(True,'mutation rejected')
 else:raise ValueError('surviving mutation '+old)
lex=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S)
stack=[];pairs={')':'(',']':'[','}':'{'}
for c in lex:
 if c in '([{':stack.append(c)
 elif c in pairs:need(bool(stack) and stack.pop()==pairs[c],'balanced lexical delimiters')
need(not stack,'closed delimiters')
for m in (1,16,128):
 for profile in (2,4):
  need(m*2*256*2==m<<10,'one plane ACK bytes')
  need(2*(m<<10)==m<<11,'two planes total ACK bytes')
  need((m<<10)<=128*1024,'append inside capacity')
  need(128*1024+(m<<10)<=128*2048,'V tail inside fixed cache')
print(json.dumps(dict(status='PASS_SOURCE_LEXICAL_CONTRACT_ONLY_NOT_SCALA_RTL_DUT',checks=checks,rejected_mutations=len(mutations),source_sha256=hashlib.sha256(P.read_bytes()).hexdigest(),base_sha256=hashlib.sha256(BASE.read_bytes()).hexdigest(),common_kv_heads=2,head_dim=256,cache_capacity_tokens=128,common_dense_rows=[16,128],cold_position=0,new_arithmetic_modules=0,whole_block_fence_closed=True,full_m128_pass=0,full_rtl_pass=0),indent=2))
