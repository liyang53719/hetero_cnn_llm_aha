// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Versioned integration command. Mode0 is the requested complete block, and
  * currently returns explicit UNSUPPORTED. Modes1..4 are internal resource
  * qualification transactions, never counted as a completed model block.
  * The public production Host serialization/typed scheduler is not added yet.
  */
class UnifiedSharedLaunchV1 extends Bundle {
  val block = new UnifiedBlockLaunchV1
  val resourceMode = UInt(3.W) //0 block/1 Matrix/2 Vector/3 Scalar/4 private state
}

/** Same physical graph and I/O for every runtime profile, no model constructor.
  * The one original4096 Matrix,16lane Vector,Scalar and fixed32head state copy
  * have real command/result paths, not dontTouch-only disconnected instances.
  * Still an integration candidate, not a complete shared block execution top.
  */
class UnifiedSharedResourceTop extends Module {
  val admission=Module(new UnifiedBlockAdmission)
  val fabric=Module(new UnifiedPhysicalFabric)
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new UnifiedSharedLaunchV1))
    val result=Decoupled(new UnifiedBlockResultV1)
    val context=Output(new UnifiedBlockDispatchV1);val contextValid=Output(Bool())
    val matrixGroup=Flipped(Decoupled(new UnifiedMatrixGroupRequest))
    val matrixStep=Flipped(Decoupled(new UnifiedMatrixStepRequest))
    val matrixResult=Decoupled(new UnifiedTaggedMatrixResult)
    val vectorRequest=Flipped(Decoupled(new UnifiedTaggedVectorRequest));val vectorResult=Decoupled(new UnifiedTaggedVectorResult)
    val scalarRequest=Flipped(Decoupled(new UnifiedTaggedScalarRequest));val scalarResult=Decoupled(new UnifiedTaggedScalarResult)
    val stateJob=Flipped(Decoupled(new UnifiedTaggedStateRequest));val committed=Input(new GdnChunkCommittedState)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool());val completeBlockImplemented=Output(Bool())
  })
  admission.io.launch.bits:=io.launch.bits.block
  io.launch.ready:=admission.io.launch.ready && !fabric.io.resetRequired
  // Never let an external resource poison accept an untracked admission.
  admission.io.launch.valid:=io.launch.valid && !fabric.io.resetRequired
  val mode=Reg(UInt(3.W))
  val committedSnapshot=Reg(new GdnChunkCommittedState)
  when(io.launch.fire){mode:=io.launch.bits.resourceMode;committedSnapshot:=io.committed}
  val resourceMode=mode>=1.U && mode<=4.U
  val rejected=RegInit(false.B)
  fabric.io.lease.valid:=admission.io.dispatch.valid && resourceMode
  fabric.io.lease.bits.context:=admission.io.dispatch.bits
  fabric.io.lease.bits.resource:=(mode-1.U)(1,0)
  admission.io.dispatch.ready:=Mux(resourceMode,fabric.io.lease.ready,!rejected)
  when(admission.io.dispatch.fire && !resourceMode){rejected:=true.B}

  val f=fabric.io.done.bits
  admission.io.completion.valid:=rejected || fabric.io.done.valid
  admission.io.completion.bits.transactionId:=Mux(rejected,admission.io.context.transactionId,f.transactionId)
  admission.io.completion.bits.profileId:=Mux(rejected,admission.io.context.profile.profileId,f.profileId)
  admission.io.completion.bits.tag:=Mux(rejected,admission.io.context.launch.tag,f.tag)
  admission.io.completion.bits.status:=Mux(rejected,"h80".U,f.status)
  admission.io.completion.bits.drained:=rejected || f.drained
  admission.io.completion.bits.resetRequired:= !rejected && (f.resetRequired||fabric.io.resetRequired)
  admission.io.completion.bits.acknowledgedWriteBytes:=Mux(rejected,0.U,f.acknowledgedWriteBytes)
  admission.io.completion.bits.issuedSliceSteps:=Mux(rejected,0.U,f.issuedSliceSteps)
  fabric.io.done.ready:= !rejected && admission.io.completion.ready
  when(rejected && admission.io.completion.fire){rejected:=false.B}
  io.result<>admission.io.result
  io.context:=admission.io.context;io.contextValid:=admission.io.active
  io.resetRequired:=admission.io.resetRequired||fabric.io.resetRequired
  io.completeBlockImplemented:=false.B // cannot silently count unsupported as success

  fabric.io.matrixGroup<>io.matrixGroup;fabric.io.matrixStep<>io.matrixStep
  io.matrixResult<>fabric.io.matrixResult
  fabric.io.vectorRequest<>io.vectorRequest;io.vectorResult<>fabric.io.vectorResult
  fabric.io.scalarRequest<>io.scalarRequest;io.scalarResult<>fabric.io.scalarResult
  fabric.io.stateJob<>io.stateJob;fabric.io.committed:=committedSnapshot
  io.memory<>fabric.io.memory;fabric.io.response<>io.response
}
