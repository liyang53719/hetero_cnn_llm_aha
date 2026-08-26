// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_dot64_scaled(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic in_valid_i,
  output logic in_ready_o,
  input  logic [2047:0] a_i,
  input  logic [2047:0] b_i,
  input  logic [31:0] scale_i,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic [31:0] result_o,
  output logic [4:0] exception_flags_o,
  output logic [31:0] accepted_o,
  output logic [31:0] completed_o
);
  typedef enum logic [1:0] {S_IDLE, S_ISSUE, S_WAIT, S_OUT} state_e;
  state_e state_q;
  logic [2047:0] a_q, b_q;
  logic [31:0] scale_q, sum_q, result_q;
  logic [1:0] chunk_q;
  logic [511:0] products;
  logic [79:0] product_flags;
  logic [4:0] product_flags_or;
  logic reduce_in_valid, reduce_in_ready, reduce_out_valid, reduce_out_ready;
  logic [31:0] partial_sum;
  logic [4:0] reduce_flags;
  logic [31:0] sum_next, scaled;
  logic [4:0] add_flags, scale_flags, flags_q;
  /* verilator lint_off UNUSEDSIGNAL */
  logic [31:0] reduce_accepted, reduce_completed;
  /* verilator lint_on UNUSEDSIGNAL */

  genvar lane;
  generate
    for (lane = 0; lane < 16; lane++) begin : g_product
      HeteroFP32Alu mul(
        .io_op(1'b1),
        .io_x(a_q[(chunk_q * 16 + lane) * 32 +: 32]),
        .io_y(b_q[(chunk_q * 16 + lane) * 32 +: 32]),
        .io_out(products[lane * 32 +: 32]),
        .io_exceptionFlags(product_flags[lane * 5 +: 5])
      );
    end
  endgenerate

  always_comb begin
    product_flags_or = '0;
    for (int i = 0; i < 16; i++)
      product_flags_or |= product_flags[i * 5 +: 5];
  end

  fp32_reduce16 reduce(
    .clk_i,
    .rst_ni,
    .in_valid_i(reduce_in_valid),
    .in_ready_o(reduce_in_ready),
    .data_i(products),
    .out_valid_o(reduce_out_valid),
    .out_ready_i(reduce_out_ready),
    .sum_o(partial_sum),
    .exception_flags_o(reduce_flags),
    .accepted_vectors_o(reduce_accepted),
    .completed_vectors_o(reduce_completed)
  );
  HeteroFP32Alu add_partial(
    .io_op(1'b0), .io_x(sum_q), .io_y(partial_sum),
    .io_out(sum_next), .io_exceptionFlags(add_flags)
  );
  HeteroFP32Alu apply_scale(
    .io_op(1'b1), .io_x(sum_next), .io_y(scale_q),
    .io_out(scaled), .io_exceptionFlags(scale_flags)
  );

  assign reduce_in_valid = state_q == S_ISSUE;
  assign reduce_out_ready = state_q == S_WAIT && reduce_out_valid;
  assign in_ready_o = state_q == S_IDLE;
  assign out_valid_o = state_q == S_OUT;
  assign result_o = result_q;
  assign exception_flags_o = flags_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      a_q <= '0;
      b_q <= '0;
      scale_q <= '0;
      sum_q <= '0;
      result_q <= '0;
      chunk_q <= '0;
      flags_q <= '0;
      accepted_o <= '0;
      completed_o <= '0;
    end else begin
      case (state_q)
        S_IDLE: if (in_valid_i) begin
          a_q <= a_i;
          b_q <= b_i;
          scale_q <= scale_i;
          sum_q <= '0;
          chunk_q <= '0;
          flags_q <= '0;
          accepted_o <= accepted_o + 1'b1;
          state_q <= S_ISSUE;
        end
        S_ISSUE: if (reduce_in_ready)
          state_q <= S_WAIT;
        S_WAIT: if (reduce_out_valid) begin
          sum_q <= sum_next;
          flags_q <= flags_q | product_flags_or | reduce_flags | add_flags |
                     (chunk_q == 2'd3 ? scale_flags : 5'd0);
          if (chunk_q == 2'd3) begin
            result_q <= scaled;
            state_q <= S_OUT;
          end else begin
            chunk_q <= chunk_q + 1'b1;
            state_q <= S_ISSUE;
          end
        end
        S_OUT: if (out_ready_i) begin
          completed_o <= completed_o + 1'b1;
          state_q <= S_IDLE;
        end
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
