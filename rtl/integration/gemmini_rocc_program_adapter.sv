// SPDX-License-Identifier: Apache-2.0
// Ready/valid bridge for an already-validated Gemmini CUSTOM_3 micro-op
// program. RocketTile remains the owner of PTW, TileLink and status context.
`timescale 1ns/1ps
module gemmini_rocc_program_adapter (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        op_valid_i,
  output logic        op_ready_o,
  input  logic        op_first_i,
  input  logic        op_last_i,
  input  logic        op_legal_i,
  input  logic [7:0]  op_status_i,
  input  logic [15:0] event_id_i,
  input  logic [6:0]  op_funct_i,
  input  logic [63:0] op_rs1_i,
  input  logic [63:0] op_rs2_i,

  output logic        rocc_cmd_valid_o,
  input  logic        rocc_cmd_ready_i,
  output logic [6:0]  rocc_inst_funct_o,
  output logic [4:0]  rocc_inst_rs2_o,
  output logic [4:0]  rocc_inst_rs1_o,
  output logic        rocc_inst_xd_o,
  output logic        rocc_inst_xs1_o,
  output logic        rocc_inst_xs2_o,
  output logic [4:0]  rocc_inst_rd_o,
  output logic [6:0]  rocc_inst_opcode_o,
  output logic [63:0] rocc_rs1_o,
  output logic [63:0] rocc_rs2_o,
  input  logic        rocc_busy_i,

  output logic        event_valid_o,
  input  logic        event_ready_i,
  output logic [55:0] event_data_o,
  output logic        illegal_program_o
);
  localparam logic [6:0] CUSTOM_3 = 7'h7b;
  localparam logic [2:0] ENGINE_MATRIX = 3'd2;
  localparam logic [7:0] STATUS_OK = 8'd0;
  localparam logic [7:0] STATUS_ILLEGAL = 8'd1;
  localparam logic [7:0] STATUS_MALFORMED = 8'd2;

  typedef enum logic [2:0] {
    S_IDLE, S_ISSUE, S_LOAD, S_WAIT_BUSY_ASSERT, S_WAIT_BUSY_CLEAR, S_EVENT
  } state_e;
  state_e state_q;
  logic last_q;
  logic [6:0] funct_q;
  logic [63:0] rs1_q, rs2_q;
  logic [15:0] event_id_q;
  logic [7:0] status_q;
  logic [28:0] accepted_q;

  assign op_ready_o = (state_q == S_IDLE) || (state_q == S_LOAD);
  assign rocc_cmd_valid_o = (state_q == S_ISSUE);
  assign rocc_inst_funct_o = funct_q;
  assign rocc_inst_rs2_o = 5'd0;
  assign rocc_inst_rs1_o = 5'd0;
  assign rocc_inst_xd_o = 1'b0;
  assign rocc_inst_xs1_o = 1'b1;
  assign rocc_inst_xs2_o = 1'b1;
  assign rocc_inst_rd_o = 5'd0;
  assign rocc_inst_opcode_o = CUSTOM_3;
  assign rocc_rs1_o = rs1_q;
  assign rocc_rs2_o = rs2_q;
  assign event_valid_o = (state_q == S_EVENT);
  assign event_data_o = {event_id_q, status_q, ENGINE_MATRIX, accepted_q};
  assign illegal_program_o = event_valid_o && (status_q != STATUS_OK);

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      last_q <= 1'b0;
      funct_q <= '0;
      rs1_q <= '0;
      rs2_q <= '0;
      event_id_q <= '0;
      status_q <= STATUS_OK;
      accepted_q <= '0;
    end else begin
      case (state_q)
        S_IDLE: begin
          if (op_valid_i && op_ready_o) begin
            event_id_q <= event_id_i;
            accepted_q <= '0;
            if (!op_first_i || !op_legal_i) begin
              status_q <= op_first_i ? (op_status_i == 0 ? STATUS_ILLEGAL : op_status_i) : STATUS_MALFORMED;
              state_q <= S_EVENT;
            end else begin
              last_q <= op_last_i;
              funct_q <= op_funct_i;
              rs1_q <= op_rs1_i;
              rs2_q <= op_rs2_i;
              status_q <= STATUS_OK;
              state_q <= S_ISSUE;
            end
          end
        end
        S_LOAD: begin
          if (op_valid_i && op_ready_o) begin
            if (op_first_i || !op_legal_i || event_id_i != event_id_q) begin
              status_q <= STATUS_MALFORMED;
              state_q <= S_EVENT;
            end else begin
              last_q <= op_last_i;
              funct_q <= op_funct_i;
              rs1_q <= op_rs1_i;
              rs2_q <= op_rs2_i;
              state_q <= S_ISSUE;
            end
          end
        end
        S_ISSUE: begin
          if (rocc_cmd_valid_o && rocc_cmd_ready_i) begin
            accepted_q <= accepted_q + 1'b1;
            if (last_q)
              state_q <= rocc_busy_i ? S_WAIT_BUSY_CLEAR : S_WAIT_BUSY_ASSERT;
            else
              state_q <= S_LOAD;
          end
        end
        S_WAIT_BUSY_ASSERT: begin
          if (rocc_busy_i)
            state_q <= S_WAIT_BUSY_CLEAR;
        end
        S_WAIT_BUSY_CLEAR: begin
          if (!rocc_busy_i)
            state_q <= S_EVENT;
        end
        S_EVENT: begin
          if (event_valid_o && event_ready_i)
            state_q <= S_IDLE;
        end
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
