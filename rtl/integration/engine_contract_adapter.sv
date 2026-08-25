// SPDX-License-Identifier: Apache-2.0
// Contract-level engine wrapper used until an official macro is connected.
// It preserves one-command-in-order, ready/valid and completion semantics.
module engine_contract_adapter #(
  parameter integer ENGINE_ID = 0,
  parameter integer LATENCY = 2
) (
  input  logic         clk_i,
  input  logic         rst_ni,
  input  logic         cmd_valid_i,
  output logic         cmd_ready_o,
  input  logic [127:0] cmd_data_i,
  output logic         event_valid_o,
  input  logic         event_ready_i,
  output logic [55:0]  event_data_o
);
  localparam logic [2:0] ENGINE_ID_W = ENGINE_ID;
  logic busy_q;
  logic [31:0] countdown_q;
  logic [15:0] signal_q;
  logic [7:0] status_q;
  logic [28:0] counter_q;
  logic event_valid_q;
  logic [55:0] event_data_q;

  assign cmd_ready_o   = !busy_q && !event_valid_q;
  assign event_valid_o = event_valid_q;
  assign event_data_o  = event_data_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      busy_q       <= 1'b0;
      countdown_q  <= '0;
      signal_q     <= '0;
      status_q     <= '0;
      counter_q    <= '0;
      event_valid_q<= 1'b0;
      event_data_q <= '0;
    end else begin
      if (event_valid_q && event_ready_i)
        event_valid_q <= 1'b0;

      if (!busy_q && !event_valid_q && cmd_valid_i && cmd_ready_o) begin
        busy_q      <= 1'b1;
        countdown_q <= (LATENCY <= 1) ? 1 : LATENCY;
        signal_q    <= cmd_data_i[55:40];
        status_q    <= (cmd_data_i[10:8] == ENGINE_ID_W) ? 8'd0 : 8'd1;
        counter_q   <= '0;
      end else if (busy_q) begin
        if (countdown_q <= 1) begin
          busy_q        <= 1'b0;
          event_valid_q <= 1'b1;
          event_data_q  <= {signal_q, status_q, ENGINE_ID_W, counter_q};
        end else begin
          countdown_q <= countdown_q - 1'b1;
          counter_q   <= counter_q + 1'b1;
        end
      end
    end
  end
endmodule
