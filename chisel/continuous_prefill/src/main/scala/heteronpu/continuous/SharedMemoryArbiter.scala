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
class SharedMemoryArbiter(clients: Int = 3) extends Module {
  require(clients >= 2 && clients <= 16)
  val io = IO(new Bundle {
    val requests = Flipped(Vec(clients, Decoupled(new MemoryRequest)))
    val responses = Vec(clients, Decoupled(new MemoryResponse))
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val resetRequired = Output(Bool())
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
  val accepted = RegInit(VecInit(Seq.fill(clients)(0.U(64.W))))
  val returned = RegInit(VecInit(Seq.fill(clients)(0.U(64.W))))
  val arb = Module(new RRArbiter(new MemoryRequest, clients))
  for (i <- 0 until clients) {
    arb.io.in(i) <> io.requests(i)
    io.responses(i).valid := state === deliver && owner === i.U
    io.responses(i).bits := reply
  }
  arb.io.out.ready := state === idle && !poison
  io.memory.valid := state === issue
  io.memory.bits := request
  io.response.ready := state === awaitResponse
  io.resetRequired := poison
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
    val bad = io.response.bits.error || io.response.bits.tag =/= request.tag
    reply.data := Mux(bad, 0.U, io.response.bits.data)
    reply.tag := originalTag
    reply.error := bad
    poison := bad
    state := deliver
  }
  when(state === deliver && io.responses(owner).ready) {
    returned(owner) := returned(owner) + 1.U
    state := Mux(poison, locked, idle)
  }
}
