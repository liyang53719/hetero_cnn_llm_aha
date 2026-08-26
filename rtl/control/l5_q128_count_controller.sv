// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module l5_q128_count_controller(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic start_i,
  output logic command_valid_o,
  input  logic command_ready_i,
  output logic [4:0] operation_o,
  output logic [2:0] engine_o,
  output logic [31:0] work_items_o,
  output logic [31:0] matrix_steps_o,
  output logic measured_latency_valid_o,
  output logic score_matrix_o,
  input  logic engine_done_i,
  output logic done_o,
  output logic [31:0] commands_issued_o,
  output logic [31:0] matrix_steps_total_o,
  output logic [31:0] rope_pairs_total_o,
  output logic [31:0] dot_operations_total_o,
  output logic [31:0] online_updates_total_o,
  output logic [31:0] reciprocals_total_o,
  output logic [31:0] normalization_chunks_total_o,
  output logic [31:0] silu_scalars_total_o,
  output logic [31:0] product_chunks_total_o,
  output logic [31:0] score_matrix_commands_o
);
  typedef enum logic [2:0] {S_IDLE, S_ISSUE, S_WAIT, S_DONE} state_e;
  state_e state_q;
  logic [4:0] command_index_q;

  function automatic logic [4:0] operation(input logic [4:0] index);
    case (index)
      0,17: operation = 5'd0;     // RMSNorm
      1: operation = 5'd1;        // Q
      2: operation = 5'd2;        // K
      3: operation = 5'd3;        // V
      4: operation = 5'd4;        // Q bias
      5: operation = 5'd5;        // K bias
      6: operation = 5'd6;        // V bias
      7: operation = 5'd7;        // Q RoPE
      8: operation = 5'd8;        // K RoPE
      9: operation = 5'd9;        // K GQA
      10: operation = 5'd10;      // V GQA
      11: operation = 5'd11;      // dot128
      12: operation = 5'd12;      // online update
      13: operation = 5'd13;      // reciprocal
      14: operation = 5'd14;      // O/L
      15: operation = 5'd15;      // OProj
      16: operation = 5'd16;      // residual1
      18: operation = 5'd17;      // gate
      19: operation = 5'd18;      // up
      20: operation = 5'd19;      // SiLU
      21: operation = 5'd20;      // product
      22: operation = 5'd21;      // down
      23: operation = 5'd22;      // final residual
      default: operation = 5'd31;
    endcase
  endfunction

  function automatic logic [2:0] engine(input logic [4:0] index);
    case (index)
      1,2,3,15,18,19,22: engine = 3'd0;
      0,17: engine = 3'd1;
      4,5,6: engine = 3'd2;
      7,8,9,10: engine = 3'd3;
      11,12,13,14: engine = 3'd4;
      default: engine = 3'd5;
    endcase
  endfunction

  function automatic logic [31:0] work(input logic [4:0] index);
    case (index)
      0,17: work = 32'd12288;
      1: work = 32'd589824;
      2,3: work = 32'd98304;
      4: work = 32'd12288;
      5,6: work = 32'd2048;
      7: work = 32'd98304;
      8: work = 32'd16384;
      9,10: work = 32'd12288;
      11,12: work = 32'd99072;
      13: work = 32'd1536;
      14,16,23: work = 32'd12288;
      15: work = 32'd589824;
      18,19,22: work = 32'd3440640;
      20: work = 32'd1146880;
      21: work = 32'd71680;
      default: work = 32'd0;
    endcase
  endfunction

  function automatic logic [31:0] matrix_steps(input logic [4:0] index);
    case (index)
      1,15: matrix_steps = 32'd589824;
      2,3: matrix_steps = 32'd98304;
      18,19,22: matrix_steps = 32'd3440640;
      default: matrix_steps = 32'd0;
    endcase
  endfunction

  assign command_valid_o = state_q == S_ISSUE;
  assign operation_o = operation(command_index_q);
  assign engine_o = engine(command_index_q);
  assign work_items_o = work(command_index_q);
  assign matrix_steps_o = matrix_steps(command_index_q);
  assign measured_latency_valid_o = 1'b0;
  assign score_matrix_o = 1'b0;
  assign done_o = state_q == S_DONE;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      command_index_q <= '0;
      commands_issued_o <= '0;
      matrix_steps_total_o <= '0;
      rope_pairs_total_o <= '0;
      dot_operations_total_o <= '0;
      online_updates_total_o <= '0;
      reciprocals_total_o <= '0;
      normalization_chunks_total_o <= '0;
      silu_scalars_total_o <= '0;
      product_chunks_total_o <= '0;
      score_matrix_commands_o <= '0;
    end else begin
      case (state_q)
        S_IDLE: if (start_i) begin
          command_index_q <= '0;
          commands_issued_o <= '0;
          matrix_steps_total_o <= '0;
          rope_pairs_total_o <= '0;
          dot_operations_total_o <= '0;
          online_updates_total_o <= '0;
          reciprocals_total_o <= '0;
          normalization_chunks_total_o <= '0;
          silu_scalars_total_o <= '0;
          product_chunks_total_o <= '0;
          score_matrix_commands_o <= '0;
          state_q <= S_ISSUE;
        end
        S_ISSUE: if (command_ready_i) begin
          commands_issued_o <= commands_issued_o + 1'b1;
          matrix_steps_total_o <= matrix_steps_total_o + matrix_steps_o;
          if (command_index_q == 7 || command_index_q == 8)
            rope_pairs_total_o <= rope_pairs_total_o + work_items_o;
          if (command_index_q == 11)
            dot_operations_total_o <= dot_operations_total_o + work_items_o;
          if (command_index_q == 12)
            online_updates_total_o <= online_updates_total_o + work_items_o;
          if (command_index_q == 13)
            reciprocals_total_o <= reciprocals_total_o + work_items_o;
          if (command_index_q == 14)
            normalization_chunks_total_o <= normalization_chunks_total_o + work_items_o;
          if (command_index_q == 20)
            silu_scalars_total_o <= silu_scalars_total_o + work_items_o;
          if (command_index_q == 21)
            product_chunks_total_o <= product_chunks_total_o + work_items_o;
          if (score_matrix_o)
            score_matrix_commands_o <= score_matrix_commands_o + 1'b1;
          state_q <= S_WAIT;
        end
        S_WAIT: if (engine_done_i) begin
          if (command_index_q == 5'd23)
            state_q <= S_DONE;
          else begin
            command_index_q <= command_index_q + 1'b1;
            state_q <= S_ISSUE;
          end
        end
        S_DONE: if (start_i) state_q <= S_IDLE;
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
