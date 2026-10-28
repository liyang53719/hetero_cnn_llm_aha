"""Bounded source/mutation contracts only. Not Scala elaboration or DUT evidence."""
from pathlib import Path
import re,json,hashlib
C=Path(__file__).resolve().parent;B=C.parent/'host_runtime_rope/source'
checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
def pin(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def lex(s):return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"','',s)
s={p.name:p.read_text() for p in (C/'source').glob('*.scala')}
r=json.loads((C/'SOURCE_PINS.json').read_text())['source_check_originals']['QwenOwnerProtocol.scala']
q=pin(B/'QwenOwnerProtocol.scala');need(q['bytes']==r['bytes'] and q['sha256']==r['sha256'],'exact public predecessor QwenOwnerProtocol')
required={
 'QwenOwnerProtocol.scala':[
  'enableRuntimeKvAppend:Boolean=false','require(!enableRuntimeKvAppend || enableRuntimeRope',
  'Module(new Bf16KvAppendRuntimeOwnerV13)','bf16AttentionCore && !enableRuntimeKvAppend',
  'enableRuntimeKvAppend.B && ordinaryJob.bits.activationBf16 && ordinaryJob.bits.weightBf16 && ordinaryJob.bits.outputBf16',
  'runtimeKvAppend.foreach(_.io.parentFault:=port.parentFault)',
  'runtimeKvAppend.toSeq.map(_.io.resetRequired)','runtimeKvAppend.map(_.io.resourcesDrained).getOrElse(true.B)',
  '(enableRuntimeKvAppend.B && kvAppendJobHeld && choose===12.U)',
  'kv.io.job.bits:=Bf16KvAppendRuntimeJobV13.fromOwner(ordinaryJob.bits)',
  'io.runtimeKvAppendDoneFire.get.valid:=kv.io.done.fire',
  'd.keyAckBytes=/=planeBytes || d.valueAckBytes=/=planeBytes',
  'd.memoryAccepted=/=(j.tokens.pad(32)<<6) || d.memoryReturned=/=d.memoryAccepted',
  'runtimeKvAppend.toSeq.map(x=>12->x.io.memory)','runtimeKvAppend.toSeq.map(x=>12->x.io.response)'],
 'HostBlockTopV4.scala':[
  'enableRuntimeRope=true,enableRuntimeKvAppend=true','new SharedMemoryArbiter(17)',
  'val kvPlaneBytes=nj.m.pad(80)<<10','val kvPlaneStride=nj.cacheCapacity.pad(80)<<10',
  'val kvTailOffset=nj.queryStart.pad(80)<<10',
  'nwithin(nj.dst.pad(80)+kvTailOffset,kvPlaneBytes) || nwithin(nj.dst.pad(80)+kvPlaneStride+kvTailOffset,kvPlaneBytes)',
  'Mux(kvJob,nwithin(nj.a,kvPlaneBytes) || nwithin(nj.b,kvPlaneBytes)',
  'nr.bits.tag(63,32)===nj.tag && nrights','owner.io.response<>hub.io.responses(1)',
  'val normPublish=HeldDecoupledOffer'],
 'HostRuntimePrefixLeaseWiringV8.scala':[
  '(j.kind===QwenOwnerKind.KvAppend.U && j.activationBf16 && j.weightBf16 && j.outputBf16)',
  'authority.transaction===rotatedKTransaction','authority.launch.asUInt===rotatedKHost.asUInt',
  '!rotatedKValid || !rotatedKCurrent || !ropeQCommitted || !projectionCurrent',
  'rotatedKTransaction=/=projectionTransaction || rotatedKHost.asUInt=/=projectionHost.asUInt',
  'rotatedKResult.accepted.output=/=q.a || rotatedKResult.accepted.positionBase=/=q.queryStart',
  'v.qkRole=/=2.U || v.n=/=512.U || v.m=/=q.m || v.dst=/=q.b',
  'v.tag=/=vd.tag || vd.status=/=Status.Ok.U || vd.writeBytes=/=(q.m.pad(64)<<10)',
  '(rotatedKJob.tag<=kvLastKey || v.tag<=kvLastValue)',
  'logical.n===512.U && logical.k===256.U && logical.cacheCapacity===128.U',
  'logical.cold && logical.queryStart===0.U && logical.cacheLength===0.U && logical.expectedCacheLength===0.U',
  'kvKeyProducer.tag<g.io.physicalJob.bits.tag && kvValueProducer.tag<g.io.physicalJob.bits.tag',
  'kvKeyProducer.tag=/="hffffffff".U && kvValueProducer.tag=/="hffffffff".U',
  'kvKeyProducer.asUInt===rotatedKJob.asUInt && kvKeyResult.asUInt===rotatedKResult.asUInt',
  'kvValueProducer.asUInt===projectionJobs(2).asUInt && kvValueResult.asUInt===projectionResults(2).asUInt',
  '.elsewhen(kvShape){','kvLastKey:=kvKeyProducer.tag;kvLastValue:=kvValueProducer.tag',
  'kvEvent.bits.accepted.asUInt===kvExpected.asUInt',
  'kvEvent.bits.proposalValid && kvEvent.bits.drained','!leaseEventSubmitted && kvEvent.bits.cacheBase===logical.dst',
  'kvEvent.bits.keyAckBytes===kvPlaneBytes && kvEvent.bits.valueAckBytes===kvPlaneBytes',
  'kvEvent.bits.memoryAccepted===(logical.m.pad(32)<<6)',
  'kvEvent.bits.memoryReturned===kvEvent.bits.memoryAccepted','(kvShape && !kvEvent.valid)',
  'rotatedKJob:=retainedPhysical;rotatedKResult:=ropeEvent.bits',
  'kvReceipt.job:=retainedPhysical;kvReceipt.result:=kvEvent.bits;kvReceiptValid:=true.B',
  'authority.launch.asUInt===kvReceipt.host.asUInt','out.kvReceipt.valid:=kvReceiptValid && kvReceiptCurrent && !receiptFault && !kvLogical && !busy']}
def contracts(src):
 for n,rows in required.items():
  for row in rows:
   if row not in src[n]:raise ValueError(n+': '+row)
contracts(s)
for n,rows in required.items():
 for row in rows:need(row in s[n],n+': '+row)
for n,src in s.items():
 stack=[]
 for ch in lex(src):
  if ch in '([{':stack.append(ch)
  elif ch in ')]}':need(bool(stack) and stack.pop()=={')':'(',']':'[','}':'{'}[ch],n+' delimiter')
 need(not stack,n+' balanced')
need(s['HostBlockTopV4.scala'].count('enableRuntimeKvAppend=true')==2,'same common constructor flags')
need(s['QwenOwnerProtocol.scala'].count('Module(new Bf16KvAppendRuntimeOwnerV13)')==1,'one runtime owner')
need('Module(new' not in lex(s['Bf16KvAppendRuntimeOwnerV13.scala']),'zero new arithmetic/DMA bank')
prefix=s['HostRuntimePrefixLeaseWiringV8.scala'];branch=prefix.split('.elsewhen(kvShape){',1)[1].split('.elsewhen(prepShape)',1)[0]
need('acquirePending:=true.B' not in branch and 'leaseEventSubmitted:=true.B' not in branch,'KV gets zero arithmetic authority')
need('mode===12.U' not in s['QwenOwnerProtocol.scala'].split('sharedScalarAvailable:=',1)[1].split('transportFault:=',1)[0],'no scalar12 lending exception')
for marker in ('val core=Module(new Qwen2ContinuousBlock(','val matrix=Module(new MatrixPipelineService('):
 old=[x.strip() for x in (B/'QwenOwnerProtocol.scala').read_text().splitlines() if marker in x]
 new=[x.strip() for x in s['QwenOwnerProtocol.scala'].splitlines() if marker in x]
 need(old==new,'unchanged actual core/Matrix instantiation')
old=(B/'QwenOwnerProtocol.scala').read_text().split('class QwenOwnerJob extends Bundle {',1)[1].split('\n}',1)[0]
new=s['QwenOwnerProtocol.scala'].split('class QwenOwnerJob extends Bundle {',1)[1].split('\n}',1)[0]
need(lex(old)==lex(new),'QwenOwnerJob entire ABI unchanged')
need('state===issue && !boundRuntimePrefix && io.resident.get.resetRequired' in s['HostBlockCommandsV4.scala'],'r2 held resident fix')
mutations=[]
for n,rows in required.items():
 for row in rows:
  changed=dict(s);changed[n]=s[n].replace(row,'REMOVED_CONTRACT')
  try:contracts(changed)
  except ValueError:mutations.append(n+': '+row)
  else:raise ValueError('survived source mutation')
print(json.dumps(dict(status='PASS_SOURCE_CONTRACTS_ONLY_NOT_SCALA_OR_DUT',checks=checks,mutation_rejections=len(mutations),source_pins=[pin(p) for p in sorted((C/'source').glob('*.scala'))]),indent=2))
