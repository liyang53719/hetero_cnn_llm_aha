// SPDX-License-Identifier: Apache-2.0
// Two-stage elastic datapath: FP32 multiplies and FP32 add are separated by
// real registers.  Both stages retain their payload under downstream stall.
module fp32_mlo_merge_beat #(
  parameter integer LANES = 4
)(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic in_valid_i,
  output logic in_ready_o,
  input  logic [31:0] alpha_i,
  input  logic [31:0] beta_i,
  input  logic [LANES*32-1:0] oa_i,
  input  logic [LANES*32-1:0] ob_i,
  input  logic last_i,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic [LANES*32-1:0] o_o,
  output logic last_o
);
  logic mul_valid_q, out_valid_q;
  logic mul_ready, out_stage_ready;
  logic mul_last_q, out_last_q;
  logic [LANES*32-1:0] product_a, product_b;
  logic [LANES*32-1:0] product_a_q, product_b_q;
  logic [LANES*32-1:0] sum;
  logic [LANES*32-1:0] out_q;
  logic [LANES*15-1:0] unused_flags;

  genvar lane;
  generate
    for (lane = 0; lane < LANES; lane++) begin : g_lane
      HeteroFP32Alu mul_a(
        .io_op(1'b1), .io_x(oa_i[lane*32 +: 32]), .io_y(alpha_i),
        .io_out(product_a[lane*32 +: 32]),
        .io_exceptionFlags(unused_flags[lane*15 +: 5])
      );
      HeteroFP32Alu mul_b(
        .io_op(1'b1), .io_x(ob_i[lane*32 +: 32]), .io_y(beta_i),
        .io_out(product_b[lane*32 +: 32]),
        .io_exceptionFlags(unused_flags[lane*15+5 +: 5])
      );
      HeteroFP32Alu add_o(
        .io_op(1'b0), .io_x(product_a_q[lane*32 +: 32]),
        .io_y(product_b_q[lane*32 +: 32]),
        .io_out(sum[lane*32 +: 32]),
        .io_exceptionFlags(unused_flags[lane*15+10 +: 5])
      );
    end
  endgenerate

  assign out_stage_ready = !out_valid_q || out_ready_i;
  assign mul_ready = !mul_valid_q || out_stage_ready;
  assign in_ready_o = mul_ready;
  assign out_valid_o = out_valid_q;
  assign o_o = out_q;
  assign last_o = out_last_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      mul_valid_q <= 1'b0;
      out_valid_q <= 1'b0;
      product_a_q <= '0;
      product_b_q <= '0;
      mul_last_q <= 1'b0;
      out_q <= '0;
      out_last_q <= 1'b0;
    end else begin
      if (out_stage_ready) begin
        out_valid_q <= mul_valid_q;
        if (mul_valid_q) begin
          out_q <= sum;
          out_last_q <= mul_last_q;
        end
      end
      if (mul_ready) begin
        mul_valid_q <= in_valid_i;
        if (in_valid_i) begin
          product_a_q <= product_a;
          product_b_q <= product_b;
          mul_last_q <= last_i;
        end
      end
    end
  end
endmodule
