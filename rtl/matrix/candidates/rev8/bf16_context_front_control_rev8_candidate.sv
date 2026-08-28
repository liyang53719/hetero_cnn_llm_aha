// SPDX-License-Identifier: Apache-2.0
// Revision 8A scalar front-control implementation hierarchy.
// It jointly contains the existing four-context scheduler, the unchanged
// four-stage elastic valid chain, and aligned context metadata.  No payload or
// accumulator data is stored here and no architectural cycle is added.
`timescale 1ns/1ps
module bf16_context_front_control_rev8_candidate (
  input  logic       clk_i,
  input  logic       rst_ni,
  input  logic       in_valid_i,
  output logic       in_ready_o,
  input  logic [1:0] context_i,
  input  logic       clear_i,
  input  logic       last_i,
  output logic       out_valid_o,
  input  logic       out_ready_i,
  output logic [1:0] context_o,
  output logic       last_o,
  output logic [3:0] busy_o,
  output logic [3:0] accumulator_valid_o,
  output logic [31:0] accepted_steps_o,
  output logic [31:0] completed_steps_o,
  output logic       protocol_error_o,
  output logic       pre_write_o,
  output logic       mul_write_o,
  output logic       post_write_o,
  output logic       output_write_o,
  output logic [1:0] issue_context_o,
  output logic       issue_clear_o,
  output logic [1:0] early_commit_context_o,
  output logic [1:0] output_context_o
);
  logic scheduler_array_in_valid, scheduler_array_in_ready;
  logic scheduler_array_out_valid, scheduler_array_out_ready;
  logic issue_bypass_unused, issue_use_bank_unused;
  logic completion_fire_unused;
  logic [1:0] completion_context_unused;
  logic [31:0] array_accepted_unused, array_completed_unused;
  logic scheduler_protocol_error, tag_mismatch_q;

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
    .issue_context_o(issue_context_o), .issue_clear_o(issue_clear_o),
    .issue_bypass_o(issue_bypass_unused),
    .issue_use_bank_o(issue_use_bank_unused),
    .completion_fire_o(completion_fire_unused),
    .completion_context_o(completion_context_unused),
    .busy_o(busy_o), .accumulator_valid_o(accumulator_valid_o),
    .accepted_steps_o(accepted_steps_o),
    .completed_steps_o(completed_steps_o),
    .protocol_error_o(scheduler_protocol_error)
  );

  bf16_outer_product_array_control_rev8_candidate array_control (
    .clk_i(clk_i), .rst_ni(rst_ni),
    .in_valid_i(scheduler_array_in_valid),
    .in_ready_o(scheduler_array_in_ready),
    .out_valid_o(scheduler_array_out_valid),
    .out_ready_i(scheduler_array_out_ready),
    .pre_write_o(pre_write_o), .mul_write_o(mul_write_o),
    .post_write_o(post_write_o), .output_write_o(output_write_o),
    .accepted_steps_o(array_accepted_unused),
    .completed_steps_o(array_completed_unused)
  );

  bf16_context_tag_pipeline4_rev8_candidate tags (
    .clk_i(clk_i), .rst_ni(rst_ni),
    .pre_write_i(pre_write_o), .mul_write_i(mul_write_o),
    .post_write_i(post_write_o), .output_write_i(output_write_o),
    .issue_context_i(issue_context_o),
    .early_commit_context_o(early_commit_context_o),
    .output_context_o(output_context_o)
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni)
      tag_mismatch_q <= 1'b0;
    else if (out_valid_o && output_context_o != context_o)
      tag_mismatch_q <= 1'b1;
  end
  assign protocol_error_o = scheduler_protocol_error | tag_mismatch_q;
endmodule
