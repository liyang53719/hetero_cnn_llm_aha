// SPDX-License-Identifier: Apache-2.0
// Test-only alias. Candidate filelists must exclude canonical production RTL.
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
  bf16_outer_product_context_array_rev8b_a_candidate #(
    .ROWS(ROWS), .COLS(COLS), .CONTEXTS(CONTEXTS), .FIFO_DEPTH(FIFO_DEPTH)
  ) candidate (.*);
endmodule
