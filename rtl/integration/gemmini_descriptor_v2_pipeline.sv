// SPDX-License-Identifier: Apache-2.0
// Production schema-v2 Matrix frontend through retained Rocket CUSTOM_3.
`timescale 1ns/1ps
module gemmini_descriptor_v2_pipeline(
  input logic clk_i,input logic rst_ni,
  input logic cmd_valid_i,output logic cmd_ready_o,input logic[127:0]cmd_data_i,
  input logic[63:0]descriptor_base_i,
  output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,
  output logic[23:0]descriptor_req_index_o,output logic[63:0]descriptor_req_byte_addr_o,
  input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,
  input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
  output logic scale_req_valid_o,input logic scale_req_ready_i,output logic[47:0]scale_req_addr_o,
  input logic scale_rsp_valid_i,output logic scale_rsp_ready_o,input logic[31:0]scale_rsp_data_i,
  input logic scale_rsp_error_i,
  output logic rocc_cmd_valid_o,input logic rocc_cmd_ready_i,
  output logic[6:0]rocc_inst_funct_o,output logic[4:0]rocc_inst_rs2_o,
  output logic[4:0]rocc_inst_rs1_o,output logic rocc_inst_xd_o,
  output logic rocc_inst_xs1_o,output logic rocc_inst_xs2_o,
  output logic[4:0]rocc_inst_rd_o,output logic[6:0]rocc_inst_opcode_o,
  output logic[63:0]rocc_rs1_o,output logic[63:0]rocc_rs2_o,input logic rocc_busy_i,
  output logic event_valid_o,input logic event_ready_i,output logic[55:0]event_data_o,
  output logic illegal_program_o
);
  logic snap_valid,snap_ready,snap_legal;logic[7:0]snap_status;logic[127:0]snap_cmd;logic[6:0]snap_count;
  logic rec_valid,rec_ready;logic[1:0]rec_chain;logic[23:0]rec_index;logic[127:0]rec_data;logic rec_first,rec_last;
  logic ctx_valid,ctx_ready,ctx_legal;logic[7:0]ctx_status;logic[127:0]ctx_cmd;
  logic[255:0]ctx_addr;logic[287:0]ctx_shape,ctx_stride;logic[47:0]ctx_meta;
  logic[71:0]ctx_op,ctx_aux,ctx_conv;logic ctx_conv_valid;logic[1:0]ctx_quant_valid;logic[143:0]ctx_quant;
  logic op_valid,op_ready,op_first,op_last,op_legal;logic[7:0]op_status;
  logic[15:0]op_event;logic[6:0]op_funct;logic[63:0]op_rs1,op_rs2;

  matrix_descriptor_v2_snapshot u_snapshot(.*,
    .snapshot_valid_o(snap_valid),.snapshot_ready_i(snap_ready),.snapshot_legal_o(snap_legal),
    .snapshot_status_o(snap_status),.snapshot_command_o(snap_cmd),.snapshot_record_count_o(snap_count),
    .record_valid_o(rec_valid),.record_ready_i(rec_ready),.record_chain_o(rec_chain),
    .record_index_o(rec_index),.record_data_o(rec_data),.record_first_o(rec_first),.record_last_o(rec_last));
  matrix_descriptor_v2_decode u_decode(
    .clk_i,.rst_ni,.snapshot_valid_i(snap_valid),.snapshot_ready_o(snap_ready),
    .snapshot_legal_i(snap_legal),.snapshot_status_i(snap_status),.snapshot_command_i(snap_cmd),
    .snapshot_record_count_i(snap_count),.record_valid_i(rec_valid),.record_ready_o(rec_ready),
    .record_chain_i(rec_chain),.record_index_i(rec_index),.record_data_i(rec_data),
    .record_first_i(rec_first),.record_last_i(rec_last),.context_valid_o(ctx_valid),
    .context_ready_i(ctx_ready),.context_legal_o(ctx_legal),.context_status_o(ctx_status),
    .context_command_o(ctx_cmd),.tensor_addr_o(ctx_addr),.tensor_shape_o(ctx_shape),
    .tensor_stride_o(ctx_stride),.tensor_meta_o(ctx_meta),.matrix_op_payload_o(ctx_op),
    .matrix_aux_payload_o(ctx_aux),.conv_valid_o(ctx_conv_valid),.conv_payload_o(ctx_conv),
    .quant_valid_o(ctx_quant_valid),.quant_payload_o(ctx_quant));
  gemmini_descriptor_v2_emitter u_emitter(
    .clk_i,.rst_ni,.context_valid_i(ctx_valid),.context_ready_o(ctx_ready),
    .context_legal_i(ctx_legal),.context_status_i(ctx_status),.context_command_i(ctx_cmd),
    .tensor_addr_i(ctx_addr),.tensor_shape_i(ctx_shape),.tensor_stride_i(ctx_stride),
    .tensor_meta_i(ctx_meta),.matrix_op_payload_i(ctx_op),.matrix_aux_payload_i(ctx_aux),
    .conv_valid_i(ctx_conv_valid),.conv_payload_i(ctx_conv),.quant_valid_i(ctx_quant_valid),
    .quant_payload_i(ctx_quant),.op_valid_o(op_valid),.op_ready_i(op_ready),
    .op_first_o(op_first),.op_last_o(op_last),.op_legal_o(op_legal),.op_status_o(op_status),
    .op_event_id_o(op_event),.op_funct_o(op_funct),.op_rs1_o(op_rs1),.op_rs2_o(op_rs2),.*);
  gemmini_rocc_program_adapter u_program(
    .clk_i,.rst_ni,.op_valid_i(op_valid),.op_ready_o(op_ready),.op_first_i(op_first),
    .op_last_i(op_last),.op_legal_i(op_legal),.op_status_i(op_status),.event_id_i(op_event),
    .op_funct_i(op_funct),.op_rs1_i(op_rs1),.op_rs2_i(op_rs2),.*);
endmodule
