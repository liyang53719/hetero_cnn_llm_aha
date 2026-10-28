"""Actual integration source/mutation checks only; no Scala/elab/RTL/DUT."""
from pathlib import Path
import hashlib,json,re
C=Path(__file__).resolve().parent;B=C.parent/'host_runtime_qknorm/source'
s={p.name:p.read_text() for p in (C/'source').glob('*.scala')};checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
def pin(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def lex(x):return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"','',x)
r=json.loads((C/'SOURCE_PINS.json').read_text())['source_check_originals']['QwenOwnerProtocol.scala']
q=pin(B/'QwenOwnerProtocol.scala');need(q['bytes']==r['bytes'] and q['sha256']==r['sha256'],'exact public predecessor QwenOwnerProtocol')
required={
'QwenOwnerProtocol.scala':[
'enableRuntimeRope:Boolean=false','require(!enableRuntimeRope || enableRuntimeQkNorm',
'Module(new PartialRopeRuntimeOwnerV12)','bf16QkNormRope && !enableRuntimeRope',
'runtimeRope.toSeq.map(n=>(11,n.io.scalar))','runtimeRope.foreach(_.io.parentFault:=port.parentFault)',
'runtimeRope.map(_.io.resourcesDrained).getOrElse(true.B)','(enableRuntimeRope.B && ropeJobHeld && choose===11.U)',
'r.io.job.bits:=PartialRopeRuntimeJobV12.fromOwner(ordinaryJob.bits)',
'io.runtimeRopeDoneFire.get.valid:=r.io.done.fire','runtimeRope.toSeq.map(x=>11->x.io.memory)',
'runtimeRope.toSeq.map(x=>11->x.io.response)','(enableRuntimeRope.B && mode===11.U)'],
'HostBlockTopV4.scala':[
'enableRuntimeQkNorm=true,enableRuntimeRope=true','new SharedMemoryArbiter(17)',
'val ropeTrigBytes=nj.qkTrigTokens.pad(80)<<7','Mux(qkNormJob || ropeJob,qkNormBytes',
'Mux(ropeJob,nwithin(nj.a,qkNormBytes) || nwithin(nj.b,ropeTrigBytes)',
'nr.bits.tag(63,32)===nj.tag && nrights','owner.io.response<>hub.io.responses(1)',
'val normPublish=HeldDecoupledOffer'],
'HostRuntimePrefixLeaseWiringV8.scala':[
'normalizedValid=RegInit(VecInit(Seq.fill(2)(false.B)))',
'authority.transaction===normalizedTransaction','authority.launch.asUInt===normalizedHost.asUInt',
'!normalizedValid.asUInt.andR || !normalizedCurrent','p.dst=/=q.a || p.m=/=q.m || p.n=/=q.n || p.k=/=q.k',
'd.status=/=Status.Ok.U || !d.outputCommitted || d.outputAckBytes=/=p.writeBytes',
'(q.qkRole===1.U && !ropeQCommitted)','p.tag<=ropeLastProducer(role)',
'ropeProducer.tag<g.io.physicalJob.bits.tag','logical.qkNormPolicy==="hb1".U',
'p.authorityKind:=Mux(ropeShape,UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U',
'stage:=Mux(ropeShape,75.U','Mux(ropeShape,logical.n.pad(32)*192.U',
'ropeLastProducer(role):=ropeProducer.tag;ropeLastTransaction(role):=transaction',
'ropeEvent.bits.accepted.asUInt===ropeExpected.asUInt','ropeEvent.bits.scalarAccepted===leases(0).lease.expectedOperations',
'ropeEvent.bits.scalarReturned===leases(0).lease.expectedOperations',
'ropeEvent.bits.memoryAccepted===(logical.m.pad(32)*(2.U+logical.n.pad(32)*16.U))(31,0)',
'ropeEvent.bits.memoryReturned===ropeEvent.bits.memoryAccepted','ropeEvent.bits.outputAckBytes===logical.writeBytes',
'(ropeShape && !ropeEvent.valid)','normalizedJobs(role):=retainedPhysical;normalizedResults(role):=qkEvent.bits',
'acquirePending && !qkShape && !ropeShape','retirePending && !qkShape && !ropeShape',
'val scalarPublish=HeldDecoupledOffer','scalar.result<>scalarPort.result']}
def contracts(src):
 for n,rs in required.items():
  for r in rs:
   if r not in src[n]:raise ValueError(n+': '+r)
contracts(s)
for n,rs in required.items():
 for r in rs:need(r in s[n],n+': '+r)
for n,x in s.items():
 stack=[]
 for ch in lex(x):
  if ch in '([{':stack.append(ch)
  elif ch in ')]}':need(bool(stack) and stack.pop()=={')':'(',']':'[','}':'{'}[ch],n+' delimiters')
 need(not stack,n+' unclosed')
need(s['HostBlockTopV4.scala'].count('enableRuntimeRope=true')==2,'common Commands and Kernel same fixed install')
need(s['QwenOwnerProtocol.scala'].count('Module(new PartialRopeRuntimeOwnerV12)')==1,'single owner')
need('Module(new' not in lex(s['PartialRopeRuntimeOwnerV12.scala']),'no new arithmetic unit')
for n,marker in [('QwenOwnerProtocol.scala','val core=Module(new Qwen2ContinuousBlock('),('QwenOwnerProtocol.scala','val matrix=Module(new MatrixPipelineService(')]:
 old=(B/n).read_text();need(next(x.strip() for x in old.splitlines() if marker in x)==next(x.strip() for x in s[n].splitlines() if marker in x),'same physical '+marker)
need('state===issue && !boundRuntimePrefix && io.resident.get.resetRequired' in s['HostBlockCommandsV4.scala'],'r2 held source-offer repair')
need('val kind=UInt(4.W); val m=UInt(16.W); val n=UInt(16.W); val k=UInt(16.W)' in s['QwenOwnerProtocol.scala'],'unwidened owner ABI')
oldjob=(B/'QwenOwnerProtocol.scala').read_text().split('class QwenOwnerJob extends Bundle {',1)[1].split('\n}',1)[0]
newjob=s['QwenOwnerProtocol.scala'].split('class QwenOwnerJob extends Bundle {',1)[1].split('\n}',1)[0]
need(re.sub(r'\s+','',lex(oldjob))==re.sub(r'\s+','',lex(newjob)),'entire QwenOwnerJob ABI byte-normalized unchanged')
for m in (1,16,128):
 for h in (2,8,16):need(m*h*192<=393216,'cap only; not claim common M1 support')
need(128*16*192==393216,'Q16scalar');need(128*(2+16*16)==33024,'Q16memory');need(128*16*512==1048576,'Q16ACK')
mut=[]
for n,rs in required.items():
 for r in rs:
  t=dict(s);t[n]=s[n].replace(r,'REMOVED_CONTRACT')
  try:contracts(t)
  except ValueError:mut.append(n+': '+r)
  else:raise ValueError('accepted mutation')
print(json.dumps(dict(status='PASS_SOURCE_MODELS_ONLY_NOT_SCALA_OR_DUT',checks=checks,mutation_rejections=len(mut),source_pins=[pin(p) for p in sorted((C/'source').glob('*.scala'))]),indent=2))
