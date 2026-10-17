// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class FfnTileInvocation extends Bundle {
  val identity=UInt(32.W);val ng=UInt(16.W);val rows=UInt(8.W);val cols=UInt(8.W)
}

/** Production bounded tile-to-SFU bridge, shared by the resident coordinator.
  * Sealed gate/up tiles 0/1 are consumed through real SRAM ports, passed to the
  * existing owner's one sixteen-lane SFU, and written into tile 2. No DDR
  * stand-in or second SFU. Only the gate operand needs a new 512-bit hold.
  */
class FfnTileSiluBridge(enableMatrixProducerOrder:Boolean=false) extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new FfnTileInvocation));val abort=Input(Bool())
    val tiles=Flipped(new FfnTilePort(enableMatrixProducerOrder));val silu=Flipped(new FfnSiluLoanPort)
    val busy=Output(Bool());val complete=Output(Bool());val resetRequired=Output(Bool())
  })
  val idle::begin::gateRead::gateWait::upRead::upWait::result::seal::releaseGate::releaseUp::retire::drain::locked::Nil=Enum(13)
  val state=RegInit(idle);val call=Reg(new FfnTileInvocation);val index=RegInit(0.U(11.W))
  val gate=Reg(Vec(16,UInt(32.W)));val poison=RegInit(false.B)
  val bad=io.abort || poison || io.tiles.resetRequired || io.silu.resetRequired ||
    (io.tiles.response.valid && io.tiles.response.bits.error) ||
    (io.silu.result.valid && io.silu.result.bits.error)
  val count=(call.rows>>4)*call.cols
  // BEGIN_CANONICAL_TILE_RESPONSE_TAP_V1
  // Observation only: the selected official resident/public21 instance is
  // qualified externally. Producer order is not a numeric-policy proof.
  if(enableMatrixProducerOrder){
    val canonicalTileTap=Wire(new Bundle {
      val valid=Bool();val slot=UInt(2.W);val identity=UInt(32.W)
      val ng=UInt(16.W);val index=UInt(11.W);val rows=UInt(8.W);val cols=UInt(8.W)
      val value=Vec(16,UInt(32.W))
    })
    canonicalTileTap:=0.U.asTypeOf(canonicalTileTap)
    canonicalTileTap.valid:=io.tiles.response.fire && !bad && (state===gateWait || state===upWait)
    when(canonicalTileTap.valid){
      canonicalTileTap.slot:=io.tiles.response.bits.key.slot
      canonicalTileTap.identity:=io.tiles.response.bits.key.identity
      canonicalTileTap.ng:=io.tiles.response.bits.key.ng
      canonicalTileTap.index:=io.tiles.response.bits.key.index
      canonicalTileTap.rows:=call.rows;canonicalTileTap.cols:=call.cols
      canonicalTileTap.value:=io.tiles.response.bits.value
    }
    dontTouch(canonicalTileTap)
  }
  // END_CANONICAL_TILE_RESPONSE_TAP_V1
  io.start.ready:=state===idle && !bad
  io.busy:=state=/=idle && state=/=locked;io.complete:=false.B;io.resetRequired:=poison || bad
  io.tiles.abort:=bad;io.silu.abort:=io.abort || poison
  io.tiles.control.valid:= !bad && (state===begin || state===seal || state===releaseGate || state===releaseUp)
  io.tiles.control.bits.op:=Mux(state===begin,0.U,Mux(state===seal,1.U,2.U))
  io.tiles.control.bits.slot:=Mux(state===releaseGate,0.U,Mux(state===releaseUp,1.U,2.U))
  io.tiles.control.bits.identity:=call.identity;io.tiles.control.bits.ng:=call.ng
  io.tiles.control.bits.rows:=call.rows;io.tiles.control.bits.cols:=call.cols
  io.tiles.control.bits.matrixProducerOrder.foreach(_:=false.B)
  io.tiles.read.valid:= !bad && (state===gateRead || state===upRead)
  io.tiles.read.bits.slot:=Mux(state===gateRead,0.U,1.U)
  io.tiles.read.bits.identity:=call.identity;io.tiles.read.bits.ng:=call.ng;io.tiles.read.bits.index:=index
  io.tiles.response.ready:=bad || state===gateWait || (state===upWait && io.silu.request.ready)
  io.silu.request.valid:= !bad && state===upWait && io.tiles.response.valid
  io.silu.request.bits.gate:=gate;io.silu.request.bits.up:=io.tiles.response.bits.value
  io.tiles.write.valid:= !bad && state===result && io.silu.result.valid
  io.tiles.write.bits.key.slot:=2.U;io.tiles.write.bits.key.identity:=call.identity
  io.tiles.write.bits.key.ng:=call.ng;io.tiles.write.bits.key.index:=index
  io.tiles.write.bits.value:=io.silu.result.bits.value
  io.silu.result.ready:=bad || (state===result && io.tiles.write.ready)
  def same(t:FfnTileState,c:FfnTileInvocation):Bool=t.identity===c.identity && t.ng===c.ng &&
    t.rows===c.rows && t.cols===c.cols && t.expected===(c.rows>>4)*c.cols
  val startShape=io.start.bits.identity=/=0.U && io.start.bits.ng(4,0)===0.U &&
    (io.start.bits.rows===16.U || io.start.bits.rows===128.U) &&
    io.start.bits.cols>0.U && io.start.bits.cols<=160.U && io.start.bits.cols(4,0)===0.U
  val inputsReady=Seq(0,1).map{i=>
    val t=io.tiles.state(i)
    t.live && t.sealedTile && same(t,io.start.bits) && t.produced===t.expected && t.consumed===0.U
  }.reduce(_&&_)
  when(io.start.fire){
    call:=io.start.bits;index:=0.U
    when(startShape && inputsReady && !io.tiles.state(2).live && io.tiles.drained && io.silu.drained){state:=begin}
    .otherwise{poison:=true.B;state:=locked}
  }
  when(io.tiles.control.fire){
    when(state===begin){state:=gateRead}
    when(state===seal){state:=releaseGate}
    when(state===releaseGate){state:=releaseUp}
    when(state===releaseUp){state:=retire}
  }
  when(io.tiles.read.fire){state:=Mux(state===gateRead,gateWait,upWait)}
  when(io.tiles.response.fire && state===gateWait && !bad){gate:=io.tiles.response.bits.value;state:=upRead}
  when(io.silu.request.fire){state:=result}
  when(io.tiles.write.fire){
    when(index+1.U===count){state:=seal}.otherwise{index:=index+1.U;state:=gateRead}
  }
  // A control fire is only acceptance. Observe the bank's validated state
  // on the following cycle before publishing completion.
  when(state===retire && !bad){
    val t=io.tiles.state(2)
    val committed= !io.tiles.state(0).live && !io.tiles.state(1).live &&
      t.live && t.sealedTile && same(t,call) && t.produced===t.expected && t.consumed===0.U &&
      io.tiles.drained && io.silu.drained
    when(committed){io.complete:=true.B;state:=idle}.otherwise{poison:=true.B;state:=drain}
  }
  when(bad){poison:=true.B;state:=Mux(state===idle || state===locked,locked,drain)}
  when((state===drain || bad) && io.tiles.drained && io.silu.drained){state:=locked}
}

