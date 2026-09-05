// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0
import chisel3._
import chisel3.util._

class DmaPort extends Bundle {
  val valid = Output(Bool()); val ready = Input(Bool()); val kind = Output(UInt(2.W))
  val source = Output(UInt(64.W)); val destination = Output(UInt(64.W))
  val rowBytes = Output(UInt(32.W)); val rows = Output(UInt(32.W)); val sourceStride = Output(UInt(32.W)); val destinationStride = Output(UInt(32.W))
  val response = Input(Bool()); val responseReady = Output(Bool()); val error = Input(Bool())
}
class LocalMemoryPort(val bits: Int) extends Bundle {
  val read = Output(Bool()); val readReady = Input(Bool()); val readAddress = Output(UInt(bits.W))
  val response = Input(Bool()); val responseReady = Output(Bool()); val data = Input(UInt(512.W))
  val write = Output(Bool()); val writeReady = Input(Bool()); val writeAddress = Output(UInt(bits.W))
  val writeData = Output(UInt(512.W)); val byteEnable = Output(UInt(64.W))
}

/** Migrated as well to avoid the legacy Norm wrapper instantiating a parameterized
  * handwritten transpose module. No normalization arithmetic is done here.
  */
class NormTileLoader(val cfg: LocalSramConfig = LocalSramConfig()) extends Module {
  val io = IO(new Bundle {
    val start = Input(Bool()); val base = Input(UInt(64.W)); val token = Input(UInt(32.W))
    val dma = new DmaPort; val memory = new LocalMemoryPort(cfg.addressBits)
    val done = Output(Bool()); val status = Output(UInt(8.W)); val bytes = Output(UInt(64.W))
  })
  val idle :: request :: response :: transposeRequest :: transposeResponse :: done :: Nil = Enum(6)
  val state = RegInit(idle); val source = RegInit(0.U(64.W)); val status = RegInit(0.U(8.W)); val bytes = RegInit(0.U(64.W))
  val candidate = io.base.pad(66) + io.token.pad(66)*3072.U
  val legal = candidate + 49152.U <= (BigInt(1)<<64).U && (cfg.bytes >= BigInt("98000",16)).B
  val tr = Module(new TileTranspose(cfg))
  tr.io.request_valid_i := state === transposeRequest; tr.io.completion_ready_i := true.B
  tr.io.source_i := "h60000".U; tr.io.destination_i := "h80000".U; tr.io.source_stride_i := 3072.U; tr.io.rows_i := 16.U; tr.io.depth_i := 1536.U
  tr.io.rd_ready_i := io.memory.readReady; io.memory.read := tr.io.rd_valid_o; io.memory.readAddress := tr.io.rd_addr_o
  tr.io.rsp_valid_i := io.memory.response; io.memory.responseReady := tr.io.rsp_ready_o; tr.io.rsp_data_i := io.memory.data; tr.io.rsp_error_i := false.B
  io.memory.write := tr.io.wr_valid_o; tr.io.wr_ready_i := io.memory.writeReady
  io.memory.writeAddress := tr.io.wr_addr_o; io.memory.writeData := tr.io.wr_data_o; io.memory.byteEnable := tr.io.wr_be_o
  io.dma.valid := state === request; io.dma.kind := 1.U; io.dma.source := source; io.dma.destination := "h60000".U
  io.dma.rowBytes := 3072.U; io.dma.rows := 16.U; io.dma.sourceStride := 3072.U; io.dma.destinationStride := 3072.U; io.dma.responseReady := state === response
  io.done := state === done; io.status := status; io.bytes := bytes
  switch(state) {
    is(idle) { when(io.start) { source := candidate; status := Mux(legal,0.U,5.U); bytes := 0.U; state := Mux(legal,request,done) } }
    is(request) { when(io.dma.ready) { state := response } }
    is(response) { when(io.dma.response) { when(io.dma.error) { status := 3.U; state := done }.otherwise { bytes := 49152.U; state := transposeRequest } } }
    is(transposeRequest) { when(tr.io.request_ready_o) { state := transposeResponse } }
    is(transposeResponse) { when(tr.io.completion_valid_o) { status := tr.io.status_o; state := done } }
    is(done) { state := idle }
  }
}
