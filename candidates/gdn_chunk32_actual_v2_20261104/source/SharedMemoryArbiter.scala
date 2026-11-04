// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** One transactional memory port for metadata and existing compute owners.
  * Requests are captured before being offered to iDMA. The owner and original
  * 64-bit tag survive arbitrary downstream and return-path backpressure.
  * A transport tag is allocated independently of client tags; two clients may
  * legitimately both submit tag zero. A bad response is returned to its owner
  * as an error and quarantines the whole port until reset. No silent reroute.
  * There is deliberately one outstanding transfer, matching the pinned iDMA
  * mailbox adapter. This module is not an AXI burst/performance scheduler.
  */
class SharedMemoryArbiter(clients: Int = 3, cancellationClient: Int = -1) extends Module {
  // Seventeen logical users on the SAME one-outstanding port. Selection is
  // log2Ceil(clients), including the actual 5-bit owner/RR state at clients=17.
  require(clients >= 2 && clients <= 32)
  require(cancellationClient >= -1 && cancellationClient < clients)
  val io = IO(new Bundle {
    val requests = Flipped(Vec(clients, Decoupled(new MemoryRequest)))
    val cancel=if(cancellationClient>=0)Some(Input(Bool()))else None
    val cancelled=if(cancellationClient>=0)Some(Output(Bool()))else None
    val responses = Vec(clients, Decoupled(new MemoryResponse))
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val resetRequired = Output(Bool())
    val resourcesDrained = Output(Bool()) // private actual transport/lifetime fence
    val accepted = Output(Vec(clients, UInt(64.W)))
    val returned = Output(Vec(clients, UInt(64.W)))
  })
  val idle :: issue :: awaitResponse :: deliver :: locked :: Nil = Enum(5)
  val state = RegInit(idle)
  val owner = Reg(UInt(log2Ceil(clients).W))
  val request = Reg(new MemoryRequest)
  val originalTag = Reg(UInt(64.W))
  val reply = Reg(new MemoryResponse)
  val sequence = RegInit(0.U(64.W))
  val poison = RegInit(false.B)
  val unknownResponse=io.response.valid && state=/=awaitResponse
  val quarantine=RegInit(false.B)
  when(unknownResponse){quarantine:=true.B}
  val accepted = RegInit(VecInit(Seq.fill(clients)(0.U(64.W))))
  val returned = RegInit(VecInit(Seq.fill(clients)(0.U(64.W))))
  val arb = Module(new RRArbiter(new MemoryRequest, clients))
  for (i <- 0 until clients) {
    if(i==cancellationClient){
      // RR input has no captured payload before fire. Accepted owner/request
      // registers below are untouched, even if they belong to this client.
      arb.io.in(i).valid:=io.requests(i).valid && !io.cancel.get
      arb.io.in(i).bits:=io.requests(i).bits
      io.requests(i).ready:=arb.io.in(i).ready && !io.cancel.get
      io.cancelled.get:=io.cancel.get && io.requests(i).valid
      assert(!(io.cancelled.get && io.requests(i).fire))
    }else{arb.io.in(i) <> io.requests(i)}
    io.responses(i).valid := state === deliver && owner === i.U
    io.responses(i).bits := reply
  }
  arb.io.out.ready := state === idle && !poison && !quarantine && !unknownResponse
  io.memory.valid := state === issue
  io.memory.bits := request
  io.response.ready := state === awaitResponse && (if(cancellationClient>=0) !quarantine else true.B)
  io.resetRequired := poison || quarantine || unknownResponse
  io.resourcesDrained:=state===idle && !poison && !quarantine && !unknownResponse &&
    !arb.io.out.valid && !io.memory.valid && !io.responses.map(_.valid).reduce(_||_)
  io.accepted := accepted
  io.returned := returned

  when(arb.io.out.fire) {
    val selected = arb.io.chosen
    owner := selected
    originalTag := arb.io.out.bits.tag
    accepted(selected) := accepted(selected) + 1.U
    request := arb.io.out.bits
    request.tag := sequence
    when(sequence.andR) {
      reply.data := 0.U
      reply.tag := arb.io.out.bits.tag
      reply.error := true.B
      poison := true.B
      state := deliver
    }.otherwise {
      sequence := sequence + 1.U
      state := issue
    }
  }
  when(io.memory.fire) { state := awaitResponse }
  when(io.response.fire) {
    val tagMatches=io.response.bits.tag===request.tag
    // In the opted-in cancellation contract an unknown transport return is
    // never rewritten into an apparent matched leaf error. Keep accepted debt.
    if(cancellationClient>=0){
      when(!tagMatches){quarantine:=true.B}.otherwise{
        reply.data:=Mux(io.response.bits.error,0.U,io.response.bits.data)
        reply.tag:=originalTag;reply.error:=io.response.bits.error
        poison:=io.response.bits.error;state:=deliver
      }
    }else{
      val bad = io.response.bits.error || !tagMatches
      reply.data := Mux(bad, 0.U, io.response.bits.data)
      reply.tag := originalTag;reply.error := bad;poison := bad;state := deliver
    }
  }
  when(state === deliver && io.responses(owner).ready) {
    returned(owner) := returned(owner) + 1.U
    state := Mux(poison, locked, idle)
  }
}
