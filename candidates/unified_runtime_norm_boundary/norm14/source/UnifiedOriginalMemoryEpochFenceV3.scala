// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** One ORIGINAL shared arbiter and one physical transport sequence for all
  * fixed eight clients. This is a component of the common resource fabric,
  * not a second arbiter to put in series with or beside its existing instance.
  * Parent replaces that instance with this wrapper at integration.
  *
  * Wrong/unsolicited physical responses never reach the original arbiter's
  * error-to-current-owner path. They quarantine real debt until coordinated
  * transport isolation/reset. Known matching error responses still retire as
  * errors, never as successful zero data. Minimum response latency is one edge.
  * Sequence survives every job, but not reset: a reset MUST isolate/reset the
  * transport too. There is no host-set epoch-safe/drained Boolean.
  */
class UnifiedOriginalMemoryEpochFenceV3 extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Vec(8,Decoupled(new MemoryRequest)))
    val response=Vec(8,Decoupled(new MemoryResponse))
    val memory=Decoupled(new MemoryRequest)
    val returned=Flipped(Decoupled(new MemoryResponse))
    val parentPoison=Input(Bool()) // registered; stops new jobs, not held obligations
    val resetRequired=Output(Bool());val quarantined=Output(Bool())
    val resourcesDrained=Output(Bool())
    val accepted=Output(Vec(8,UInt(64.W)));val retired=Output(Vec(8,UInt(64.W)))
  })
  val arb=Module(new SharedMemoryArbiter(8))
  val pending=RegInit(false.B);val physicalTag=Reg(UInt(64.W))
  val quarantine=RegInit(false.B)
  val unknownNow=io.returned.valid && (!pending || io.returned.bits.tag=/=physicalTag)
  val counterPoison=RegInit(false.B)
  val counterExhausted=arb.io.accepted.map(_.andR).reduce(_||_)
  when(counterExhausted){counterPoison:=true.B}
  // Client offers already held must not be retracted on late poison. The
  // upstream scheduler must not create any new job after parentPoison.
  for(i<-0 until 8){
    val offer=HeldDecoupledOffer(io.request(i).valid,arb.io.requests(i).ready,
      quarantine || unknownNow || counterExhausted || counterPoison || arb.io.resetRequired)
    arb.io.requests(i).valid:=offer.valid;arb.io.requests(i).bits:=io.request(i).bits
    io.request(i).ready:=offer.valid && arb.io.requests(i).ready
    io.response(i)<>arb.io.responses(i)
  }
  io.memory<>arb.io.memory
  val expected=pending && io.returned.bits.tag===physicalTag
  arb.io.response.valid:=io.returned.valid && expected && !quarantine
  arb.io.response.bits:=io.returned.bits
  io.returned.ready:=arb.io.response.ready && expected && !quarantine
  when(io.memory.fire){
    assert(!pending,"original one-outstanding transport")
    pending:=true.B;physicalTag:=io.memory.bits.tag
  }
  when(io.returned.fire){pending:=false.B}
  when(unknownNow){quarantine:=true.B}
  io.accepted:=arb.io.accepted;io.retired:=arb.io.returned
  val equal=arb.io.accepted.zip(arb.io.returned).map{case(a,b)=>a===b}.reduce(_&&_)
  val quiet= !io.request.map(_.valid).reduce(_||_) && !io.response.map(_.valid).reduce(_||_) &&
    !io.memory.valid && !io.returned.valid && !pending
  io.resourcesDrained:=quiet && equal && !quarantine && !unknownNow && !counterPoison && !counterExhausted
  io.quarantined:=quarantine || unknownNow
  io.resetRequired:=quarantine || unknownNow || counterExhausted || counterPoison || arb.io.resetRequired || io.parentPoison
}
