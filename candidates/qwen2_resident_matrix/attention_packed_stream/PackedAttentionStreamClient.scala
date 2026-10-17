// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class PackedAttentionGroup extends Bundle {
  val tag=UInt(32.W);val pv=Bool();val count=UInt(8.W)
}
class PackedAttentionOperands extends Bundle {
  val index=UInt(8.W);val a=Vec(16,UInt(16.W));val b=Vec(256,UInt(16.W))
}
/** Proposed default-off control only: no arithmetic, operands or tile registers.
  * Consumer must check selected arithmetic and commit writes before result.ready.
  * stepsDrained MUST connect to the matching service's optional status output.
  * Operational abort drains accepted work; reset is a global recovery action.
  */
class PackedAttentionStreamClient(enabled:Boolean=false) extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new PackedAttentionGroup))
    val operands=Flipped(Decoupled(new PackedAttentionOperands))
    val result=Decoupled(new MatrixStreamResult)
    val completion=Decoupled(new MatrixStreamDone)
    val port=new MatrixStreamPort
    val pause=Input(Bool());val stepsDrained=Input(Bool());val pauseGranted=Output(Bool())
    val abort=Input(Bool());val resetRequired=Output(Bool())
    val successAccepted=Output(Bool())
  })
  io.start.ready:=false.B;io.operands.ready:=false.B
  io.result.valid:=false.B;io.result.bits:=io.port.result.bits
  io.completion.valid:=false.B;io.completion.bits:=0.U.asTypeOf(new MatrixStreamDone)
  io.port.group.valid:=false.B;io.port.group.bits:=0.U.asTypeOf(new MatrixStreamGroup)
  io.port.step.valid:=false.B;io.port.step.bits:=0.U.asTypeOf(new MatrixStreamStep)
  io.port.result.ready:=false.B;io.port.done.ready:=false.B;io.port.abort:=false.B
  io.pauseGranted:=false.B;io.resetRequired:=false.B
  io.successAccepted:=false.B
  if(enabled){
    val idle::opening::issuing::awaitResult::awaitDone::draining::reply::locked::Nil=Enum(8)
    val state=RegInit(idle)
    val descriptor=Reg(new PackedAttentionGroup) // 41 control bits
    val index=RegInit(0.U(8.W));val poison=RegInit(false.B)
    val finalIndex=Mux(descriptor.pv,descriptor.count-1.U,7.U)
    val active=state===issuing||state===awaitResult||state===awaitDone||state===draining
    val badResult=io.port.result.bits.context=/=0.U|| !io.port.result.bits.last||io.port.result.bits.error
    val matchingDone=io.port.done.bits.tag===descriptor.tag
    io.resetRequired:=poison
    io.successAccepted:=io.completion.fire && !io.completion.bits.error
    io.start.ready:=state===idle && !io.abort
    io.port.group.valid:=state===opening && !io.abort
    io.port.group.bits.tag:=descriptor.tag
    io.port.group.bits.opcode:=Mux(descriptor.pv,0x24.U,0x23.U)
    io.port.group.bits.sliceMask:=Mux(descriptor.pv,0x0f.U,0xff.U)
    val canOffer=state===issuing && !io.pause && !io.abort && !poison && !io.port.result.valid && !io.port.done.valid
    val legalIndex=io.operands.bits.index===index
    io.port.step.valid:=canOffer && io.operands.valid && legalIndex
    io.port.step.bits.a:=io.operands.bits.a;io.port.step.bits.b:=io.operands.bits.b
    io.port.step.bits.context:=0.U;io.port.step.bits.clear:=index===0.U
    io.port.step.bits.last:=index===finalIndex;io.port.step.bits.finish:=index===finalIndex
    io.port.step.bits.emit:=index===finalIndex
    io.operands.ready:=canOffer && Mux(legalIndex,io.port.step.ready,true.B)
    io.pauseGranted:=state===issuing && io.pause && io.stepsDrained && !io.abort && !poison && !io.port.result.valid && !io.port.done.valid
    // No copy: consumer sees the physical FIFO head for its complete lifetime.
    io.result.valid:=state===awaitResult && io.port.result.valid && !badResult && !io.abort && !poison
    io.port.result.ready:=state===draining || (state===awaitResult && (badResult||io.result.ready) && !io.abort)
    io.port.done.ready:=(state===awaitDone||state===draining) && matchingDone
    io.port.abort:=state===draining || (active && io.abort)
    io.completion.valid:=state===reply;io.completion.bits.tag:=descriptor.tag;io.completion.bits.error:=poison||io.abort
    when(io.start.fire){
      descriptor:=io.start.bits;index:=0.U
      val legal=io.start.bits.tag=/=0.U && io.start.bits.count=/=0.U &&
        Mux(io.start.bits.pv,io.start.bits.count<=128.U,io.start.bits.count<=16.U)
      when(legal){state:=opening}.otherwise{poison:=true.B;state:=reply}
    }
    when(io.port.group.fire){state:=issuing}
    when(io.operands.fire){
      when(!legalIndex){poison:=true.B;state:=draining}
      .elsewhen(index===finalIndex){state:=awaitResult}
      .otherwise{index:=index+1.U}
    }
    when(io.port.result.fire && state===awaitResult){
      when(badResult){poison:=true.B;state:=draining}.otherwise{state:=awaitDone}
    }
    when(io.port.done.fire){
      when(io.port.done.bits.error){poison:=true.B}
      state:=reply
    }
    when(io.completion.fire){state:=Mux(poison||io.abort,locked,idle)}
    // Decoupled completion is cancellable until ACK; abort upgrades error.
    when(state===reply && io.abort){poison:=true.B}
    // Unexpected/foreign terminal signals never retire an unrelated tag.
    when(active && ((io.port.result.valid && state=/=awaitResult && state=/=draining) ||
      (io.port.done.valid && (!matchingDone || (state=/=awaitDone && state=/=draining))))){poison:=true.B;state:=Mux(io.port.done.fire,reply,draining)}
    when(io.abort && state=/=idle && state=/=reply && state=/=locked){
      poison:=true.B;state:=Mux(state===opening||io.port.done.fire,reply,draining)
    }
  }
}
