// SPDX-License-Identifier: Apache-2.0
// Revision 8A production-geometry candidate.  Public ports and four-cycle
// arithmetic contract match bf16_outer_product_context_array.  Completion
// handshake remains architectural; accumulator data is committed one stage
// earlier into the four lane-local output/context banks.
`timescale 1ns/1ps
module bf16_outer_product_context_array_rev8_candidate #(
  parameter integer ROWS = 16,
  parameter integer COLS = 32,
  parameter integer CONTEXTS = 4,
  parameter integer FIFO_DEPTH = 8,
  localparam integer LANES = ROWS * COLS,
  localparam integer CONTEXT_BITS = (CONTEXTS <= 1) ? 1 : $clog2(CONTEXTS)
)(
  input logic clk_i, rst_ni,
  input logic in_valid_i, output logic in_ready_o,
  input logic [CONTEXT_BITS-1:0] context_i,
  input logic clear_i, last_i,
  input logic [ROWS*16-1:0] a_i,
  input logic [COLS*16-1:0] b_i,
  output logic out_valid_o, input logic out_ready_i,
  output logic [CONTEXT_BITS-1:0] context_o,
  output logic last_o,
  output logic [LANES*32-1:0] acc_o,
  output logic [4:0] exception_flags_o,
  output logic [CONTEXTS-1:0] busy_o, accumulator_valid_o,
  output logic [31:0] accepted_steps_o, completed_steps_o,
  output logic protocol_error_o
);
  logic pre_write, mul_write, post_write, output_write;
  logic [1:0] issue_context, early_commit_context, tag_output_context;
  logic issue_clear;
  logic [512*16-1:0] lane_a, lane_b;
  logic [512*32-1:0] lane_result;
  logic [512*5-1:0] lane_flags;
  logic [511:0] lane_rst_ni;

  generate
    if (ROWS == 16 && COLS == 32 && CONTEXTS == 4 && FIFO_DEPTH == 8) begin : g_production
      bf16_context_front_control_rev8_candidate front_control (
        .clk_i(clk_i), .rst_ni(rst_ni),
        .in_valid_i(in_valid_i), .in_ready_o(in_ready_o),
        .context_i(context_i), .clear_i(clear_i), .last_i(last_i),
        .out_valid_o(out_valid_o), .out_ready_i(out_ready_i),
        .context_o(context_o), .last_o(last_o),
        .busy_o(busy_o), .accumulator_valid_o(accumulator_valid_o),
        .accepted_steps_o(accepted_steps_o),
        .completed_steps_o(completed_steps_o),
        .protocol_error_o(protocol_error_o),
        .pre_write_o(pre_write), .mul_write_o(mul_write),
        .post_write_o(post_write), .output_write_o(output_write),
        .issue_context_o(issue_context), .issue_clear_o(issue_clear),
        .early_commit_context_o(early_commit_context),
        .output_context_o(tag_output_context)
      );

      for (genvar row = 0; row < 16; row++) begin : g_lane_input_row
        for (genvar col = 0; col < 32; col++) begin : g_lane_input_col
          localparam integer LANE = row * 32 + col;
          assign lane_a[LANE*16 +: 16] = a_i[row*16 +: 16];
          assign lane_b[LANE*16 +: 16] = b_i[col*16 +: 16];
        end
      end

      bf16_outer_product_array_glue512 glue (
        .rst_ni(rst_ni), .lane_flags_i(lane_flags),
        .lane_rst_ni_o(lane_rst_ni), .flags_o(exception_flags_o)
      );

      for (genvar cluster = 0; cluster < 32; cluster++) begin : g_cluster
        bf16_context_lane_cluster16_rev8_candidate u_cluster (
          .clk_i(clk_i),
          .lane_rst_ni_i(lane_rst_ni[cluster*16 +: 16]),
          .pre_write_i(pre_write), .mul_write_i(mul_write),
          .post_write_i(post_write), .output_write_i(output_write),
          .lane_a_i(lane_a[cluster*16*16 +: 16*16]),
          .lane_b_i(lane_b[cluster*16*16 +: 16*16]),
          .issue_context_i(issue_context), .issue_clear_i(issue_clear),
          .early_commit_context_i(early_commit_context),
          .output_context_i(tag_output_context),
          .lane_out_o(lane_result[cluster*16*32 +: 16*32]),
          .lane_flags_o(lane_flags[cluster*16*5 +: 16*5])
        );
      end
      assign acc_o = lane_result;

    end else begin : g_unsupported
      initial $fatal(1, "Revision 8A candidate requires 16x32, 4 contexts, FIFO 8");
      assign in_ready_o = 1'b0;
      assign out_valid_o = 1'b0;
      assign context_o = '0;
      assign last_o = 1'b0;
      assign acc_o = '0;
      assign exception_flags_o = '0;
      assign busy_o = '0;
      assign accumulator_valid_o = '0;
      assign accepted_steps_o = '0;
      assign completed_steps_o = '0;
      assign protocol_error_o = 1'b1;
    end
  endgenerate
endmodule
