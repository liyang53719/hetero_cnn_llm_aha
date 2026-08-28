// SPDX-License-Identifier: Apache-2.0
// Structural four-context, fixed 16x32 BF16 array with lane-local state.
`timescale 1ns/1ps
module bf16_outer_product_context_array #(
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
  logic scheduler_array_in_valid, scheduler_array_in_ready;
  logic scheduler_array_out_valid, scheduler_array_out_ready;
  logic [1:0] issue_context, completion_context;
  logic issue_clear, issue_bypass, issue_use_bank, completion_fire;
  logic [511:0] lane_pre_write, lane_mul_write, lane_post_write;
  logic [511:0] lane_output_write, lane_rst_ni;
  logic [1023:0] lane_issue_context, lane_completion_context;
  logic [511:0] lane_issue_clear, lane_issue_bypass, lane_issue_use_bank;
  logic [511:0] lane_completion_fire;
  logic [LANES*32-1:0] lane_result;
  logic [LANES*5-1:0] lane_flags;
  logic [31:0] array_accepted_unused, array_completed_unused;

  generate
    if (ROWS == 16 && COLS == 32 && CONTEXTS == 4 && FIFO_DEPTH == 8) begin : g_production
      bf16_context_scheduler4 scheduler (
        .clk_i(clk_i), .rst_ni(rst_ni),
        .in_valid_i(in_valid_i), .in_ready_o(in_ready_o),
        .context_i(context_i), .clear_i(clear_i), .last_i(last_i),
        .out_valid_o(out_valid_o), .out_ready_i(out_ready_i),
        .context_o(context_o), .last_o(last_o),
        .array_in_valid_o(scheduler_array_in_valid),
        .array_in_ready_i(scheduler_array_in_ready),
        .array_out_valid_i(scheduler_array_out_valid),
        .array_out_ready_o(scheduler_array_out_ready),
        .issue_context_o(issue_context), .issue_clear_o(issue_clear),
        .issue_bypass_o(issue_bypass), .issue_use_bank_o(issue_use_bank),
        .completion_fire_o(completion_fire),
        .completion_context_o(completion_context),
        .busy_o(busy_o), .accumulator_valid_o(accumulator_valid_o),
        .accepted_steps_o(accepted_steps_o),
        .completed_steps_o(completed_steps_o),
        .protocol_error_o(protocol_error_o)
      );

      bf16_outer_product_array_control512 array_control (
        .clk_i(clk_i), .rst_ni(rst_ni),
        .in_valid_i(scheduler_array_in_valid),
        .in_ready_o(scheduler_array_in_ready),
        .out_valid_o(scheduler_array_out_valid),
        .out_ready_i(scheduler_array_out_ready),
        .lane_pre_write_o(lane_pre_write),
        .lane_mul_write_o(lane_mul_write),
        .lane_post_write_o(lane_post_write),
        .lane_output_write_o(lane_output_write),
        .accepted_steps_o(array_accepted_unused),
        .completed_steps_o(array_completed_unused)
      );

      bf16_context_control_broadcast512 context_broadcast (
        .issue_context_i(issue_context), .issue_clear_i(issue_clear),
        .issue_bypass_i(issue_bypass), .issue_use_bank_i(issue_use_bank),
        .completion_fire_i(completion_fire),
        .completion_context_i(completion_context),
        .lane_issue_context_o(lane_issue_context),
        .lane_issue_clear_o(lane_issue_clear),
        .lane_issue_bypass_o(lane_issue_bypass),
        .lane_issue_use_bank_o(lane_issue_use_bank),
        .lane_completion_fire_o(lane_completion_fire),
        .lane_completion_context_o(lane_completion_context)
      );

      bf16_outer_product_array_glue512 glue (
        .rst_ni(rst_ni), .lane_flags_i(lane_flags),
        .lane_rst_ni_o(lane_rst_ni), .flags_o(exception_flags_o)
      );

      for (genvar row = 0; row < 16; row++) begin : g_row
        for (genvar col = 0; col < 32; col++) begin : g_col
          localparam integer LANE = row * 32 + col;
          bf16_context_fma_pipeline_lane4 lane (
            .clk_i(clk_i), .rst_ni(lane_rst_ni[LANE]),
            .pre_write_i(lane_pre_write[LANE]),
            .mul_write_i(lane_mul_write[LANE]),
            .post_write_i(lane_post_write[LANE]),
            .output_write_i(lane_output_write[LANE]),
            .a_i(a_i[row*16 +: 16]), .b_i(b_i[col*16 +: 16]),
            .issue_context_i(lane_issue_context[LANE*2 +: 2]),
            .issue_clear_i(lane_issue_clear[LANE]),
            .issue_bypass_i(lane_issue_bypass[LANE]),
            .issue_use_bank_i(lane_issue_use_bank[LANE]),
            .completion_fire_i(lane_completion_fire[LANE]),
            .completion_context_i(lane_completion_context[LANE*2 +: 2]),
            .out_o(lane_result[LANE*32 +: 32]),
            .flags_o(lane_flags[LANE*5 +: 5])
          );
        end
      end
      assign acc_o = lane_result;
    end else begin : g_unsupported
      initial $fatal(1, "production context array requires 16x32, 4 contexts, FIFO 8");
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
