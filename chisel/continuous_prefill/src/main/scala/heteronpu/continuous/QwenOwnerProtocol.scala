// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal, decoded owner job. Never a Host opcode or on-DDR encoding. */
object QwenOwnerKind { val Norm=0; val Dense=1; val Bias=2; val Rope=3; val Attention=4; val Add=5; val Activation=6; val KvAppend=7 }
class QwenOwnerJob extends Bundle {
  val kind=UInt(3.W); val m=UInt(16.W); val n=UInt(16.W); val k=UInt(16.W)
  val a=UInt(64.W); val b=UInt(64.W); val c=UInt(64.W); val dst=UInt(64.W)
  val weightBf16=Bool() // Dense B storage only; compute remains BF16 x BF16 + FP32.
  val writeBytes=UInt(64.W); val tag=UInt(32.W)
}
class QwenOwnerResult extends Bundle {
  val tag=UInt(32.W); val status=UInt(8.W); val writeBytes=UInt(64.W)
  val cycles=UInt(64.W); val usefulMacs=UInt(64.W); val executedMacs=UInt(64.W)
}
/** No block launch is exposed. One decoded owner operation per transaction;
  * the arithmetic implementation must return instead of advancing to a phase.
  */
class QwenOwnerKernel(s:QwenBlockShape,pipelined:Boolean=false) extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob)); val done=Decoupled(new QwenOwnerResult)
    val memory=Decoupled(new MemoryRequest); val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool())
    val burst=if(pipelined)Some(Decoupled(new BurstReadRequest))else None
    val burstResponse=if(pipelined)Some(Flipped(Decoupled(new BurstReadResponse)))else None
    val pipelineIssues=Output(UInt(64.W));val pipelineStalls=Output(UInt(64.W))
  })
  if(!pipelined){
  val core=Module(new Qwen2ContinuousBlock(s,ownerDriven=true))
  core.io.launch.valid:=false.B;core.io.launch.bits:=0.U.asTypeOf(new BlockLaunch)
  core.io.ownerJob.get<>io.job
  val tag=Reg(UInt(32.W));when(io.job.fire){tag:=io.job.bits.tag}
  io.done.valid:=core.io.result.valid;core.io.result.ready:=io.done.ready
  io.done.bits.tag:=tag;io.done.bits.status:=core.io.result.bits.status
  io.done.bits.writeBytes:=core.io.acknowledgedWriteBytes
  io.done.bits.cycles:=core.io.result.bits.cycles
  io.done.bits.usefulMacs:=core.io.result.bits.macs;io.done.bits.executedMacs:=core.io.result.bits.executedMacs
  io.memory<>core.io.memory;core.io.response<>io.response;io.resetRequired:=core.io.resetRequired
    io.pipelineIssues:=0.U;io.pipelineStalls:=0.U
  }else{
    require(s.matrixColumns==256 && s.retainedMatrix)
    val core=Module(new Qwen2ContinuousBlock(s,ownerDriven=true,externalMatrix=true))
    core.io.launch.valid:=false.B;core.io.launch.bits:=0.U.asTypeOf(new BlockLaunch)
    val dense=Module(new StreamingDenseOwner(s.maxRow))
    val silu=Module(new VectorSiluOwner)
    val matrix=Module(new MatrixPipelineService)
    val legacy=Module(new LegacyMatrixStreamClient)
    legacy.io.request<>core.io.matrixRequest.get;core.io.matrixResult.get<>legacy.io.result
    core.io.matrixAcceptedSteps.get:=matrix.io.acceptedSteps
    dense.io.physicalSteps:=matrix.io.acceptedSteps
    val active=RegInit(false.B);val mode=Reg(UInt(2.W));val tag=Reg(UInt(32.W))
    val choose=Mux(io.job.bits.kind===QwenOwnerKind.Dense.U,1.U,Mux(io.job.bits.kind===QwenOwnerKind.Activation.U,2.U,0.U))
    io.job.ready:= !active && MuxLookup(choose,core.io.ownerJob.get.ready)(Seq(1.U->dense.io.job.ready,2.U->silu.io.job.ready))
    core.io.ownerJob.get.valid:=io.job.valid && !active && choose===0.U;core.io.ownerJob.get.bits:=io.job.bits
    dense.io.job.valid:=io.job.valid && !active && choose===1.U;dense.io.job.bits:=io.job.bits
    silu.io.job.valid:=io.job.valid && !active && choose===2.U;silu.io.job.bits:=io.job.bits
    when(io.job.fire){active:=true.B;mode:=choose;tag:=io.job.bits.tag}
    val oldDone=Wire(new QwenOwnerResult)
    oldDone.tag:=tag;oldDone.status:=core.io.result.bits.status;oldDone.cycles:=core.io.result.bits.cycles
    oldDone.writeBytes:=core.io.acknowledgedWriteBytes;oldDone.usefulMacs:=core.io.result.bits.macs;oldDone.executedMacs:=core.io.result.bits.executedMacs
    io.done.valid:=active && MuxLookup(mode,core.io.result.valid)(Seq(1.U->dense.io.done.valid,2.U->silu.io.done.valid))
    io.done.bits:=MuxLookup(mode,oldDone)(Seq(1.U->dense.io.done.bits,2.U->silu.io.done.bits))
    core.io.result.ready:=active&&mode===0.U&&io.done.ready
    dense.io.done.ready:=active&&mode===1.U&&io.done.ready;silu.io.done.ready:=active&&mode===2.U&&io.done.ready
    when(io.done.fire){active:=false.B}
    val memories=Seq(core.io.memory,dense.io.memory,silu.io.memory)
    val responses=Seq(core.io.response,dense.io.response,silu.io.response)
    io.memory.valid:=active&&MuxLookup(mode,memories(0).valid)(Seq(1.U->memories(1).valid,2.U->memories(2).valid))
    io.memory.bits:=MuxLookup(mode,memories(0).bits)(Seq(1.U->memories(1).bits,2.U->memories(2).bits))
    io.response.ready:=active&&MuxLookup(mode,responses(0).ready)(Seq(1.U->responses(1).ready,2.U->responses(2).ready))
    for(i<-0 until 3){memories(i).ready:=active&&mode===i.U&&io.memory.ready
      responses(i).valid:=active&&mode===i.U&&io.response.valid;responses(i).bits:=io.response.bits}
    io.burst.get<>dense.io.burst;dense.io.burstResponse<>io.burstResponse.get
    val useDense=active&&mode===1.U
    for((client,index)<-Seq(legacy.io.port,dense.io.matrix).zipWithIndex){
      val selected=if(index==1)useDense else !useDense
      client.group.ready:=selected&&matrix.io.port.group.ready
      client.step.ready:=selected&&matrix.io.port.step.ready
      client.result.valid:=selected&&matrix.io.port.result.valid;client.result.bits:=matrix.io.port.result.bits
      client.done.valid:=selected&&matrix.io.port.done.valid;client.done.bits:=matrix.io.port.done.bits
    }
    matrix.io.port.group.valid:=Mux(useDense,dense.io.matrix.group.valid,legacy.io.port.group.valid)
    matrix.io.port.group.bits:=Mux(useDense,dense.io.matrix.group.bits,legacy.io.port.group.bits)
    matrix.io.port.step.valid:=Mux(useDense,dense.io.matrix.step.valid,legacy.io.port.step.valid)
    matrix.io.port.step.bits:=Mux(useDense,dense.io.matrix.step.bits,legacy.io.port.step.bits)
    matrix.io.port.result.ready:=Mux(useDense,dense.io.matrix.result.ready,legacy.io.port.result.ready)
    matrix.io.port.done.ready:=Mux(useDense,dense.io.matrix.done.ready,legacy.io.port.done.ready)
    matrix.io.port.abort:=Mux(useDense,dense.io.matrix.abort,legacy.io.port.abort)
    io.pipelineIssues:=matrix.io.wideSteps;io.pipelineStalls:=matrix.io.stallCycles
    io.resetRequired:=core.io.resetRequired||dense.io.resetRequired||silu.io.resetRequired||matrix.io.resetRequired||legacy.io.resetRequired
  }
}
