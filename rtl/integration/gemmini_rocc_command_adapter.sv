// SPDX-License-Identifier: Apache-2.0
// Wrapper-only boundary between the frozen 128-bit command envelope and the
// generated Gemmini RoCC command interface.  This module does not instantiate
// the official Gemmini: RocketTile must still provide PTW, TileLink scratchpad
// and architectural status fields described in the official interface audit.
module gemmini_rocc_command_adapter (
  input  logic         clk_i,
  input  logic         rst_ni,

  input  logic         host_cmd_valid_i,
  output logic         host_cmd_ready_o,
  input  logic [127:0] host_cmd_data_i,

  output logic         rocc_cmd_valid_o,
  input  logic         rocc_cmd_ready_i,
  output logic [6:0]   rocc_inst_funct_o,
  output logic [4:0]   rocc_inst_rs2_o,
  output logic [4:0]   rocc_inst_rs1_o,
  output logic         rocc_inst_xd_o,
  output logic         rocc_inst_xs1_o,
  output logic         rocc_inst_xs2_o,
  output logic [4:0]   rocc_inst_rd_o,
  output logic [6:0]   rocc_inst_opcode_o,
  output logic [63:0]  rocc_rs1_o,
  output logic [63:0]  rocc_rs2_o,

  input  logic         rocc_resp_valid_i,
  output logic         rocc_resp_ready_o,
  input  logic [4:0]   rocc_resp_rd_i,
  input  logic [63:0]  rocc_resp_data_i,
  input  logic         rocc_busy_i,

  output logic         event_valid_o,
  input  logic         event_ready_i,
  output logic [55:0]  event_data_o,
  output logic         illegal_command_o
);
  localparam logic [7:0] OP_MATRIX_GEMM = 8'h20;
  localparam logic [7:0] OP_MATRIX_GEMV = 8'h21;
  localparam logic [7:0] OP_MATRIX_CONV = 8'h22;
  localparam logic [2:0] ENGINE_MATRIX  = 3'd2;
  localparam logic [6:0] ROCC_CUSTOM0   = 7'b0001011;

  typedef enum logic [1:0] {S_IDLE, S_ISSUE, S_WAIT_RESP, S_EVENT} state_e;
  state_e state_q;
  logic [15:0] wait_q, signal_q;
  logic [127:0] command_q;
  logic [7:0] event_status_q;
  logic [4:0] response_rd_q;
  logic [63:0] response_data_q;

  logic command_legal;
  logic [6:0] decoded_funct_q;
  assign command_legal = (host_cmd_data_i[10:8] == ENGINE_MATRIX) &&
                         ((host_cmd_data_i[7:0] == OP_MATRIX_GEMM) ||
                          (host_cmd_data_i[7:0] == OP_MATRIX_GEMV) ||
                          (host_cmd_data_i[7:0] == OP_MATRIX_CONV));
  assign host_cmd_ready_o = (state_q == S_IDLE);
  assign rocc_cmd_valid_o = (state_q == S_ISSUE);
  assign rocc_resp_ready_o = (state_q == S_WAIT_RESP);
  assign event_valid_o = (state_q == S_EVENT);
  assign illegal_command_o = (state_q == S_EVENT) && (event_status_q != 0);

  assign rocc_inst_funct_o  = decoded_funct_q;
  assign rocc_inst_rs1_o   = 5'd0;
  assign rocc_inst_rs2_o   = 5'd0;
  assign rocc_inst_rd_o    = command_q[108:104];
  assign rocc_inst_xd_o    = (command_q[127:104] != 0);
  assign rocc_inst_xs1_o   = 1'b1;
  assign rocc_inst_xs2_o   = 1'b1;
  assign rocc_inst_opcode_o= ROCC_CUSTOM0;
  assign rocc_rs1_o       = {40'd0, command_q[79:56]};
  assign rocc_rs2_o       = {40'd0, command_q[103:80]};
  assign event_data_o     = {signal_q, wait_q, response_rd_q, event_status_q, 11'd0};

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q         <= S_IDLE;
      command_q      <= '0;
      decoded_funct_q<= 7'h7f;
      wait_q         <= '0;
      signal_q       <= '0;
      event_status_q <= '0;
      response_rd_q  <= '0;
      response_data_q<= '0;
    end else begin
      unique case (state_q)
        S_IDLE: begin
          if (host_cmd_valid_i && host_cmd_ready_o) begin
            command_q <= host_cmd_data_i;
            unique case (host_cmd_data_i[7:0])
              OP_MATRIX_GEMM: decoded_funct_q <= 7'h00;
              OP_MATRIX_GEMV: decoded_funct_q <= 7'h01;
              OP_MATRIX_CONV: decoded_funct_q <= 7'h02;
              default:        decoded_funct_q <= 7'h7f;
            endcase
            wait_q    <= host_cmd_data_i[39:24];
            signal_q  <= host_cmd_data_i[55:40];
            response_rd_q   <= '0;
            response_data_q <= '0;
            if (command_legal) begin
              event_status_q <= 8'd0;
              state_q <= S_ISSUE;
            end else begin
              event_status_q <= 8'd1;
              state_q <= S_EVENT;
            end
          end
        end
        S_ISSUE: begin
          if (rocc_cmd_valid_o && rocc_cmd_ready_i)
            state_q <= S_WAIT_RESP;
        end
        S_WAIT_RESP: begin
          if (rocc_resp_valid_i && rocc_resp_ready_o) begin
            response_rd_q   <= rocc_resp_rd_i;
            response_data_q <= rocc_resp_data_i;
            state_q         <= S_EVENT;
          end
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
