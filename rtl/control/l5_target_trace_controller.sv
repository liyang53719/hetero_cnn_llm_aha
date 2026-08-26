// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module l5_target_trace_controller(
  input  logic clk_i,
  input  logic rst_ni,
  input  logic start_i,
  output logic command_valid_o,
  input  logic command_ready_i,
  output logic [4:0] operation_o,
  output logic [2:0] engine_o,
  output logic [31:0] work_items_o,
  output logic [31:0] matrix_steps_o,
  output logic [31:0] measured_latency_o,
  output logic score_matrix_o,
  input  logic engine_done_i,
  output logic active_o,
  output logic done_o,
  output logic [31:0] commands_issued_o,
  output logic [31:0] matrix_steps_total_o,
  output logic [63:0] busy_cycles_o,
  output logic [31:0] score_matrix_commands_o
);
  typedef enum logic [2:0] {S_IDLE, S_ISSUE, S_WAIT, S_DONE} state_e;
  state_e state_q;
  logic [4:0] command_index_q;

  function automatic logic [4:0] operation(input logic [4:0] index);
    case (index)
      0,1,16: operation = 5'd0;       // RMSNorm
      2: operation = 5'd1;            // Q projection
      3,4: operation = 5'd2;          // K projection
      5,6: operation = 5'd3;          // V projection
      7: operation = 5'd4;            // QKV bias/GQA boundary
      8: operation = 5'd5;            // split-half RoPE
      9: operation = 5'd6;            // post-RoPE K GQA
      10: operation = 5'd7;           // dot128 stream
      11: operation = 5'd8;           // online M/L/O
      12: operation = 5'd9;           // reciprocal L
      13: operation = 5'd10;          // O/L chunks
      14: operation = 5'd11;          // OProj
      15: operation = 5'd12;          // residual1
      17: operation = 5'd13;          // gate projection
      18: operation = 5'd14;          // up projection
      19: operation = 5'd15;          // SiLU
      20: operation = 5'd16;          // gate-times-up
      21: operation = 5'd17;          // down projection
      22: operation = 5'd18;          // final residual
      default: operation = 5'd31;
    endcase
  endfunction

  function automatic logic [2:0] engine(input logic [4:0] index);
    case (index)
      2,3,4,5,6,14,17,18,21: engine = 3'd0; // Matrix
      0,1,16: engine = 3'd1;                 // RMSNorm
      7: engine = 3'd2;                      // QKV boundary
      8,9: engine = 3'd3;                    // RoPE/GQA
      10,11,12,13: engine = 3'd4;            // Attention SFU
      default: engine = 3'd5;                // Elementwise/MLP SFU
    endcase
  endfunction

  function automatic logic [31:0] work_items(input logic [4:0] index);
    case (index)
      0,1,16: work_items = 32'd96;
      2: work_items = 32'd73728;
      3,4,5,6: work_items = 32'd12288;
      7: work_items = 32'd480;
      8: work_items = 32'd1024;
      9: work_items = 32'd192;
      10,11: work_items = 32'd24;
      12: work_items = 32'd12;
      13,15,22: work_items = 32'd96;
      14: work_items = 32'd73728;
      17,18,21: work_items = 32'd430080;
      19: work_items = 32'd8960;
      20: work_items = 32'd560;
      default: work_items = 32'd0;
    endcase
  endfunction

  function automatic logic [31:0] matrix_steps(input logic [4:0] index);
    case (index)
      2,14: matrix_steps = 32'd73728;
      3,4,5,6: matrix_steps = 32'd12288;
      17,18,21: matrix_steps = 32'd430080;
      default: matrix_steps = 32'd0;
    endcase
  endfunction

  function automatic logic [31:0] latency(input logic [4:0] index);
    case (index)
      0,1,16: latency = 32'd390;
      2,14: latency = 32'd294912;
      3,4,5,6: latency = 32'd49152;
      7: latency = 32'd800;
      8: latency = 32'd4096;
      9: latency = 32'd296;
      10: latency = 32'd648;
      11: latency = 32'd108;
      12: latency = 32'd48;
      13,15,22: latency = 32'd96;
      17,18,21: latency = 32'd1720320;
      19: latency = 32'd80640;
      20: latency = 32'd560;
      default: latency = 32'd0;
    endcase
  endfunction

  assign command_valid_o = state_q == S_ISSUE;
  assign operation_o = operation(command_index_q);
  assign engine_o = engine(command_index_q);
  assign work_items_o = work_items(command_index_q);
  assign matrix_steps_o = matrix_steps(command_index_q);
  assign measured_latency_o = latency(command_index_q);
  assign score_matrix_o = 1'b0;
  assign active_o = state_q == S_ISSUE || state_q == S_WAIT;
  assign done_o = state_q == S_DONE;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      command_index_q <= '0;
      commands_issued_o <= '0;
      matrix_steps_total_o <= '0;
      busy_cycles_o <= '0;
      score_matrix_commands_o <= '0;
    end else begin
      case (state_q)
        S_IDLE: if (start_i) begin
          command_index_q <= '0;
          commands_issued_o <= '0;
          matrix_steps_total_o <= '0;
          busy_cycles_o <= '0;
          score_matrix_commands_o <= '0;
          state_q <= S_ISSUE;
        end
        S_ISSUE: if (command_ready_i) begin
          commands_issued_o <= commands_issued_o + 1'b1;
          matrix_steps_total_o <= matrix_steps_total_o + matrix_steps_o;
          if (score_matrix_o)
            score_matrix_commands_o <= score_matrix_commands_o + 1'b1;
          state_q <= S_WAIT;
        end
        S_WAIT: begin
          busy_cycles_o <= busy_cycles_o + 1'b1;
          if (engine_done_i) begin
            if (command_index_q == 5'd22)
              state_q <= S_DONE;
            else begin
              command_index_q <= command_index_q + 1'b1;
              state_q <= S_ISSUE;
            end
          end
        end
        S_DONE: if (start_i) begin
          command_index_q <= '0;
          commands_issued_o <= '0;
          matrix_steps_total_o <= '0;
          busy_cycles_o <= '0;
          score_matrix_commands_o <= '0;
          state_q <= S_ISSUE;
        end
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
