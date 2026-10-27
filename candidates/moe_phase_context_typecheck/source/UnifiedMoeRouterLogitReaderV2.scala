// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class UnifiedMoeRouterLogitBeatV2 extends Bundle {
  val transactionId=UInt(64.W);val ownerSequence=UInt(32.W)
  val token=UInt(7.W);val beat=UInt(3.W);val data=UInt(512.W)
}
class UnifiedMoeRouterReadResultV2 extends Bundle {
  val transactionId=UInt(64.W);val ownerSequence=UInt(32.W)
  val readBytes=UInt(32.W);val status=UInt(8.W);val drained=Bool()
}
/** Original Dense committed BF16 DDR -> 8 real 64B beats per token. This does
  * NOT declare a probability/route result; the numeric owner must receive all
  * 256 logits, compute all 256 FP32 probabilities, and only then select top8.
  * One 512-bit held beat, no Matrix/Scalar/vector/TopK instance or second top.
  * Parent's unique memory arbiter assigns physical transport sequence; local
  * tag remains a client obligation. Source/allocator identity is private.
  * readResult is only read-stream retirement, NEVER a full router/block fence.
  */
class UnifiedMoeRouterLogitReaderV2 extends Module {
  val io=IO(new Bundle {
    val commit=Flipped(Decoupled(new UnifiedMoeRouterLogitCommitV2))
    val sourceResetRequired=Input(Bool());val memoryResetRequired=Input(Bool())
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val logits=Decoupled(new UnifiedMoeRouterLogitBeatV2)
    val done=Decoupled(new UnifiedMoeRouterReadResultV2)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
  })
  val idle::offer::waiting::emit::report::locked::Nil=Enum(6)
  val state=RegInit(idle);val command=Reg(new UnifiedMoeRouterDenseCommandV2)
  val token=Reg(UInt(7.W));val beat=Reg(UInt(3.W));val data=Reg(UInt(512.W))
  val sequence=RegInit(0.U(64.W));val pendingTag=Reg(UInt(64.W))
  val out=Reg(new UnifiedMoeRouterReadResultV2)
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknown=io.response.valid && state=/=waiting
  when(unknown || io.memoryResetRequired){poison:=true.B;quarantine:=true.B}
  when(io.sourceResetRequired){poison:=true.B}
  val fault=poison||quarantine||unknown||io.memoryResetRequired||io.sourceResetRequired
  io.resetRequired:=fault;io.contextReserved:=state=/=idle || io.commit.valid
  io.commit.ready:=state===idle && !fault
  io.memory.valid:=state===offer // held offer never disappears after a fault
  io.memory.bits.address:=command.output+(token.pad(64)<<9)+(beat.pad(64)<<6)
  io.memory.bits.write:=false.B;io.memory.bits.data:=0.U;io.memory.bits.mask:=0.U;io.memory.bits.tag:=sequence
  io.response.ready:=state===waiting && !quarantine && !io.memoryResetRequired
  io.logits.valid:=state===emit;io.logits.bits.transactionId:=command.context.transactionId
  io.logits.bits.ownerSequence:=command.ownerSequence;io.logits.bits.token:=token
  io.logits.bits.beat:=beat;io.logits.bits.data:=data
  io.done.valid:=state===report;io.done.bits:=out
  val (decoded,shapeLegal)=UnifiedMoeRouterDenseCommandV2.decode(io.commit.bits.command)
  when(io.commit.fire){
    command:=io.commit.bits.command;token:=0.U;beat:=0.U
    out:=0.U.asTypeOf(new UnifiedMoeRouterReadResultV2)
    out.transactionId:=io.commit.bits.command.context.transactionId
    out.ownerSequence:=io.commit.bits.command.ownerSequence
    val good=shapeLegal && io.commit.bits.successfulWriteback &&
      io.commit.bits.result.status===Status.Ok.U &&
      io.commit.bits.result.tag===decoded.tag && io.commit.bits.result.writeBytes===decoded.writeBytes &&
      sequence.pad(65)+(io.commit.bits.command.context.tokens.pad(65)<<3)<=(BigInt(1)<<64).U-1.U
    when(good){state:=offer}.otherwise{out.status:=Status.Dependency.U;out.drained:=true.B;state:=report}
  }
  when(io.memory.fire){pendingTag:=sequence;sequence:=sequence+1.U;state:=waiting}
  when(io.response.fire){
    when(io.response.bits.tag=/=pendingTag || io.response.bits.error){
      poison:=true.B;quarantine:=true.B // no zero data, fake completion or new credit
    }.otherwise{data:=io.response.bits.data;out.readBytes:=out.readBytes+64.U;state:=emit}
  }
  when(io.logits.fire){
    when(fault){out.status:=Status.Dependency.U;out.drained:= !quarantine && !unknown && !io.memoryResetRequired;state:=report}
    .elsewhen(beat===7.U && token.pad(16)+1.U===command.context.tokens){out.status:=Status.Ok.U;out.drained:=true.B;state:=report}
    .otherwise{when(beat===7.U){beat:=0.U;token:=token+1.U}.otherwise{beat:=beat+1.U};state:=offer}
  }
  when(io.done.fire){state:=Mux(fault,locked,idle)}
  // A never-returning or quarantined transport obligation waits for external
  // isolation/watchdog. readBytes is received data, not a DDR write commit.
}
