`timescale 1ns/1ps
module tb_operator_control_endpoint_v3;
  logic clk_i = 0, rst_ni = 1;
  always #1 clk_i = ~clk_i;
  logic req_valid_i, req_ready_o;
  logic [7:0] req_opcode_i;
  logic [15:0] req_tag_i, req_index0_i;
  logic [7:0] req_parent_phase_i, req_terminal_phase_i;
  logic ack_valid_i, fail_valid_i;
  logic [3:0] ack_domain_i;
  logic completion_valid_o, completion_ready_i, protocol_error_o;
  logic [15:0] completion_tag_o;
  logic [7:0] completion_parent_phase_o, completion_terminal_phase_o, completion_status_o;

  operator_control_endpoint_v3 dut(.*);

  task automatic request(input logic [7:0] opcode, input logic [15:0] mask, input logic [15:0] tag);
    begin
      @(negedge clk_i);
      req_opcode_i = opcode; req_index0_i = mask; req_tag_i = tag;
      req_parent_phase_i = 8'h12; req_terminal_phase_i = 8'h34;
      req_valid_i = 1;
      do @(posedge clk_i); while (!req_ready_o);
      @(negedge clk_i);
      req_valid_i = 0;
    end
  endtask

  task automatic acknowledge(input logic [3:0] domain);
    begin
      @(negedge clk_i);
      ack_domain_i = domain; ack_valid_i = 1;
      @(posedge clk_i); @(negedge clk_i); ack_valid_i = 0;
    end
  endtask

  initial begin
    repeat(500) @(posedge clk_i);
    $display("DEBUG state=%0d req_ready=%0b completion=%0b start_ready=%0b finish_ready=%0b done=%0b active=%0b expected=%h ack=%h",
      dut.state_q, req_ready_o, completion_valid_o, dut.barrier_start_ready,
      dut.barrier_finish_ready, dut.barrier_done_valid, dut.u_barrier.active_q[2],
      dut.u_barrier.expected_q[2], dut.u_barrier.ack_q[2]);
    $fatal(1,"watchdog timeout");
  end

  initial begin
    #0.1 rst_ni=0;
    req_valid_i=0; req_opcode_i=0; req_tag_i=0; req_index0_i=0;
    req_parent_phase_i=0; req_terminal_phase_i=0; ack_valid_i=0;
    ack_domain_i=0; fail_valid_i=0; completion_ready_i=0;
    repeat(3) @(posedge clk_i); @(negedge clk_i); rst_ni=1;

    request(8'h01, 16'h0005, 16'h55aa);
    repeat(5) begin @(posedge clk_i); if(completion_valid_o) $fatal(1,"early completion"); end
    acknowledge(0);
    repeat(3) begin @(posedge clk_i); if(completion_valid_o) $fatal(1,"completion before domain2"); end
    acknowledge(2);
    wait(completion_valid_o);
    if(completion_status_o!=0 || completion_tag_o!=16'h55aa ||
       completion_parent_phase_o!=8'h12 || completion_terminal_phase_o!=8'h34)
      $fatal(1,"bad successful completion");
    repeat(3) begin
      @(posedge clk_i);
      if(!completion_valid_o || completion_tag_o!=16'h55aa) $fatal(1,"unstable completion");
    end
    @(negedge clk_i); completion_ready_i=1; @(posedge clk_i); @(negedge clk_i); completion_ready_i=0;

    request(8'h01, 16'h0000, 16'h0101);
    wait(completion_valid_o);
    if(completion_status_o!=8'd4) $fatal(1,"zero mask accepted");
    @(negedge clk_i); completion_ready_i=1; @(posedge clk_i); @(negedge clk_i); completion_ready_i=0;

    request(8'hff, 16'h0001, 16'h0202);
    wait(completion_valid_o);
    if(completion_status_o!=8'd4) $fatal(1,"illegal opcode accepted");
    @(negedge clk_i); completion_ready_i=1; @(posedge clk_i); @(negedge clk_i); completion_ready_i=0;

    if(protocol_error_o) $fatal(1,"unexpected protocol error");
    $display("OPERATOR_CONTROL_ENDPOINT_V3_PASS barriers=1 illegal=2 early_completion=0");
    $finish;
  end
endmodule
