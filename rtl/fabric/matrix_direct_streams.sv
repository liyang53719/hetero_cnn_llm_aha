// SPDX-License-Identifier: Apache-2.0
// Channel order: 0 M->SFU, 1 SFU->M, 2 M->KV, 3 KV->M.
`timescale 1ns/1ps
module matrix_direct_streams (
  input logic clk_i,input logic rst_ni,
  input logic[3:0] in_valid_i,output logic[3:0] in_ready_o,
  input logic[4*512-1:0] in_data_i,input logic[4*64-1:0] in_be_i,
  input logic[4*16-1:0] in_tag_i,input logic[4*12-1:0] in_tensor_id_i,
  input logic[3:0] in_last_i,input logic[4*4-1:0] in_format_i,
  output logic[3:0] out_valid_o,input logic[3:0] out_ready_i,
  output logic[4*512-1:0] out_data_o,output logic[4*64-1:0] out_be_o,
  output logic[4*16-1:0] out_tag_o,output logic[4*12-1:0] out_tensor_id_o,
  output logic[3:0] out_last_o,output logic[4*4-1:0] out_format_o
);
  genvar channel;
  generate for(channel=0;channel<4;channel++) begin:g_channel
    tensor_stream_skid u_skid(
      .clk_i(clk_i),.rst_ni(rst_ni),
      .in_valid_i(in_valid_i[channel]),.in_ready_o(in_ready_o[channel]),
      .in_data_i(in_data_i[channel*512 +: 512]),.in_be_i(in_be_i[channel*64 +: 64]),
      .in_tag_i(in_tag_i[channel*16 +: 16]),
      .in_tensor_id_i(in_tensor_id_i[channel*12 +: 12]),
      .in_last_i(in_last_i[channel]),.in_format_i(in_format_i[channel*4 +: 4]),
      .out_valid_o(out_valid_o[channel]),.out_ready_i(out_ready_i[channel]),
      .out_data_o(out_data_o[channel*512 +: 512]),.out_be_o(out_be_o[channel*64 +: 64]),
      .out_tag_o(out_tag_o[channel*16 +: 16]),
      .out_tensor_id_o(out_tensor_id_o[channel*12 +: 12]),
      .out_last_o(out_last_o[channel]),.out_format_o(out_format_o[channel*4 +: 4]));
  end endgenerate
endmodule
