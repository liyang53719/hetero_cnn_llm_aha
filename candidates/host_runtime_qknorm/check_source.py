"""Actual source and arithmetic-authority contracts only; NOT Scala/elab/DUT."""
from pathlib import Path
import hashlib,json,re
C=Path(__file__).resolve().parent;B=C.parent/'host_runtime_gatednorm'
s={p.name:p.read_text() for p in (C/'source').glob('*.scala')};checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
def pin(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def lex(x):return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"','',x)
for n,r in json.loads((C/'SOURCE_PINS.json').read_text())['source_check_originals'].items():
 q=pin(C/r['path']);need(q['bytes']==r['bytes'] and q['sha256']==r['sha256'],'pinned public ancestor '+n)
required={
'QwenOwnerProtocol.scala':['val qkNormPolicy=UInt(8.W)','enableRuntimeQkNorm:Boolean=false','Module(new QkNormRuntimeOwnerV11)','bf16QkNormRope && !enableRuntimeQkNorm','runtimeQkNorm.toSeq.map(n=>(10,n.io.scalar))','runtimeQkNorm.foreach(_.io.parentFault:=port.parentFault)','runtimeQkNorm.toSeq.map(x=>10->x.io.memory)','runtimeQkNorm.toSeq.map(x=>10->x.io.response)','(enableRuntimeQkNorm.B && mode===10.U)','runtimeQkNorm.map(_.io.resourcesDrained).getOrElse(true.B)','io.runtimeQkNormDoneFire.get.valid:=n.io.done.fire','(enableRuntimeQkNorm.B && qkNormJobHeld && choose===10.U)','n.io.job.bits:=QkNormRuntimeJobV11.fromOwner(ordinaryJob.bits)'],
'HostBlockTopV4.scala':['enableRuntimeQkNorm=true','new SharedMemoryArbiter(17)','qkNormJob && nj.qkRole===0.U && nwithin(nj.c,qkNormBytes)','Mux(qkNormJob,nwithin(nj.a,Mux(nj.qkRole===0.U,qkNormBytes<<1,qkNormBytes)) || nwithin(nj.b,512.U)','nr.bits.tag(63,32)===nj.tag && nrights','owner.io.response<>hub.io.responses(1)'],
'HostRuntimePrefixLeaseWiringV8.scala':['projectionStart=g.io.physicalJob.fire','projectionBusy && g.io.physicalDone.fire','authority.launch.asUInt===projectionHost.asUInt','authority.transaction===projectionTransaction','d.writeBytes===projectionPending.writeBytes','d.usefulMacs===(projectionPending.m.pad(64)*projectionPending.n.pad(64)*projectionPending.k.pad(64))(63,0)','!projectionValid.asUInt.andR','qkProducer.tag<g.io.physicalJob.bits.tag','qkLastTransaction(role):=transaction','Mux(qkShape,74.U','logical.qkNormPolicy==="hc2".U,1316.U,1290.U','acquirePending && !qkShape','retirePending && !qkShape','qkEvent.bits.accepted.asUInt===qkExpected.asUInt','qkEvent.bits.scalarReturned===leases(0).lease.expectedOperations','qkEvent.bits.outputAckBytes===logical.writeBytes','(qkShape && !qkEvent.valid)','scalar.result<>scalarPort.result'],
'UnifiedMoeSharedArithmeticProtocolV5.scala':['val OrdinaryQkNormScalar=8','val OrdinaryQkNormStage=74','val OrdinaryQkNormMaximumOperations=2695168','val Count=11','val OrdinaryQkNorm=6','val OrdinaryGatedNormStage=73'],
'UnifiedMoeSharedArithmeticAdapterV5.scala':['Module(new UnifiedVectorElement32BankV4)','k===UnifiedArithmeticAuthorityKindV5.OrdinaryQkNorm.U','else if(i==9) ordinaryKind(a.authorityKind) && !ordinaryChunk && !ordinaryQkNorm','else if(i==10) ordinaryChunk','Mux(ordinaryQkNorm,UnifiedMoeArithmeticClientV5.OrdinaryQkNormStage.U','Mux(ordinaryQkNorm,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryQkNormMaximumOperations.U else 0.U)'],
'QkNorm256RuntimeOwnerV11.scala':['class QkNormRuntimeOwnerV11 extends Module','val MaxTokens = 128','val MaxQueryHeads = 16','io.scalar.result.bits.primitiveFlagsValid','io.scalar.result.bits.flags','io.done.valid:=state===report;io.done.bits:=terminal','when(state===finish && io.resourcesDrained)','val memoryHeld=HeldDecoupledOffer','val scalarHeld=HeldDecoupledOffer']}
def contracts(src):
 for n,rs in required.items():
  for r in rs:
   if r not in src[n]:raise ValueError(n+' missing '+r)
contracts(s)
for n,rs in required.items():
 for r in rs:need(r in s[n],n+' '+r)
for n,x in s.items():
 stack=[]
 for c in lex(x):
  if c in '([{':stack.append(c)
  elif c in ')]}':need(bool(stack) and stack.pop()=={')':'(',']':'[','}':'{'}[c],'delimiter '+n)
 need(not stack,'unclosed '+n)
need(s['UnifiedMoeSharedArithmeticAdapterV5.scala'].count('Module(new UnifiedVectorElement32BankV4)')==1,'one bank')
need(s['QwenOwnerProtocol.scala'].count('Module(new QkNormRuntimeOwnerV11)')==1,'one runtime QK owner')
need(s['QwenOwnerProtocol.scala'].count('Module(new MatrixPipelineService(')==1,'one matrix service')
need('Module(new' not in lex(s['QkNorm256RuntimeOwnerV11.scala']),'QK no arithmetic/service instances')
for n,marker in [('UnifiedMoeSharedArithmeticProtocolV5.scala','val MaximumOperations='),('QwenOwnerProtocol.scala','val core=Module(new Qwen2ContinuousBlock(')]:
 old=(B/'source'/n).read_text()
 need(next(x.strip() for x in s[n].splitlines() if marker in x)==next(x.strip() for x in old.splitlines() if marker in x),'unchanged '+marker)
for m in (16,128):
 for heads in (2,8,16):
  for scalar in (1290,1316):need(m*heads*scalar<=2695168,'scalar cap')
need(128*16*1290==2641920,'C1 Q16 M128 count');need(128*16*1316==2695168,'C2 Q16 M128 count')
mutations=[]
for n,rs in required.items():
 for r in rs[:3]:
  t=dict(s);t[n]=s[n].replace(r,'REMOVED_CONTRACT')
  try:contracts(t)
  except ValueError:mutations.append(n+':'+r)
  else:raise ValueError('mutation accepted '+r)
result=dict(scope='source/lexical/geometry contracts only; no Scala, elaboration, RTL, DUT or numerical PASS',checks=checks,mutation_rejections=len(mutations),mutations=mutations,source_pins=[pin(p) for p in sorted((C/'source').glob('*.scala'))])
print(json.dumps(result,indent=2))
