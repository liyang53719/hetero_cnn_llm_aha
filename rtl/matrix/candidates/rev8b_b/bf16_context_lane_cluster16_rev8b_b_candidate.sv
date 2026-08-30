// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_context_lane_cluster16_rev8b_b_candidate (
  input logic clk_i,
  input logic [15:0] lane_rst_ni_i,
  input logic input_write_i,pre_write_i,mul_write_i,post_write_i,output_write_i,
  input logic [16*16-1:0] lane_a_i,lane_b_i,
  input logic [2:0] issue_context_i,
  input logic issue_clear_i,
  input logic [2:0] early_commit_context_i,output_context_i,
  output logic [16*32-1:0] lane_out_o,
  output logic [16*5-1:0] lane_flags_o
);
  for(genvar lane=0;lane<16;lane++)begin:g_lane
    logic [4:0] bank_valid_unused;
    bf16_context_fma_pipeline_lane5_rev8b_b_candidate u_lane(
      .clk_i(clk_i),.rst_ni(lane_rst_ni_i[lane]),
      .input_write_i(input_write_i),.pre_write_i(pre_write_i),.mul_write_i(mul_write_i),
      .post_write_i(post_write_i),.output_write_i(output_write_i),
      .a_i(lane_a_i[lane*16+:16]),.b_i(lane_b_i[lane*16+:16]),
      .issue_context_i(issue_context_i),.issue_clear_i(issue_clear_i),
      .early_commit_context_i(early_commit_context_i),.output_context_i(output_context_i),
      .out_o(lane_out_o[lane*32+:32]),.flags_o(lane_flags_o[lane*5+:5]),
      .bank_valid_o(bank_valid_unused));
  end
endmodule
