// SPDX-License-Identifier: Apache-2.0
module operator_control_endpoint_v3 #(
  parameter int DOMAINS = 10,
  parameter int DOMAIN_W = $clog2(DOMAINS)
) (
  input  logic                 clk_i,
  input  logic                 rst_ni,
  input  logic                 req_valid_i,
  output logic                 req_ready_o,
  input  logic [7:0]           req_opcode_i,
  input  logic [15:0]          req_tag_i,
  input  logic [7:0]           req_parent_phase_i,
  input  logic [7:0]           req_terminal_phase_i,
  input  logic [15:0]          req_index0_i,
  input  logic                 ack_valid_i,
  input  logic [DOMAIN_W-1:0]  ack_domain_i,
  input  logic                 fail_valid_i,
  output logic                 completion_valid_o,
  input  logic                 completion_ready_i,
  output logic [15:0]          completion_tag_o,
  output logic [7:0]           completion_parent_phase_o,
  output logic [7:0]           completion_terminal_phase_o,
  output logic [7:0]           completion_status_o,
  output logic                 protocol_error_o
);
  localparam logic [7:0] OP_BARRIER = 8'h01;
  localparam logic [1:0] S_IDLE = 2'd0;
  localparam logic [1:0] S_START = 2'd1;
  localparam logic [1:0] S_WAIT = 2'd2;
  localparam logic [1:0] S_REPORT = 2'd3;
  logic [1:0] state_q;

  logic [15:0] tag_q;
  logic [7:0] parent_phase_q, terminal_phase_q, status_q;
  logic [DOMAINS-1:0] expected_mask_q;
  logic barrier_start_ready, barrier_finish_ready;
  logic barrier_done_valid, barrier_done_commit, barrier_protocol_error;

  assign req_ready_o = state_q == S_IDLE;
  assign completion_valid_o = state_q == S_REPORT;
  assign completion_tag_o = tag_q;
  assign completion_parent_phase_o = parent_phase_q;
  assign completion_terminal_phase_o = terminal_phase_q;
  assign completion_status_o = status_q;
  assign protocol_error_o = barrier_protocol_error;

  state_commit_barrier #(.SLOTS(8), .TXN_W(16), .DOMAINS(DOMAINS)) u_barrier (
    .clk_i,
    .rst_ni,
    .start_valid_i(state_q == S_START),
    .start_ready_o(barrier_start_ready),
    .start_slot_i(tag_q[2:0]),
    .start_txn_i(tag_q),
    .start_expected_mask_i(expected_mask_q),
    .ack_valid_i(state_q == S_WAIT && ack_valid_i),
    .ack_slot_i(tag_q[2:0]),
    .ack_domain_i,
    .fail_valid_i(state_q == S_WAIT && fail_valid_i),
    .fail_slot_i(tag_q[2:0]),
    .finish_valid_i(state_q == S_WAIT && barrier_finish_ready),
    .finish_ready_o(barrier_finish_ready),
    .finish_slot_i(tag_q[2:0]),
    .finish_commit_i(1'b1),
    .done_valid_o(barrier_done_valid),
    .done_ready_i(state_q == S_WAIT),
    .done_txn_o(),
    .done_commit_o(barrier_done_commit),
    .protocol_error_o(barrier_protocol_error)
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      tag_q <= '0;
      parent_phase_q <= '0;
      terminal_phase_q <= '0;
      status_q <= '0;
      expected_mask_q <= '0;
    end else begin
      case (state_q)
        S_IDLE: if (req_valid_i && req_ready_o) begin
          tag_q <= req_tag_i;
          parent_phase_q <= req_parent_phase_i;
          terminal_phase_q <= req_terminal_phase_i;
          expected_mask_q <= req_index0_i[DOMAINS-1:0];
          if (req_opcode_i != OP_BARRIER || req_index0_i[DOMAINS-1:0] == '0) begin
            status_q <= 8'd4;
            state_q <= S_REPORT;
          end else begin
            status_q <= 8'd0;
            state_q <= S_START;
          end
        end
        S_START: if (barrier_start_ready) state_q <= S_WAIT;
        S_WAIT: begin
          if (barrier_protocol_error) begin
            status_q <= 8'd7;
            state_q <= S_REPORT;
          end else if (barrier_done_valid) begin
            status_q <= barrier_done_commit ? 8'd0 : 8'd7;
            state_q <= S_REPORT;
          end
        end
        S_REPORT: if (completion_valid_o && completion_ready_i) state_q <= S_IDLE;
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
