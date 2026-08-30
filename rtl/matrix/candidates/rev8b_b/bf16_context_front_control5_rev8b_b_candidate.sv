// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_context_front_control5_rev8b_b_candidate (
  input logic clk_i,rst_ni,in_valid_i,
  output logic in_ready_o,
  input logic [2:0] context_i,
  input logic clear_i,last_i,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic [2:0] context_o,
  output logic last_o,
  output logic [4:0] busy_o,accumulator_valid_o,
  output logic [31:0] accepted_steps_o,completed_steps_o,
  output logic protocol_error_o,
  output logic input_write_o,pre_write_o,mul_write_o,post_write_o,output_write_o,
  output logic [2:0] issue_context_o,
  output logic issue_clear_o,
  output logic [2:0] early_commit_context_o,output_context_o,
  output logic completion_pop_o
);
  logic array_in_valid,array_in_ready,array_out_valid,array_out_ready;
  logic completion_fire_unused;
  logic [2:0] completion_context_unused;
  logic [31:0] array_accepted_unused,array_completed_unused;
  logic scheduler_error;
  logic [2:0] tag_output_context_unused;
  bf16_context_scheduler5_rev8b_b_candidate scheduler(
    .clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(in_valid_i),.in_ready_o(in_ready_o),
    .context_i(context_i),.clear_i(clear_i),.last_i(last_i),.out_valid_o(out_valid_o),
    .out_ready_i(out_ready_i),.context_o(context_o),.last_o(last_o),
    .array_in_valid_o(array_in_valid),.array_in_ready_i(array_in_ready),
    .array_out_valid_i(array_out_valid),.array_out_ready_o(array_out_ready),
    .issue_context_o(issue_context_o),.issue_clear_o(issue_clear_o),
    .completion_fire_o(completion_fire_unused),.completion_context_o(completion_context_unused),
    .busy_o(busy_o),.accumulator_valid_o(accumulator_valid_o),
    .accepted_steps_o(accepted_steps_o),.completed_steps_o(completed_steps_o),
    .protocol_error_o(scheduler_error));
  bf16_outer_product_array_control5_rev8b_b_candidate array_control(
    .clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(array_in_valid),.in_ready_o(array_in_ready),
    .out_valid_o(array_out_valid),.out_ready_i(array_out_ready),
    .input_write_o(input_write_o),.pre_write_o(pre_write_o),.mul_write_o(mul_write_o),
    .post_write_o(post_write_o),.output_write_o(output_write_o),
    .accepted_steps_o(array_accepted_unused),.completed_steps_o(array_completed_unused));
  bf16_context_tag_pipeline5_rev8b_b_candidate tags(
    .clk_i(clk_i),.rst_ni(rst_ni),.input_write_i(input_write_o),.pre_write_i(pre_write_o),
    .mul_write_i(mul_write_o),.post_write_i(post_write_o),.output_write_i(output_write_o),
    .issue_context_i(issue_context_o),.early_commit_context_o(early_commit_context_o),
    .output_context_o(tag_output_context_unused));
  assign output_context_o=context_o;
  assign completion_pop_o=out_valid_o&&out_ready_i;
  assign protocol_error_o=scheduler_error;
endmodule
