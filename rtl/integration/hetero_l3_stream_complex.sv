// SPDX-License-Identifier: Apache-2.0
// Production Matrix/AHA/KV direct-stream complex with fixed channel mapping.
`timescale 1ns/1ps
module hetero_l3_stream_complex (
  input  logic          clk_i,
  input  logic          rst_ni,

  input  logic          matrix_cfg_valid_i,
  output logic          matrix_cfg_ready_o,
  input  logic          matrix_cfg_direction_i,
  input  logic          matrix_cfg_route_i,
  input  logic [11:0]   matrix_cfg_last_addr_i,
  input  logic [15:0]   matrix_cfg_tag_i,
  input  logic [11:0]   matrix_cfg_tensor_id_i,
  input  logic [3:0]    matrix_cfg_format_i,
  input  logic [3:0]    matrix_spad_write_valid_i,
  output logic [3:0]    matrix_spad_write_ready_o,
  input  logic [47:0]   matrix_spad_write_addr_i,
  input  logic [511:0]  matrix_spad_write_data_i,
  input  logic [63:0]   matrix_spad_write_mask_i,
  input  logic [3:0]    matrix_spad_read_req_valid_i,
  output logic [3:0]    matrix_spad_read_req_ready_o,
  input  logic [47:0]   matrix_spad_read_req_addr_i,
  output logic [3:0]    matrix_spad_read_resp_valid_o,
  input  logic [3:0]    matrix_spad_read_resp_ready_i,
  output logic [511:0]  matrix_spad_read_resp_data_o,
  output logic          matrix_transfer_done_o,
  output logic [31:0]   matrix_protocol_error_count_o,

  input  logic          aha_cfg_valid_i,
  output logic          aha_cfg_ready_o,
  input  logic [17:0]   aha_cfg_input_base_i,
  input  logic [17:0]   aha_cfg_output_base_i,
  input  logic [15:0]   aha_cfg_input_beats_i,
  input  logic [15:0]   aha_cfg_output_beats_i,
  input  logic [15:0]   aha_cfg_output_tag_i,
  input  logic [11:0]   aha_cfg_output_tensor_id_i,
  input  logic [3:0]    aha_cfg_output_format_i,
  input  logic [63:0]   aha_cfg_output_last_be_i,
  input  logic          aha_run_done_i,
  output logic          aha_proc_packet_wr_en_o,
  output logic [17:0]   aha_proc_packet_wr_addr_o,
  output logic [63:0]   aha_proc_packet_wr_data_o,
  output logic [7:0]    aha_proc_packet_wr_strb_o,
  output logic          aha_proc_packet_rd_en_o,
  output logic [17:0]   aha_proc_packet_rd_addr_o,
  input  logic [63:0]   aha_proc_packet_rd_data_i,
  input  logic          aha_proc_packet_rd_data_valid_i,
  output logic          aha_native_eos_o,
  output logic          aha_transfer_done_o,
  output logic [31:0]   aha_protocol_error_count_o,

  input  logic          kv_cfg_valid_i,
  output logic          kv_cfg_ready_o,
  input  logic          kv_cfg_direction_i,
  input  logic [18:0]   kv_cfg_base_addr_i,
  input  logic [15:0]   kv_cfg_beats_i,
  input  logic [15:0]   kv_cfg_tag_i,
  input  logic [11:0]   kv_cfg_tensor_id_i,
  input  logic [3:0]    kv_cfg_format_i,
  input  logic [63:0]   kv_cfg_last_be_i,
  output logic          kv_mem_write_valid_o,
  input  logic          kv_mem_write_ready_i,
  output logic [18:0]   kv_mem_write_addr_o,
  output logic [511:0]  kv_mem_write_data_o,
  output logic [63:0]   kv_mem_write_be_o,
  output logic          kv_mem_read_req_valid_o,
  input  logic          kv_mem_read_req_ready_i,
  output logic [18:0]   kv_mem_read_req_addr_o,
  input  logic          kv_mem_read_rsp_valid_i,
  output logic          kv_mem_read_rsp_ready_o,
  input  logic [511:0]  kv_mem_read_rsp_data_i,
  input  logic          kv_mem_read_rsp_error_i,
  output logic          kv_transfer_done_o,
  output logic [31:0]   kv_protocol_error_count_o
);
  logic matrix_tx_valid, matrix_tx_ready, matrix_tx_route, matrix_tx_last;
  logic [511:0] matrix_tx_data;
  logic [63:0] matrix_tx_be;
  logic [15:0] matrix_tx_tag;
  logic [11:0] matrix_tx_tensor;
  logic [3:0] matrix_tx_format;
  logic matrix_rx_valid, matrix_rx_ready, matrix_rx_route, matrix_rx_last;
  logic [511:0] matrix_rx_data;
  logic [63:0] matrix_rx_be;
  logic [15:0] matrix_rx_tag;
  logic [11:0] matrix_rx_tensor;
  logic [3:0] matrix_rx_format;

  logic aha_in_ready, aha_out_valid, aha_out_ready, aha_out_last;
  logic [511:0] aha_out_data;
  logic [63:0] aha_out_be;
  logic [15:0] aha_out_tag;
  logic [11:0] aha_out_tensor;
  logic [3:0] aha_out_format;
  logic kv_in_ready, kv_out_valid, kv_out_ready, kv_out_last;
  logic [511:0] kv_out_data;
  logic [63:0] kv_out_be;
  logic [15:0] kv_out_tag;
  logic [11:0] kv_out_tensor;
  logic [3:0] kv_out_format;

  logic [3:0] stream_in_valid, stream_in_ready, stream_in_last;
  logic [2047:0] stream_in_data;
  logic [255:0] stream_in_be;
  logic [63:0] stream_in_tag;
  logic [47:0] stream_in_tensor;
  logic [15:0] stream_in_format;
  logic [3:0] stream_out_valid, stream_out_ready, stream_out_last;
  logic [2047:0] stream_out_data;
  logic [255:0] stream_out_be;
  logic [63:0] stream_out_tag;
  logic [47:0] stream_out_tensor;
  logic [15:0] stream_out_format;

  gemmini_spad_tensor_gateway u_matrix_gateway (
    .clk_i, .rst_ni, .cfg_valid_i(matrix_cfg_valid_i),
    .cfg_ready_o(matrix_cfg_ready_o), .cfg_direction_i(matrix_cfg_direction_i),
    .cfg_route_i(matrix_cfg_route_i), .cfg_last_addr_i(matrix_cfg_last_addr_i),
    .cfg_tag_i(matrix_cfg_tag_i), .cfg_tensor_id_i(matrix_cfg_tensor_id_i),
    .cfg_format_i(matrix_cfg_format_i),
    .spad_write_valid_i(matrix_spad_write_valid_i),
    .spad_write_ready_o(matrix_spad_write_ready_o),
    .spad_write_addr_i(matrix_spad_write_addr_i),
    .spad_write_data_i(matrix_spad_write_data_i),
    .spad_write_mask_i(matrix_spad_write_mask_i),
    .spad_read_req_valid_i(matrix_spad_read_req_valid_i),
    .spad_read_req_ready_o(matrix_spad_read_req_ready_o),
    .spad_read_req_addr_i(matrix_spad_read_req_addr_i),
    .spad_read_resp_valid_o(matrix_spad_read_resp_valid_o),
    .spad_read_resp_ready_i(matrix_spad_read_resp_ready_i),
    .spad_read_resp_data_o(matrix_spad_read_resp_data_o),
    .tx_valid_o(matrix_tx_valid), .tx_ready_i(matrix_tx_ready),
    .tx_route_o(matrix_tx_route), .tx_data_o(matrix_tx_data),
    .tx_be_o(matrix_tx_be), .tx_tag_o(matrix_tx_tag),
    .tx_tensor_id_o(matrix_tx_tensor), .tx_last_o(matrix_tx_last),
    .tx_format_o(matrix_tx_format), .rx_valid_i(matrix_rx_valid),
    .rx_ready_o(matrix_rx_ready), .rx_route_i(matrix_rx_route),
    .rx_data_i(matrix_rx_data), .rx_be_i(matrix_rx_be),
    .rx_tag_i(matrix_rx_tag), .rx_tensor_id_i(matrix_rx_tensor),
    .rx_last_i(matrix_rx_last), .rx_format_i(matrix_rx_format),
    .transfer_done_o(matrix_transfer_done_o),
    .protocol_error_count_o(matrix_protocol_error_count_o)
  );

  aha_tensor_stream_endpoint u_aha_endpoint (
    .clk_i, .rst_ni, .cfg_valid_i(aha_cfg_valid_i), .cfg_ready_o(aha_cfg_ready_o),
    .cfg_input_base_i(aha_cfg_input_base_i), .cfg_output_base_i(aha_cfg_output_base_i),
    .cfg_input_beats_i(aha_cfg_input_beats_i), .cfg_output_beats_i(aha_cfg_output_beats_i),
    .cfg_output_tag_i(aha_cfg_output_tag_i),
    .cfg_output_tensor_id_i(aha_cfg_output_tensor_id_i),
    .cfg_output_format_i(aha_cfg_output_format_i),
    .cfg_output_last_be_i(aha_cfg_output_last_be_i), .run_done_i(aha_run_done_i),
    .stream_in_valid_i(stream_out_valid[0]), .stream_in_ready_o(aha_in_ready),
    .stream_in_data_i(stream_out_data[0*512 +: 512]),
    .stream_in_be_i(stream_out_be[0*64 +: 64]),
    .stream_in_tag_i(stream_out_tag[0*16 +: 16]),
    .stream_in_tensor_id_i(stream_out_tensor[0*12 +: 12]),
    .stream_in_last_i(stream_out_last[0]),
    .stream_in_format_i(stream_out_format[0*4 +: 4]),
    .stream_out_valid_o(aha_out_valid), .stream_out_ready_i(aha_out_ready),
    .stream_out_data_o(aha_out_data), .stream_out_be_o(aha_out_be),
    .stream_out_tag_o(aha_out_tag), .stream_out_tensor_id_o(aha_out_tensor),
    .stream_out_last_o(aha_out_last), .stream_out_format_o(aha_out_format),
    .proc_packet_wr_en_o(aha_proc_packet_wr_en_o),
    .proc_packet_wr_addr_o(aha_proc_packet_wr_addr_o),
    .proc_packet_wr_data_o(aha_proc_packet_wr_data_o),
    .proc_packet_wr_strb_o(aha_proc_packet_wr_strb_o),
    .proc_packet_rd_en_o(aha_proc_packet_rd_en_o),
    .proc_packet_rd_addr_o(aha_proc_packet_rd_addr_o),
    .proc_packet_rd_data_i(aha_proc_packet_rd_data_i),
    .proc_packet_rd_data_valid_i(aha_proc_packet_rd_data_valid_i),
    .native_eos_o(aha_native_eos_o), .transfer_done_o(aha_transfer_done_o),
    .protocol_error_count_o(aha_protocol_error_count_o)
  );

  kv_tensor_stream_endpoint u_kv_endpoint (
    .clk_i, .rst_ni, .cfg_valid_i(kv_cfg_valid_i), .cfg_ready_o(kv_cfg_ready_o),
    .cfg_direction_i(kv_cfg_direction_i), .cfg_base_addr_i(kv_cfg_base_addr_i),
    .cfg_beats_i(kv_cfg_beats_i), .cfg_tag_i(kv_cfg_tag_i),
    .cfg_tensor_id_i(kv_cfg_tensor_id_i), .cfg_format_i(kv_cfg_format_i),
    .cfg_last_be_i(kv_cfg_last_be_i),
    .stream_in_valid_i(stream_out_valid[2]), .stream_in_ready_o(kv_in_ready),
    .stream_in_data_i(stream_out_data[2*512 +: 512]),
    .stream_in_be_i(stream_out_be[2*64 +: 64]),
    .stream_in_tag_i(stream_out_tag[2*16 +: 16]),
    .stream_in_tensor_id_i(stream_out_tensor[2*12 +: 12]),
    .stream_in_last_i(stream_out_last[2]),
    .stream_in_format_i(stream_out_format[2*4 +: 4]),
    .stream_out_valid_o(kv_out_valid), .stream_out_ready_i(kv_out_ready),
    .stream_out_data_o(kv_out_data), .stream_out_be_o(kv_out_be),
    .stream_out_tag_o(kv_out_tag), .stream_out_tensor_id_o(kv_out_tensor),
    .stream_out_last_o(kv_out_last), .stream_out_format_o(kv_out_format),
    .mem_write_valid_o(kv_mem_write_valid_o),
    .mem_write_ready_i(kv_mem_write_ready_i), .mem_write_addr_o(kv_mem_write_addr_o),
    .mem_write_data_o(kv_mem_write_data_o), .mem_write_be_o(kv_mem_write_be_o),
    .mem_read_req_valid_o(kv_mem_read_req_valid_o),
    .mem_read_req_ready_i(kv_mem_read_req_ready_i),
    .mem_read_req_addr_o(kv_mem_read_req_addr_o),
    .mem_read_rsp_valid_i(kv_mem_read_rsp_valid_i),
    .mem_read_rsp_ready_o(kv_mem_read_rsp_ready_o),
    .mem_read_rsp_data_i(kv_mem_read_rsp_data_i),
    .mem_read_rsp_error_i(kv_mem_read_rsp_error_i),
    .transfer_done_o(kv_transfer_done_o),
    .protocol_error_count_o(kv_protocol_error_count_o)
  );

  matrix_direct_streams u_streams (
    .clk_i, .rst_ni, .in_valid_i(stream_in_valid), .in_ready_o(stream_in_ready),
    .in_data_i(stream_in_data), .in_be_i(stream_in_be), .in_tag_i(stream_in_tag),
    .in_tensor_id_i(stream_in_tensor), .in_last_i(stream_in_last),
    .in_format_i(stream_in_format), .out_valid_o(stream_out_valid),
    .out_ready_i(stream_out_ready), .out_data_o(stream_out_data),
    .out_be_o(stream_out_be), .out_tag_o(stream_out_tag),
    .out_tensor_id_o(stream_out_tensor), .out_last_o(stream_out_last),
    .out_format_o(stream_out_format)
  );

  always_comb begin
    stream_in_valid = 0;
    stream_in_data = 0;
    stream_in_be = 0;
    stream_in_tag = 0;
    stream_in_tensor = 0;
    stream_in_last = 0;
    stream_in_format = 0;
    stream_out_ready = 0;

    stream_in_valid[matrix_tx_route ? 2 : 0] = matrix_tx_valid;
    stream_in_data[(matrix_tx_route ? 2 : 0)*512 +: 512] = matrix_tx_data;
    stream_in_be[(matrix_tx_route ? 2 : 0)*64 +: 64] = matrix_tx_be;
    stream_in_tag[(matrix_tx_route ? 2 : 0)*16 +: 16] = matrix_tx_tag;
    stream_in_tensor[(matrix_tx_route ? 2 : 0)*12 +: 12] = matrix_tx_tensor;
    stream_in_last[matrix_tx_route ? 2 : 0] = matrix_tx_last;
    stream_in_format[(matrix_tx_route ? 2 : 0)*4 +: 4] = matrix_tx_format;
    matrix_tx_ready = stream_in_ready[matrix_tx_route ? 2 : 0];

    stream_in_valid[1] = aha_out_valid;
    stream_in_data[1*512 +: 512] = aha_out_data;
    stream_in_be[1*64 +: 64] = aha_out_be;
    stream_in_tag[1*16 +: 16] = aha_out_tag;
    stream_in_tensor[1*12 +: 12] = aha_out_tensor;
    stream_in_last[1] = aha_out_last;
    stream_in_format[1*4 +: 4] = aha_out_format;
    aha_out_ready = stream_in_ready[1];

    stream_in_valid[3] = kv_out_valid;
    stream_in_data[3*512 +: 512] = kv_out_data;
    stream_in_be[3*64 +: 64] = kv_out_be;
    stream_in_tag[3*16 +: 16] = kv_out_tag;
    stream_in_tensor[3*12 +: 12] = kv_out_tensor;
    stream_in_last[3] = kv_out_last;
    stream_in_format[3*4 +: 4] = kv_out_format;
    kv_out_ready = stream_in_ready[3];

    stream_out_ready[0] = aha_in_ready;
    stream_out_ready[2] = kv_in_ready;
    stream_out_ready[matrix_cfg_route_i ? 3 : 1] = matrix_rx_ready;
    matrix_rx_valid = stream_out_valid[matrix_cfg_route_i ? 3 : 1];
    matrix_rx_data = stream_out_data[(matrix_cfg_route_i ? 3 : 1)*512 +: 512];
    matrix_rx_be = stream_out_be[(matrix_cfg_route_i ? 3 : 1)*64 +: 64];
    matrix_rx_tag = stream_out_tag[(matrix_cfg_route_i ? 3 : 1)*16 +: 16];
    matrix_rx_tensor = stream_out_tensor[(matrix_cfg_route_i ? 3 : 1)*12 +: 12];
    matrix_rx_last = stream_out_last[matrix_cfg_route_i ? 3 : 1];
    matrix_rx_format = stream_out_format[(matrix_cfg_route_i ? 3 : 1)*4 +: 4];
    matrix_rx_route = matrix_cfg_route_i;
  end
endmodule
