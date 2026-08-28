// SPDX-License-Identifier: Apache-2.0
// Scalar four-stage elastic control for Revision 8A clusters.  Cluster mapping
// provides the physical fanout; no 512-way synchronous control tree is frozen
// above the cluster boundary.
`timescale 1ns/1ps
module bf16_outer_product_array_control_rev8_candidate (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic in_valid_i,
  output logic in_ready_o,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic pre_write_o,
  output logic mul_write_o,
  output logic post_write_o,
  output logic output_write_o,
  output logic [31:0] accepted_steps_o,
  output logic [31:0] completed_steps_o
);
  logic pre_valid_q, mul_valid_q, post_valid_q, output_valid_q;
  logic pre_ready, mul_ready, post_ready, output_ready;

  assign output_ready = !output_valid_q || out_ready_i;
  assign post_ready = !post_valid_q || output_ready;
  assign mul_ready = !mul_valid_q || post_ready;
  assign pre_ready = !pre_valid_q || mul_ready;
  assign in_ready_o = pre_ready;
  assign out_valid_o = output_valid_q;
  assign pre_write_o = pre_ready && in_valid_i;
  assign mul_write_o = mul_ready && pre_valid_q;
  assign post_write_o = post_ready && mul_valid_q;
  assign output_write_o = output_ready && post_valid_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      pre_valid_q <= 1'b0;
      mul_valid_q <= 1'b0;
      post_valid_q <= 1'b0;
      output_valid_q <= 1'b0;
      accepted_steps_o <= '0;
      completed_steps_o <= '0;
    end else begin
      if (in_valid_i && in_ready_o) accepted_steps_o <= accepted_steps_o + 1'b1;
      if (out_valid_o && out_ready_i) completed_steps_o <= completed_steps_o + 1'b1;
      if (output_ready) output_valid_q <= post_valid_q;
      if (post_ready) post_valid_q <= mul_valid_q;
      if (mul_ready) mul_valid_q <= pre_valid_q;
      if (pre_ready) pre_valid_q <= in_valid_i;
    end
  end
endmodule
