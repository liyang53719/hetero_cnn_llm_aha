// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

class FfnTileInvocation extends Bundle {
  val identity=UInt(32.W);val ng=UInt(16.W);val rows=UInt(8.W);val cols=UInt(8.W)
}

/** Bounded source harness controller, NOT production Host FFN dispatch.
  * Sealed gate/up tiles 0/1 are consumed through real SRAM ports, passed to the
  * existing owner's one sixteen-lane SFU, and written into tile 2. No DDR
  * stand-in or second SFU. Only the gate operand needs a new 512-bit hold.
  */
class FfnTileSiluBridge extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new FfnTileInvocation));val abort=Input(Bool())
    val tiles=Flipped(new FfnTilePort);val silu=Flipped(new FfnSiluLoanPort)
    val busy=Output(Bool());val complete=Output(Bool());val resetRequired=Output(Bool())
  })
  val idle::begin::gateRead::gateWait::upRead::upWait::result::seal::releaseGate::releaseUp::retire::drain::locked::Nil=Enum(13)
  val state=RegInit(idle);val call=Reg(new FfnTileInvocation);val index=RegInit(0.U(11.W))
  val gate=Reg(Vec(16,UInt(32.W)));val poison=RegInit(false.B)
  val bad=io.abort || poison || io.tiles.resetRequired || io.silu.resetRequired ||
    (io.tiles.response.valid && io.tiles.response.bits.error) ||
    (io.silu.result.valid && io.silu.result.bits.error)
  val count=(call.rows>>4)*call.cols
  io.start.ready:=state===idle && !bad
  io.busy:=state=/=idle && state=/=locked;io.complete:=false.B;io.resetRequired:=poison || bad
  io.tiles.abort:=bad;io.silu.abort:=bad
  io.tiles.control.valid:= !bad && (state===begin || state===seal || state===releaseGate || state===releaseUp)
  io.tiles.control.bits.op:=Mux(state===begin,0.U,Mux(state===seal,1.U,2.U))
  io.tiles.control.bits.slot:=Mux(state===releaseGate,0.U,Mux(state===releaseUp,1.U,2.U))
  io.tiles.control.bits.identity:=call.identity;io.tiles.control.bits.ng:=call.ng
  io.tiles.control.bits.rows:=call.rows;io.tiles.control.bits.cols:=call.cols
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

/** Only the bank service + actual ScheduledSiluOwner loan + bridge are
  * elaborated here. External service access is for preparing/reading tiles;
  * bridge takes exclusive service ownership from start through drain.
  */
class FfnTileSiluHarness extends Module {
  val io=IO(new Bundle {
    val tiles=new FfnTilePort;val start=Flipped(Decoupled(new FfnTileInvocation))
    val complete=Output(Bool());val bridgeBusy=Output(Bool());val resetRequired=Output(Bool())
  })
  val banks=Module(new TransposedDownDenseBanks(enableFfnTiles=true))
  val owner=Module(new ScheduledSiluOwner(enableTileLoan=true))
  val bridge=Module(new FfnTileSiluBridge)
  val route=bridge.io.busy
  banks.io.tileEnable.get:=true.B
  banks.io.zero.valid:=false.B;banks.io.zero.bits:=0.U
  banks.io.activation.valid:=false.B;banks.io.activation.bits:=0.U.asTypeOf(new TransposedDownActivationLoad)
  banks.io.weight.valid:=false.B;banks.io.weight.bits:=0.U.asTypeOf(new TransposedDownWeightLoad)
  banks.io.read.valid:=false.B;banks.io.read.bits:=0.U.asTypeOf(new TransposedDownOperandRead)
  val p=banks.io.tiles.get;val b=bridge.io.tiles
  p.control.valid:=Mux(route,b.control.valid,io.tiles.control.valid && !io.start.valid)
  p.control.bits:=Mux(route,b.control.bits,io.tiles.control.bits)
  b.control.ready:=route && p.control.ready;io.tiles.control.ready:= !route && !io.start.valid && p.control.ready
  p.write.valid:=Mux(route,b.write.valid,io.tiles.write.valid && !io.start.valid);p.write.bits:=Mux(route,b.write.bits,io.tiles.write.bits)
  b.write.ready:=route && p.write.ready;io.tiles.write.ready:= !route && !io.start.valid && p.write.ready
  p.read.valid:=Mux(route,b.read.valid,io.tiles.read.valid && !io.start.valid);p.read.bits:=Mux(route,b.read.bits,io.tiles.read.bits)
  b.read.ready:=route && p.read.ready;io.tiles.read.ready:= !route && !io.start.valid && p.read.ready
  p.response.ready:=Mux(route,b.response.ready,io.tiles.response.ready)
  b.response.valid:=route && p.response.valid;b.response.bits:=p.response.bits
  io.tiles.response.valid:= !route && p.response.valid;io.tiles.response.bits:=p.response.bits
  p.abort:=io.tiles.abort || b.abort
  b.busy:=p.busy;b.leased:=p.leased;b.drained:=p.drained;b.resetRequired:=p.resetRequired;b.state:=p.state
  io.tiles.busy:=p.busy;io.tiles.leased:=p.leased;io.tiles.drained:=p.drained;io.tiles.resetRequired:=p.resetRequired;io.tiles.state:=p.state
  bridge.io.start.valid:=io.start.valid && p.drained;bridge.io.start.bits:=io.start.bits
  io.start.ready:=bridge.io.start.ready && p.drained
  bridge.io.abort:=io.tiles.abort;owner.io.loan.get<>bridge.io.silu
  owner.io.job.valid:=false.B;owner.io.job.bits:=0.U.asTypeOf(new QwenOwnerJob)
  owner.io.done.ready:=true.B;owner.io.memory.ready:=false.B
  owner.io.response.valid:=false.B;owner.io.response.bits:=0.U.asTypeOf(new MemoryResponse)
  io.complete:=bridge.io.complete && !p.resetRequired && !owner.io.resetRequired
  io.bridgeBusy:=bridge.io.busy;io.resetRequired:=p.resetRequired || owner.io.resetRequired || bridge.io.resetRequired
}

object FfnTileElaboration extends App {
  require(args.length==1)
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out));Files.createDirectories(out)
  def emit(name:String,module: => RawModule):Unit=Files.writeString(out.resolve(name+".fir"),ChiselStage.emitCHIRRTL(module))
  emit("banks_baseline",new TransposedDownDenseBanksBaseline)
  emit("banks_disabled",new TransposedDownDenseBanks)
  emit("banks_enabled",new TransposedDownDenseBanks(enableFfnTiles=true))
  emit("owner_baseline",new TransposedDenseDownOwnerBaseline)
  emit("owner_disabled",new TransposedDenseDownOwner)
  emit("owner_enabled",new TransposedDenseDownOwner(enableFfnTiles=true))
  emit("silu_baseline",new VectorSiluOwnerBaseline)
  emit("silu_disabled",new VectorSiluOwner)
  emit("silu_enabled",new VectorSiluOwner(enableTileLoan=true))
  emit("tile_silu_harness",new FfnTileSiluHarness)
  println("PASS: typed physical tile ports and existing sixteen-lane SFU source/frontend only; no RTL execution")
}
