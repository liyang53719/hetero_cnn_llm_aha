// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class UnifiedRuntimeDenseResultV2 extends Bundle {
  val transactionId=UInt(64.W);val role=UInt(4.W);val result=new QwenOwnerResult
  val nextOwnerSequence=UInt(32.W);val drained=Bool();val resetRequired=Bool()
}

/** First execution integration slice, not another model-specific hardware top.
  * Reuses ONE unmodified original SRAM/DDR feeder. Matrix/vector/Scalar are
  * external UNIQUE shared resources; this module instantiates none of them.
  * One projection terminal includes original feeder's actual write ACKs.
  * Complete-block scheduling and producer provenance are separate obligations. */
class UnifiedOriginalDenseClientV2 extends Module {
  val io=IO(new Bundle {
    val command=Flipped(Decoupled(new UnifiedRuntimeDenseCommandV2))
    val result=Decoupled(new UnifiedRuntimeDenseResultV2)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val burst=Decoupled(new BurstReadRequest);val burstResponse=Flipped(Decoupled(new BurstReadResponse))
    val matrixLease=Decoupled(new UnifiedOverlapLeaseV2)
    val matrixGroup=Decoupled(new MatrixStreamGroup(false,false))
    val matrixStep=Decoupled(new MatrixStreamStep(0))
    val matrixResult=Flipped(Decoupled(new MatrixStreamResult(0)))
    val matrixDone=Flipped(Decoupled(new UnifiedOverlapDoneV2))
    val physicalSteps=Input(UInt(64.W))
    val contextReserved=Output(Bool());val resetRequired=Output(Bool())
  })
  val feeder=Module(new StreamingDenseOwner(maxK=8960,maxTokenTiles=5,burstWrites=false,coalesceWeightReads=true))
  val bridge=Module(new UnifiedDenseGroupLeaseBridgeV2)
  val idle::launch::running::report::locked::Nil=Enum(5)
  val state=RegInit(idle);val plan=Reg(new UnifiedRuntimeDensePlanV2)
  val out=Reg(new UnifiedRuntimeDenseResultV2)
  val decoded=UnifiedRuntimeDensePlanV2.decode(io.command.bits)
  io.command.ready:=state===idle && !bridge.io.resetRequired && !feeder.io.resetRequired
  io.contextReserved:=state=/=idle || io.command.valid
  io.resetRequired:=state===locked || bridge.io.resetRequired || feeder.io.resetRequired
  io.result.valid:=state===report;io.result.bits:=out
  when(io.command.fire){
    plan:=decoded;out:=0.U.asTypeOf(new UnifiedRuntimeDenseResultV2)
    out.transactionId:=io.command.bits.context.transactionId;out.role:=io.command.bits.role
    out.nextOwnerSequence:=io.command.bits.firstOwnerSequence
    out.result.tag:=io.command.bits.firstOwnerSequence
    when(!decoded.valid){out.result.status:=Status.Bounds.U;out.drained:=true.B;state:=report}
      .elsewhen(decoded.route=/=UnifiedDenseRouteV2.StreamingBf16.U){
        // The common scheduler must send Qwen2 to the existing public21
        // reduction/resident route, NEVER fall back to this simpler feeder.
        out.result.status:=Status.Unsupported.U;out.drained:=true.B;state:=report
      }.otherwise{state:=launch}
  }
  // Atomic acceptance: neither child can start alone.
  feeder.io.job.valid:=state===launch && bridge.io.start.ready
  feeder.io.job.bits:=plan.job
  bridge.io.start.valid:=state===launch && feeder.io.job.ready;bridge.io.start.bits:=plan
  when(feeder.io.job.fire){assert(bridge.io.start.fire);state:=running}
  bridge.io.feeder<>feeder.io.matrix
  io.matrixLease<>bridge.io.lease;io.matrixGroup<>bridge.io.group;io.matrixStep<>bridge.io.step
  bridge.io.result<>io.matrixResult;bridge.io.done<>io.matrixDone
  feeder.io.physicalSteps:=io.physicalSteps
  io.memory<>feeder.io.memory;feeder.io.response<>io.response
  io.burst<>feeder.io.burst;feeder.io.burstResponse<>io.burstResponse
  feeder.io.done.ready:=state===running
  bridge.io.finish:=feeder.io.done.fire
  when(feeder.io.done.fire){
    out.result:=feeder.io.done.bits;out.nextOwnerSequence:=bridge.io.nextOwnerSequence
    val bad=feeder.io.done.bits.status=/=0.U || feeder.io.done.bits.tag=/=plan.job.tag || bridge.io.resetRequired || feeder.io.resetRequired || !bridge.io.allGroupsReturned
    out.result.status:=Mux(bad && feeder.io.done.bits.status===0.U,Status.Protocol.U,feeder.io.done.bits.status)
    out.drained:= !bad;out.resetRequired:=bad;state:=report
  }
  when(io.result.fire){state:=Mux(out.resetRequired,locked,idle)}
}
