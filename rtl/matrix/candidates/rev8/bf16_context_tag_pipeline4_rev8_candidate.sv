// SPDX-License-Identifier: Apache-2.0
// Revision 8A candidate: context metadata follows the existing four elastic
// data stages.  No arithmetic or architectural state is implemented here.
`timescale 1ns/1ps
module bf16_context_tag_pipeline4_rev8_candidate (
  input  logic       clk_i,
  input  logic       rst_ni,
  input  logic       pre_write_i,
  input  logic       mul_write_i,
  input  logic       post_write_i,
  input  logic       output_write_i,
  input  logic [1:0] issue_context_i,
  output logic [1:0] early_commit_context_o,
  output logic [1:0] output_context_o
);
  logic [1:0] pre_context_q, mul_context_q, post_context_q, output_context_q;

  assign early_commit_context_o = post_context_q;
  assign output_context_o = output_context_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      pre_context_q <= '0;
      mul_context_q <= '0;
      post_context_q <= '0;
      output_context_q <= '0;
    end else begin
      if (output_write_i) output_context_q <= post_context_q;
      if (post_write_i) post_context_q <= mul_context_q;
      if (mul_write_i) mul_context_q <= pre_context_q;
      if (pre_write_i) pre_context_q <= issue_context_i;
    end
  end
endmodule
