// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** One existing Vector32 bank, one new ordinary slot11. Real Guard fires are
  * authority; a matching request tag or Host value alone cannot acquire it.
  * P0 uses only Vector11: its four scalar operations remain inside the original
  * Core (borrowing Scalar8 here would deadlock against that same Core).
  * Runtime Norm retains its independently checked prefix lease and uses
  * Scalar8+Vector11. No Format9/Chunk10 permission is broadened. */
object HostOrderedRms32WiringV1 {
  class View extends Bundle {val localFault=Bool();val resourcesDrained=Bool();val eventsPending=Bool()}
  def connect(a:UnifiedMoeSharedArithmeticAdapterV5,g:HostRuntimeOwnerGuardV5,
      authority:HostRuntimeAuthoritySnapshotV4,k:QwenOwnerKernel,
      prefix:HostRuntimePrefixLeaseWiringV8.View,currentIndependentFault:Bool,enableP0:Boolean):View={
    connectPorts(Rms32PortRefsV1.arithmetic(a),Rms32PortRefsV1.guard(g),authority,Rms32PortRefsV1.owner(k),prefix,currentIndependentFault,enableP0)
  }
  def connectPorts(a:Rms32PortRefsV1.Arithmetic,g:Rms32PortRefsV1.Guard,
      authority:HostRuntimeAuthoritySnapshotV4,k:Rms32PortRefsV1.Owner,
      prefix:HostRuntimePrefixLeaseWiringV8.View,currentIndependentFault:Bool,enableP0:Boolean):View={
    val out=Wire(new View)
    val poison=RegInit(false.B);val waiting=RegInit(false.B);val owned=RegInit(false.B)
    val logical=Reg(new QwenOwnerJob);val accepted=Reg(new QwenOwnerJob)
    val host=Reg(new HostCommandLaunchV4);val transaction=Reg(UInt(64.W))
    val lease=Reg(new UnifiedMoeArithmeticLeaseV5)
    val acquire=RegInit(false.B);val retire=RegInit(false.B);val retireStatus=Reg(UInt(8.W))
    val submitted=RegInit(false.B);val routeP0=RegInit(false.B)
    val slot=a.io.status(UnifiedMoeArithmeticClientV5.OrdinaryRmsVector32)
    val slotBusy=slot.active || slot.retiring || !slot.resourcesDrained
    def isP0Norm(j:QwenOwnerJob):Bool=enableP0.B && j.kind===QwenOwnerKind.Norm.U
    def shape(j:QwenOwnerJob):Bool=authority.accepted && authority.launch.profileId===0.U &&
      j.m>=1.U && j.m<=128.U && j.n===1536.U && j.k===1536.U &&
      !j.activationBf16 && !j.weightBf16 && !j.outputBf16 && j.writeBytes===(j.m.pad(64)*6144.U)
    val busy=waiting || owned || acquire || retire || routeP0
    val contextChanged=(waiting || owned || routeP0) &&
      (!authority.accepted || authority.transaction=/=transaction || authority.launch.asUInt=/=host.asUInt)
    acquire:=false.B;retire:=false.B
    when(g.io.job.fire && isP0Norm(g.io.job.bits)){
      when(busy || slotBusy || !shape(g.io.job.bits) || prefix.owned){poison:=true.B}
      .otherwise{logical:=g.io.job.bits;host:=authority.launch;transaction:=authority.transaction;waiting:=true.B}
    }
    val expected=WireDefault(logical);expected.tag:=g.io.physicalJob.bits.tag
    val exact=waiting && !contextChanged && g.io.physicalJob.bits.asUInt===expected.asUInt &&
      g.io.physicalJob.bits.tag=/="hffffffff".U && shape(g.io.physicalJob.bits)
    when(g.io.physicalJob.fire && isP0Norm(g.io.physicalJob.bits)){
      owned:=true.B;waiting:=false.B;accepted:=g.io.physicalJob.bits
      when(!exact || poison || slotBusy || prefix.owned || currentIndependentFault || authority.currentFault || g.io.localFault){poison:=true.B}
      .otherwise{
        val p=WireDefault(0.U.asTypeOf(new UnifiedMoeArithmeticLeaseV5))
        p.authorityKind:=UnifiedArithmeticAuthorityKindV5.OrdinaryRms32.U
        p.allocationValid:=false.B;p.allocationSequence:=0.U;p.hostEpoch:=host.epoch
        p.lease.identity.transactionId:=transaction;p.lease.identity.ownerSequence:=g.io.physicalJob.bits.tag
        p.lease.identity.stage:=UnifiedMoeArithmeticClientV5.OrdinaryRms32Stage.U
        p.lease.resource:=1.U;p.lease.expectedOperations:=g.io.physicalJob.bits.m.pad(32)*111.U
        lease:=p;acquire:=true.B;submitted:=true.B;routeP0:=true.B
      }
    }
    val countsExact=slot.lease.asUInt===lease.asUInt && slot.resourcesDrained &&
      slot.counts.accepted===lease.lease.expectedOperations.pad(33) &&
      slot.counts.issued===lease.lease.expectedOperations.pad(33) &&
      slot.counts.returned===lease.lease.expectedOperations.pad(33)
    val coreDrained=if(enableP0)k.io.rmsVectorDrained.get else true.B
    val corePoison=if(enableP0)k.io.rmsVectorResetRequired.get else false.B
    val terminalExact=g.io.physicalDone.bits.tag===accepted.tag && !contextChanged &&
      coreDrained && (!submitted || (slot.resourcesDrained && slot.lease.asUInt===lease.asUInt)) &&
      (g.io.physicalDone.bits.status=/=Status.Ok.U ||
      (submitted && countsExact && !corePoison && g.io.physicalDone.bits.writeBytes===accepted.writeBytes))
    when(owned && g.io.physicalDone.valid && !terminalExact){poison:=true.B}
    when(owned && g.io.physicalDone.fire){
      when(!terminalExact){poison:=true.B}
      .otherwise{owned:=false.B;retire:=submitted;retireStatus:=g.io.physicalDone.bits.status;submitted:=false.B}
    }
    when(contextChanged || corePoison){poison:=true.B}
    when(routeP0 && !owned && !acquire && !retire && !slotBusy){routeP0:=false.B}
    val eventConflict=(acquire && prefix.vectorAcquire.valid) || (retire && prefix.vectorRetire.valid) ||
      (routeP0 && prefix.vectorRequest.valid) || (owned && prefix.owned)
    when(eventConflict){poison:=true.B}
    a.io.acquire(11).valid:=(acquire || prefix.vectorAcquire.valid) && !eventConflict
    a.io.acquire(11).bits:=Mux(acquire,lease,prefix.vectorAcquire.bits)
    a.io.retire(11).valid:=(retire || prefix.vectorRetire.valid) && !eventConflict
    a.io.retire(11).bits.lease:=Mux(retire,lease,prefix.vectorRetire.bits.lease)
    a.io.retire(11).bits.status:=Mux(retire,retireStatus,prefix.vectorRetire.bits.status)
    val firstFault=currentIndependentFault || poison || corePoison || contextChanged || eventConflict || g.io.localFault || authority.currentFault
    val p0Held=WireDefault(false.B)
    if(enableP0){
      val r=k.io.rmsVectorRequest.get;val result=k.io.rmsVectorResult.get
      val published=HeldDecoupledOffer(owned && submitted && r.valid,a.io.rmsVectorRequest.ready,firstFault)
      p0Held:=published.held
      k.io.rmsVectorPublished.get:=routeP0 && published.valid
      a.io.rmsVectorRequest.valid:=Mux(routeP0,published.valid,prefix.vectorRequest.valid)
      a.io.rmsVectorRequest.bits:=Mux(routeP0,r.bits,prefix.vectorRequest.bits)
      r.ready:=routeP0 && published.valid && a.io.rmsVectorRequest.ready
      result.valid:=routeP0 && a.io.rmsVectorResult.valid;result.bits:=a.io.rmsVectorResult.bits
      a.io.rmsVectorResult.ready:=Mux(routeP0,result.ready,prefix.vectorResult.ready)
    }else{
      a.io.rmsVectorRequest.valid:=prefix.vectorRequest.valid;a.io.rmsVectorRequest.bits:=prefix.vectorRequest.bits
      a.io.rmsVectorResult.ready:=prefix.vectorResult.ready
    }
    prefix.vectorRequest.ready:= !routeP0 && a.io.rmsVectorRequest.ready
    prefix.vectorResult.valid:= !routeP0 && a.io.rmsVectorResult.valid
    prefix.vectorResult.bits:=a.io.rmsVectorResult.bits
    // Raw-publication conflicts are registered above, never reflected through
    // authority.currentFault back into the same held-publication valid.
    out.localFault:=poison || contextChanged
    out.eventsPending:=waiting || acquire || retire || p0Held
    out.resourcesDrained:= !busy && !p0Held && coreDrained && !slotBusy
    out
  }
}
