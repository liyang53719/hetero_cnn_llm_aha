// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal wiring return, NOT a Host capability or synthetic done source. */
final case class HostMoePhaseLifetimeSignalsV5(
  lease:HostMoeRuntimePhaseLeaseV5, active:Bool, stage:UInt,
  localFault:Bool, registeredPoison:Bool)

/** Invoke only INSIDE the original Host Top with its actual unique allocator,
  * Guard, Commands and real numerical consumer objects. No Module/ALU/reader/
  * Dense/physical transport is created here. The Loop reuses its ONE existing
  * FFN/activation instance for shared continuation.
  *
  * physicalDrained and arithmeticDrained are the actual physical state and
  * parent full-tag outstanding/held ledgers, excluding mere reservation bits.
  * They must not come from Host fields, child equality counts alone, or this
  * controller's state. Both final release channels have independent held
  * valid/accepted state; no valid is combinationally gated by the other's ready.
  * Only both actual release.fire events permit the final Commands receipt.
  */
object HostMoePhaseLifetimeWiringV5 {
  def connect(cmd:HostBlockCommandsV4,guard:HostRuntimeOwnerGuardV5,
      allocator:HostRuntimeMoePhaseAllocatorV5,
      loop:UnifiedMoeRuntimeExpertLoopV4,sigmoid:UnifiedMoeSharedGateSigmoidOwnerV5,
      merge:UnifiedMoePhaseMergeOwnerV5,residual:UnifiedMoePhaseResidualOwnerV5,
      imageValid:Bool,physicalImage:DecodedTensor,
      physicalDrained:Bool,arithmeticDrained:Bool,physicalFault:Bool):HostMoePhaseLifetimeSignalsV5={
    val ss=Enum(19)
    val idle=ss(0);val offerRouted=ss(1);val waitRouted=ss(2)
    val drainShared=ss(3);val offerShared=ss(4);val waitShared=ss(5)
    val drainSigmoid=ss(6);val offerSigmoid=ss(7);val waitSigmoid=ss(8)
    val drainMerge=ss(9);val offerMerge=ss(10);val waitMerge=ss(11)
    val drainResidual=ss(12);val offerResidual=ss(13);val waitResidual=ss(14)
    val drainFinal=ss(15);val releasing=ss(16);val report=ss(17);val locked=ss(18)
    val state=RegInit(idle);val poison=RegInit(false.B);val quarantine=RegInit(false.B)
    // Ownership outlives error/report/locked FSM states. Only BOTH real releases
    // below (or the external coordinated reset) retire the phase reservation.
    val owned=RegInit(false.B)
    val lease=Reg(new HostMoeRuntimePhaseLeaseV5)
    val image=Reg(new HostMoeSharedGateImageV5)
    val routed=Reg(new HostMoeRoutedPhaseResultV5)
    val shared=Reg(new UnifiedMoeFfnGroupResultV3)
    val sigmoidCommit=Reg(new UnifiedMoeSharedSigmoidCommitV5)
    val mergeCommit=Reg(new UnifiedMoePhaseMergeCommitV5)
    val residualCommit=Reg(new UnifiedMoePhaseResidualCommitV5)
    val terminal=Reg(new HostMoePhaseRetirementV5)
    val guardReleased=RegInit(false.B);val allocatorReleased=RegInit(false.B)
    val useful=RegInit(0.U(64.W));val executed=RegInit(0.U(64.W))
    val contextCurrent=cmd.io.runtimeAuthority.accepted &&
      cmd.io.runtimeAuthority.transaction===lease.context.transactionId &&
      cmd.io.runtimeAuthority.launch.asUInt===lease.context.host.asUInt
    val routedIdentity=loop.io.done.bits.transactionId===lease.context.transactionId &&
      loop.io.done.bits.allocationSequence===lease.allocationSequence
    val sharedIdentity=loop.io.sharedResult.bits.context.asUInt===lease.context.asUInt &&
      loop.io.sharedResult.bits.allocationSequence===lease.allocationSequence
    val sigmoidIdentity=sigmoid.io.done.bits.context.asUInt===lease.context.asUInt &&
      sigmoid.io.done.bits.allocationSequence===lease.allocationSequence
    val mergeIdentity=merge.io.done.bits.context.asUInt===lease.context.asUInt &&
      merge.io.done.bits.allocationSequence===lease.allocationSequence
    val residualIdentity=residual.io.done.bits.context.asUInt===lease.context.asUInt &&
      residual.io.done.bits.allocationSequence===lease.allocationSequence
    val unknown=(loop.io.done.valid && (state=/=waitRouted || !routedIdentity)) ||
      (loop.io.sharedResult.valid && (state=/=waitShared || !sharedIdentity)) ||
      (sigmoid.io.done.valid && (state=/=waitSigmoid || !sigmoidIdentity)) ||
      (merge.io.done.valid && (state=/=waitMerge || !mergeIdentity)) ||
      (residual.io.done.valid && (state=/=waitResidual || !residualIdentity))
    val active=owned
    val contextChanged=active && !contextCurrent
    val childFault=loop.io.resetRequired || sigmoid.io.resetRequired || merge.io.resetRequired || residual.io.resetRequired
    val localEvent=WireDefault(false.B)
    val localFault=poison || quarantine || unknown || contextChanged || localEvent
    val fault=localFault || physicalFault || childFault || (active && cmd.io.runtimeAuthority.currentFault)
    when(fault){poison:=true.B};when(unknown || contextChanged){quarantine:=true.B}
    val registeredPoison=RegNext(fault,false.B)
    // Only registered feedback enters the same consumers whose faults are read.
    loop.io.currentFault:=registeredPoison
    sigmoid.io.sourceResetRequired:=registeredPoison
    merge.io.externalPoison:=registeredPoison;residual.io.externalPoison:=registeredPoison
    val allServicesDrained=physicalDrained && arithmeticDrained

    def fail(status:UInt):Unit={
      terminal.context:=lease.context;terminal.outputAddress:=lease.context.output.address
      terminal.acknowledgedWriteBytes:=0.U;terminal.usefulMacs:=useful;terminal.executedMacs:=executed
      terminal.status:=Mux(status===Status.Ok.U,Status.Protocol.U,status)
      terminal.resourcesRetired:=false.B;poison:=true.B;state:=report
    }
    allocator.io.grant.ready:=state===idle && !owned && !poison && !quarantine && !unknown
    val candidateImage=Wire(new HostMoeSharedGateImageV5)
    candidateImage.logicalWeight:=allocator.io.grant.bits.weights(HostMoeWeightRoleV4.SharedGateLogit)
    candidateImage.physicalWeight:=physicalImage;candidateImage.layoutId:=HostMoeSharedGatePlanV5.LayoutId.U
    val candidateOK=imageValid && HostMoeSharedGatePlanV5.imageLegal(allocator.io.grant.bits,candidateImage)
    when(allocator.io.grant.fire){
      lease:=allocator.io.grant.bits;image:=candidateImage;owned:=true.B
      useful:=0.U;executed:=0.U;guardReleased:=false.B;allocatorReleased:=false.B
      when(!candidateOK || fault){
        terminal:=0.U.asTypeOf(new HostMoePhaseRetirementV5)
        terminal.context:=allocator.io.grant.bits.context
        terminal.outputAddress:=allocator.io.grant.bits.context.output.address
        terminal.status:=Status.Protocol.U;terminal.resourcesRetired:=false.B
        poison:=true.B;state:=report
      }.otherwise{state:=offerRouted}
    }

    // All packet constructors are unconditional, outside when. These stable
    // retained packets are offered once; fault cannot retract an already-held offer.
    loop.io.begin.bits:=lease
    loop.io.sharedBegin.bits.context:=lease.context;loop.io.sharedBegin.bits.allocationSequence:=lease.allocationSequence
    sigmoid.io.begin.bits.lease:=lease;sigmoid.io.begin.bits.image:=image;sigmoid.io.begin.bits.shared:=shared
    merge.io.begin.bits.lease:=lease;merge.io.begin.bits.routed:=routed
    merge.io.begin.bits.shared:=shared;merge.io.begin.bits.sigmoid:=sigmoidCommit
    residual.io.begin.bits.lease:=lease;residual.io.begin.bits.merge:=mergeCommit
    val ro=HeldDecoupledOffer(state===offerRouted,loop.io.begin.ready,fault)
    val so=HeldDecoupledOffer(state===offerShared,loop.io.sharedBegin.ready,fault)
    val no=HeldDecoupledOffer(state===offerSigmoid,sigmoid.io.begin.ready,fault)
    val mo=HeldDecoupledOffer(state===offerMerge,merge.io.begin.ready,fault)
    val ao=HeldDecoupledOffer(state===offerResidual,residual.io.begin.ready,fault)
    loop.io.begin.valid:=ro.valid;loop.io.sharedBegin.valid:=so.valid
    sigmoid.io.begin.valid:=no.valid;merge.io.begin.valid:=mo.valid;residual.io.begin.valid:=ao.valid
    when(loop.io.begin.fire){state:=waitRouted};when(loop.io.sharedBegin.fire){state:=waitShared}
    when(sigmoid.io.begin.fire){state:=waitSigmoid};when(merge.io.begin.fire){state:=waitMerge}
    when(residual.io.begin.fire){state:=waitResidual}
    for((s,o)<-Seq(offerRouted->ro,offerShared->so,offerSigmoid->no,offerMerge->mo,offerResidual->ao)){
      when(state===s && fault && !o.held && !o.valid){fail(Status.Protocol.U)}
    }
    loop.io.done.ready:=state===waitRouted && routedIdentity && !quarantine
    loop.io.sharedResult.ready:=state===waitShared && sharedIdentity && !quarantine
    sigmoid.io.done.ready:=state===waitSigmoid && sigmoidIdentity && !quarantine
    merge.io.done.ready:=state===waitMerge && mergeIdentity && !quarantine
    residual.io.done.ready:=state===waitResidual && residualIdentity && !quarantine
    val (_,routedGood)=UnifiedMoeSharedFfnPlanV5.fromActualRoutedRetirement(lease,loop.io.done.bits)
    when(loop.io.done.fire){
      when(fault || !routedGood){fail(loop.io.done.bits.status)}
      .otherwise{routed:=loop.io.done.bits;state:=drainShared}
    }
    when(loop.io.sharedResult.fire){
      when(fault || !UnifiedMoeSharedFfnPlanV5.completed(lease,loop.io.sharedResult.bits.result)){
        fail(loop.io.sharedResult.bits.result.status)
      }.otherwise{shared:=loop.io.sharedResult.bits.result;state:=drainSigmoid}
    }
    val sg=sigmoid.io.done.bits;val n=lease.context.tokens
    val (expectedN1Receipt,n1Exact)=HostMoeSharedGatePlanV5.fromActualDense(lease,image,sg.source.acceptedJob,sg.source.result)
    val sigmoidGood=n1Exact && sg.source.asUInt===expectedN1Receipt.asUInt &&
      sg.status===Status.Ok.U && sg.drained && sg.rows===n && sg.output===lease.upOutput &&
      sg.ownerSequence.pad(33)===lease.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.SharedSigmoid.U &&
      sg.acknowledgedWriteBytes===(n.pad(64)<<1) &&
      sg.scalarIssued===(n.pad(33)<<2) && sg.scalarReturned===sg.scalarIssued &&
      sg.formatIssued===n.pad(33) && sg.formatReturned===sg.formatIssued &&
      sg.memoryIssued===n.pad(9)+((n.pad(9)+31.U)>>5) && sg.memoryReturned===sg.memoryIssued
    when(sigmoid.io.done.fire){when(fault || !sigmoidGood){fail(sg.status)}
      .otherwise{sigmoidCommit:=sg;state:=drainMerge}}
    when(merge.io.done.fire){
      when(fault || !UnifiedMoePhaseMergeReceiptV5.matches(lease,merge.io.done.bits)){fail(merge.io.done.bits.status)}
      .otherwise{mergeCommit:=merge.io.done.bits;state:=drainResidual}
    }
    val rr=residual.io.done.bits;val tiles=n.pad(33)<<6
    val residualGood=rr.status===Status.Ok.U && rr.drained && rr.output===lease.context.output.address &&
      rr.ownerSequence.pad(33)===lease.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.Residual.U &&
      rr.completedTokens===n && rr.completedTiles===tiles && rr.acknowledgedWriteBytes===lease.context.output.payloadBytes &&
      rr.vectorIssued===(tiles<<1) && rr.vectorReturned===rr.vectorIssued &&
      rr.memoryIssued===tiles*3.U && rr.memoryReturned===rr.memoryIssued
    when(residual.io.done.fire){when(fault || !residualGood){fail(rr.status)}
      .otherwise{residualCommit:=rr;state:=drainFinal}}
    for((before,after)<-Seq(drainShared->offerShared,drainSigmoid->offerSigmoid,
      drainMerge->offerMerge,drainResidual->offerResidual,drainFinal->releasing)){
      when(state===before){when(fault){fail(Status.Protocol.U)}.elsewhen(allServicesDrained){state:=after}}
    }

    // Actual original Guard retirement is the only arithmetic MAC accounting
    // source. Local groups/expected-MAC constants do not synthesize executed work.
    val gr=guard.io.retired.bits
    val phaseDenseRetired=guard.io.retired.valid && active &&
      gr.transactionId===lease.context.transactionId && gr.host.asUInt===lease.context.host.asUInt &&
      gr.physicalSequence>=lease.firstOwnerSequence &&
      gr.physicalSequence.pad(33)<lease.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.Count.U
    val usefulNext=useful.pad(65)+gr.logicalResult.usefulMacs.pad(65)
    val executedNext=executed.pad(65)+gr.logicalResult.executedMacs.pad(65)
    when(phaseDenseRetired){
      when(usefulNext(64)||executedNext(64)){localEvent:=true.B}
      .otherwise{useful:=usefulNext(63,0);executed:=executedNext(63,0)}
    }
    guard.io.release.bits.transactionId:=lease.context.transactionId
    guard.io.release.bits.allocationSequence:=lease.allocationSequence
    guard.io.release.bits.first:=lease.firstOwnerSequence
    guard.io.release.bits.endExclusive:=lease.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.Count.U
    guard.io.release.bits.outputAddress:=residualCommit.output
    guard.io.release.bits.acknowledgedWriteBytes:=residualCommit.acknowledgedWriteBytes
    guard.io.release.bits.status:=Status.Ok.U
    allocator.io.release.bits.transactionId:=lease.context.transactionId
    allocator.io.release.bits.allocationSequence:=lease.allocationSequence
    guard.io.release.valid:=state===releasing && !guardReleased
    allocator.io.release.valid:=state===releasing && !allocatorReleased
    guard.io.finalPhaseRetired:=state===releasing && allServicesDrained && !fault
    allocator.io.finalMergeRetired:=state===releasing && allServicesDrained && !fault
    when(guard.io.release.fire){guardReleased:=true.B}
    when(allocator.io.release.fire){allocatorReleased:=true.B}
    when(state===releasing && (guardReleased||guard.io.release.fire) &&
      (allocatorReleased||allocator.io.release.fire)){
      terminal.context:=lease.context;terminal.outputAddress:=residualCommit.output
      terminal.acknowledgedWriteBytes:=residualCommit.acknowledgedWriteBytes
      terminal.usefulMacs:=useful;terminal.executedMacs:=executed
      terminal.status:=Mux(fault,Status.Protocol.U,Status.Ok.U)
      terminal.resourcesRetired:= !fault;owned:=false.B;state:=report
    }
    cmd.io.moePhaseResult.valid:=state===report;cmd.io.moePhaseResult.bits:=terminal
    when(cmd.io.moePhaseResult.fire){state:=Mux(fault || terminal.status=/=Status.Ok.U,locked,idle)}
    HostMoePhaseLifetimeSignalsV5(lease,active,state,localFault,registeredPoison)
  }
}
