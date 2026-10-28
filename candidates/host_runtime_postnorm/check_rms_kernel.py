"""Bounded source/protocol checks, NOT Chisel elaboration, RTL, or a DUT test."""
from pathlib import Path
import argparse,json,hashlib,re
C=Path(__file__).resolve().parent;W=C.parent
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--original-rms-source',type=Path,required=True)
args,unittest_args=parser.parse_known_args()
BASE=args.original_rms_source
r=json.loads((C/'SOURCE_PINS.json').read_text())['original_rms_recipe']
b=BASE.read_bytes()
if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('exact original RMS source pin required')
checks=0
def need(v,m):
 global checks
 checks+=1
 if not v:raise ValueError(m)
def section(s,a,b):
 need(s.count(a)==1 and s.count(b)==1,'unique section '+a[:40]);return s[s.index(a):s.index(b)]
def check(r,k,t,base):
 global checks
 checks=0
 # Exact numerical graph nodes and block order, not algebraic equivalence.
 for a,b in [
 ('  // Original reduction lane encoding:','  val expectedBytes='),
 ('  io.scalar.request.valid:=','  io.scalar.result.ready:='),
 ('    val r=io.scalar.result.bits;','  when(io.formatRequest.fire)'),
 ('    when(io.formatResult.bits.error','  val expectedScalar=')]:
  if a=='  io.scalar.request.valid:=':
   # Only handshake wrapper changes; request payload graph remains identical.
   a='  io.scalar.request.bits.payload.op:='
  if a=='    when(io.formatResult.bits.error':
   # Original stops at finish block; new stops at explicit counter formulas.
   old=section(base,a,'  when(state===finish && io.resourcesDrained)')
   new=section(r,a,b)
  else: old=section(base,a,b);new=section(r,a,b)
  need(old==new,'exact original numerical graph '+a[:35])
 need(r.count('Reg(Vec(32,UInt(512.W)))')==3,'same three physical payload cache definitions')
 need(r.count('Module(')==0,'no arithmetic module in RMS leaf')
 need('val accumulator=RegInit(0.U(32.W));val value=Reg(UInt(32.W));val normalized=RegInit(0.U(32.W));val invRms=Reg(UInt(32.W))' in r,'four working registers retained')
 fragments=[
 'val phase=UInt(2.W)','r.phase:=j.qkRole','r.reductionRecipe:=1.U',
 'class GdnRuntimeRmsNormResultV16 extends GdnRmsNormResult',
 'val accepted=new GdnRuntimeRmsNormJobV3',
 'terminal.accepted:=accepted','terminal.outputAckBytes:=bytes','terminal.resourcesDrained:=io.resourcesDrained',
 'terminal.scalarAccepted:=scalarAccepted;terminal.scalarReturned:=scalarReturned',
 'terminal.formatAccepted:=formatAccepted;terminal.formatReturned:=formatReturned',
 'terminal.memoryAccepted:=memoryAccepted;terminal.memoryReturned:=sequence',
 'when(io.memory.fire){memoryAccepted:=memoryAccepted+1.U;',
 'when(io.scalar.request.fire){scalarAccepted:=scalarAccepted+1.U;',
 'scalarReturned:=scalarReturned+1.U',
 'when(io.formatRequest.fire){formatAccepted:=formatAccepted+1.U;',
 'formatReturned:=formatReturned+1.U',
 'val expectedScalar=accepted.tokens.pad(64)*Mux(accepted.hiddenWidth===1024.U,5228.U,10412.U)',
 'val expectedMemory=(expectedFormat>>5)<<2',
 'scalarAccepted.pad(64)===expectedScalar && scalarReturned.pad(64)===expectedScalar',
 'formatAccepted.pad(64)===expectedFormat && formatReturned.pad(64)===expectedFormat',
 'memoryAccepted.pad(64)===expectedMemory && sequence.pad(64)===expectedMemory',
 'bytes===expectedBytes && countsExact',
 '(bytes=/=expectedBytes || !countsExact)',
 '!(j.phase===0.U || j.phase===3.U)',
 'j.tag==="hffffffff".U',
 'bad(j.input,nb) || bad(j.weight,wb) || bad(j.output,nb)',
 'overlap(j.input,nb,j.output,nb) || overlap(j.weight,wb,j.output,nb)',
 'val visible=intent && ((!poison && !quarantine && !currentFault) || held)',
 'when(published){held:= !ready}',
 'publishedOffer(memoryOffer,io.memory.ready,io.published.memory)',
 'publishedOffer(state===scalarIssue,io.scalar.request.ready,io.published.scalar)',
 'publishedOffer(state===formatIssue,io.formatRequest.ready,io.published.format)',
 'io.resetRequired:=poison || quarantine || currentFault',
 'when(memoryOffer && !memoryHeld.held && !io.memory.fire){state:=finish}',
 'when(state===scalarIssue && !scalarHeld.held && !io.scalar.request.fire){state:=finish}',
 'when(state===formatIssue && !formatHeld.held && !io.formatRequest.fire){state:=finish}',
 ]
 for f in fragments:need(f in r,'RMS contract '+f)
 for f in [
 'val runtimeRmsDoneFire=if(enableRuntimeRmsNorm)Some(Output(Valid(new GdnRuntimeRmsNormResultV16)))else None',
 'val rmsAccepted=if(enableRuntimeRmsNorm)Some(Reg(new GdnRuntimeRmsNormJobV3))else None',
 'val rmsJobHeld=RegInit(false.B)',
 '(enableRuntimeRmsNorm.B && rmsJobHeld && choose===8.U)',
 'when(choose===8.U){rmsAccepted.foreach(_:=GdnRuntimeRmsNormJobV3.fromOwner(ordinaryJob.bits))}',
 'n.io.published:=io.runtimeRmsPublished.get',
 'when(n.io.job.valid){rmsJobHeld:= !n.io.job.ready}',
 'n.io.job.bits:=GdnRuntimeRmsNormJobV3.fromOwner(ordinaryJob.bits)',
 'val r=n.io.done.bits;val j=rmsAccepted.get',
 'r.accepted.asUInt=/=j.asUInt || r.tag=/=j.tag || r.outputAckBytes=/=r.writeBytes',
 'r.scalarReturned.pad(64)=/=expectedScalar || r.formatAccepted.pad(64)=/=elems',
 'r.formatReturned.pad(64)=/=elems || r.memoryAccepted.pad(64)=/=expectedMemory',
 'r.memoryReturned.pad(64)=/=expectedMemory',
 'io.runtimeRmsDoneFire.get.valid:=n.io.done.fire;io.runtimeRmsDoneFire.get.bits:=r',
 'val rmsScalarDrain=enableRuntimeRmsNorm.B && active && mode===8.U &&',
 '(!gdnPoison || elementScalarDrain || rmsScalarDrain) && !sharedPoison && !legacyScalarDebt && !rawReturn',
 ]:need(f in k,'Kernel contract '+f)
 rms=section(k,'    runtimeRms.foreach{n=>','    val elementDone=')
 for f in ['r.accepted.asUInt=/=j.asUInt || r.tag=/=j.tag || r.outputAckBytes=/=r.writeBytes',
   'r.scalarReturned.pad(64)=/=expectedScalar || r.formatAccepted.pad(64)=/=elems',
   'r.formatReturned.pad(64)=/=elems || r.memoryAccepted.pad(64)=/=expectedMemory',
   'r.memoryReturned.pad(64)=/=expectedMemory',
   'n.io.job.valid:=ordinaryJob.valid && ordinaryCanStart && choose===8.U']:
  need(f in rms,'mode8-specific Kernel contract '+f)
 for f in [
 'cmd.io.runtimePostnormReceipt:=normLease.postnormReceipt',
 'val rmsJob=nj.kind===QwenOwnerKind.GdnRmsNorm.U',
 'owner.io.runtimeRmsPublished.get.memory:=normLease.owned && rmsJob && hub.io.requests(1).valid',
 'owner.io.runtimeRmsPublished.get.scalar:=normLease.owned && rmsJob && moeArithmetic.io.scalar(3).request.valid',
 'owner.io.runtimeRmsPublished.get.format:=normLease.owned && rmsJob && moeArithmetic.io.formatRequest(3).valid',
 ]:need(f in t,'Top contract '+f)
 # Constructor count and Core/Matrix/storage selection remain fixed.
 need(k.count('Module(new GdnRuntimeRmsNormOwnerV3)')==1,'single runtime RMS instance')
 need('GdnRuntimeRmsNormOwnerV3' not in t,'Top has no duplicate RMS')
 return checks

def main():
 r=(C/'source/GdnRuntimeRmsNormOwnerV3.scala').read_text();k=(C/'source/QwenOwnerProtocol.scala').read_text();t=(C/'source/HostBlockTopV4.scala').read_text()
 n=check(r,k,t,BASE.read_text())
 print(json.dumps(dict(status='PASS_RMS_KERNEL_TOP_SOURCE_CONTRACT_ONLY',checks=n,scope='Original arithmetic graph exact; actual source/counter/publication contracts. NOT compiled or DUT numerical proof.')))
if __name__=='__main__':main()
