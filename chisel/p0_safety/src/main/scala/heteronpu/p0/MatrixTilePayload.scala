// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0

import chisel3._
import chisel3.util._

class MatrixTilePayloadIO(val addressBits: Int) extends Bundle {
  val start_i = Input(Bool())
  val activation_local_i = Input(UInt(64.W))
  val weight_local_i = Input(UInt(64.W))
  val output_local_i = Input(UInt(64.W))
  val depth_i = Input(UInt(16.W))
  val weight_k_stride_i = Input(UInt(32.W))
  val rows_i = Input(UInt(16.W))
  val columns_i = Input(UInt(16.W))
  val output_fp32_i = Input(Bool())
  val status_o = Output(UInt(8.W))
  val l2_rd_valid_o = Output(Bool())
  val l2_rd_ready_i = Input(Bool())
  val l2_rd_addr_o = Output(UInt(addressBits.W))
  val l2_rsp_valid_i = Input(Bool())
  val l2_rsp_ready_o = Output(Bool())
  val l2_rsp_data_i = Input(UInt(512.W))
  val l2_wr_valid_o = Output(Bool())
  val l2_wr_ready_i = Input(Bool())
  val l2_wr_addr_o = Output(UInt(addressBits.W))
  val l2_wr_data_o = Output(UInt(512.W))
  val l2_wr_be_o = Output(UInt(64.W))
  val matrix_step_valid_o = Output(Bool())
  val matrix_step_ready_i = Input(Bool())
  val matrix_context_o = Output(UInt(3.W))
  val matrix_clear_o = Output(Bool())
  val matrix_last_o = Output(Bool())
  val matrix_a_o = Output(UInt(256.W))
  val matrix_b_o = Output(UInt(512.W))
  val matrix_out_valid_i = Input(Bool())
  val matrix_out_ready_o = Output(Bool())
  val matrix_out_last_i = Input(Bool())
  val matrix_acc_i = Input(UInt(16384.W))
  val done_o = Output(Bool())
  val read_beats_o = Output(UInt(32.W))
  val write_beats_o = Output(UInt(32.W))
  val matrix_steps_o = Output(UInt(32.W))
}

/** Full payload FSM, lane masks, FP32/BF16 packing and local-memory interface.
  * Arithmetic remains the existing external Matrix endpoint, not a fake MAC.
  * A rejected request emits neither a memory request nor a Matrix step.
  */
class MatrixTilePayload(val cfg: LocalSramConfig = LocalSramConfig()) extends Module {
  val io = IO(new MatrixTilePayloadIO(cfg.addressBits))
  val idle :: aReq :: aRsp :: bReq :: bRsp :: issue :: waitLast :: write :: done :: Nil = Enum(9)
  val state = RegInit(idle)
  val aBase = RegInit(0.U(64.W)); val bBase = RegInit(0.U(64.W)); val cBase = RegInit(0.U(64.W))
  val stride = RegInit(0.U(32.W)); val depth = RegInit(0.U(16.W))
  val rows = RegInit(0.U(16.W)); val columns = RegInit(0.U(16.W)); val k = RegInit(0.U(16.W))
  val row = RegInit(0.U(4.W)); val half = RegInit(false.B); val fp32 = RegInit(false.B)
  val a = RegInit(0.U(512.W)); val b = RegInit(0.U(512.W))
  val acc = RegInit(0.U(16384.W)); val finalSeen = RegInit(false.B)
  val status = RegInit(0.U(8.W))
  val reads = RegInit(0.U(32.W)); val writes = RegInit(0.U(32.W)); val steps = RegInit(0.U(32.W))
  val inRowBeats = Mux(io.output_fp32_i && io.columns_i > 16.U, 2.U(2.W), 1.U(2.W))
  val rowBeats = Mux(fp32 && columns > 16.U, 2.U(2.W), 1.U(2.W))
  val bSpan = (io.depth_i - 1.U) * io.weight_k_stride_i +& 64.U
  val legal = io.depth_i =/= 0.U && io.rows_i > 0.U && io.rows_i <= 16.U &&
    io.columns_i > 0.U && io.columns_i <= 32.U &&
    io.activation_local_i(5,0) === 0.U && io.weight_local_i(5,0) === 0.U && io.output_local_i(5,0) === 0.U &&
    io.weight_k_stride_i >= 64.U && io.weight_k_stride_i(5,0) === 0.U &&
    cfg.contains(io.activation_local_i, io.depth_i << 6) && cfg.contains(io.weight_local_i, bSpan) &&
    cfg.contains(io.output_local_i, (io.rows_i * inRowBeats) << 6)
  io.status_o := status; io.done_o := state === done
  io.read_beats_o := reads; io.write_beats_o := writes; io.matrix_steps_o := steps
  io.l2_rd_valid_o := state === aReq || state === bReq
  io.l2_rd_addr_o := Mux(state === aReq, (aBase >> 6) + k, (bBase >> 6) + k * (stride >> 6))
  io.l2_rsp_ready_o := state === aRsp || state === bRsp
  io.matrix_step_valid_o := state === issue
  io.matrix_context_o := 0.U; io.matrix_clear_o := k === 0.U; io.matrix_last_o := k === depth - 1.U
  io.matrix_a_o := Cat((0 until 16).reverse.map(r => Mux(r.U < rows, a(16*r+15,16*r), 0.U(16.W))))
  io.matrix_b_o := Cat((0 until 32).reverse.map(c => Mux(c.U < columns, b(16*c+15,16*c), 0.U(16.W))))
  io.matrix_out_ready_o := true.B
  io.l2_wr_valid_o := state === write
  io.l2_wr_addr_o := (cBase >> 6) + row * rowBeats + half.asUInt
  val accRows = acc.asTypeOf(Vec(16, Vec(32, UInt(32.W))))
  val selectedRow = accRows(row)
  def rne(x: UInt): UInt = { val rounded = x + "h00007fff".U(32.W) + x(16); rounded(31,16) }
  val bfPacked = Cat((0 until 32).reverse.map(c => rne(selectedRow(c))))
  val fpPacked = Mux(half, selectedRow.asUInt(1023,512), selectedRow.asUInt(511,0))
  io.l2_wr_data_o := Mux(fp32, fpPacked, bfPacked)
  val bfMask = Cat((0 until 32).reverse.map(c => Mux(c.U < columns, 3.U(2.W), 0.U(2.W))))
  val fpMask = Cat((0 until 16).reverse.map(c => Mux(c.U + Mux(half,16.U,0.U) < columns, 15.U(4.W), 0.U(4.W))))
  io.l2_wr_be_o := Mux(fp32, fpMask, bfMask)
  when(state =/= idle && state =/= done && io.matrix_out_valid_i && io.matrix_out_last_i) {
    acc := io.matrix_acc_i; finalSeen := true.B
  }
  switch(state) {
    is(idle) { when(io.start_i) {
      aBase := io.activation_local_i; bBase := io.weight_local_i; cBase := io.output_local_i
      stride := io.weight_k_stride_i; depth := io.depth_i; rows := io.rows_i; columns := io.columns_i; fp32 := io.output_fp32_i
      k := 0.U; row := 0.U; half := false.B; finalSeen := false.B
      reads := 0.U; writes := 0.U; steps := 0.U; status := Mux(legal,0.U,5.U); state := Mux(legal,aReq,done)
    } }
    is(aReq) { when(io.l2_rd_ready_i) { state := aRsp } }
    is(aRsp) { when(io.l2_rsp_valid_i) { a := io.l2_rsp_data_i; reads := reads + 1.U; state := bReq } }
    is(bReq) { when(io.l2_rd_ready_i) { state := bRsp } }
    is(bRsp) { when(io.l2_rsp_valid_i) { b := io.l2_rsp_data_i; reads := reads + 1.U; state := issue } }
    is(issue) { when(io.matrix_step_ready_i) {
      steps := steps + 1.U
      when(k === depth - 1.U) { state := waitLast }.otherwise { k := k + 1.U; state := aReq }
    } }
    is(waitLast) { when(finalSeen) { row := 0.U; state := write } }
    is(write) { when(io.l2_wr_ready_i) {
      writes := writes + 1.U
      when(fp32 && columns > 16.U && !half) { half := true.B }
        .otherwise { half := false.B; when(row +& 1.U === rows) { state := done }.otherwise { row := row + 1.U } }
    } }
    is(done) { state := idle }
  }
}
