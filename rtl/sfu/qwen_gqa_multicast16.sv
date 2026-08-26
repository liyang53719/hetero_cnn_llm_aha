// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module qwen_gqa_multicast16(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic in_valid_i,
  output logic in_ready_o,
  input  logic [1:0] role_i,
  input  logic kv_head_i,
  input  logic [2:0] head_chunk_i,
  input  logic last_i,
  input  logic [15:0] tag_i,
  input  logic [511:0] data_i,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic [1:0] role_o,
  output logic [3:0] query_head_o,
  output logic kv_head_o,
  output logic [2:0] head_chunk_o,
  output logic last_o,
  output logic [15:0] tag_o,
  output logic [511:0] data_o,
  output logic illegal_o,
  output logic [31:0] accepted_inputs_o,
  output logic [31:0] completed_outputs_o,
  output logic [31:0] illegal_inputs_o
);
  typedef enum logic {S_IDLE, S_OUT} state_e;
  state_e state_q;
  logic [1:0] role_q;
  logic kv_head_q;
  logic [2:0] head_chunk_q, replica_q;
  logic last_q, illegal_q;
  logic [15:0] tag_q;
  logic [511:0] data_q;
  logic input_illegal;

  always_comb begin
    input_illegal = (role_i != 2'd1 && role_i != 2'd2) ||
                    (last_i != (head_chunk_i == 3'd7));
  end

  assign in_ready_o = state_q == S_IDLE;
  assign out_valid_o = state_q == S_OUT;
  assign role_o = role_q;
  assign query_head_o = (kv_head_q ? 4'd6 : 4'd0) + {1'b0, replica_q};
  assign kv_head_o = kv_head_q;
  assign head_chunk_o = head_chunk_q;
  assign last_o = last_q;
  assign tag_o = tag_q;
  assign data_o = data_q;
  assign illegal_o = illegal_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      role_q <= '0;
      kv_head_q <= '0;
      head_chunk_q <= '0;
      replica_q <= '0;
      last_q <= '0;
      illegal_q <= '0;
      tag_q <= '0;
      data_q <= '0;
      accepted_inputs_o <= '0;
      completed_outputs_o <= '0;
      illegal_inputs_o <= '0;
    end else begin
      case (state_q)
        S_IDLE: if (in_valid_i) begin
          role_q <= role_i;
          kv_head_q <= kv_head_i;
          head_chunk_q <= head_chunk_i;
          last_q <= last_i;
          tag_q <= tag_i;
          data_q <= input_illegal ? 512'd0 : data_i;
          illegal_q <= input_illegal;
          replica_q <= '0;
          accepted_inputs_o <= accepted_inputs_o + 1'b1;
          if (input_illegal)
            illegal_inputs_o <= illegal_inputs_o + 1'b1;
          state_q <= S_OUT;
        end
        S_OUT: if (out_ready_i) begin
          completed_outputs_o <= completed_outputs_o + 1'b1;
          if (!illegal_q && replica_q != 3'd5)
            replica_q <= replica_q + 1'b1;
          else
            state_q <= S_IDLE;
        end
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
