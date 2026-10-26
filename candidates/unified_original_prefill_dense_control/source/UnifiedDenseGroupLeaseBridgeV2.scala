// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** One real StreamingDenseOwner can issue many groups for one projection.
  * Translate each real group to the already tested shared Matrix owner port.
  * No arithmetic, fake result, or Host-supplied drain is implemented here.
  * A failed/undrained group locks this client; isolation/reset is external. */
class UnifiedDenseGroupLeaseBridgeV2 extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new UnifiedRuntimeDensePlanV2))
    val feeder=Flipped(new MatrixStreamPort(0,false,false))
    val lease=Decoupled(new UnifiedOverlapLeaseV2)
    val group=Decoupled(new MatrixStreamGroup(false,false))
    val step=Decoupled(new MatrixStreamStep(0))
    val result=Flipped(Decoupled(new MatrixStreamResult(0)))
    val done=Flipped(Decoupled(new UnifiedOverlapDoneV2))
    val finish=Input(Bool()) // real feeder terminal is consumed, never a Host clear
    val idle=Output(Bool());val resetRequired=Output(Bool())
    val allGroupsReturned=Output(Bool())
    val nextOwnerSequence=Output(UInt(32.W))
  })
  val idle::takeGroup::acquire::sendGroup::running::reply::locked::Nil=Enum(7)
  val state=RegInit(idle);val plan=Reg(new UnifiedRuntimeDensePlanV2)
  val group=Reg(new MatrixStreamGroup(false,false));val sequence=Reg(UInt(32.W))
  val heldLease=Reg(new UnifiedOverlapLeaseV2);val returned=Reg(new MatrixStreamDone)
  val poison=RegInit(false.B);val failed=RegInit(false.B)
  val identity=io.done.bits.lease.asUInt===heldLease.asUInt
  val faultNow=io.feeder.abort || (io.done.valid && (state=/=running || !identity)) ||
    (state===takeGroup && io.feeder.group.valid && sequence==="hffffffff".U)
  io.start.ready:=state===idle && !poison && !faultNow;io.idle:=state===idle
  io.resetRequired:=poison||faultNow;io.nextOwnerSequence:=sequence
  io.allGroupsReturned:=state===takeGroup && !poison && !faultNow
  when(io.start.fire){plan:=io.start.bits;sequence:=io.start.bits.firstOwnerSequence;state:=takeGroup}
  io.feeder.group.ready:=state===takeGroup && !io.finish && sequence=/="hffffffff".U && !poison && !faultNow
  when(io.feeder.group.fire){
    group:=io.feeder.group.bits
    heldLease:=0.U.asTypeOf(new UnifiedOverlapLeaseV2)
    heldLease.transactionId:=plan.context.transactionId;heldLease.ownerSequence:=sequence
    heldLease.stage:=1.U // existing Matrix resource lease; not full-block completion
    state:=acquire
  }
  io.lease.valid:=state===acquire;io.lease.bits:=heldLease
  when(io.lease.fire){sequence:=sequence+1.U;state:=sendGroup}
  io.group.valid:=state===sendGroup;io.group.bits:=group
  when(io.group.fire){state:=running}
  io.step.valid:=state===running && io.feeder.step.valid
  io.step.bits:=io.feeder.step.bits;io.feeder.step.ready:=state===running && io.step.ready
  io.feeder.result.valid:=state===running && io.result.valid
  io.feeder.result.bits:=io.result.bits;io.result.ready:=state===running && io.feeder.result.ready
  io.done.ready:=state===running && identity
  when(io.done.fire){
    val bad=io.done.bits.status=/=0.U || !io.done.bits.drained || io.done.bits.resetRequired || poison || faultNow
    returned.tag:=group.tag;returned.error:=bad;failed:=bad;state:=reply
    when(bad){poison:=true.B}
  }
  io.feeder.done.valid:=state===reply;io.feeder.done.bits:=returned
  when(io.feeder.done.fire){state:=Mux(failed,locked,takeGroup)}
  when(io.finish && state===takeGroup){state:=idle}
  // Existing feeder abort is NOT a safe cancellation of an owned physical
  // group. Keep outstanding ownership; never synthesize success or drained.
  when(faultNow){poison:=true.B}
}
