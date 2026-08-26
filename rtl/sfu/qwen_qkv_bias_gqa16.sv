// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module qwen_qkv_bias_gqa16(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic in_valid_i,
  output logic in_ready_o,
  input  logic [1:0] role_i,
  input  logic [6:0] chunk_i,
  input  logic [15:0] tag_i,
  input  logic [511:0] data_i,
  input  logic [511:0] bias_i,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic [1:0] role_o,
  output logic [6:0] chunk_o,
  output logic [15:0] tag_o,
  output logic [3:0] query_head_o,
  output logic kv_head_o,
  output logic [2:0] head_chunk_o,
  output logic last_o,
  output logic illegal_o,
  output logic [511:0] data_o,
  output logic [4:0] exception_flags_o,
  output logic [31:0] accepted_inputs_o,
  output logic [31:0] completed_outputs_o,
  output logic [31:0] illegal_inputs_o
);
  typedef enum logic {S_IDLE, S_OUT} state_e;
  state_e state_q;
  logic [1:0] role_q;
  logic [6:0] chunk_q;
  logic [15:0] tag_q;
  logic [511:0] data_q;
  logic [4:0] flags_q;
  logic [2:0] replica_q;
  logic [3:0] query_head_base_q;
  logic kv_head_q;
  logic [2:0] head_chunk_q;
  logic last_q, illegal_q, input_illegal;
  logic [511:0] biased_data;
  logic [79:0] add_flags;
  logic [4:0] add_flags_or;

  genvar lane;
  generate
    for (lane = 0; lane < 16; lane++) begin : g_bias
      HeteroFP32Alu add(
        .io_op(1'b0),
        .io_x(data_i[lane * 32 +: 32]),
        .io_y(bias_i[lane * 32 +: 32]),
        .io_out(biased_data[lane * 32 +: 32]),
        .io_exceptionFlags(add_flags[lane * 5 +: 5])
      );
    end
  endgenerate

  always_comb begin
    add_flags_or = '0;
    for (int i = 0; i < 16; i++)
      add_flags_or |= add_flags[i * 5 +: 5];
    input_illegal = role_i == 2'd3 ||
                    (role_i == 2'd0 && chunk_i >= 7'd96) ||
                    ((role_i == 2'd1 || role_i == 2'd2) && chunk_i >= 7'd16);
  end

  assign in_ready_o = state_q == S_IDLE;
  assign out_valid_o = state_q == S_OUT;
  assign role_o = role_q;
  assign chunk_o = chunk_q;
  assign tag_o = tag_q;
  assign query_head_o = query_head_base_q + {1'b0, replica_q};
  assign kv_head_o = kv_head_q;
  assign head_chunk_o = head_chunk_q;
  assign last_o = last_q;
  assign illegal_o = illegal_q;
  assign data_o = data_q;
  assign exception_flags_o = flags_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      role_q <= '0;
      chunk_q <= '0;
      tag_q <= '0;
      data_q <= '0;
      flags_q <= '0;
      replica_q <= '0;
      query_head_base_q <= '0;
      kv_head_q <= '0;
      head_chunk_q <= '0;
      last_q <= '0;
      illegal_q <= '0;
      accepted_inputs_o <= '0;
      completed_outputs_o <= '0;
      illegal_inputs_o <= '0;
    end else begin
      case (state_q)
        S_IDLE: if (in_valid_i) begin
          role_q <= role_i;
          chunk_q <= chunk_i;
          tag_q <= tag_i;
          replica_q <= '0;
          illegal_q <= input_illegal;
          accepted_inputs_o <= accepted_inputs_o + 1'b1;
          if (input_illegal) begin
            data_q <= '0;
            flags_q <= '0;
            query_head_base_q <= '0;
            kv_head_q <= '0;
            head_chunk_q <= '0;
            last_q <= '0;
            illegal_inputs_o <= illegal_inputs_o + 1'b1;
          end else begin
            data_q <= biased_data;
            flags_q <= add_flags_or;
            head_chunk_q <= chunk_i[2:0];
            last_q <= chunk_i[2:0] == 3'd7;
            if (role_i == 2'd0) begin
              query_head_base_q <= chunk_i[6:3];
              kv_head_q <= chunk_i[6:3] >= 4'd6;
            end else begin
              kv_head_q <= chunk_i >= 8;
              query_head_base_q <= chunk_i >= 8 ? 4'd6 : 4'd0;
            end
          end
          state_q <= S_OUT;
        end
        S_OUT: if (out_ready_i) begin
          completed_outputs_o <= completed_outputs_o + 1'b1;
          if (!illegal_q && role_q != 2'd0 && replica_q != 3'd5)
            replica_q <= replica_q + 1'b1;
          else
            state_q <= S_IDLE;
        end
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
