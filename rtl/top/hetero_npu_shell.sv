// SPDX-License-Identifier: Apache-2.0
// Integration shell: command queue + per-engine command ports + completion
// event arbiter.  Generated Gemmini and Garnet macros are connected outside
// this clean-room shell through adapters.
module hetero_npu_shell #(
  parameter integer CMD_DEPTH = 16
) (
  input  logic         clk_i,
  input  logic         rst_ni,

  input  logic         host_cmd_valid_i,
  output logic         host_cmd_ready_o,
  input  logic [127:0] host_cmd_data_i,

  output logic         control_cmd_valid_o,
  input  logic         control_cmd_ready_i,
  output logic [127:0] control_cmd_data_o,
  output logic         dma_cmd_valid_o,
  input  logic         dma_cmd_ready_i,
  output logic [127:0] dma_cmd_data_o,
  output logic         matrix_cmd_valid_o,
  input  logic         matrix_cmd_ready_i,
  output logic [127:0] matrix_cmd_data_o,
  output logic         sfu_cmd_valid_o,
  input  logic         sfu_cmd_ready_i,
  output logic [127:0] sfu_cmd_data_o,
  output logic         kv_cmd_valid_o,
  input  logic         kv_cmd_ready_i,
  output logic [127:0] kv_cmd_data_o,
  output logic         collective_cmd_valid_o,
  input  logic         collective_cmd_ready_i,
  output logic [127:0] collective_cmd_data_o,

  input  logic [5:0]   engine_event_valid_i,
  output logic [5:0]   engine_event_ready_o,
  input  logic [6*56-1:0] engine_event_data_i, // {event_id[15:0],status[7:0],engine[2:0],counter[28:0]}
  output logic         event_valid_o,
  input  logic         event_ready_i,
  output logic [55:0]  event_data_o,
  output logic         illegal_engine_o
);
  logic fifo_valid, fifo_ready;
  logic [127:0] fifo_data;
  logic [$clog2(CMD_DEPTH+1)-1:0] unused_level;

  rv_fifo #(.WIDTH(128), .DEPTH(CMD_DEPTH)) u_cmd_fifo (
    .clk_i,
    .rst_ni,
    .in_valid_i(host_cmd_valid_i),
    .in_ready_o(host_cmd_ready_o),
    .in_data_i(host_cmd_data_i),
    .out_valid_o(fifo_valid),
    .out_ready_i(fifo_ready),
    .out_data_o(fifo_data),
    .level_o(unused_level)
  );

  command_dispatch u_dispatch (
    .cmd_valid_i(fifo_valid),
    .cmd_ready_o(fifo_ready),
    .cmd_data_i(fifo_data),
    .control_valid_o(control_cmd_valid_o),
    .control_ready_i(control_cmd_ready_i),
    .control_data_o(control_cmd_data_o),
    .dma_valid_o(dma_cmd_valid_o),
    .dma_ready_i(dma_cmd_ready_i),
    .dma_data_o(dma_cmd_data_o),
    .matrix_valid_o(matrix_cmd_valid_o),
    .matrix_ready_i(matrix_cmd_ready_i),
    .matrix_data_o(matrix_cmd_data_o),
    .sfu_valid_o(sfu_cmd_valid_o),
    .sfu_ready_i(sfu_cmd_ready_i),
    .sfu_data_o(sfu_cmd_data_o),
    .kv_valid_o(kv_cmd_valid_o),
    .kv_ready_i(kv_cmd_ready_i),
    .kv_data_o(kv_cmd_data_o),
    .collective_valid_o(collective_cmd_valid_o),
    .collective_ready_i(collective_cmd_ready_i),
    .collective_data_o(collective_cmd_data_o),
    .illegal_engine_o(illegal_engine_o)
  );

  // Fixed-priority event arbiter.  Events are low-rate control traffic; a
  // round-robin arbiter can replace this without changing the interface.
  integer e;
  logic selected;
  always_comb begin
    event_valid_o       = 1'b0;
    event_data_o        = '0;
    engine_event_ready_o= '0;
    selected            = 1'b0;
    for (e = 0; e < 6; e++) begin
      if (!selected && engine_event_valid_i[e]) begin
        event_valid_o = 1'b1;
        event_data_o  = engine_event_data_i[e*56 +: 56];
        engine_event_ready_o[e] = event_ready_i;
        selected = 1'b1;
      end
    end
  end
endmodule
