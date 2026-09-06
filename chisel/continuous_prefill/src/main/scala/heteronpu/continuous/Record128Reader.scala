// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** A physical table of existing 16-byte Command128 or typed descriptor records.
  * limit is the exclusive mapped allocation boundary, including beat padding.
  * The reader does not invent a block opcode or claim descriptor execution.
  */
class Record128Request extends Bundle {
  val tableBase = UInt(64.W)
  val tableLimit = UInt(64.W)
  val entryCount = UInt(25.W)
  val index = UInt(24.W)
  val requestTag = UInt(64.W)
}
class Record128Result extends Bundle {
  val data = UInt(128.W)
  val requestTag = UInt(64.W)
  val status = UInt(8.W)
}
/** Shared bounded DDR reader for the frozen command/descriptor table format.
  * A 512-bit read fetches four adjacent records; index[1:0] selects the record.
  * No caching: changing a descriptor between quiescent requests is observable.
  * Runtime response errors quarantine the reader until reset; admission errors
  * produce an error without emitting a memory request. The memory port directly
  * matches RetainedIdmaMemoryAdapter, so data crosses the real iDMA backend.
  */
class Record128Reader extends Module {
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new Record128Request))
    val result = Decoupled(new Record128Result)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val resetRequired = Output(Bool())
  })
  val idle :: issue :: waitResponse :: reply :: locked :: Nil = Enum(5)
  val state = RegInit(idle)
  val address = Reg(UInt(64.W)); val slot = Reg(UInt(2.W))
  val result = Reg(new Record128Result)
  val serial = RegInit(0.U(64.W)); val poison = RegInit(false.B)
  io.request.ready := state === idle && !poison
  io.result.valid := state === reply; io.result.bits := result
  io.memory.valid := state === issue
  io.memory.bits := 0.U.asTypeOf(new MemoryRequest)
  io.memory.bits.address := address; io.memory.bits.tag := serial
  io.response.ready := state === waitResponse
  io.resetRequired := poison

  when(io.request.fire) {
    val x = io.request.bits
    val span = ((x.entryCount.pad(66) * 16.U + 63.U) >> 6) << 6
    val tableEnd = x.tableBase.pad(66) + span
    val beat = x.tableBase.pad(66) + ((x.index.pad(66) >> 2) << 6)
    val legal = x.entryCount > 0.U && x.entryCount <= 0xffffff.U &&
      x.index =/= 0xffffff.U && x.index < x.entryCount &&
      x.tableBase(5,0) === 0.U && tableEnd <= x.tableLimit.pad(66) &&
      x.tableLimit <= (BigInt(1) << 56).U && tableEnd > x.tableBase &&
      beat + 64.U <= tableEnd
    result.data := 0.U; result.requestTag := x.requestTag; result.status := Status.Ok.U
    when(!legal) { result.status := Status.Bounds.U; state := reply }
    .elsewhen(serial.andR) { result.status := Status.Protocol.U; poison := true.B; state := reply }
    .otherwise { address := beat(63,0); slot := x.index(1,0); serial := serial + 1.U; state := issue }
  }
  when(state === issue && io.memory.fire) { state := waitResponse }
  when(state === waitResponse && io.response.fire) {
    when(io.response.bits.tag =/= serial) {
      result.status := Status.Protocol.U; poison := true.B
    }.elsewhen(io.response.bits.error) {
      result.status := Status.Memory.U; poison := true.B
    }.otherwise {
      result.data := (io.response.bits.data >> Cat(slot, 0.U(7.W)))(127,0)
    }
    state := reply
  }
  when(state === reply && io.result.fire) { state := Mux(poison, locked, idle) }
}
/** Actual upstream iDMA and external AXI composition, no mock memory service. */
class Record128IdmaTop extends Module {
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new Record128Request))
    val result = Decoupled(new Record128Result)
    val axi = new BlockAxiMaster
    val resetRequired = Output(Bool()); val idmaTransfers = Output(UInt(64.W))
  })
  val reader = Module(new Record128Reader)
  val dma = Module(new RetainedIdmaMemoryAdapter)
  io.request <> reader.io.request; io.result <> reader.io.result
  dma.io.request <> reader.io.memory; reader.io.response <> dma.io.response
  io.axi <> dma.io.axi
  io.resetRequired := reader.io.resetRequired || dma.io.resetRequired
  io.idmaTransfers := dma.io.transfers
}
