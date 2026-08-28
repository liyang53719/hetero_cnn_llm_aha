// SPDX-License-Identifier: Apache-2.0
// Revision 8A candidate: the four accumulator banks are also the output-stage
// registers.  A result is written when Post advances into Output.  External
// completion/busy/valid semantics remain in the unchanged global scheduler.
`timescale 1ns/1ps
module bf16_context_fma_pipeline_lane4_rev8_candidate (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        pre_write_i,
  input  logic        mul_write_i,
  input  logic        post_write_i,
  input  logic        output_write_i,
  input  logic [15:0] a_i,
  input  logic [15:0] b_i,
  input  logic [1:0]  issue_context_i,
  input  logic        issue_clear_i,
  input  logic [1:0]  early_commit_context_i,
  input  logic [1:0]  output_context_i,
  output logic [31:0] out_o,
  output logic [4:0]  flags_o,
  output logic [3:0]  bank_valid_o
);
  logic [31:0] accumulator_bank [0:3];
  logic [3:0] bank_valid_q;
  logic [31:0] issue_accumulator;

  logic [23:0] pre_a, pre_b, pre_a_q, pre_b_q;
  logic [47:0] pre_c, pre_c_q;
  logic [53:0] pre_meta, pre_meta_q, mul_meta_q;
  logic [48:0] mul_result, mul_result_q;
  logic [40:0] post_raw, post_raw_q;
  logic post_invalid, post_invalid_q;
  logic [31:0] round_out;
  logic [4:0] round_flags, flags_q;

  always_comb begin
    if (issue_clear_i)
      issue_accumulator = '0;
    else if (bank_valid_q[issue_context_i])
      issue_accumulator = accumulator_bank[issue_context_i];
    else
      issue_accumulator = '0;
  end

  HeteroBF16FmaPre u_pre (
    .io_a(a_i), .io_b(b_i), .io_c(issue_accumulator),
    .io_mulAddA(pre_a), .io_mulAddB(pre_b), .io_mulAddC(pre_c),
    .io_meta(pre_meta)
  );
  HeteroBF16FmaMul u_mul (
    .io_mulAddA(pre_a_q), .io_mulAddB(pre_b_q), .io_mulAddC(pre_c_q),
    .io_mulAddResult(mul_result)
  );
  HeteroBF16FmaPost u_post (
    .io_meta(mul_meta_q), .io_mulAddResult(mul_result_q),
    .io_raw(post_raw), .io_invalid(post_invalid)
  );
  HeteroBF16FmaRound u_round (
    .io_raw(post_raw_q), .io_invalid(post_invalid_q),
    .io_out(round_out), .io_exceptionFlags(round_flags)
  );

  assign out_o = bank_valid_q[output_context_i]
               ? accumulator_bank[output_context_i] : '0;
  assign flags_o = flags_q;
  assign bank_valid_o = bank_valid_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      pre_a_q <= '0;
      pre_b_q <= '0;
      pre_c_q <= '0;
      pre_meta_q <= '0;
      mul_result_q <= '0;
      mul_meta_q <= '0;
      post_raw_q <= '0;
      post_invalid_q <= 1'b0;
      bank_valid_q <= '0;
      flags_q <= '0;
    end else begin
      if (pre_write_i) begin
        pre_a_q <= pre_a;
        pre_b_q <= pre_b;
        pre_c_q <= pre_c;
        pre_meta_q <= pre_meta;
      end
      if (mul_write_i) begin
        mul_result_q <= mul_result;
        mul_meta_q <= pre_meta_q;
      end
      if (post_write_i) begin
        post_raw_q <= post_raw;
        post_invalid_q <= post_invalid;
      end
      if (output_write_i) begin
        accumulator_bank[early_commit_context_i] <= round_out;
        bank_valid_q[early_commit_context_i] <= 1'b1;
        flags_q <= round_flags;
      end
    end
  end
endmodule
