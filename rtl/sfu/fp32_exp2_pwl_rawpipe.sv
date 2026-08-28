// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Timing-closure candidate using generated HardFloat raw/round pipelines.
// It is intentionally single-transaction; the Block128 coefficient path has
// only one outstanding summary header.
module fp32_exp2_pwl_rawpipe(
  input logic clk_i, rst_ni,
  input logic in_valid_i, output logic in_ready_o, input logic [31:0] x_i,
  output logic out_valid_o, input logic out_ready_i, output logic [31:0] y_o,
  output logic [12:0] exception_flags_o,
  output logic [31:0] accepted_o, completed_o
);
  `include "rtl/sfu/fp32_exp2_coeffs.svh"
  typedef enum logic [3:0] {IDLE, FLOOR, COEFF, MUL_ISSUE, MUL_WAIT,
    ADD_ISSUE, ADD_WAIT, OUT} state_t;
  state_t state_q;
  logic [31:0] x_q, m_q, b_q, mul_q, y_q;
  logic [12:0] flags_q;
  logic special_q;
  logic [31:0] special_result_q;
  logic [15:0] scaled_floor;
  logic [7:0] floor_flags;
  logic signed [15:0] floor_signed;
  logic signed [15:0] floor_q;
  logic [7:0] index;
  logic [63:0] coeff;
  logic mul_ready, mul_valid, mul_fire;
  logic [31:0] mul_out;
  logic [4:0] mul_flags;
  logic [11:0] mul_tag;
  logic add_ready, add_valid, add_fire;
  logic [31:0] add_out;
  logic [4:0] add_flags;
  logic [11:0] add_tag;

  HeteroFP32Scale16Floor floor_unit(
    .io_x(x_q), .io_out(scaled_floor), .io_exceptionFlags(floor_flags)
  );
  assign floor_signed = $signed(scaled_floor);
  assign index = 8'($signed(floor_q) + 16'sd256);
  assign coeff = exp2_pwl_coeff(index);

  assign mul_fire = state_q == MUL_ISSUE && mul_ready;
  HeteroFP32MulPipeTag12 mul_unit(
    .clock(clk_i), .reset(!rst_ni),
    .io_inValid(mul_fire), .io_inReady(mul_ready),
    .io_x(m_q), .io_y(x_q), .io_userIn(12'd0),
    .io_outValid(mul_valid), .io_outReady(state_q == MUL_WAIT),
    .io_out(mul_out), .io_exceptionFlags(mul_flags), .io_userOut(mul_tag)
  );
  assign add_fire = state_q == ADD_ISSUE && add_ready;
  HeteroFP32AddPipeTag12 add_unit(
    .clock(clk_i), .reset(!rst_ni),
    .io_inValid(add_fire), .io_inReady(add_ready),
    .io_x(mul_q), .io_y(b_q), .io_userIn(12'd0),
    .io_outValid(add_valid), .io_outReady(state_q == ADD_WAIT),
    .io_out(add_out), .io_exceptionFlags(add_flags), .io_userOut(add_tag)
  );

  assign in_ready_o = state_q == IDLE;
  assign out_valid_o = state_q == OUT;
  assign y_o = y_q;
  assign exception_flags_o = flags_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= IDLE; x_q <= '0; m_q <= '0; b_q <= '0; mul_q <= '0; floor_q <= '0;
      y_q <= '0; flags_q <= '0; special_q <= 1'b0;
      special_result_q <= '0; accepted_o <= '0; completed_o <= '0;
    end else begin
      case (state_q)
        IDLE: if (in_valid_i) begin
          x_q <= x_i; accepted_o <= accepted_o + 1'b1; state_q <= FLOOR;
        end
        FLOOR: begin
          floor_q <= floor_signed; flags_q <= {floor_flags, 5'd0};
          special_q <= (&x_q[30:23] && |x_q[22:0]) ||
            (&x_q[30:23] && !(|x_q[22:0])) || floor_signed < -16'sd256 || floor_signed >= 0;
          if (&x_q[30:23] && |x_q[22:0]) special_result_q <= 32'd0;
          else if (&x_q[30:23] && !(|x_q[22:0])) special_result_q <= x_q[31] ? 32'd0 : 32'h3f800000;
          else if (floor_signed < -16'sd256) special_result_q <= 32'd0;
          else special_result_q <= 32'h3f800000;
          if ((&x_q[30:23]) || floor_signed < -16'sd256 || floor_signed >= 0)
            state_q <= OUT;
          else state_q <= COEFF;
        end
        COEFF: begin m_q <= coeff[63:32]; b_q <= coeff[31:0]; state_q <= MUL_ISSUE; end
        MUL_ISSUE: if (mul_fire) state_q <= MUL_WAIT;
        MUL_WAIT: if (mul_valid) begin
          mul_q <= mul_out; flags_q <= flags_q | {8'd0, mul_flags}; state_q <= ADD_ISSUE;
        end
        ADD_ISSUE: if (add_fire) state_q <= ADD_WAIT;
        ADD_WAIT: if (add_valid) begin
          y_q <= add_out; flags_q <= flags_q | {8'd0, add_flags}; state_q <= OUT;
        end
        OUT: if (out_ready_i) begin completed_o <= completed_o + 1'b1; state_q <= IDLE; end
        default: state_q <= IDLE;
      endcase
      if (state_q == FLOOR && ((&x_q[30:23]) || floor_signed < -16'sd256 || floor_signed >= 0)) begin
        if (&x_q[30:23] && |x_q[22:0]) y_q <= 32'd0;
        else if (&x_q[30:23] && !(|x_q[22:0])) y_q <= x_q[31] ? 32'd0 : 32'h3f800000;
        else if (floor_signed < -16'sd256) y_q <= 32'd0;
        else y_q <= 32'h3f800000;
      end
    end
  end
endmodule
