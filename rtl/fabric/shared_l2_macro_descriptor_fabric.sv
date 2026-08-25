// SPDX-License-Identifier: Apache-2.0
// Production Shared-L2 composition: descriptor traffic owns read client zero;
// the remaining 512-bit client and writes retain normal fabric arbitration.
`timescale 1ns/1ps
module shared_l2_macro_descriptor_fabric #(
  parameter integer ADDR_W=15,
  parameter logic[63:0] SRAM_BYTES=64'd1572864
)(
  input logic clk_i,input logic rst_ni,input logic[63:0] descriptor_base_i,
  input logic descriptor_req_valid_i,output logic descriptor_req_ready_o,
  input logic[23:0] descriptor_req_index_i,
  output logic descriptor_rsp_valid_o,input logic descriptor_rsp_ready_i,
  output logic[127:0] descriptor_rsp_data_o,output logic descriptor_rsp_error_o,
  input logic rd_valid_i,output logic rd_ready_o,input logic[ADDR_W-1:0] rd_addr_i,
  output logic rd_resp_valid_o,input logic rd_resp_ready_i,output logic[511:0] rd_data_o,
  input logic wr_valid_i,output logic wr_ready_o,input logic[ADDR_W-1:0] wr_addr_i,
  input logic[511:0] wr_data_i,input logic[63:0] wr_be_i,
  output logic[63:0] cycle_count_o,output logic[63:0] read_count_o,
  output logic[63:0] write_count_o,output logic[63:0] bank_conflict_count_o,
  output logic[63:0] read_stall_count_o,output logic[63:0] write_stall_count_o,
  output logic[63:0] macro_error_count_o
);
  logic descriptor_fabric_req_valid,descriptor_fabric_req_ready;
  logic[ADDR_W-1:0] descriptor_fabric_req_addr;
  logic descriptor_fabric_rsp_valid,descriptor_fabric_rsp_ready,descriptor_fabric_rsp_error;
  logic[511:0] descriptor_fabric_rsp_data;
  logic[1:0] fabric_rd_valid,fabric_rd_ready,fabric_rsp_valid,fabric_rsp_ready,fabric_rsp_error;
  logic[2*ADDR_W-1:0] fabric_rd_addr;
  logic[1023:0] fabric_rsp_data;

  shared_l2_descriptor_port #(.ADDR_W(ADDR_W),.SRAM_BYTES(SRAM_BYTES)) u_descriptor(
    .clk_i,.rst_ni,.descriptor_base_i,.descriptor_req_valid_i,.descriptor_req_ready_o,
    .descriptor_req_index_i,.descriptor_rsp_valid_o,.descriptor_rsp_ready_i,
    .descriptor_rsp_data_o,.descriptor_rsp_error_o,
    .fabric_req_valid_o(descriptor_fabric_req_valid),.fabric_req_ready_i(descriptor_fabric_req_ready),
    .fabric_req_addr_o(descriptor_fabric_req_addr),.fabric_rsp_valid_i(descriptor_fabric_rsp_valid),
    .fabric_rsp_ready_o(descriptor_fabric_rsp_ready),.fabric_rsp_data_i(descriptor_fabric_rsp_data),
    .fabric_rsp_error_i(descriptor_fabric_rsp_error));

  assign fabric_rd_valid={rd_valid_i,descriptor_fabric_req_valid};
  assign descriptor_fabric_req_ready=fabric_rd_ready[0];
  assign rd_ready_o=fabric_rd_ready[1];
  assign fabric_rd_addr={rd_addr_i,descriptor_fabric_req_addr};
  assign descriptor_fabric_rsp_valid=fabric_rsp_valid[0];
  assign rd_resp_valid_o=fabric_rsp_valid[1];
  assign fabric_rsp_ready={rd_resp_ready_i,descriptor_fabric_rsp_ready};
  assign descriptor_fabric_rsp_data=fabric_rsp_data[0 +: 512];
  assign rd_data_o=fabric_rsp_data[512 +: 512];
  assign descriptor_fabric_rsp_error=fabric_rsp_error[0];

  shared_l2_macro_fabric #(.ADDR_W(ADDR_W)) u_fabric(
    .clk_i,.rst_ni,.rd_valid_i(fabric_rd_valid),.rd_ready_o(fabric_rd_ready),
    .rd_addr_i(fabric_rd_addr),.rd_resp_valid_o(fabric_rsp_valid),
    .rd_resp_ready_i(fabric_rsp_ready),.rd_resp_error_o(fabric_rsp_error),
    .rd_data_o(fabric_rsp_data),.wr_valid_i,.wr_ready_o,.wr_addr_i,.wr_data_i,.wr_be_i,
    .cycle_count_o,.read_count_o,.write_count_o,.bank_conflict_count_o,
    .read_stall_count_o,.write_stall_count_o,.macro_error_count_o);
endmodule
