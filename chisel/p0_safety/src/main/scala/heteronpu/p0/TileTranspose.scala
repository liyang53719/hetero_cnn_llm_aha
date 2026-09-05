// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0

import chisel3._
import chisel3.util._

class TileTransposeIO(val addressBits: Int) extends Bundle {
  val request_valid_i = Input(Bool()); val request_ready_o = Output(Bool())
  val source_i = Input(UInt(64.W)); val destination_i = Input(UInt(64.W)); val source_stride_i = Input(UInt(32.W))
  val rows_i = Input(UInt(16.W)); val depth_i = Input(UInt(16.W))
  val rd_valid_o = Output(Bool()); val rd_ready_i = Input(Bool()); val rd_addr_o = Output(UInt(addressBits.W))
  val rsp_valid_i = Input(Bool()); val rsp_ready_o = Output(Bool()); val rsp_data_i = Input(UInt(512.W)); val rsp_error_i = Input(Bool())
  val wr_valid_o = Output(Bool()); val wr_ready_i = Input(Bool()); val wr_addr_o = Output(UInt(addressBits.W))
  val wr_data_o = Output(UInt(512.W)); val wr_be_o = Output(UInt(64.W))
  val completion_valid_o = Output(Bool()); val completion_ready_i = Input(Bool()); val status_o = Output(UInt(8.W))
  val read_beats_o = Output(UInt(64.W)); val write_beats_o = Output(UInt(64.W))
}

/** Real 16x512-bit staging and lane selection; no software transpose helper. */
class TileTranspose(val cfg: LocalSramConfig = LocalSramConfig()) extends Module {
  val io = IO(new TileTransposeIO(cfg.addressBits))
  val idle :: readReq :: readRsp :: write :: complete :: Nil = Enum(5)
  val state = RegInit(idle)
  val source = RegInit(0.U(64.W)); val dest = RegInit(0.U(64.W)); val stride = RegInit(0.U(32.W))
  val rows = RegInit(0.U(16.W)); val depth = RegInit(0.U(16.W)); val k = RegInit(0.U(16.W))
  val row = RegInit(0.U(4.W)); val lane = RegInit(0.U(5.W))
  val buffer = Reg(Vec(16, UInt(512.W)))
  val reads = RegInit(0.U(64.W)); val writes = RegInit(0.U(64.W)); val status = RegInit(0.U(8.W))
  val paddedBytes = ((io.depth_i.pad(66) + 31.U) >> 5) << 6
  val srcSpan = (io.rows_i - 1.U) * io.source_stride_i +& paddedBytes
  val dstSpan = io.depth_i << 6
  val srcEnd = io.source_i.pad(66) + srcSpan.pad(66); val dstEnd = io.destination_i.pad(66) + dstSpan.pad(66)
  val legal = io.rows_i > 0.U && io.rows_i <= 16.U && io.depth_i =/= 0.U &&
    io.source_i(5,0) === 0.U && io.destination_i(5,0) === 0.U && io.source_stride_i(5,0) === 0.U &&
    io.source_stride_i >= paddedBytes && cfg.contains(io.source_i,srcSpan) && cfg.contains(io.destination_i,dstSpan) &&
    (srcEnd <= io.destination_i.pad(66) || dstEnd <= io.source_i.pad(66))
  io.request_ready_o := state === idle; io.completion_valid_o := state === complete; io.status_o := status
  io.rd_valid_o := state === readReq; io.rsp_ready_o := state === readRsp
  io.rd_addr_o := (source + row * stride + ((k >> 5) << 6)) >> 6
  io.wr_valid_o := state === write; io.wr_addr_o := (dest >> 6) + k + lane
  io.wr_be_o := Fill(64,1.U(1.W))
  val lanes = (0 until 16).map(r => Mux(r.U < rows, (buffer(r) >> (lane << 4))(15,0), 0.U(16.W)))
  io.wr_data_o := Cat(0.U(256.W), Cat(lanes.reverse))
  io.read_beats_o := reads; io.write_beats_o := writes
  switch(state) {
    is(idle) { when(io.request_valid_i) {
      source := io.source_i; dest := io.destination_i; stride := io.source_stride_i
      rows := io.rows_i; depth := io.depth_i; k := 0.U; row := 0.U; lane := 0.U
      reads := 0.U; writes := 0.U; status := Mux(legal,0.U,5.U); state := Mux(legal,readReq,complete)
    } }
    is(readReq) { when(io.rd_ready_i) { state := readRsp } }
    is(readRsp) { when(io.rsp_valid_i) {
      when(io.rsp_error_i) { status := 3.U; state := complete }.otherwise {
        buffer(row) := io.rsp_data_i; reads := reads + 1.U
        when(row +& 1.U === rows) { lane := 0.U; state := write }.otherwise { row := row + 1.U; state := readReq }
      }
    } }
    is(write) { when(io.wr_ready_i) {
      writes := writes + 1.U
      when(k.pad(17) + lane.pad(17) + 1.U === depth.pad(17)) { state := complete }
        .elsewhen(lane === 31.U) { k := k + 32.U; row := 0.U; state := readReq }
        .otherwise { lane := lane + 1.U }
    } }
    is(complete) { when(io.completion_ready_i) { state := idle } }
  }
}
