// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal, decoded owner job. Never a Host opcode or on-DDR encoding. */
object QwenOwnerKind { val Norm=0; val Dense=1; val Bias=2; val Rope=3; val Attention=4; val Add=5; val Activation=6; val KvAppend=7 }
class QwenOwnerJob extends Bundle {
  val kind=UInt(3.W); val m=UInt(16.W); val n=UInt(16.W); val k=UInt(16.W)
  val a=UInt(64.W); val b=UInt(64.W); val c=UInt(64.W); val dst=UInt(64.W)
  val writeBytes=UInt(64.W); val tag=UInt(32.W)
}
class QwenOwnerResult extends Bundle {
  val tag=UInt(32.W); val status=UInt(8.W); val writeBytes=UInt(64.W)
  val cycles=UInt(64.W); val usefulMacs=UInt(64.W); val executedMacs=UInt(64.W)
}
/** No block launch is exposed. One decoded owner operation per transaction;
  * the arithmetic implementation must return instead of advancing to a phase.
  */
class QwenOwnerKernel(s:QwenBlockShape) extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob)); val done=Decoupled(new QwenOwnerResult)
    val memory=Decoupled(new MemoryRequest); val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool())
  })
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
}
