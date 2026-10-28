// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** All ports below are PRIVATE original-parent wiring, never Host permissions. */
class HostMoeOwnerRangeRequestV5 extends Bundle {
  val context=new HostMoePhaseContextV4
  val allocationSequence=UInt(64.W)
  val count=UInt(32.W)
}
class HostMoeOwnerRangeResultV5 extends Bundle {
  val context=new HostMoePhaseContextV4
  val allocationSequence=UInt(64.W)
  val first=UInt(32.W);val endExclusive=UInt(33.W)
  val postnormPhysicalSequence=UInt(32.W)
  val status=UInt(8.W)
}
class HostMoePhysicalOwnerJobV5 extends Bundle {
  val context=new HostMoePhaseContextV4
  val allocationSequence=UInt(64.W)
  val job=new QwenOwnerJob
}
class HostOwnerPhysicalRetirementV5 extends Bundle {
  val transactionId=UInt(64.W);val host=new HostCommandLaunchV4
  val physicalSequence=UInt(32.W)
  val logicalJob=new QwenOwnerJob;val logicalResult=new QwenOwnerResult
}
class HostMoeOwnerRangeReleaseV5 extends Bundle {
  val transactionId=UInt(64.W);val allocationSequence=UInt(64.W)
  val first=UInt(32.W);val endExclusive=UInt(33.W)
  val outputAddress=UInt(64.W);val acknowledgedWriteBytes=UInt(64.W)
  val status=UInt(8.W)
}

/** Successor of the ONE original Guard, NOT a parallel dispatcher/Kernel.
  * Ordinary job.tag remains the original logical Cat(epoch,pc) externally.
  * Only its physical copy is replaced by this persistent no-wrap32 sequence.
  * Matching physical returns restore the original tag before Commands sees it.
  * A phase atomically reserves1289 IDs and shares the SAME held offer/pending/
  * report registers. Every reserved-but-unused ID remains consumed permanently.
  *
  * Reset clears this counter, so reset MUST jointly isolate/drain/reset the
  * physical Kernel/transport before another launch. Full64 retained metadata
  * cannot authenticate an old same-tag return after an unsafe reset. This
  * source does not pretend the missing parent joint-reset connection is done.
  * transportDrained/finalPhaseRetired must be actual internal resource/final
  * write-ACK fences, never software booleans or merely routed-loop completion.
  */
class HostRuntimeOwnerGuardV5 extends Module {
  val io=IO(new Bundle {
    val authority=Input(new HostRuntimeAuthoritySnapshotV4)
    val globalFault=Input(Bool())
    val localFault=Output(Bool()) // excludes reflected authority/global combinational fault
    val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
    val physicalJob=Decoupled(new QwenOwnerJob);val physicalDone=Flipped(Decoupled(new QwenOwnerResult))
    val reserve=Flipped(Decoupled(new HostMoeOwnerRangeRequestV5))
    val reservation=Decoupled(new HostMoeOwnerRangeResultV5)
    val phaseJob=Flipped(Decoupled(new HostMoePhysicalOwnerJobV5))
    val phaseDone=Decoupled(new QwenOwnerResult)
    val release=Flipped(Decoupled(new HostMoeOwnerRangeReleaseV5))
    val transportDrained=Input(Bool());val finalPhaseRetired=Input(Bool())
    val retired=Output(Valid(new HostOwnerPhysicalRetirementV5))
    val resetRequired=Output(Bool());val localBusy=Output(Bool())
    val acceptedTransaction=Output(UInt(64.W))
    val sequenceExhausted=Output(Bool());val phaseReserved=Output(Bool())
  })
  val idle::offer::pending::report::Nil=Enum(4)
  val state=RegInit(idle);val quarantine=RegInit(false.B);val poisoned=RegInit(false.B)
  val heldJob=Reg(new QwenOwnerJob);val heldLaunch=Reg(new HostCommandLaunchV4)
  val heldTransaction=Reg(UInt(64.W));val heldResult=Reg(new QwenOwnerResult)
  val heldPhysicalSequence=Reg(UInt(32.W));val heldPhase=RegInit(false.B)
  val nextSequence=RegInit(0.U(32.W)) // allones is reserved, never issued/wrapped
  val lastOrdinaryRetired=RegInit(false.B)
  val phaseOwned=RegInit(false.B);val phaseContext=Reg(new HostMoePhaseContextV4)
  val phaseAllocation=Reg(UInt(64.W));val phaseFirst=Reg(UInt(32.W));val phaseEnd=Reg(UInt(33.W))
  val phaseHasIssued=RegInit(false.B);val phaseLastIssued=Reg(UInt(32.W))
  val grantFull=RegInit(false.B);val grant=Reg(new HostMoeOwnerRangeResultV5)
  val sequenceAvailable=nextSequence=/="hffffffff".U
  val (decoded,known)=UnifiedRuntimeProfile.decode(io.authority.launch.profileId)
  val permitted=io.authority.accepted && io.authority.ownerValidated &&
    HostCommandLaunchV4.known(io.authority.launch) && known &&
    decoded.asUInt===io.authority.profile.asUInt &&
    io.job.bits.asUInt===io.authority.ownerJob.asUInt &&
    !io.authority.currentFault && !io.globalFault
  val sameContext=io.authority.accepted && io.authority.transaction===heldTransaction &&
    io.authority.launch.asUInt===heldLaunch.asUInt
  val phaseContextCurrent=io.authority.accepted && io.authority.transaction===phaseContext.transactionId &&
    io.authority.launch.asUInt===phaseContext.host.asUInt
  val unknownReply=io.physicalDone.valid && state=/=pending
  val wrongReply=io.physicalDone.valid && state===pending &&
    (io.physicalDone.bits.tag=/=heldPhysicalSequence || !sameContext)
  val contextChanged=state=/=idle && !sameContext
  val reservationContextChanged=phaseOwned && !phaseContextCurrent
  val releaseIdentity=phaseOwned && io.release.bits.transactionId===phaseContext.transactionId &&
    io.release.bits.allocationSequence===phaseAllocation && io.release.bits.first===phaseFirst &&
    io.release.bits.endExclusive===phaseEnd
  val finalWrite=io.release.bits.status===Status.Ok.U &&
    io.release.bits.outputAddress===phaseContext.output.address &&
    io.release.bits.acknowledgedWriteBytes===phaseContext.output.payloadBytes
  val wrongRelease=io.release.valid && (!releaseIdentity || !finalWrite)
  val phaseBits=io.phaseJob.bits
  val phaseIdentity=phaseOwned && phaseBits.context.asUInt===phaseContext.asUInt &&
    phaseBits.allocationSequence===phaseAllocation && phaseBits.job.kind===QwenOwnerKind.Dense.U &&
    phaseBits.job.tag>=phaseFirst && phaseBits.job.tag.pad(33)<phaseEnd &&
    (!phaseHasIssued || phaseBits.job.tag>phaseLastIssued)
  val wrongPhaseOffer=io.phaseJob.valid && !phaseIdentity
  val faultNow=unknownReply || wrongReply || contextChanged || reservationContextChanged || wrongRelease || wrongPhaseOffer
  when(faultNow){quarantine:=true.B;poisoned:=true.B}
  val ownedAuthorityFault=(state=/=idle || phaseOwned) && io.authority.currentFault
  when(ownedAuthorityFault || io.globalFault){poisoned:=true.B}
  io.localFault:=quarantine || poisoned || faultNow
  io.resetRequired:=quarantine || poisoned || faultNow || ownedAuthorityFault || io.globalFault
  io.localBusy:=state=/=idle || phaseOwned || grantFull || quarantine || faultNow
  io.acceptedTransaction:=heldTransaction
  io.sequenceExhausted:= !sequenceAvailable // admission veto, NOT poison of last valid work
  io.phaseReserved:=phaseOwned
  val clean= !quarantine && !poisoned && !faultNow && !io.globalFault && !io.authority.currentFault

  io.job.ready:=state===idle && !phaseOwned && !grantFull && sequenceAvailable && clean && permitted
  io.phaseJob.ready:=state===idle && phaseOwned && !grantFull && clean && phaseContextCurrent && phaseIdentity
  when(io.job.fire){
    heldJob:=io.job.bits;heldLaunch:=io.authority.launch;heldTransaction:=io.authority.transaction
    heldPhysicalSequence:=nextSequence;nextSequence:=nextSequence+1.U
    heldPhase:=false.B;lastOrdinaryRetired:=false.B;state:=offer
  }
  when(io.phaseJob.fire){
    heldJob:=phaseBits.job;heldLaunch:=phaseContext.host;heldTransaction:=phaseContext.transactionId
    heldPhysicalSequence:=phaseBits.job.tag;heldPhase:=true.B
    phaseHasIssued:=true.B;phaseLastIssued:=phaseBits.job.tag;lastOrdinaryRetired:=false.B;state:=offer
  }
  io.physicalJob.valid:=state===offer;io.physicalJob.bits:=heldJob
  io.physicalJob.bits.tag:=heldPhysicalSequence
  when(io.physicalJob.fire){state:=pending}
  io.physicalDone.ready:=state===pending && !quarantine && !faultNow && sameContext &&
    io.physicalDone.bits.tag===heldPhysicalSequence
  when(io.physicalDone.fire){
    heldResult:=io.physicalDone.bits;heldResult.tag:=heldJob.tag
    when(poisoned || io.globalFault || io.authority.currentFault){heldResult.status:=Status.Protocol.U}
    state:=report
  }
  // Late faults never retract either held terminal or mutate its payload.
  io.done.valid:=state===report && !heldPhase;io.done.bits:=heldResult
  io.phaseDone.valid:=state===report && heldPhase;io.phaseDone.bits:=heldResult
  // Read-only transport retirement; status/current live faults must still be checked.
  io.retired.valid:=io.done.fire || io.phaseDone.fire
  io.retired.bits.transactionId:=heldTransaction;io.retired.bits.host:=heldLaunch
  io.retired.bits.physicalSequence:=heldPhysicalSequence
  io.retired.bits.logicalJob:=heldJob;io.retired.bits.logicalResult:=heldResult
  when(io.done.fire){lastOrdinaryRetired:=true.B;state:=idle}
  when(io.phaseDone.fire){state:=idle}

  // Request.ready has NO dependency on metadata.fire. Parent couples the
  // original clean metadata handoff to reserve.fire; event is checked ONLY
  // after that handshake, never used to make a ready->valid loop.
  io.reserve.ready:=state===idle && !phaseOwned && !grantFull && !io.job.valid &&
    clean && sequenceAvailable
  val (derived,metadataEvent)=HostMoePhaseContextV4.fromActualMetadata(io.authority)
  val endWide=nextSequence.pad(33)+io.reserve.bits.count.pad(33)
  val receipt=lastOrdinaryRetired && !heldPhase && heldTransaction===derived.transactionId &&
    heldLaunch.asUInt===derived.host.asUInt && heldJob.asUInt===io.authority.postnormJob.asUInt &&
    heldResult.asUInt===io.authority.postnormResult.asUInt && heldResult.status===Status.Ok.U
  val reserveLegal=metadataEvent && receipt && io.transportDrained &&
    io.reserve.bits.context.asUInt===derived.asUInt && io.reserve.bits.allocationSequence=/=0.U &&
    io.reserve.bits.count===HostMoeOwnerRangeV5.Count.U && endWide<="hffffffff".U(33.W)
  when(io.reserve.fire){
    grant.context:=io.reserve.bits.context;grant.allocationSequence:=io.reserve.bits.allocationSequence
    grant.first:=nextSequence;grant.endExclusive:=endWide
    grant.postnormPhysicalSequence:=heldPhysicalSequence
    grant.status:=Mux(reserveLegal,Status.Ok.U,Status.Dependency.U);grantFull:=true.B
    when(reserveLegal){
      phaseOwned:=true.B;phaseContext:=io.reserve.bits.context;phaseAllocation:=io.reserve.bits.allocationSequence
      phaseFirst:=nextSequence;phaseEnd:=endWide;nextSequence:=endWide(31,0)
      phaseHasIssued:=false.B
    }
  }
  io.reservation.valid:=grantFull;io.reservation.bits:=grant
  when(io.reservation.fire){grantFull:=false.B}
  io.release.ready:=releaseIdentity && state===idle && !grantFull && clean &&
    phaseContextCurrent && finalWrite && io.finalPhaseRetired && io.transportDrained && !io.phaseJob.valid
  when(io.release.fire){phaseOwned:=false.B}
}
