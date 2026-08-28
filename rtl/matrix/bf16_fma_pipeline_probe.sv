// SPDX-License-Identifier: Apache-2.0
// One-lane timing probe using the exact production BF16 FMA stage boundaries.
`timescale 1ns/1ps
module bf16_fma_pipeline_probe (
  input logic clk_i, rst_ni,
  input logic [15:0] a_i, b_i,
  input logic [31:0] c_i,
  output logic [31:0] out_o,
  output logic [4:0] flags_o
);
  logic [23:0] pre_a, pre_b, pre_a_q, pre_b_q;
  logic [47:0] pre_c, pre_c_q;
  logic [53:0] pre_meta, pre_meta_q, mul_meta_q;
  logic [48:0] mul_result, mul_result_q;
  logic [40:0] post_raw, post_raw_q;
  logic post_invalid, post_invalid_q;
  logic [31:0] round_out;
  logic [4:0] round_flags;

  HeteroBF16FmaPre u_pre(
    .io_a(a_i), .io_b(b_i), .io_c(c_i), .io_mulAddA(pre_a),
    .io_mulAddB(pre_b), .io_mulAddC(pre_c), .io_meta(pre_meta));
  HeteroBF16FmaMul u_mul(
    .io_mulAddA(pre_a_q), .io_mulAddB(pre_b_q), .io_mulAddC(pre_c_q),
    .io_mulAddResult(mul_result));
  HeteroBF16FmaPost u_post(
    .io_meta(mul_meta_q), .io_mulAddResult(mul_result_q),
    .io_raw(post_raw), .io_invalid(post_invalid));
  HeteroBF16FmaRound u_round(
    .io_raw(post_raw_q), .io_invalid(post_invalid_q),
    .io_out(round_out), .io_exceptionFlags(round_flags));

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      pre_a_q <= '0; pre_b_q <= '0; pre_c_q <= '0; pre_meta_q <= '0;
      mul_result_q <= '0; mul_meta_q <= '0; post_raw_q <= '0;
      post_invalid_q <= 1'b0; out_o <= '0; flags_o <= '0;
    end else begin
      pre_a_q <= pre_a; pre_b_q <= pre_b; pre_c_q <= pre_c; pre_meta_q <= pre_meta;
      mul_result_q <= mul_result; mul_meta_q <= pre_meta_q;
      post_raw_q <= post_raw; post_invalid_q <= post_invalid;
      out_o <= round_out; flags_o <= round_flags;
    end
  end
endmodule
