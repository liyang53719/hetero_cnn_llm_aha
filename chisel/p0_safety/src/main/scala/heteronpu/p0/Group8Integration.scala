// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0
import chisel3._
import chisel3.util._

/** These two BlackBoxes are unchanged, retained upstream dependency boundaries.
  * None of the migrated/fixed modules is implemented by BlackBox or SV inline.
  */
class RetainedDescriptor extends BlackBox(Map("ALLOW_FP32_OUTPUT" -> 1)) {
  override def desiredName = "qwen2_projection_descriptor_context"
  val io = IO(new Bundle {
    val clk_i = Input(Clock()); val rst_ni = Input(Bool()); val start_i = Input(Bool()); val command_i = Input(UInt(128.W))
    val descriptor_req_valid_o = Output(Bool()); val descriptor_req_ready_i = Input(Bool()); val descriptor_req_index_o = Output(UInt(24.W))
    val descriptor_rsp_valid_i = Input(Bool()); val descriptor_rsp_ready_o = Output(Bool()); val descriptor_rsp_data_i = Input(UInt(128.W)); val descriptor_rsp_error_i = Input(Bool())
    val context_valid_o = Output(Bool()); val context_ready_i = Input(Bool()); val context_legal_o = Output(Bool()); val context_status_o = Output(UInt(8.W))
    val tensor_address_o = Output(UInt(168.W)); val tensor_shape_o = Output(UInt(216.W)); val output_columns_o = Output(UInt(18.W))
    val weight_row_bytes_o = Output(UInt(32.W)); val column_tiles_o = Output(UInt(6.W)); val output_fp32_o = Output(Bool())
  })
}
class RetainedMatrix extends BlackBox {
  override def desiredName = "qwen2_matrix_command_endpoint"
  val io = IO(new Bundle {
    val clk_i = Input(Clock()); val rst_ni = Input(Bool()); val cmd_valid_i = Input(Bool()); val cmd_ready_o = Output(Bool()); val cmd_i = Input(UInt(128.W))
    val step_valid_i = Input(Bool()); val step_ready_o = Output(Bool()); val step_context_i = Input(UInt(3.W)); val step_clear_i = Input(Bool()); val step_last_i = Input(Bool())
    val command_last_tile_i = Input(Bool()); val step_a_i = Input(UInt(256.W)); val step_b_i = Input(UInt(512.W))
    val out_valid_o = Output(Bool()); val out_ready_i = Input(Bool()); val out_context_o = Output(UInt(3.W)); val out_last_o = Output(Bool()); val out_acc_o = Output(UInt(16384.W))
    val completion_valid_o = Output(Bool()); val completion_ready_i = Input(Bool()); val completion_data_o = Output(UInt(56.W)); val protocol_error_o = Output(Bool())
  })
}
class Group8TopIO(val addressBits: Int) extends Bundle {
  val start_i = Input(Bool()); val command_i = Input(UInt(128.W)); val trace_only_i = Input(Bool()); val batch_count_i = Input(UInt(32.W))
  val descriptor_req_valid_o = Output(Bool()); val descriptor_req_ready_i = Input(Bool()); val descriptor_req_index_o = Output(UInt(24.W))
  val descriptor_rsp_valid_i = Input(Bool()); val descriptor_rsp_ready_o = Output(Bool()); val descriptor_rsp_data_i = Input(UInt(128.W)); val descriptor_rsp_error_i = Input(Bool())
  val dma_req_valid_o = Output(Bool()); val dma_req_ready_i = Input(Bool()); val dma_req_kind_o = Output(UInt(2.W))
  val dma_src_addr_o = Output(UInt(64.W)); val dma_dst_addr_o = Output(UInt(64.W)); val dma_row_bytes_o = Output(UInt(32.W)); val dma_rows_o = Output(UInt(32.W))
  val dma_src_stride_o = Output(UInt(32.W)); val dma_dst_stride_o = Output(UInt(32.W)); val dma_rsp_valid_i = Input(Bool()); val dma_rsp_ready_o = Output(Bool()); val dma_rsp_error_i = Input(Bool())
  val l2_rd_valid_o = Output(Bool()); val l2_rd_ready_i = Input(Bool()); val l2_rd_addr_o = Output(UInt(addressBits.W))
  val l2_rsp_valid_i = Input(Bool()); val l2_rsp_ready_o = Output(Bool()); val l2_rsp_data_i = Input(UInt(512.W))
  val l2_wr_valid_o = Output(Bool()); val l2_wr_ready_i = Input(Bool()); val l2_wr_addr_o = Output(UInt(addressBits.W)); val l2_wr_data_o = Output(UInt(512.W)); val l2_wr_be_o = Output(UInt(64.W))
  val done_o = Output(Bool()); val status_o = Output(UInt(8.W)); val matrix_steps_o = Output(UInt(32.W)); val values_o = Output(UInt(32.W))
  val weight_tile_loads_o = Output(UInt(32.W)); val norm_batch_loads_o = Output(UInt(32.W)); val ddr_read_bytes_o = Output(UInt(64.W)); val ddr_write_bytes_o = Output(UInt(64.W))
  val reset_required_o = Output(Bool())
}
class Group8Integration(val cfg: LocalSramConfig = LocalSramConfig()) extends Module {
  val io = IO(new Group8TopIO(cfg.addressBits))
  val ctl = Module(new Group8Scheduler); val desc = Module(new RetainedDescriptor)
  val norm = Module(new NormTileLoader(cfg)); val pay = Module(new MatrixTilePayload(cfg)); val matrix = Module(new RetainedMatrix)
  desc.io.clk_i := clock; desc.io.rst_ni := !reset.asBool; matrix.io.clk_i := clock; matrix.io.rst_ni := !reset.asBool
  ctl.io.start := io.start_i; ctl.io.command := io.command_i; ctl.io.traceOnly := io.trace_only_i; ctl.io.batches := io.batch_count_i
  desc.io.start_i := ctl.io.descriptorStart; desc.io.command_i := ctl.io.heldCommand
  io.descriptor_req_valid_o := desc.io.descriptor_req_valid_o; desc.io.descriptor_req_ready_i := io.descriptor_req_ready_i; io.descriptor_req_index_o := desc.io.descriptor_req_index_o
  desc.io.descriptor_rsp_valid_i := io.descriptor_rsp_valid_i; io.descriptor_rsp_ready_o := desc.io.descriptor_rsp_ready_o; desc.io.descriptor_rsp_data_i := io.descriptor_rsp_data_i; desc.io.descriptor_rsp_error_i := io.descriptor_rsp_error_i
  ctl.io.contextValid := desc.io.context_valid_o; desc.io.context_ready_i := ctl.io.contextReady; ctl.io.contextLegal := desc.io.context_legal_o; ctl.io.contextStatus := desc.io.context_status_o
  ctl.io.addresses := desc.io.tensor_address_o; ctl.io.columns := desc.io.output_columns_o; ctl.io.weightStride := desc.io.weight_row_bytes_o; ctl.io.tiles := desc.io.column_tiles_o; ctl.io.contextFp32 := desc.io.output_fp32_o
  norm.io.start := ctl.io.normStart; norm.io.base := ctl.io.normBase; norm.io.token := ctl.io.tokenBase
  ctl.io.normDone := norm.io.done; ctl.io.normStatus := norm.io.status; ctl.io.normBytes := norm.io.bytes
  pay.io.start_i := ctl.io.payloadStart; pay.io.activation_local_i := "h80000".U; pay.io.weight_local_i := ctl.io.payloadWeight; pay.io.output_local_i := "h160000".U
  pay.io.depth_i := 1536.U; pay.io.weight_k_stride_i := ctl.io.payloadStride; pay.io.rows_i := 16.U; pay.io.columns_i := 32.U; pay.io.output_fp32_i := ctl.io.outputFp32
  ctl.io.payloadDone := pay.io.done_o; ctl.io.payloadStatus := pay.io.status_o; ctl.io.payloadSteps := pay.io.matrix_steps_o
  matrix.io.cmd_valid_i := ctl.io.matrixCmdValid; ctl.io.matrixCmdReady := matrix.io.cmd_ready_o; matrix.io.cmd_i := ctl.io.heldCommand
  matrix.io.step_valid_i := pay.io.matrix_step_valid_o; pay.io.matrix_step_ready_i := matrix.io.step_ready_o
  matrix.io.step_context_i := pay.io.matrix_context_o; matrix.io.step_clear_i := pay.io.matrix_clear_o; matrix.io.step_last_i := pay.io.matrix_last_o
  matrix.io.command_last_tile_i := ctl.io.lastTile; matrix.io.step_a_i := pay.io.matrix_a_o; matrix.io.step_b_i := pay.io.matrix_b_o
  pay.io.matrix_out_valid_i := matrix.io.out_valid_o; matrix.io.out_ready_i := pay.io.matrix_out_ready_o; pay.io.matrix_out_last_i := matrix.io.out_last_o; pay.io.matrix_acc_i := matrix.io.out_acc_o
  ctl.io.matrixCompletion := matrix.io.completion_valid_o; matrix.io.completion_ready_i := true.B; ctl.io.matrixStatus := matrix.io.completion_data_o(39,32); ctl.io.matrixError := matrix.io.protocol_error_o
  val n = ctl.io.selectNorm; val p = ctl.io.selectPayload
  io.dma_req_valid_o := Mux(n,norm.io.dma.valid,ctl.io.dmaValid); io.dma_req_kind_o := Mux(n,norm.io.dma.kind,ctl.io.dmaKind)
  io.dma_src_addr_o := Mux(n,norm.io.dma.source,ctl.io.dmaSource); io.dma_dst_addr_o := Mux(n,norm.io.dma.destination,ctl.io.dmaDestination)
  io.dma_row_bytes_o := Mux(n,norm.io.dma.rowBytes,ctl.io.dmaRowBytes); io.dma_rows_o := Mux(n,norm.io.dma.rows,ctl.io.dmaRows)
  io.dma_src_stride_o := Mux(n,norm.io.dma.sourceStride,ctl.io.dmaSourceStride); io.dma_dst_stride_o := Mux(n,norm.io.dma.destinationStride,ctl.io.dmaDestinationStride)
  norm.io.dma.ready := n && io.dma_req_ready_i; norm.io.dma.response := n && io.dma_rsp_valid_i; norm.io.dma.error := io.dma_rsp_error_i
  ctl.io.dmaReady := !n && io.dma_req_ready_i; ctl.io.dmaResponse := !n && io.dma_rsp_valid_i; ctl.io.dmaError := io.dma_rsp_error_i
  io.dma_rsp_ready_o := Mux(n,norm.io.dma.responseReady,ctl.io.dmaResponseReady)
  io.l2_rd_valid_o := Mux(n,norm.io.memory.read,p && pay.io.l2_rd_valid_o); io.l2_rd_addr_o := Mux(n,norm.io.memory.readAddress,pay.io.l2_rd_addr_o)
  norm.io.memory.readReady := n && io.l2_rd_ready_i; pay.io.l2_rd_ready_i := p && io.l2_rd_ready_i
  norm.io.memory.response := n && io.l2_rsp_valid_i; pay.io.l2_rsp_valid_i := p && io.l2_rsp_valid_i
  norm.io.memory.data := io.l2_rsp_data_i; pay.io.l2_rsp_data_i := io.l2_rsp_data_i
  io.l2_rsp_ready_o := Mux(n,norm.io.memory.responseReady,p && pay.io.l2_rsp_ready_o)
  io.l2_wr_valid_o := Mux(n,norm.io.memory.write,p && pay.io.l2_wr_valid_o)
  io.l2_wr_addr_o := Mux(n,norm.io.memory.writeAddress,pay.io.l2_wr_addr_o); io.l2_wr_data_o := Mux(n,norm.io.memory.writeData,pay.io.l2_wr_data_o)
  io.l2_wr_be_o := Mux(n,norm.io.memory.byteEnable,pay.io.l2_wr_be_o)
  norm.io.memory.writeReady := n && io.l2_wr_ready_i; pay.io.l2_wr_ready_i := p && io.l2_wr_ready_i
  io.done_o := ctl.io.done; io.status_o := ctl.io.status; io.reset_required_o := ctl.io.resetRequired
  io.matrix_steps_o := ctl.io.matrixSteps; io.values_o := ctl.io.values; io.weight_tile_loads_o := ctl.io.weightLoads; io.norm_batch_loads_o := ctl.io.normLoads
  io.ddr_read_bytes_o := ctl.io.readBytes; io.ddr_write_bytes_o := ctl.io.writeBytes
}
