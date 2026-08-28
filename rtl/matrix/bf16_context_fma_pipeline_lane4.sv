// SPDX-License-Identifier: Apache-2.0
// One physical FMA lane with four lane-local FP32 accumulator contexts.
`timescale 1ns/1ps
module bf16_context_fma_pipeline_lane4 (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic pre_write_i,
  input  logic mul_write_i,
  input  logic post_write_i,
  input  logic output_write_i,
  input  logic [15:0] a_i,
  input  logic [15:0] b_i,
  input  logic [1:0] issue_context_i,
  input  logic issue_clear_i,
  input  logic issue_bypass_i,
  input  logic issue_use_bank_i,
  input  logic completion_fire_i,
  input  logic [1:0] completion_context_i,
  output logic [31:0] out_o,
  output logic [4:0] flags_o
);
  logic [31:0] accumulator_bank [0:3];
  logic [31:0] issue_accumulator;
  logic [31:0] fma_out;

  always_comb begin
    if (issue_clear_i)
      issue_accumulator = '0;
    else if (issue_bypass_i)
      issue_accumulator = fma_out;
    else if (issue_use_bank_i)
      issue_accumulator = accumulator_bank[issue_context_i];
    else
      issue_accumulator = '0;
  end

  bf16_fma_pipeline_lane fma (
    .clk_i(clk_i), .rst_ni(rst_ni),
    .pre_write_i(pre_write_i), .mul_write_i(mul_write_i),
    .post_write_i(post_write_i), .output_write_i(output_write_i),
    .a_i(a_i), .b_i(b_i), .c_i(issue_accumulator),
    .out_o(fma_out), .flags_o(flags_o)
  );

  always_ff @(posedge clk_i) begin
    if (completion_fire_i)
      accumulator_bank[completion_context_i] <= fma_out;
  end

  assign out_o = fma_out;
endmodule
