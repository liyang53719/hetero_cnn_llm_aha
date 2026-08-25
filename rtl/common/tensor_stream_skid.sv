// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module tensor_stream_skid (
  input logic clk_i,input logic rst_ni,
  input logic in_valid_i,output logic in_ready_o,
  input logic[511:0] in_data_i,input logic[63:0] in_be_i,
  input logic[15:0] in_tag_i,input logic[11:0] in_tensor_id_i,
  input logic in_last_i,input logic[3:0] in_format_i,
  output logic out_valid_o,input logic out_ready_i,
  output logic[511:0] out_data_o,output logic[63:0] out_be_o,
  output logic[15:0] out_tag_o,output logic[11:0] out_tensor_id_o,
  output logic out_last_o,output logic[3:0] out_format_o
);
  logic full_q;
  logic[511:0] data_q;
  logic[63:0] be_q;
  logic[15:0] tag_q;
  logic[11:0] tensor_id_q;
  logic last_q;
  logic[3:0] format_q;
  assign in_ready_o=!full_q||out_ready_i;
  assign out_valid_o=full_q;
  assign out_data_o=data_q;assign out_be_o=be_q;assign out_tag_o=tag_q;
  assign out_tensor_id_o=tensor_id_q;assign out_last_o=last_q;assign out_format_o=format_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      full_q<=0;data_q<='0;be_q<='0;tag_q<='0;tensor_id_q<='0;last_q<=0;format_q<='0;
    end else if(in_ready_o) begin
      if(in_valid_i) begin
        full_q<=1;data_q<=in_data_i;be_q<=in_be_i;tag_q<=in_tag_i;
        tensor_id_q<=in_tensor_id_i;last_q<=in_last_i;format_q<=in_format_i;
      end else if(out_ready_i) full_q<=0;
    end
  end
endmodule
