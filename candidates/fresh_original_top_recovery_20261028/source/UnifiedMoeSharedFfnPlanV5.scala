// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Source-level binding for the actual common phase scheduler. No Module or
  * arithmetic engine. Invoke the constructor unconditionally outside when;
  * register its packet only at the true routedLoop.done.fire associated with
  * the SAME retained allocator lease. Geometry/equality are not authorization.
  * The parent must reserve HostMoeOwnerRangeV5.Count identities in one actual
  * Guard transaction and gate creation of a new offer on current global fault.
  */
object UnifiedMoeSharedFfnPlanV5 {
  def fromActualRoutedRetirement(l:HostMoeRuntimePhaseLeaseV5,
      r:HostMoeRoutedPhaseResultV5):(UnifiedMoeFfnGroupJobV3,Bool)={
    val j=WireDefault(0.U.asTypeOf(new UnifiedMoeFfnGroupJobV3))
    j.context:=l.context;j.expert:=256.U;j.groupRows:=l.context.tokens
    // Fixed tail offset. Actual routed nextOwnerSequence is progress only;
    // unused routed-reservoir identities are never reclaimed or reused.
    j.firstOwnerSequence:=l.firstOwnerSequence+HostMoeOwnerRangeV5.SharedFfnFirst.U
    j.input:=l.postnormBase
    j.gateWeight:=l.weights(HostMoeWeightRoleV4.SharedGate).address
    j.upWeight:=l.weights(HostMoeWeightRoleV4.SharedUp).address
    j.downWeight:=l.weights(HostMoeWeightRoleV4.SharedDown).address
    j.gateOutput:=l.gateOutput;j.upOutput:=l.upOutput
    j.activationOutput:=l.activationOutput;j.downOutput:=l.sharedDown
    j.allocationEnd:=l.allocationEnd
    val weights=(HostMoeWeightRoleV4.SharedGate to HostMoeWeightRoleV4.SharedDown).map{i=>
      val w=l.weights(i);val k=if(i==HostMoeWeightRoleV4.SharedDown)512 else 2048
      val n=if(i==HostMoeWeightRoleV4.SharedDown)2048 else 512
      w.dtype===5.U && w.rank===2.U && w.dims(0)===k.U && w.dims(1)===n.U &&
        w.dims(2)===1.U && w.dims(3)===1.U && w.elementCount===(k*n).U &&
        w.payloadBytes===(k*n*2).U && w.address=/=0.U && w.address(5,0)===0.U &&
        w.paddedEnd.pad(96)>=w.address.pad(96)+w.payloadBytes.pad(96) &&
        w.paddedEnd<=(BigInt(1)<<56).U
    }.reduce(_&&_)
    val routed=r.transactionId===l.context.transactionId && r.allocationSequence===l.allocationSequence &&
      r.status===Status.Ok.U && r.locallyDrained && !r.resetRequired &&
      r.groups>=1.U && r.groups<=256.U && r.routedRows===(l.context.tokens.pad(11)<<3) &&
      r.routedDownBase===l.routedDown &&
      r.nextOwnerSequence.pad(33)===l.firstOwnerSequence.pad(33)+1.U+r.groups.pad(33)*5.U
    val (_,_,_,ffnLegal)=UnifiedMoeFfnGroupPlanV3.decode(j)
    val legal=UnifiedMoeRuntimeLeaseGeometryV4.legal(l) && weights && routed && ffnLegal &&
      l.firstOwnerSequence.pad(33)<=HostMoeOwnerRangeV5.MaximumFirst.U(33.W)
    (j,legal)
  }

  /** Check an actual shared sequencer.result.fire before scratch reuse/N1.
    * This predicate does not manufacture the result or authorize later memory.
    * Global resource counts/unknown-return poison and actual child inactivity
    * must independently close in the parent before any N1 offer is created.
    * SharedDown and routedDown are NOT released by this intermediate event.
    */
  def completed(l:HostMoeRuntimePhaseLeaseV5,r:UnifiedMoeFfnGroupResultV3):Bool={
    val d=r.down;val a=r.activation;val first=l.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.SharedFfnFirst.U
    val rows=l.context.tokens
    val down=d.context.asUInt===l.context.asUInt && d.expert===256.U && d.stage===2.U &&
      d.groupRows===rows && d.output===l.sharedDown && d.ownerSequence.pad(33)===first+3.U &&
      d.result.tag===d.ownerSequence && d.result.status===Status.Ok.U &&
      d.result.writeBytes===(rows.pad(64)<<12) && d.successfulWriteback
    val activation=a.context.asUInt===l.context.asUInt && a.expert===256.U && a.groupRows===rows &&
      a.output===l.activationOutput && a.ownerSequence.pad(33)===first+2.U &&
      a.status===Status.Ok.U && a.drained && a.acknowledgedWriteBytes===(rows.pad(64)<<10) &&
      a.scalarIssued===(rows.pad(33)*3072.U) && a.scalarReturned===a.scalarIssued &&
      a.formatIssued===(rows.pad(33)<<10) && a.formatReturned===a.formatIssued
    r.status===Status.Ok.U && r.drained && r.downCommitted && r.completedStages===4.U &&
      down && activation && l.firstOwnerSequence.pad(33)<=HostMoeOwnerRangeV5.MaximumFirst.U(33.W)
  }
}
