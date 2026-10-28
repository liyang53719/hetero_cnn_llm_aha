// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE decoded graph information, retained by the original Host scheduler.
  * This is not a Host launch/grant port. All tensor records come from actual
  * TypedTensorReader handshakes; context is the phase-only view of that same actual graph; no full-block V1 is synthesized.
  * propose consumes the retained receipt of an actual successful postnorm
  * done.fire, not a software completion or a re-created pulse.
  */
class HostMoePhaseProposalV5 extends Bundle {
  val context=new HostMoePhaseContextV4
  val postnormJob=new QwenOwnerJob
  val postnormResult=new QwenOwnerResult
  val weights=Vec(HostMoeWeightRoleV4.Count,new DecodedTensor)
}
class HostMoePhaseReleaseV5 extends Bundle {
  val transactionId=UInt(64.W);val allocationSequence=UInt(64.W)
}
class HostMoePhaseFailureV5 extends Bundle {
  val transactionId=UInt(64.W);val status=UInt(8.W)
}

/** External DDR-only phase plan. This SIX MiB is a phase lifetime requirement,
  * not a new physical SRAM or an approved global arena increase. The exact
  * accepted region3 must contain it; all older live scratch spans must be out
  * of its range, and the real previous phase transport must have retired.
  * All1024 expert down rows stay live until final token-nine reader retirement.
  */
object HostMoePhaseLayoutV4 {
  val Bytes=6L*1024*1024
  val Metadata=0L;val Descriptors=16L*1024;val Router=64L*1024
  val Gather=128L*1024;val Gate=640L*1024;val Up=768L*1024
  val Activation=896L*1024;val RoutedDown=1024L*1024
  val SharedDown=5L*1024*1024;val Merged=5632L*1024
  val Regions:Seq[(Long,Long)]=Seq(
    Metadata->(16L*1024),Descriptors->(16L*1024),Router->(64L*1024),
    Gather->(512L*1024),Gate->(128L*1024),Up->(128L*1024),
    Activation->(128L*1024),RoutedDown->(4L*1024*1024),
    SharedDown->(512L*1024),Merged->(512L*1024))
  require(Regions.forall{case(o,n)=>o>=0 && n>0 && o%64==0 && n%64==0 && o+n<=Bytes})
  require(Regions.indices.forall(i=>Regions.indices.forall(j=>i==j ||
    Regions(i)._1+Regions(i)._2<=Regions(j)._1 || Regions(j)._1+Regions(j)._2<=Regions(i)._1)))
  def overlap(a:UInt,ae:UInt,b:UInt,be:UInt):Bool=a<be && b<ae
}

/** A real allocator control, no arithmetic engine or payload bank. Its inputs
  * must be wired INSIDE the original parent. In particular authority is the
  * original decoder's retained output. propose.fire must be the same actual
  * metadata handoff as ownerReserve.fire when fields qualify. No separate
  * dispatchOwned Boolean or invented full-block context authorizes a phase.
  *
  * This module does not assert that those missing parent connections already
  * exist. It cannot turn arbitrary matching packet bits into source authority.
  * full64 identity still needs physical epoch/joint-reset stale isolation.
  */
class HostRuntimeMoePhaseAllocatorV5 extends Module {
  val io=IO(new Bundle {
    val authority=Input(new HostRuntimeAuthoritySnapshotV4)
    val propose=Flipped(Decoupled(new HostMoePhaseProposalV5))
    val ownerReserve=Decoupled(new HostMoeOwnerRangeRequestV5)
    val ownerReservation=Flipped(Decoupled(new HostMoeOwnerRangeResultV5))
    // ACTUAL global lifetime/physical-accounting signals, never Host booleans.
    // liveRegionConflict is wired only from the original Commands freshSpan
    // checks for every fixed allocation subregion against its actual live tables.
    val priorPhaseDrained=Input(Bool());val physicalDrained=Input(Bool())
    val finalMergeRetired=Input(Bool())
    val liveRegionConflict=Input(Bool())
    val currentFault=Input(Bool())
    val localFault=Output(Bool()) // local identity/lifetime/quarantine only; no reflected authority fault
    val grant=Decoupled(new HostMoeRuntimePhaseLeaseV5)
    val failure=Decoupled(new HostMoePhaseFailureV5)
    val release=Flipped(Decoupled(new HostMoePhaseReleaseV5))
    val resetRequired=Output(Bool());val reserved=Output(Bool())
  })
  val idle::waitingRange::offer::active::failed::locked::Nil=Enum(6)
  val state=RegInit(idle);val poison=RegInit(false.B)
  val nextAllocation=RegInit(1.U(64.W));val exhausted=RegInit(false.B)
  val haveTransaction=RegInit(false.B);val lastTransaction=Reg(UInt(64.W))
  val held=Reg(new HostMoeRuntimePhaseLeaseV5);val failure=Reg(new HostMoePhaseFailureV5)
  val owned=state===waitingRange || state===offer || state===active
  val sameContext=io.authority.accepted &&
    io.authority.transaction===held.context.transactionId &&
    io.authority.launch.asUInt===held.context.host.asUInt &&
    io.authority.profile.asUInt===held.context.profile.asUInt
  val staleRelease=io.release.valid && (state=/=active ||
    io.release.bits.transactionId=/=held.context.transactionId ||
    io.release.bits.allocationSequence=/=held.allocationSequence)
  val unknownRange=io.ownerReservation.valid && (state=/=waitingRange ||
    io.ownerReservation.bits.context.asUInt=/=held.context.asUInt ||
    io.ownerReservation.bits.allocationSequence=/=held.allocationSequence)
  val localFaultNow=(owned && (!sameContext || io.liveRegionConflict)) || staleRelease || unknownRange
  val faultNow=io.currentFault || (owned && io.authority.currentFault) || localFaultNow
  when(faultNow){poison:=true.B}
  io.localFault:=poison || localFaultNow
  io.resetRequired:=poison || faultNow
  io.reserved:=state=/=idle || poison || exhausted
  io.grant.valid:=state===offer;io.grant.bits:=held
  io.failure.valid:=state===failed;io.failure.bits:=failure
  when(io.grant.fire){state:=active}
  when(io.failure.fire){state:=Mux(poison||faultNow,locked,idle)}
  // A staged expert loop result is NOT release permission. This release is
  // generated only by the final real merge-reader/vector/write-ACK fence.
  io.release.ready:=state===active && !poison && !faultNow && sameContext &&
    io.physicalDrained && io.finalMergeRetired
  when(io.release.fire){state:=idle}

  val p=io.propose.bits;val c=p.context;val a=io.authority
  val region=c.host.regions(3);val base=region.base
  val endWide=base.pad(80)+HostMoePhaseLayoutV4.Bytes.U(80.W)
  val end=endWide(63,0);val job=p.postnormJob
  val (shape,known)=UnifiedRuntimeProfile.decode(c.host.profileId)
  val profileOK=known && (c.host.profileId===3.U || c.host.profileId===4.U) &&
    shape.asUInt===c.profile.asUInt && shape.hidden===2048.U
  val (derived,actualMetadataEvent)=HostMoePhaseContextV4.fromActualMetadata(a)
  // Field qualification is independent of ready/fire. The actual source event
  // is checked by the Guard only at the coupled metadata/reserve handshake.
  val identity=c.asUInt===derived.asUInt && a.accepted && a.postnormCommitValid && !a.currentFault &&
    a.moeWeights.asUInt===p.weights.asUInt && a.moeOutput.asUInt===c.output.asUInt &&
    HostCommandLaunchV4.known(a.launch) && a.transaction===c.transactionId &&
    a.launch.asUInt===c.host.asUInt && a.profile.asUInt===c.profile.asUInt &&
    c.version===HostMoePhaseContextV4.Version.U && c.phase===HostMoePhaseContextV4.MoePhase.U &&
    (!haveTransaction || c.transactionId>lastTransaction)
  val source=(a.postnormJob.asUInt===job.asUInt) &&
    (a.postnormResidual.asUInt===c.residual.asUInt) &&
    (a.postnormResult.asUInt===p.postnormResult.asUInt) &&
    job.kind===QwenOwnerKind.GdnRmsNorm.U && job.m===c.tokens &&
    job.m>0.U && job.m<=128.U && job.n===2048.U && job.k===2048.U &&
    job.activationBf16 && job.weightBf16 && job.outputBf16 &&
    job.dst(5,0)===0.U && job.a===c.residual.address &&
    job.writeBytes===(job.m.pad(64)<<12) && p.postnormResult.tag===job.tag &&
    p.postnormResult.status===Status.Ok.U && p.postnormResult.writeBytes===job.writeBytes
  val arena=region.read && region.write && region.base<region.limit &&
    region.base(5,0)===0.U && region.limit(5,0)===0.U &&
    endWide<=region.limit.pad(80) && region.limit<=(BigInt(1)<<56).U && io.priorPhaseDrained
  def range(base:UInt,size:UInt):Bool=base(5,0)===0.U && size>0.U &&
    base.pad(80)+size.pad(80)<=(BigInt(1)<<56).U &&
    !HostMoePhaseLayoutV4.overlap(base.pad(80),base.pad(80)+size.pad(80),region.base.pad(80),endWide)
  def readable(t:DecodedTensor,readOnly:Boolean):Bool=a.launch.regions.map(r=>
    r.read && (if(readOnly) !r.write else true.B) &&
    t.address>=r.base && t.paddedEnd<=r.limit && t.address<t.paddedEnd).reduce(_||_)
  val residual=c.residual.dtype===5.U && c.residual.rank===2.U &&
    c.residual.dims(0)===job.m && c.residual.dims(1)===2048.U &&
    c.residual.elementCount===(job.m.pad(32)<<11) &&
    c.residual.payloadBytes===job.writeBytes && readable(c.residual,false) &&
    range(c.residual.address,c.residual.paddedEnd-c.residual.address)
  val finalOutputRange=range(c.output.address,c.output.paddedEnd-c.output.address) &&
    c.input.asUInt===a.postnormOutputTensor.asUInt && c.input.address===job.dst &&
    c.residual.asUInt===a.postnormResidual.asUInt
  val normRange=range(job.dst,job.writeBytes) && a.launch.regions.map(r=>r.read && r.write &&
    job.dst>=r.base && job.dst.pad(80)+job.writeBytes<=r.limit.pad(80)).reduce(_||_)
  val weights=p.weights.zipWithIndex.map{case(t,i)=>
    val expert=(i>=1 && i<=3);val k=if(i==3 || i==6)512 else 2048
    val n=if(i==0)256 else if(i==3 || i==6)2048 else if(i==7)1 else 512
    val count=BigInt(k)*n*(if(expert)256 else 1)
    val dims=if(expert)t.rank===3.U && t.dims(0)===256.U && t.dims(1)===k.U && t.dims(2)===n.U
      else t.rank===2.U && t.dims(0)===k.U && t.dims(1)===n.U
    t.dtype===5.U && dims && t.elementCount===count.U && t.payloadBytes===(count*2).U &&
      t.paddedEnd.pad(80)>=t.address.pad(80)+t.payloadBytes && readable(t,true) &&
      range(t.address,t.paddedEnd-t.address)
  }.reduce(_&&_)
  val lives= !io.liveRegionConflict
  val legal=identity && profileOK && source && arena && residual && normRange && finalOutputRange && weights && lives
  val reserveHeld=HeldDecoupledOffer(state===idle && io.propose.valid,
    io.ownerReserve.ready,poison || faultNow || exhausted || !legal)
  io.ownerReserve.valid:=reserveHeld.valid
  io.ownerReserve.bits.context:=c;io.ownerReserve.bits.allocationSequence:=nextAllocation
  io.ownerReserve.bits.count:=HostMoeOwnerRangeV5.Count.U
  // A previously offered reservation cannot be withdrawn or have its upstream
  // proposal consumed as an unrelated error while that offer still exists.
  io.propose.ready:=state===idle && Mux(reserveHeld.valid,io.ownerReserve.ready,
    !reserveHeld.held && !legal && !exhausted)
  // Actual one-Guard range assignment, never a Host supplied first sequence.
  io.ownerReservation.ready:=state===waitingRange && !unknownRange
  when(io.ownerReservation.fire){
    val r=io.ownerReservation.bits
    val rangeOK=r.endExclusive===r.first.pad(33)+HostMoeOwnerRangeV5.Count.U &&
      r.endExclusive<="hffffffff".U(33.W) && r.first>r.postnormPhysicalSequence
    when(r.status=/=Status.Ok.U || !rangeOK || poison || faultNow){
      failure.transactionId:=held.context.transactionId
      failure.status:=Mux(r.status=/=Status.Ok.U,r.status,Status.Protocol.U)
      when(!rangeOK || poison || faultNow){poison:=true.B}
      state:=failed
    }.otherwise{
      held.firstOwnerSequence:=r.first
      held.postnormPhysicalSequence:=r.postnormPhysicalSequence
      state:=offer
    }
  }
  when(io.propose.fire){
    failure.transactionId:=c.transactionId;failure.status:=Status.Bounds.U
    when(!io.ownerReserve.fire){failure.status:=Mux(poison||faultNow,Status.Protocol.U,Status.Bounds.U);state:=failed}
    .otherwise{
      held:=0.U.asTypeOf(new HostMoeRuntimePhaseLeaseV5)
      held.context:=c;held.allocationSequence:=nextAllocation
      held.hostEpoch:=a.launch.epoch
      held.postnormJob:=job;held.postnormResult:=p.postnormResult
      held.postnormOwnerSequence:=job.tag;held.postnormBase:=job.dst
      held.residualBase:=c.residual.address;held.weights:=p.weights
      held.allocationBase:=base;held.allocationEnd:=end
      held.metadataBase:=base+HostMoePhaseLayoutV4.Metadata.U
      held.descriptorBase:=base+HostMoePhaseLayoutV4.Descriptors.U
      held.routerLogits:=base+HostMoePhaseLayoutV4.Router.U
      held.gatheredInput:=base+HostMoePhaseLayoutV4.Gather.U
      held.gateOutput:=base+HostMoePhaseLayoutV4.Gate.U
      held.upOutput:=base+HostMoePhaseLayoutV4.Up.U
      held.activationOutput:=base+HostMoePhaseLayoutV4.Activation.U
      held.routedDown:=base+HostMoePhaseLayoutV4.RoutedDown.U
      held.sharedDown:=base+HostMoePhaseLayoutV4.SharedDown.U
      held.mergedOutput:=base+HostMoePhaseLayoutV4.Merged.U
      haveTransaction:=true.B;lastTransaction:=c.transactionId
      when(nextAllocation==="hffffffffffffffff".U){exhausted:=true.B}
        .otherwise{nextAllocation:=nextAllocation+1.U}
      // The Guard independently checks the SAME event and full receipt. If a
      // parent failed to couple the original scanner handoff, never issue grant.
      when(!actualMetadataEvent || !legal){poison:=true.B}
      state:=waitingRange
    }
  }
}
