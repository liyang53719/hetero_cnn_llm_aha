// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal typed group, after the public Host descriptor preflight. */
class FfnResidentRequest extends Bundle {
  val gate=new QwenOwnerJob;val up=new QwenOwnerJob;val act=new QwenOwnerJob
  val identity=UInt(32.W)
}
class FfnResidentPort extends Bundle {
  val request=Flipped(Decoupled(new FfnResidentRequest));val result=Decoupled(new QwenOwnerResult)
  val abort=Input(Bool());val busy=Output(Bool());val resetRequired=Output(Bool())
}

/** Serial owner of the original Matrix, banks, sixteen SFU lanes and iDMA.
  * There is no tensor payload storage here. Gate/Up/Act occupy the three
  * existing tile slots. Act always reaches DDR before the next N group.
  * Handoff is a full no-request cycle: the retained iDMA changes its window
  * and flushes before any request for the next producer can be accepted.
  */
class FfnResidentCoordinator extends Module {
  val io=IO(new Bundle {
    val observation=Output(Valid(new FfnResidentObservation))
    val group=new FfnResidentPort
    val window=Flipped(new FfnWindowPort(enableCounters=true))
    val drain=Flipped(new FfnDrainPort)
    val tiles=Flipped(new FfnTilePort(enableMatrixProducerOrder=true))
    val silu=Flipped(new FfnSiluLoanPort)
    val handoff=Output(Valid(new QwenOwnerJob))
  })
  val idle::gateFlush::gateIssue::gateWait::upFlush::upIssue::upWait::siluIssue::siluWait::actFlush::actIssue::actWait::invalidate::retire::draining::reply::locked::Nil=Enum(17)
  val state=RegInit(idle);val call=Reg(new FfnResidentRequest);val ng=RegInit(0.U(16.W))
  val poison=RegInit(false.B);val status=RegInit(0.U(8.W))
  val cycles=RegInit(0.U(64.W));val bytes=RegInit(0.U(64.W))
  val useful=RegInit(0.U(64.W));val executed=RegInit(0.U(64.W))
  val result=Reg(new QwenOwnerResult)
  val bridge=Module(new FfnTileSiluBridge(enableMatrixProducerOrder=true))
  io.tiles<>bridge.io.tiles;io.silu<>bridge.io.silu
  val abort=io.group.abort || poison
  val serviceError=io.window.resetRequired || io.drain.resetRequired || bridge.io.resetRequired
  val bad=abort || serviceError
  val live=state=/=idle && state=/=reply && state=/=locked
  io.observation:=bridge.io.observation
  io.observation.valid:=bridge.io.observation.valid && state===siluWait && !bad
  io.observation.bits.gateTag:=call.gate.tag
  io.observation.bits.upTag:=call.up.tag
  io.observation.bits.actTag:=call.act.tag
  val expected=(call.gate.m>>4)*160.U
  val windowJob=Mux(state===upFlush || state===upIssue || state===upWait,call.up,call.gate)
  val up=state===upIssue || state===upWait
  io.group.request.ready:=state===idle && !bad && !io.window.busy && !io.drain.busy &&
    io.tiles.drained && !io.tiles.leased && io.silu.drained
  io.group.busy:=state=/=idle && state=/=locked
  io.group.resetRequired:=poison || io.group.abort || serviceError
  io.group.result.valid:=state===reply;io.group.result.bits:=result
  io.handoff.valid:= !bad && (state===gateFlush || state===upFlush || state===actFlush)
  io.handoff.bits:=Mux(state===actFlush,call.act,windowJob)
  io.window.request.valid:= !bad && (state===gateIssue || state===upIssue)
  io.window.request.bits.job:=windowJob;io.window.request.bits.identity:=call.identity
  io.window.request.bits.ng:=ng;io.window.request.bits.cols:=160.U
  io.window.request.bits.slot:=Mux(up,1.U,0.U);io.window.request.bits.reuseA:=up || ng=/=0.U
  io.window.result.ready:=state===gateWait || state===upWait || state===draining
  io.window.invalidateLease:=abort || state===invalidate || state===retire
  io.drain.request.valid:= !bad && state===actIssue
  io.drain.request.bits.job:=call.act;io.drain.request.bits.identity:=call.identity
  io.drain.request.bits.ng:=ng;io.drain.request.bits.cols:=160.U
  io.drain.result.ready:=state===actWait || state===draining
  io.drain.abort:=abort
  bridge.io.start.valid:= !bad && state===siluIssue
  bridge.io.start.bits.identity:=call.identity;bridge.io.start.bits.ng:=ng
  bridge.io.start.bits.rows:=call.gate.m;bridge.io.start.bits.cols:=160.U
  bridge.io.abort:=abort
  def denseShape(j:QwenOwnerJob):Bool=j.kind===QwenOwnerKind.Dense.U &&
    (j.m===16.U || j.m===128.U) && j.n===8960.U && j.k===1536.U &&
    j.weightBf16 && !j.activationBf16 && !j.outputBf16 && j.writeBytes===j.m.pad(64)*8960.U*4.U
  def shape(r:FfnResidentRequest):Bool=denseShape(r.gate) && denseShape(r.up) &&
    r.identity=/=0.U && r.up.m===r.gate.m && r.up.a===r.gate.a &&
    r.act.kind===QwenOwnerKind.Activation.U && r.act.m===r.gate.m && r.act.n===8960.U && r.act.k===8960.U &&
    !r.act.weightBf16 && !r.act.activationBf16 && !r.act.outputBf16 &&
    r.act.a===r.gate.dst && r.act.b===r.up.dst && r.act.writeBytes===r.gate.writeBytes
  def fail(code:UInt):Unit={poison:=true.B;status:=Mux(code===0.U,Status.Protocol.U,code);state:=draining}
  when(io.group.request.fire){
    call:=io.group.request.bits;ng:=0.U;cycles:=0.U;bytes:=0.U;useful:=0.U;executed:=0.U;status:=0.U
    when(shape(io.group.request.bits)){state:=gateFlush}.otherwise{fail(Status.Malformed.U)}
  }
  when(live){cycles:=cycles+1.U}
  when(state===gateFlush && !bad){state:=gateIssue}
  when(state===upFlush && !bad){state:=upIssue}
  when(state===actFlush && !bad){state:=actIssue}
  when(io.window.request.fire){state:=Mux(up,upWait,gateWait)}
  // Each underlying terminal is accepted once, including an error terminal
  // during drain. Counters describe real accepted work even when unpublished.
  when(io.window.result.fire){useful:=useful+io.window.result.bits.usefulMacs.get;executed:=executed+io.window.result.bits.executedMacs.get}
  when(io.drain.result.fire){bytes:=bytes+io.drain.result.bits.ddrWriteBytes;useful:=useful+io.drain.result.bits.usefulMacs;executed:=executed+io.drain.result.bits.executedMacs}
  when(io.window.result.fire && (state===gateWait || state===upWait)){
    val r=io.window.result.bits
    val exact=r.tag===windowJob.tag && r.identity===call.identity && r.ng===ng &&
      r.cols===160.U && r.slot===Mux(up,1.U,0.U) && r.rows===call.gate.m &&
      r.committed && r.producedBeats===expected && r.ddrWriteBytes===0.U && io.window.leaseValid
    when(r.status=/=0.U || !exact || bad){fail(r.status)}.otherwise{
      state:=Mux(up,siluIssue,upFlush)
    }
  }
  when(bridge.io.start.fire){state:=siluWait}
  when(state===siluWait && bridge.io.complete && !bad){state:=actFlush}
  when(io.drain.request.fire){state:=actWait}
  when(io.drain.result.fire && state===actWait){
    val r=io.drain.result.bits
    val exact=r.tag===call.act.tag && r.identity===call.identity && r.ng===ng && r.rows===call.gate.m &&
      r.cols===160.U && r.committed && r.consumedBeats===expected &&
      r.ddrWriteBytes===call.gate.m.pad(64)*160.U*4.U && !io.tiles.leased && io.tiles.drained
    when(r.status=/=0.U || !exact || bad){fail(r.status)}.otherwise{
      when(ng+160.U===8960.U){
        when(bytes+r.ddrWriteBytes===call.act.writeBytes){state:=invalidate}.otherwise{fail(Status.Protocol.U)}
      }.otherwise{ng:=ng+160.U;state:=gateFlush}
    }
  }
  when(state===invalidate && !bad){state:=retire}
  when(state===retire && !bad){
    when(!io.window.leaseValid && !io.window.busy && !io.drain.busy && !io.tiles.leased && io.tiles.drained && io.silu.drained){
      result.tag:=call.act.tag;result.status:=0.U;result.writeBytes:=bytes
      result.cycles:=cycles+1.U;result.usefulMacs:=useful;result.executedMacs:=executed;state:=reply
    }
  }
  val explicitError=(io.window.result.fire && io.window.result.bits.status=/=0.U) ||
    (io.drain.result.fire && io.drain.result.bits.status=/=0.U)
  when(bad && live && state=/=draining && !explicitError){fail(Status.Protocol.U)}
  // A late abort revokes a held success through a sticky sideband without
  // mutating its Decoupled payload, including a one-cycle external pulse.
  when(io.group.abort || serviceError){poison:=true.B}
  // Accepted memory, Matrix, bank-RMW and SFU paths retire before failure.
  // No successful Host publication is possible from this terminal result.
  when(state===draining && !io.window.busy && !io.drain.busy && io.tiles.drained && io.silu.drained && !bridge.io.busy){
    result.tag:=call.act.tag;result.status:=Mux(status===0.U,Status.Protocol.U,status)
    result.writeBytes:=bytes;result.cycles:=cycles+1.U;result.usefulMacs:=useful;result.executedMacs:=executed;state:=reply
  }
  when(io.group.result.fire){state:=Mux(poison || bad,locked,idle)}
}
