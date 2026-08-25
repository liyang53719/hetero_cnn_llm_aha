// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module l2_512b_macro_bank_group (
  input logic clk_i, input logic rst_ni,
  input logic req_valid_i, output logic req_ready_o,
  input logic req_write_i, input logic [12:0] req_row_i,
  input logic [511:0] req_wdata_i, input logic [63:0] req_wstrb_i,
  output logic rsp_valid_o, input logic rsp_ready_i,
  output logic rsp_error_o, output logic [511:0] rsp_rdata_o
);
  logic [3:0] lane_req_valid,lane_req_ready,lane_rsp_valid,lane_rsp_ready,lane_rsp_error;
  logic [4*128-1:0] lane_rdata;
  logic all_req_ready,all_rsp_valid;
  assign all_req_ready=&lane_req_ready;
  assign all_rsp_valid=&lane_rsp_valid;
  assign req_ready_o=all_req_ready;
  assign lane_req_valid={4{req_valid_i&&all_req_ready}};
  assign rsp_valid_o=all_rsp_valid;
  assign lane_rsp_ready={4{rsp_ready_i&&all_rsp_valid}};
  assign rsp_error_o=|lane_rsp_error;
  assign rsp_rdata_o=lane_rdata;

  genvar lane;
  generate for(lane=0;lane<4;lane++) begin: g_lane
    l2_sp6144x128_macro_wrapper u_lane (
      .clk_i(clk_i),.rst_ni(rst_ni),
      .req_valid_i(lane_req_valid[lane]),.req_ready_o(lane_req_ready[lane]),
      .req_write_i(req_write_i),.req_addr_i(req_row_i),
      .req_wdata_i(req_wdata_i[lane*128 +: 128]),
      .req_wstrb_i(req_wstrb_i[lane*16 +: 16]),
      .rsp_valid_o(lane_rsp_valid[lane]),.rsp_ready_i(lane_rsp_ready[lane]),
      .rsp_error_o(lane_rsp_error[lane]),
      .rsp_rdata_o(lane_rdata[lane*128 +: 128]));
  end endgenerate
endmodule
