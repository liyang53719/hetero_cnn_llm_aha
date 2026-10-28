"""Static contract and seeded mutation checks; never Chisel/DUT proof."""
from pathlib import Path
import json,hashlib,argparse
C=Path(__file__).resolve().parent
P=C/'source/HostRuntimePrefixLeaseWiringV8.scala'
def need(v,m):
 if not v:raise ValueError(m)
REQUIRED=[
'class HostRuntimePostnormStagedReceiptV16 extends Bundle',
'val logicalJob=new QwenOwnerJob',
'val result=new GdnRuntimeRmsNormResultV16',
'val residual=new HostRuntimeOutputStagedReceiptV15',
'val postnormReceipt=Valid(new HostRuntimePostnormStagedReceiptV16)',
'val residualValid=RegInit(false.B)',
'val normPostPhase=RegInit(false.B)',
'val postnormInput=Reg(new HostRuntimeOutputStagedReceiptV15)',
'authority.transaction===postnormReceipt.transactionId',
'authority.launch.asUInt===postnormReceipt.host.asUInt',
'j.qkRole===0.U || j.qkRole===3.U',
'j.cold && j.expectedGeneration===0.U && j.currentGeneration===0.U',
'residualValid && tailCurrent(r) && tailSuccess(r)',
'isElementwise(r.job) && r.job.gdnElementwiseOp===GdnElementwiseOp.Add.U',
'r.job.dst===q.a && r.job.m===q.m && r.job.n===q.n && r.job.k===q.k',
'r.job.writeBytes===q.writeBytes && outputRows(q)',
'r.transactionId>postnormLastTransaction',
'r.transactionId===postnormLastTransaction && r.job.tag>postnormLastProducer',
'(offeredOutput.qkRole===3.U && !postnormInputs(offeredOutput))',
'normPostPhase:=authority.ownerPostnormValidated',
'authority.ownerPostnormValidated=/=(q.qkRole===3.U)',
'postnormInput:=residualReceipt;postnormValid:=false.B',
'val normShape=normCommon(logical) && normPostPhase===(logical.qkRole===3.U)',
'val postnormShape=normShape && normPostPhase',
'val normScalarOperations=logical.m.pad(64)*Mux(logical.n===1024.U,5228.U,10412.U)',
'val normFormatOperations=logical.m.pad(64)*logical.n.pad(64)',
'val normMemoryOperations=normFormatOperations>>3',
'postnormInput.asUInt===residualReceipt.asUInt && postnormInput.transactionId===transaction',
'postnormInput.host.asUInt===host.asUInt && postnormInput.job.tag<g.io.physicalJob.bits.tag',
'postnormInput.job.tag=/="hffffffff".U',
'postnormConsumed:=true.B;postnormLastTransaction:=transaction;postnormLastProducer:=postnormInput.job.tag',
'val normEvent=k.io.runtimeRmsDoneFire.get',
'val normExpected=GdnRuntimeRmsNormJobV3.fromOwner(retainedPhysical)',
'normEvent.bits.tag===physical && normEvent.bits.accepted.asUInt===normExpected.asUInt',
'normEvent.bits.status===g.io.physicalDone.bits.status',
'normEvent.bits.writeBytes===g.io.physicalDone.bits.writeBytes',
'normEvent.bits.cycles===g.io.physicalDone.bits.cycles',
'leaseEventSubmitted && outputCountsExact',
'normEvent.bits.outputCommitted && normEvent.bits.resourcesDrained',
'normEvent.bits.outputAckBytes===logical.writeBytes && normEvent.bits.writeBytes===logical.writeBytes',
'normEvent.bits.scalarAccepted.pad(64)===normScalarOperations',
'normEvent.bits.scalarReturned===normEvent.bits.scalarAccepted',
'normEvent.bits.formatAccepted.pad(64)===normFormatOperations',
'normEvent.bits.formatReturned===normEvent.bits.formatAccepted',
'normEvent.bits.memoryAccepted.pad(64)===normMemoryOperations',
'normEvent.bits.memoryReturned===normEvent.bits.memoryAccepted',
'(!normShape || normTerminalExact)',
'when(normEvent.valid && (!owned || !normShape || !g.io.physicalDone.fire || !normTerminalExact))',
'(normShape && !normEvent.valid)',
'normShape && !normPostPhase && logical.qkRole===0.U',
'captureTail(residualReceipt);residualValid:=true.B',
'when(tailPhysicalSuccess && postnormShape && normEvent.valid && normTerminalExact)',
'postnormReceipt.job:=retainedPhysical;postnormReceipt.logicalJob:=logical',
'postnormReceipt.result:=normEvent.bits;postnormReceipt.residual:=postnormInput;postnormValid:=true.B',
'when(!tailCaptureClean || (residualValid && !tailCurrent(residualReceipt))){residualValid:=false.B}',
'when(!tailCaptureClean || (postnormValid && !postnormCurrent)){postnormValid:=false.B}',
'out.postnormReceipt.valid:=postnormValid && postnormCurrent && !receiptFault',
'r.counts.accepted===leases(i).lease.expectedOperations.pad(33)',
'r.counts.issued===leases(i).lease.expectedOperations.pad(33)',
'r.counts.returned===leases(i).lease.expectedOperations.pad(33)',
'p.lease.expectedOperations:=Mux(elementwiseShape',
'UnifiedArithmeticAuthorityKindV5.OrdinaryNorm.U',
'Mux(convShape,70.U,69.U)',
'out.scalarRetire.valid:=retirePending',
'out.scalarAcquire.valid:=acquirePending',
'val firstFault=currentIndependentFault || poison || contextChanged || physicalOfferBad',
'HeldDecoupledOffer(scalar.request.valid,scalarPort.request.ready,firstFault)',
'HeldDecoupledOffer(format.valid,a.io.formatRequest(3).ready,firstFault)',
]
def validate(s):
 for x in REQUIRED:need(x in s,'missing source contract: '+x)
 need('OrdinaryPostnorm' not in s and '78.U' not in s,'postnorm must reuse existing kind1/stage69')
 need('Module(new' not in s,'wiring must not introduce arithmetic/cache module')
 # The new private receipt is staged data, not a lease acquisition or root ACK.
 tail=s[s.index('out.postnormReceipt.bits:='):s.index('out.kvReceipt.bits:=')]
 need('out.postnormReceipt.valid:=postnormValid && postnormCurrent && !receiptFault' in tail,'registered physical proof output')
 return len(REQUIRED)+3

def main():
 s=P.read_text();n=validate(s);mutations=0
 for x in REQUIRED:
  try:validate(s.replace(x,'REMOVED_POSTNORM_CONTRACT'))
  except ValueError:mutations+=1
  else:raise ValueError('survived mutation '+x)
 report=dict(status='PASS_STATIC_PREFIX_CONTRACT_AND_NEGATIVE_MUTATIONS_NOT_DUT',source=dict(path=str(P),bytes=P.stat().st_size,sha256=hashlib.sha256(P.read_bytes()).hexdigest()),checks=n,mutations=mutations,scope='No elaboration, RTL, numerical primitive or protocol DUT execution; exact active source contract only.')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
