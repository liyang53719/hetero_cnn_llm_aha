// SPDX-License-Identifier: Apache-2.0
// Structural fixed-production BF16 outer-product array composition.
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
  logic [LANES*32-1:0] lane_result;
  logic [LANES*5-1:0] lane_flags;
  logic [511:0] lane_rst_ni, lane_pre_write, lane_mul_write;
  logic [511:0] lane_post_write, lane_output_write;

  bf16_outer_product_array_control512 control (
    .clk_i(clk_i), .rst_ni(rst_ni),
    .in_valid_i(in_valid_i), .in_ready_o(in_ready_o),
    .out_valid_o(out_valid_o), .out_ready_i(out_ready_i),
    .lane_pre_write_o(lane_pre_write), .lane_mul_write_o(lane_mul_write),
    .lane_post_write_o(lane_post_write),
    .lane_output_write_o(lane_output_write),
    .accepted_steps_o(accepted_steps_o), .completed_steps_o(completed_steps_o)
  );

  generate
    if (LANES == 512) begin : g_production_glue
      bf16_outer_product_array_glue512 glue (
        .rst_ni(rst_ni),
        .lane_flags_i(lane_flags), .lane_rst_ni_o(lane_rst_ni),
        .flags_o(exception_flags_o)
      );
    end else begin : g_unsupported_geometry
      initial $fatal(1, "production bf16_outer_product_array requires 16x32");
      assign lane_rst_ni = '0;
      assign lane_pre_write = '0;
      assign lane_mul_write = '0;
      assign lane_post_write = '0;
      assign lane_output_write = '0;
      assign exception_flags_o = '0;
    end
  endgenerate

  genvar row, col;
  generate
    for (row = 0; row < ROWS; row++) begin : g_row
      for (col = 0; col < COLS; col++) begin : g_col
        localparam integer LANE = row * COLS + col;
        bf16_fma_pipeline_lane lane (
          .clk_i(clk_i), .rst_ni(lane_rst_ni[LANE]),
          .pre_write_i(lane_pre_write[LANE]),
          .mul_write_i(lane_mul_write[LANE]),
          .post_write_i(lane_post_write[LANE]),
          .output_write_i(lane_output_write[LANE]),
          .a_i(a_i[row*16 +: 16]), .b_i(b_i[col*16 +: 16]),
          .c_i(acc_i[LANE*32 +: 32]),
          .out_o(lane_result[LANE*32 +: 32]),
          .flags_o(lane_flags[LANE*5 +: 5])
        );
      end
    end
  endgenerate

  assign acc_o = lane_result;
endmodule
