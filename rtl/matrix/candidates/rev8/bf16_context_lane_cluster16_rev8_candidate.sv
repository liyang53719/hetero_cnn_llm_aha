// SPDX-License-Identifier: Apache-2.0
// Reusable 16-lane timing cluster.  Mapping one cluster localizes the shared
// context controls while the production top instantiates exactly 32 clusters.
`timescale 1ns/1ps
module bf16_context_lane_cluster16_rev8_candidate (
  input  logic          clk_i,
  input  logic [15:0]   lane_rst_ni_i,
  input  logic          pre_write_i,
  input  logic          mul_write_i,
  input  logic          post_write_i,
  input  logic          output_write_i,
  input  logic [16*16-1:0] lane_a_i,
  input  logic [16*16-1:0] lane_b_i,
  input  logic [1:0]    issue_context_i,
  input  logic          issue_clear_i,
  input  logic [1:0]    early_commit_context_i,
  input  logic [1:0]    output_context_i,
  output logic [16*32-1:0] lane_out_o,
  output logic [16*5-1:0]  lane_flags_o
);
  for (genvar lane = 0; lane < 16; lane++) begin : g_lane
    logic [3:0] bank_valid_unused;
    bf16_context_fma_pipeline_lane4_rev8_candidate u_lane (
      .clk_i(clk_i), .rst_ni(lane_rst_ni_i[lane]),
      .pre_write_i(pre_write_i), .mul_write_i(mul_write_i),
      .post_write_i(post_write_i), .output_write_i(output_write_i),
      .a_i(lane_a_i[lane*16 +: 16]),
      .b_i(lane_b_i[lane*16 +: 16]),
      .issue_context_i(issue_context_i), .issue_clear_i(issue_clear_i),
      .early_commit_context_i(early_commit_context_i),
      .output_context_i(output_context_i),
      .out_o(lane_out_o[lane*32 +: 32]),
      .flags_o(lane_flags_o[lane*5 +: 5]),
      .bank_valid_o(bank_valid_unused)
    );
  end
endmodule
