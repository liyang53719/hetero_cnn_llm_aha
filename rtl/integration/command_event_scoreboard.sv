// SPDX-License-Identifier: Apache-2.0
// Event wait gate for the frozen 128-bit command envelope.
// v0 stores the low 8 bits of event IDs; the full 16-bit ID remains on the
// interface and IDs above 255 are deliberately rejected by the gate.
`timescale 1ns/1ps
module command_event_scoreboard #(
  parameter integer EVENT_SLOTS = 256
) (
  input  logic         clk_i,
  input  logic         rst_ni,
  input  logic         host_cmd_valid_i,
  output logic         host_cmd_ready_o,
  input  logic [127:0] host_cmd_data_i,
  output logic         runnable_cmd_valid_o,
  input  logic         runnable_cmd_ready_i,
  output logic [127:0] runnable_cmd_data_o,
  input  logic         completion_valid_i,
  input  logic         completion_ready_i,
  input  logic [55:0]  completion_data_i
);
  logic [EVENT_SLOTS-1:0] event_seen_q;
  logic [15:0] wait_id;
  logic wait_ok;

  assign wait_id = host_cmd_data_i[39:24];
  assign wait_ok = (wait_id == 16'd0) ||
                   ((wait_id[15:8] == 8'd0) && event_seen_q[wait_id[7:0]]);
  assign runnable_cmd_valid_o = host_cmd_valid_i && wait_ok;
  assign runnable_cmd_data_o  = host_cmd_data_i;
  assign host_cmd_ready_o     = wait_ok && runnable_cmd_ready_i;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      event_seen_q <= '0;
    end else if (completion_valid_i && completion_ready_i) begin
      // Frozen completion layout is {event_id[15:0], status[7:0],
      // engine_id[2:0], counter[28:0]}. v0 indexes the low event-ID byte.
      if (completion_data_i[39:32] == 8'd0)
        event_seen_q[completion_data_i[47:40]] <= 1'b1;
    end
  end
endmodule
