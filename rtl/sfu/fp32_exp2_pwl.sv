// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Four-stage elastic exp2 PWL pipeline.  Floor/ROM, FP multiply and FP add
// occupy distinct registered stages while preserving one input per cycle.
module fp32_exp2_pwl(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic in_valid_i,
  output logic in_ready_o,
  input  logic [31:0] x_i,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic [31:0] y_o,
  output logic [12:0] exception_flags_o,
  output logic [31:0] accepted_o,
  output logic [31:0] completed_o
);
  `include "rtl/sfu/fp32_exp2_coeffs.svh"

  logic valid0_q, valid1_q, valid2_q, valid3_q;
  logic ready0, ready1, ready2, ready3;
  logic [31:0] x0_q, x1_q, m1_q, b1_q, b2_q;
  logic [31:0] mx2_q, y3_q;
  logic [12:0] flags1_q, flags2_q, flags3_q;
  logic special1_q, special2_q;
  logic [31:0] special_result1_q, special_result2_q;

  logic [15:0] scaled_floor0;
  logic [7:0] convert_flags0;
  logic signed [15:0] floor_signed0;
  logic [7:0] index0;
  logic [63:0] coeff0;
  logic [31:0] mul1, add2;
  logic [4:0] mul_flags1, add_flags2;
  logic is_nan0, is_inf0, special0;
  logic [31:0] special_result0;

  HeteroFP32Scale16Floor u_floor(
    .io_x(x0_q), .io_out(scaled_floor0), .io_exceptionFlags(convert_flags0)
  );
  assign floor_signed0 = $signed(scaled_floor0);
  assign index0 = 8'($signed(floor_signed0) + 16'sd256);
  assign coeff0 = exp2_pwl_coeff(index0);
  assign is_nan0 = &x0_q[30:23] && |x0_q[22:0];
  assign is_inf0 = &x0_q[30:23] && !(|x0_q[22:0]);
  assign special0 = is_nan0 || is_inf0 || floor_signed0 < -16'sd256 || floor_signed0 >= 0;
  always_comb begin
    if (is_nan0) special_result0 = 32'd0;
    else if (is_inf0) special_result0 = x0_q[31] ? 32'd0 : 32'h3f800000;
    else if (floor_signed0 < -16'sd256) special_result0 = 32'd0;
    else special_result0 = 32'h3f800000;
  end

  HeteroFP32Alu u_mul(
    .io_op(1'b1), .io_x(m1_q), .io_y(x1_q),
    .io_out(mul1), .io_exceptionFlags(mul_flags1)
  );
  HeteroFP32Alu u_add(
    .io_op(1'b0), .io_x(mx2_q), .io_y(b2_q),
    .io_out(add2), .io_exceptionFlags(add_flags2)
  );

  assign ready3 = !valid3_q || out_ready_i;
  assign ready2 = !valid2_q || ready3;
  assign ready1 = !valid1_q || ready2;
  assign ready0 = !valid0_q || ready1;
  assign in_ready_o = ready0;
  assign out_valid_o = valid3_q;
  assign y_o = y3_q;
  assign exception_flags_o = flags3_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      valid0_q <= 1'b0;
      valid1_q <= 1'b0;
      valid2_q <= 1'b0;
      valid3_q <= 1'b0;
      x0_q <= '0;
      x1_q <= '0;
      m1_q <= '0;
      b1_q <= '0;
      b2_q <= '0;
      mx2_q <= '0;
      y3_q <= '0;
      flags1_q <= '0;
      flags2_q <= '0;
      flags3_q <= '0;
      special1_q <= 1'b0;
      special2_q <= 1'b0;
      special_result1_q <= '0;
      special_result2_q <= '0;
      accepted_o <= '0;
      completed_o <= '0;
    end else begin
      if (valid3_q && out_ready_i) completed_o <= completed_o + 1'b1;
      if (in_valid_i && in_ready_o) accepted_o <= accepted_o + 1'b1;

      if (ready3) begin
        valid3_q <= valid2_q;
        if (valid2_q) begin
          y3_q <= special2_q ? special_result2_q : add2;
          flags3_q <= flags2_q | {8'd0, add_flags2};
        end
      end
      if (ready2) begin
        valid2_q <= valid1_q;
        if (valid1_q) begin
          mx2_q <= mul1;
          b2_q <= b1_q;
          flags2_q <= flags1_q | {8'd0, mul_flags1};
          special2_q <= special1_q;
          special_result2_q <= special_result1_q;
        end
      end
      if (ready1) begin
        valid1_q <= valid0_q;
        if (valid0_q) begin
          x1_q <= x0_q;
          m1_q <= coeff0[63:32];
          b1_q <= coeff0[31:0];
          flags1_q <= {convert_flags0, 5'd0};
          special1_q <= special0;
          special_result1_q <= special_result0;
        end
      end
      if (ready0) begin
        valid0_q <= in_valid_i;
        if (in_valid_i) x0_q <= x_i;
      end
    end
  end
endmodule
