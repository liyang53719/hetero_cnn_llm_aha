`timescale 1ns/1ps
module tb_command_event_scoreboard;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  logic host_valid, host_ready, run_valid, run_ready;
  logic [127:0] host_data, run_data;
  logic completion_valid, completion_ready;
  logic [55:0] completion_data;

  command_event_scoreboard dut (
    .clk_i(clk), .rst_ni(rst_n), .host_cmd_valid_i(host_valid),
    .host_cmd_ready_o(host_ready), .host_cmd_data_i(host_data),
    .runnable_cmd_valid_o(run_valid), .runnable_cmd_ready_i(run_ready),
    .runnable_cmd_data_o(run_data), .completion_valid_i(completion_valid),
    .completion_ready_i(completion_ready), .completion_data_i(completion_data)
  );

  task automatic pulse_completion(input logic [15:0] eid, input logic [7:0] status);
    begin
      @(negedge clk); completion_data={eid,status,3'd2,29'd7}; completion_valid=1;
      @(posedge clk); @(negedge clk); completion_valid=0;
    end
  endtask

  initial begin
    host_valid=0; host_data=0; run_ready=1; completion_valid=0;
    completion_ready=1; completion_data=0;
    repeat(3) @(posedge clk); rst_n=1;
    @(negedge clk); host_data[39:24]=16'h0023; host_valid=1;
    @(posedge clk); if (host_ready || run_valid) $fatal(1,"wait released before event");
    pulse_completion(16'h0023,8'd0);
    @(posedge clk); if (!host_ready || !run_valid || run_data!=host_data) $fatal(1,"good event did not release wait");
    @(negedge clk); host_valid=0;

    @(negedge clk); host_data[39:24]=16'h0024; host_valid=1;
    pulse_completion(16'h0024,8'd1);
    @(posedge clk); if (host_ready || run_valid) $fatal(1,"error completion released wait");
    @(negedge clk); host_data[39:24]=16'h0123;
    @(posedge clk); if (host_ready || run_valid) $fatal(1,"high event ID released before completion");
    pulse_completion(16'h0123,8'd0);
    @(posedge clk); if (!host_ready || !run_valid) $fatal(1,"16-bit event ID did not release wait");
    $display("COMMAND_EVENT_SCOREBOARD_PASS");
    $finish;
  end
  initial begin repeat(200) @(posedge clk); $fatal(1,"timeout"); end
endmodule
