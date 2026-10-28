"""Source/ancestry/contract checks ONLY; never Scala, RTL or numerical proof."""
from pathlib import Path
import argparse,hashlib,json,re
C=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-source-dir',type=Path,required=True,help='21 exact original ancestry sources, not bundled')
args=parser.parse_args()
s={p.name:p.read_text() for p in (C/'source').glob('*.scala')}
checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
def pin(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
for x in json.loads((C/'SOURCE_PINS.json').read_text())['source_check_originals']:
 p=args.parent_source_dir/x['name'];q=pin(p)
 need(q['bytes']==x['bytes'] and q['sha256']==x['sha256'],'frozen source changed '+x['name'])
required={
'QwenOwnerProtocol.scala':['enableRuntimeGatedNorm:Boolean=false','new GdnRuntimeGatedNormOwnerV10','bf16GdnCore && !enableRuntimeGatedNorm','runtimeGatedNorm.toSeq.map(n=>(6,n.io.scalar,n.io.formatRequest,n.io.formatResult,n.io.resourcesDrained))','runtimeGatedNorm.foreach(_.io.parentFault:=port.parentFault)','runtimeGatedNorm.toSeq.map(x=>6->x.io.memory)','runtimeGatedNorm.toSeq.map(x=>6->x.io.response)','(enableRuntimeGatedNorm.B && mode===6.U)','runtimeGatedNorm.map(_.io.resourcesDrained).getOrElse(true.B)','io.runtimeGatedDoneFire.get.valid:=n.io.done.fire','(enableRuntimeGatedNorm.B && gatedJobHeld && choose===6.U)'],
'HostBlockTopV4.scala':['enableRuntimeGatedNorm=true','new SharedMemoryArbiter(17)','chunkStaged:=chunkLease.stagedReceipt','ordinaryAdmissionFault,prefixScalar,chunkStaged','Mux(gatedJob,nwithin(nj.a,nbytes) || nwithin(nj.b,nbytes) || nwithin(nj.c,512.U)','phaseFault || runtimeGuard.io.localFault || cmd.io.runtimeAuthority.currentFault'],
'HostRuntimeChunkWiringV9.scala':['staged.producer.ownerSequence:=physical;staged.result:=r;stagedValid:=true.B','when(r.status===Status.Ok.U && !currentFault && !authority.currentFault && !a.io.resetRequired)','!eventBusy && transportQuiet && slots.map(i=> !a.io.status(i).active && !a.io.status(i).retiring).reduce(_&&_)','r.accepted.asUInt===expectedJob.asUInt','g.io.physicalDone.bits.writeBytes===r.outputAckBytes+r.stateAckBytes','counts.returned===leases(i).lease.expectedOperations.pad(33)'],
'HostRuntimePrefixLeaseWiringV8.scala':['val gatedLogical=logicalStart && g.io.job.bits.kind===QwenOwnerKind.GdnGatedNorm.U','when(!chunkReceipt.valid','g.io.physicalJob.bits.tag>gatedProducer','gatedSource.result.accepted.context.output===logical.a','gatedSource.result.accepted.layout.valueHeads===logical.n','UnifiedArithmeticAuthorityKindV5.OrdinaryGatedNorm.U','Mux(gatedShape,73.U,Mux(convShape,70.U,69.U))','logical.n.pad(32)*1284.U','logical.n.pad(32)*256.U','val gatedTerminalExact=gatedEvent.bits.tag===physical','gatedEvent.bits.accepted.asUInt===gatedExpected.asUInt','gatedEvent.bits.writeBytes===logical.writeBytes && gatedCountsExact','when(!terminalExact || (gatedShape && !gatedEvent.valid))','firstFault=currentIndependentFault || poison || contextChanged || physicalOfferBad || prepareBad || g.io.localFault'],
'UnifiedMoeSharedArithmeticProtocolV5.scala':['val OrdinaryGatedNormScalar=8;val OrdinaryGatedNormFormat=9','val OrdinaryGatedNormStage=73','Seq(5259264,1048576)','val Count=11','OrdinaryGatedNorm=5'],
'UnifiedMoeSharedArithmeticAdapterV5.scala':['val bank=Module(new UnifiedVectorElement32BankV4)','k===UnifiedArithmeticAuthorityKindV5.OrdinaryGatedNorm.U','else if(i==9) ordinaryKind(a.authorityKind) && !ordinaryChunk','else if(i==10) ordinaryChunk','Mux(ordinaryGatedNorm,UnifiedMoeArithmeticClientV5.OrdinaryGatedNormStage.U','Mux(ordinaryGatedNorm,UnifiedMoeArithmeticClientV5.OrdinaryGatedNormMaximumOperations(i-8).U'],
'GdnRuntimeGatedNormOwnerV10.scala':['val weights=Reg(Vec(128,UInt(32.W)))','val core=Reg(Vec(128,UInt(16.W)))','val gate=Reg(Vec(128,UInt(16.W)))','val output=Reg(Vec(128,UInt(16.W)))','io.formatRequest.bits.value:=value','is(normalize){state:=formatIssue}','is(gated){state:=formatIssue}','value:=Cat(r.value,0.U(16.W));operation:=weight','output(lane):=r.value','when(state===waitOutput && !r.error){bytes:=bytes+64.U}','val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)','val unknownScalar=io.scalar.result.valid && (state=/=scalarWait || io.scalar.result.bits.policy=/=requestPolicy)','val unknownFormat=io.formatResult.valid && state=/=formatWait','when(unknown){quarantine:=true.B}','when(state===finish && io.resourcesDrained)','memoryAccepted===expectedMemory && sequence===expectedMemory','scalarAccepted===expectedScalar && scalarReturned===expectedScalar && formatAccepted===expectedFormat && formatReturned===expectedFormat','io.done.valid:=state===report;io.done.bits:=terminal','val expectedScalar=(rows*1284.U)(31,0)','val expectedFormat=(rows<<8)(31,0)','val expectedMemory=(8.U+rows*12.U)(31,0)']}
def contracts(src):
 for n,rs in required.items():
  for r in rs:
   if r not in src[n]:raise ValueError(n+' missing '+r)
for n,rs in required.items():
 for r in rs:need(r in s[n],n+' '+r)
contracts(s)
# Strip comments/string literals, then lexically check punctuation. Not a parser.
def lex(x):return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"','',x)
for n,x in s.items():
 stack=[]
 for c in lex(x):
  if c in '([{':stack.append(c)
  elif c in ')]}':need(bool(stack) and stack.pop()=={')':'(',']':'[','}':'{'}[c],'delimiter '+n)
 need(not stack,'unclosed '+n)
# Arithmetic operands are literally the same as the original runtime owner.
original=(args.parent_source_dir/'GdnRuntimeGatedNormOwner.scala').read_text()
for field,nextfield in [('op','a'),('a','b')]:
 def block(x):return re.sub(r'\s+','',x.split('io.scalar.request.bits.payload.'+field)[1].split('io.scalar.request.bits.payload.'+nextfield)[0])
 need(block(original)==block(s['GdnRuntimeGatedNormOwnerV10.scala']),'exact scalar mapping '+field)
def bblock(x):return re.sub(r'\s+','',x.split('io.scalar.request.bits.payload.b')[1].split('io.scalar.result.ready')[0])
need(bblock(original)==bblock(s['GdnRuntimeGatedNormOwnerV10.scala']),'exact scalar mapping b')
clean=lex(s['GdnRuntimeGatedNormOwnerV10.scala'])
need('Module(new' not in clean,'owner no arithmetic/service module')
need('F32.bf(' not in clean and 'TensorMath.bf16Rne(' not in clean,'no local double round')
need(s['UnifiedMoeSharedArithmeticAdapterV5.scala'].count('Module(new UnifiedVectorElement32BankV4)')==1,'one bank')
need(s['HostBlockTopV4.scala'].count('Module(new SharedMemoryArbiter(')==1,'one hub')
need(s['QwenOwnerProtocol.scala'].count('Module(new GdnRuntimeGatedNormOwnerV10)')==1,'one runtime owner')
mutations=[(n,r) for n,rs in required.items() for r in rs if any(k in r for k in ['1284.U','256.U','new SharedMemory','enableRuntimeGatedNorm=true','gatedEvent.bits.accepted','!gatedEvent.valid','!chunkReceipt.valid','tag>gatedProducer','counts.returned','state===finish','!quarantine','sequence===expectedMemory'])]
for n,r in mutations:
 m=dict(s);m[n]=m[n].replace(r,'false.B /* mutation */',1)
 try:contracts(m)
 except ValueError:pass
 else:raise ValueError('surviving '+r)
 need(True,'mutation rejected')
print(json.dumps(dict(status='PASS_SOURCE_ONLY_NOT_SCALA_DUT_OR_NUMERICAL',checks=checks,rejected_mutations=len(mutations),candidate_sources=len(s)),indent=2))
