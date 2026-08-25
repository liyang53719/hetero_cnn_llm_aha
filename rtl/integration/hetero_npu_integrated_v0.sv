// SPDX-License-Identifier: Apache-2.0
// L5/L6 contract integration: command wait/signal scoreboard, the existing
// command shell, and one in-order wrapper per engine. Official Gemmini/AHA/
// iDMA macros replace the adapters without changing this host contract.
module hetero_npu_integrated_v0 (
  input  logic         clk_i,
  input  logic         rst_ni,
  input  logic         host_cmd_valid_i,
  output logic         host_cmd_ready_o,
  input  logic [127:0] host_cmd_data_i,
  output logic         host_event_valid_o,
  input  logic         host_event_ready_i,
  output logic [55:0]  host_event_data_o,
  output logic         illegal_engine_o
);
  logic runnable_valid, runnable_ready;
  logic [127:0] runnable_data;
  logic shell_event_valid, shell_event_ready;
  logic [55:0] shell_event_data;
  logic [5:0] engine_event_valid, engine_event_ready;
  logic [6*56-1:0] engine_event_data;

  logic control_valid, dma_valid, matrix_valid, sfu_valid, kv_valid, collective_valid;
  logic control_ready, dma_ready, matrix_ready, sfu_ready, kv_ready, collective_ready;
  logic [127:0] control_data, dma_data, matrix_data, sfu_data, kv_data, collective_data;

  command_event_scoreboard u_scoreboard (
    .clk_i,
    .rst_ni,
    .host_cmd_valid_i,
    .host_cmd_ready_o,
    .host_cmd_data_i,
    .runnable_cmd_valid_o(runnable_valid),
    .runnable_cmd_ready_i(runnable_ready),
    .runnable_cmd_data_o(runnable_data),
    .completion_valid_i(shell_event_valid),
    .completion_ready_i(shell_event_ready),
    .completion_data_i(shell_event_data)
  );

  assign host_event_valid_o = shell_event_valid;
  assign host_event_data_o  = shell_event_data;
  assign shell_event_ready  = host_event_ready_i;

  hetero_npu_shell u_shell (
    .clk_i,
    .rst_ni,
    .host_cmd_valid_i(runnable_valid),
    .host_cmd_ready_o(runnable_ready),
    .host_cmd_data_i(runnable_data),
    .control_cmd_valid_o(control_valid),
    .control_cmd_ready_i(control_ready),
    .control_cmd_data_o(control_data),
    .dma_cmd_valid_o(dma_valid),
    .dma_cmd_ready_i(dma_ready),
    .dma_cmd_data_o(dma_data),
    .matrix_cmd_valid_o(matrix_valid),
    .matrix_cmd_ready_i(matrix_ready),
    .matrix_cmd_data_o(matrix_data),
    .sfu_cmd_valid_o(sfu_valid),
    .sfu_cmd_ready_i(sfu_ready),
    .sfu_cmd_data_o(sfu_data),
    .kv_cmd_valid_o(kv_valid),
    .kv_cmd_ready_i(kv_ready),
    .kv_cmd_data_o(kv_data),
    .collective_cmd_valid_o(collective_valid),
    .collective_cmd_ready_i(collective_ready),
    .collective_cmd_data_o(collective_data),
    .engine_event_valid_i(engine_event_valid),
    .engine_event_ready_o(engine_event_ready),
    .engine_event_data_i(engine_event_data),
    .event_valid_o(shell_event_valid),
    .event_ready_i(shell_event_ready),
    .event_data_o(shell_event_data),
    .illegal_engine_o
  );

  engine_contract_adapter #(.ENGINE_ID(0), .LATENCY(1)) u_control (
    .clk_i, .rst_ni, .cmd_valid_i(control_valid), .cmd_ready_o(control_ready),
    .cmd_data_i(control_data), .event_valid_o(engine_event_valid[0]),
    .event_ready_i(engine_event_ready[0]), .event_data_o(engine_event_data[0*56 +: 56])
  );
  engine_contract_adapter #(.ENGINE_ID(1), .LATENCY(2)) u_dma (
    .clk_i, .rst_ni, .cmd_valid_i(dma_valid), .cmd_ready_o(dma_ready),
    .cmd_data_i(dma_data), .event_valid_o(engine_event_valid[1]),
    .event_ready_i(engine_event_ready[1]), .event_data_o(engine_event_data[1*56 +: 56])
  );
  engine_contract_adapter #(.ENGINE_ID(2), .LATENCY(3)) u_matrix (
    .clk_i, .rst_ni, .cmd_valid_i(matrix_valid), .cmd_ready_o(matrix_ready),
    .cmd_data_i(matrix_data), .event_valid_o(engine_event_valid[2]),
    .event_ready_i(engine_event_ready[2]), .event_data_o(engine_event_data[2*56 +: 56])
  );
  engine_contract_adapter #(.ENGINE_ID(3), .LATENCY(2)) u_sfu (
    .clk_i, .rst_ni, .cmd_valid_i(sfu_valid), .cmd_ready_o(sfu_ready),
    .cmd_data_i(sfu_data), .event_valid_o(engine_event_valid[3]),
    .event_ready_i(engine_event_ready[3]), .event_data_o(engine_event_data[3*56 +: 56])
  );
  engine_contract_adapter #(.ENGINE_ID(4), .LATENCY(2)) u_kv (
    .clk_i, .rst_ni, .cmd_valid_i(kv_valid), .cmd_ready_o(kv_ready),
    .cmd_data_i(kv_data), .event_valid_o(engine_event_valid[4]),
    .event_ready_i(engine_event_ready[4]), .event_data_o(engine_event_data[4*56 +: 56])
  );
  engine_contract_adapter #(.ENGINE_ID(5), .LATENCY(1)) u_collective (
    .clk_i, .rst_ni, .cmd_valid_i(collective_valid), .cmd_ready_o(collective_ready),
    .cmd_data_i(collective_data), .event_valid_o(engine_event_valid[5]),
    .event_ready_i(engine_event_ready[5]), .event_data_o(engine_event_data[5*56 +: 56])
  );
endmodule
