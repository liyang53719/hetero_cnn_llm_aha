// SPDX-License-Identifier: Apache-2.0
// Depth-16 command/completion queues around the real-SRAM event scoreboard.
`timescale 1ns/1ps
module command_event_frontend_sram(
  input logic clk_i,input logic rst_ni,
  input logic host_cmd_valid_i,output logic host_cmd_ready_o,input logic[127:0]host_cmd_data_i,
  output logic runnable_cmd_valid_o,input logic runnable_cmd_ready_i,output logic[127:0]runnable_cmd_data_o,
  input logic completion_valid_i,output logic completion_ready_o,input logic[55:0]completion_data_i,
  output logic init_done_o,output logic[4:0]command_level_o,output logic[4:0]completion_level_o,
  output logic[31:0]macro_error_count_o
);
  logic cmd_in_ready,cmd_out_valid,cmd_out_ready;logic[127:0]cmd_out_data;
  logic completion_in_ready,completion_out_valid,completion_out_ready;logic[55:0]completion_out_data;
  logic scoreboard_init;
  assign host_cmd_ready_o=scoreboard_init&&cmd_in_ready;
  assign completion_ready_o=completion_in_ready;
  assign init_done_o=scoreboard_init;
  rv_fifo #(.WIDTH(128),.DEPTH(16))u_command_fifo(
    .clk_i,.rst_ni,.in_valid_i(host_cmd_valid_i&&scoreboard_init),.in_ready_o(cmd_in_ready),
    .in_data_i(host_cmd_data_i),.out_valid_o(cmd_out_valid),.out_ready_i(cmd_out_ready),
    .out_data_o(cmd_out_data),.level_o(command_level_o));
  rv_fifo #(.WIDTH(56),.DEPTH(16))u_completion_fifo(
    .clk_i,.rst_ni,.in_valid_i(completion_valid_i),.in_ready_o(completion_in_ready),
    .in_data_i(completion_data_i),.out_valid_o(completion_out_valid),
    .out_ready_i(completion_out_ready),.out_data_o(completion_out_data),
    .level_o(completion_level_o));
  command_event_scoreboard_sram u_scoreboard(
    .clk_i,.rst_ni,.host_cmd_valid_i(cmd_out_valid),.host_cmd_ready_o(cmd_out_ready),
    .host_cmd_data_i(cmd_out_data),.runnable_cmd_valid_o,.runnable_cmd_ready_i,
    .runnable_cmd_data_o,.completion_valid_i(completion_out_valid),
    .completion_ready_o(completion_out_ready),.completion_data_i(completion_out_data),
    .init_done_o(scoreboard_init),.macro_error_count_o);
endmodule
