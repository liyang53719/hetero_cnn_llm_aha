// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class DenseTileSumInvocation extends Bundle {
  val identity=UInt(32.W);val ng=UInt(16.W)
  val rows=UInt(8.W);val cols=UInt(8.W)
  val lhsSlot=UInt(2.W);val rhsSlot=UInt(2.W);val outputSlot=UInt(2.W)
}

/** FP32 partial reduction through the already allocated A-bank tile ports and
  * the existing sixteen-lane owner. No arithmetic unit or SRAM is instantiated.
  * One lhs beat is held. Completion seals a resident tile; no DDR bytes or
  * Host result are published by this internal controller.
  */
class DenseTileSumBridge(enableMatrixProducerOrder:Boolean=true) extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new DenseTileSumInvocation));val abort=Input(Bool())
    // The owner arbiter asserts this only after Dense operand/RMW retirement
    // and while all other external tile clients are excluded for this loan.
    val bankGranted=Input(Bool())
    val tiles=Flipped(new FfnTilePort(enableMatrixProducerOrder))
    val vector=Flipped(new FfnSiluLoanPort(enableBinaryAdd=true))
    val busy=Output(Bool());val complete=Output(Bool());val resetRequired=Output(Bool())
  })
  val idle::begin::lhsRead::lhsWait::rhsRead::rhsWait::result::seal::releaseLhs::releaseRhs::retire::drain::locked::Nil=Enum(13)
  val state=RegInit(idle);val call=Reg(new DenseTileSumInvocation)
  val index=RegInit(0.U(11.W));val lhs=Reg(Vec(16,UInt(32.W)))
  val poison=RegInit(false.B);val inflight=RegInit(false.B)
  // Never feed the current arithmetic result error back into vector.abort.
  // That response must transfer on its error-result handshake; poison is
  // registered for the next edge. resetRequired from the loan is registered.
  val loanAbort=io.abort || poison || io.tiles.resetRequired || io.vector.resetRequired ||
    (io.tiles.response.valid && io.tiles.response.bits.error)
  val unexpected=io.vector.result.valid && !inflight
  val bad=loanAbort || unexpected || (io.vector.result.valid &&
    (io.vector.result.bits.error || !io.vector.result.bits.value.map(TensorMath.finite).reduce(_&&_)))
  val count=(call.rows>>4)*call.cols
  io.start.ready:=state===idle && !bad && io.bankGranted && io.tiles.drained && io.vector.drained
  io.busy:=state=/=idle && state=/=locked;io.complete:=false.B
  // Expose registered poison for safe outer arbitration. Immediate bad still
  // gates every write/complete locally; it must not feed its own abort wire.
  io.resetRequired:=poison
  io.tiles.abort:=bad;io.vector.abort:=loanAbort
  io.tiles.control.valid:= !bad && (state===begin || state===seal || state===releaseLhs || state===releaseRhs)
  io.tiles.control.bits.op:=Mux(state===begin,0.U,Mux(state===seal,1.U,2.U))
  io.tiles.control.bits.slot:=Mux(state===releaseLhs,call.lhsSlot,Mux(state===releaseRhs,call.rhsSlot,call.outputSlot))
  io.tiles.control.bits.identity:=call.identity;io.tiles.control.bits.ng:=call.ng
  io.tiles.control.bits.rows:=call.rows;io.tiles.control.bits.cols:=call.cols
  io.tiles.control.bits.matrixProducerOrder.foreach(_:=false.B)
  io.tiles.read.valid:= !bad && (state===lhsRead || state===rhsRead)
  io.tiles.read.bits.slot:=Mux(state===lhsRead,call.lhsSlot,call.rhsSlot)
  io.tiles.read.bits.identity:=call.identity;io.tiles.read.bits.ng:=call.ng;io.tiles.read.bits.index:=index
  io.tiles.response.ready:=bad || state===lhsWait || (state===rhsWait && io.vector.request.ready)
  io.vector.request.valid:= !bad && state===rhsWait && io.tiles.response.valid
  io.vector.request.bits.gate:=lhs;io.vector.request.bits.up:=io.tiles.response.bits.value
  io.vector.request.bits.binaryAdd.get:=true.B
  io.tiles.write.valid:= !bad && state===result && io.vector.result.valid
  io.tiles.write.bits.key.slot:=call.outputSlot
  io.tiles.write.bits.key.identity:=call.identity;io.tiles.write.bits.key.ng:=call.ng
  io.tiles.write.bits.key.index:=index;io.tiles.write.bits.value:=io.vector.result.bits.value
  io.vector.result.ready:=bad || (state===result && io.tiles.write.ready)
  def same(t:FfnTileState,c:DenseTileSumInvocation):Bool=t.identity===c.identity && t.ng===c.ng &&
    t.rows===c.rows && t.cols===c.cols && t.expected===(c.rows>>4)*c.cols
  val s=io.start.bits
  val startShape=s.identity=/=0.U && s.ng(4,0)===0.U && (s.rows===16.U || s.rows===128.U) &&
    s.cols>0.U && s.cols<=160.U && s.cols(4,0)===0.U &&
    s.lhsSlot<3.U && s.rhsSlot<3.U && s.outputSlot<3.U &&
    s.lhsSlot=/=s.rhsSlot && s.lhsSlot=/=s.outputSlot && s.rhsSlot=/=s.outputSlot
  val inputsReady=Seq(s.lhsSlot,s.rhsSlot).map { slot =>
    val t=io.tiles.state(slot)
    t.live && t.sealedTile && same(t,s) && t.produced===t.expected && t.consumed===0.U
  }.reduce(_&&_)
  when(io.start.fire){
    call:=s;index:=0.U
    when(startShape && inputsReady && !io.tiles.state(s.outputSlot).live && !inflight){state:=begin}
      .otherwise{poison:=true.B;state:=locked}
  }
  when(io.tiles.control.fire){
    when(state===begin){state:=lhsRead}
    when(state===seal){state:=releaseLhs}
    when(state===releaseLhs){state:=releaseRhs}
    when(state===releaseRhs){state:=retire}
  }
  when(io.tiles.read.fire){state:=Mux(state===lhsRead,lhsWait,rhsWait)}
  when(io.tiles.response.fire && state===lhsWait && !bad){lhs:=io.tiles.response.bits.value;state:=rhsRead}
  when(io.vector.request.fire){inflight:=true.B;state:=result}
  when(io.vector.result.fire){inflight:=false.B}
  when(io.tiles.write.fire){
    when(index+1.U===count){state:=seal}.otherwise{index:=index+1.U;state:=lhsRead}
  }
  when(state===retire && !bad){
    val t=io.tiles.state(call.outputSlot)
    val committed= !io.tiles.state(call.lhsSlot).live && !io.tiles.state(call.rhsSlot).live &&
      t.live && t.sealedTile && same(t,call) && t.produced===t.expected && t.consumed===0.U &&
      io.tiles.drained && io.vector.drained && !inflight
    when(committed){io.complete:=true.B;state:=idle}.otherwise{poison:=true.B;state:=drain}
  }
  when(bad){poison:=true.B;state:=Mux(state===idle || state===locked,locked,drain)}
  // A local abort does not erase an accepted arithmetic obligation. The
  // loan's explicit drain fence includes its internal poisoned-result retire.
  when((state===drain || bad) && io.vector.drained){inflight:=false.B}
  when((state===drain || bad) && io.tiles.drained && io.vector.drained && !inflight){state:=locked}
}

