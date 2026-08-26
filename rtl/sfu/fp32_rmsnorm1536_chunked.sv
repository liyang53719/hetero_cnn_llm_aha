// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_rmsnorm1536_chunked(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic in_valid_i,
  output logic in_ready_o,
  input  logic [49151:0] x_i,
  input  logic [49151:0] weight_i,
  input  logic [31:0] epsilon_i,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic [49151:0] y_o,
  output logic [4:0] exception_flags_o,
  output logic [31:0] accepted_o,
  output logic [31:0] completed_o,
  output logic [31:0] reduction_cycles_o,
  output logic [31:0] rsqrt_cycles_o,
  output logic [31:0] output_cycles_o
);
  typedef enum logic [2:0] {
    S_IDLE, S_REDUCE_ISSUE, S_REDUCE_WAIT,
    S_RSQRT_ISSUE, S_RSQRT_WAIT, S_OUTPUT, S_DONE
  } state_e;
  state_e state_q;
  logic [49151:0] x_q, weight_q, y_q;
  logic [31:0] epsilon_q, sum_q, inverse_q, mean_epsilon_q;
  logic [6:0] chunk_q;
  logic [511:0] squares, scaled, chunk_output;
  logic [79:0] square_flags;
  logic [159:0] output_flags;
  logic [4:0] square_flags_or, output_flags_or, flags_q;
  logic reduce_in_valid, reduce_in_ready, reduce_out_valid, reduce_out_ready;
  logic [31:0] reduce_sum;
  logic [4:0] reduce_flags;
  logic [31:0] sum_next, mean, mean_epsilon;
  logic [4:0] sum_flags, mean_flags, epsilon_flags;
  logic rsqrt_in_valid, rsqrt_in_ready, rsqrt_out_valid, rsqrt_out_ready;
  logic [31:0] rsqrt_y;
  logic [4:0] rsqrt_flags;
  /* verilator lint_off UNUSEDSIGNAL */
  logic [31:0] reduce_accepted, reduce_completed, rsqrt_accepted, rsqrt_completed;
  logic rsqrt_domain_error;
  /* verilator lint_on UNUSEDSIGNAL */

  genvar lane;
  generate
    for (lane = 0; lane < 16; lane++) begin : g_square
      HeteroFP32Alu multiply(
        .io_op(1'b1),
        .io_x(x_q[(chunk_q * 16 + lane) * 32 +: 32]),
        .io_y(x_q[(chunk_q * 16 + lane) * 32 +: 32]),
        .io_out(squares[lane * 32 +: 32]),
        .io_exceptionFlags(square_flags[lane * 5 +: 5])
      );
    end
    for (lane = 0; lane < 16; lane++) begin : g_output
      HeteroFP32Alu scale_value(
        .io_op(1'b1),
        .io_x(x_q[(chunk_q * 16 + lane) * 32 +: 32]),
        .io_y(inverse_q),
        .io_out(scaled[lane * 32 +: 32]),
        .io_exceptionFlags(output_flags[lane * 10 +: 5])
      );
      HeteroFP32Alu apply_weight(
        .io_op(1'b1),
        .io_x(scaled[lane * 32 +: 32]),
        .io_y(weight_q[(chunk_q * 16 + lane) * 32 +: 32]),
        .io_out(chunk_output[lane * 32 +: 32]),
        .io_exceptionFlags(output_flags[lane * 10 + 5 +: 5])
      );
    end
  endgenerate

  always_comb begin
    square_flags_or = '0;
    output_flags_or = '0;
    for (int i = 0; i < 16; i++) begin
      square_flags_or |= square_flags[i * 5 +: 5];
      output_flags_or |= output_flags[i * 10 +: 5] |
                         output_flags[i * 10 + 5 +: 5];
    end
  end

  fp32_reduce16 reduction(
    .clk_i, .rst_ni,
    .in_valid_i(reduce_in_valid), .in_ready_o(reduce_in_ready),
    .data_i(squares), .out_valid_o(reduce_out_valid),
    .out_ready_i(reduce_out_ready), .sum_o(reduce_sum),
    .exception_flags_o(reduce_flags),
    .accepted_vectors_o(reduce_accepted), .completed_vectors_o(reduce_completed)
  );
  HeteroFP32Alu accumulate(
    .io_op(1'b0), .io_x(sum_q), .io_y(reduce_sum),
    .io_out(sum_next), .io_exceptionFlags(sum_flags)
  );
  HeteroFP32Alu calculate_mean(
    .io_op(1'b1), .io_x(sum_next), .io_y(32'h3a2aaaab),
    .io_out(mean), .io_exceptionFlags(mean_flags)
  );
  HeteroFP32Alu add_epsilon(
    .io_op(1'b0), .io_x(mean), .io_y(epsilon_q),
    .io_out(mean_epsilon), .io_exceptionFlags(epsilon_flags)
  );
  fp32_rsqrt_nr reciprocal_square_root(
    .clk_i, .rst_ni,
    .in_valid_i(rsqrt_in_valid), .in_ready_o(rsqrt_in_ready),
    .x_i(mean_epsilon_q), .out_valid_o(rsqrt_out_valid),
    .out_ready_i(rsqrt_out_ready), .y_o(rsqrt_y),
    .exception_flags_o(rsqrt_flags), .domain_error_o(rsqrt_domain_error),
    .accepted_o(rsqrt_accepted), .completed_o(rsqrt_completed)
  );

  assign reduce_in_valid = state_q == S_REDUCE_ISSUE;
  assign reduce_out_ready = state_q == S_REDUCE_WAIT && reduce_out_valid;
  assign rsqrt_in_valid = state_q == S_RSQRT_ISSUE;
  assign rsqrt_out_ready = state_q == S_RSQRT_WAIT && rsqrt_out_valid;
  assign in_ready_o = state_q == S_IDLE;
  assign out_valid_o = state_q == S_DONE;
  assign y_o = y_q;
  assign exception_flags_o = flags_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      epsilon_q <= '0;
      sum_q <= '0;
      inverse_q <= '0;
      mean_epsilon_q <= '0;
      chunk_q <= '0;
      flags_q <= '0;
      accepted_o <= '0;
      completed_o <= '0;
      reduction_cycles_o <= '0;
      rsqrt_cycles_o <= '0;
      output_cycles_o <= '0;
    end else begin
      if (state_q == S_REDUCE_ISSUE || state_q == S_REDUCE_WAIT)
        reduction_cycles_o <= reduction_cycles_o + 1'b1;
      if (state_q == S_RSQRT_ISSUE || state_q == S_RSQRT_WAIT)
        rsqrt_cycles_o <= rsqrt_cycles_o + 1'b1;
      if (state_q == S_OUTPUT)
        output_cycles_o <= output_cycles_o + 1'b1;
      case (state_q)
        S_IDLE: if (in_valid_i) begin
          x_q <= x_i;
          weight_q <= weight_i;
          epsilon_q <= epsilon_i;
          sum_q <= '0;
          mean_epsilon_q <= '0;
          chunk_q <= '0;
          flags_q <= '0;
          accepted_o <= accepted_o + 1'b1;
          state_q <= S_REDUCE_ISSUE;
        end
        S_REDUCE_ISSUE: if (reduce_in_ready)
          state_q <= S_REDUCE_WAIT;
        S_REDUCE_WAIT: if (reduce_out_valid) begin
          sum_q <= sum_next;
          flags_q <= flags_q | square_flags_or | reduce_flags | sum_flags;
          if (chunk_q == 7'd95) begin
            mean_epsilon_q <= mean_epsilon;
            state_q <= S_RSQRT_ISSUE;
          end else begin
            chunk_q <= chunk_q + 1'b1;
            state_q <= S_REDUCE_ISSUE;
          end
        end
        S_RSQRT_ISSUE: if (rsqrt_in_ready)
          state_q <= S_RSQRT_WAIT;
        S_RSQRT_WAIT: if (rsqrt_out_valid) begin
          inverse_q <= rsqrt_y;
          flags_q <= flags_q | mean_flags | epsilon_flags | rsqrt_flags;
          chunk_q <= '0;
          state_q <= S_OUTPUT;
        end
        S_OUTPUT: begin
          y_q[chunk_q * 512 +: 512] <= chunk_output;
          flags_q <= flags_q | output_flags_or;
          if (chunk_q == 7'd95)
            state_q <= S_DONE;
          else
            chunk_q <= chunk_q + 1'b1;
        end
        S_DONE: if (out_ready_i) begin
          completed_o <= completed_o + 1'b1;
          state_q <= S_IDLE;
        end
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
