// SPDX-License-Identifier: Apache-2.0
// Four-stage elastic HardFloat BF16-input/FP32-accumulator outer-product tile.
`timescale 1ns/1ps
module bf16_outer_product_array #(
  parameter integer ROWS = 16,
  parameter integer COLS = 32,
  localparam integer LANES = ROWS * COLS
)(
  input logic clk_i, rst_ni, input logic in_valid_i, output logic in_ready_o,
  input logic [ROWS*16-1:0] a_i, input logic [COLS*16-1:0] b_i,
  input logic [LANES*32-1:0] acc_i,
  output logic out_valid_o, input logic out_ready_i,
  output logic [LANES*32-1:0] acc_o, output logic [4:0] exception_flags_o,
  output logic [31:0] accepted_steps_o, completed_steps_o
);
  logic pre_valid_q, mul_valid_q, post_valid_q, output_valid_q;
  logic pre_ready, mul_ready, post_ready, output_ready;
  logic [LANES*24-1:0] pre_a_comb, pre_b_comb, pre_a_q, pre_b_q;
  logic [LANES*48-1:0] pre_c_comb, pre_c_q;
  logic [LANES*54-1:0] pre_meta_comb, pre_meta_q, mul_meta_q;
  logic [LANES*49-1:0] mul_result_comb, mul_result_q;
  logic [LANES*41-1:0] post_raw_comb, post_raw_q;
  logic [LANES-1:0] post_invalid_comb, post_invalid_q;
  logic [LANES*32-1:0] round_result, output_q;
  logic [LANES*5-1:0] round_flags;
  logic [4:0] flags_comb, flags_q;
  logic issue_fire, completion_fire;
  integer flag_lane;

  assign output_ready = !output_valid_q || out_ready_i;
  assign post_ready = !post_valid_q || output_ready;
  assign mul_ready = !mul_valid_q || post_ready;
  assign pre_ready = !pre_valid_q || mul_ready;
  assign in_ready_o = pre_ready;
  assign out_valid_o = output_valid_q;
  assign acc_o = output_q;
  assign exception_flags_o = flags_q;
  assign issue_fire = in_valid_i && in_ready_o;
  assign completion_fire = out_valid_o && out_ready_i;

  always_comb begin
    flags_comb = '0;
    for (flag_lane = 0; flag_lane < LANES; flag_lane++)
      flags_comb |= round_flags[flag_lane*5 +: 5];
  end

  genvar row, col;
  generate
    for (row = 0; row < ROWS; row++) begin : g_row
      for (col = 0; col < COLS; col++) begin : g_col
        localparam integer LANE = row * COLS + col;
        HeteroBF16FmaPre u_pre (
          .io_a(a_i[row*16 +: 16]), .io_b(b_i[col*16 +: 16]),
          .io_c(acc_i[LANE*32 +: 32]),
          .io_mulAddA(pre_a_comb[LANE*24 +: 24]),
          .io_mulAddB(pre_b_comb[LANE*24 +: 24]),
          .io_mulAddC(pre_c_comb[LANE*48 +: 48]),
          .io_meta(pre_meta_comb[LANE*54 +: 54])
        );
        HeteroBF16FmaMul u_mul (
          .io_mulAddA(pre_a_q[LANE*24 +: 24]),
          .io_mulAddB(pre_b_q[LANE*24 +: 24]),
          .io_mulAddC(pre_c_q[LANE*48 +: 48]),
          .io_mulAddResult(mul_result_comb[LANE*49 +: 49])
        );
        HeteroBF16FmaPost u_post (
          .io_meta(mul_meta_q[LANE*54 +: 54]),
          .io_mulAddResult(mul_result_q[LANE*49 +: 49]),
          .io_raw(post_raw_comb[LANE*41 +: 41]),
          .io_invalid(post_invalid_comb[LANE])
        );
        HeteroBF16FmaRound u_round (
          .io_raw(post_raw_q[LANE*41 +: 41]),
          .io_invalid(post_invalid_q[LANE]),
          .io_out(round_result[LANE*32 +: 32]),
          .io_exceptionFlags(round_flags[LANE*5 +: 5])
        );
      end
    end
  endgenerate

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      pre_valid_q <= 1'b0; mul_valid_q <= 1'b0; post_valid_q <= 1'b0;
      output_valid_q <= 1'b0; pre_a_q <= '0; pre_b_q <= '0; pre_c_q <= '0;
      pre_meta_q <= '0; mul_result_q <= '0; mul_meta_q <= '0;
      post_raw_q <= '0; post_invalid_q <= '0; output_q <= '0; flags_q <= '0;
      accepted_steps_o <= '0; completed_steps_o <= '0;
    end else begin
      if (issue_fire) accepted_steps_o <= accepted_steps_o + 1'b1;
      if (completion_fire) completed_steps_o <= completed_steps_o + 1'b1;
      if (output_ready) begin
        output_valid_q <= post_valid_q;
        if (post_valid_q) begin output_q <= round_result; flags_q <= flags_comb; end
      end
      if (post_ready) begin
        post_valid_q <= mul_valid_q;
        if (mul_valid_q) begin post_raw_q <= post_raw_comb; post_invalid_q <= post_invalid_comb; end
      end
      if (mul_ready) begin
        mul_valid_q <= pre_valid_q;
        if (pre_valid_q) begin mul_result_q <= mul_result_comb; mul_meta_q <= pre_meta_q; end
      end
      if (pre_ready) begin
        pre_valid_q <= in_valid_i;
        if (in_valid_i) begin
          pre_a_q <= pre_a_comb; pre_b_q <= pre_b_comb; pre_c_q <= pre_c_comb;
          pre_meta_q <= pre_meta_comb;
        end
      end
    end
  end
endmodule
