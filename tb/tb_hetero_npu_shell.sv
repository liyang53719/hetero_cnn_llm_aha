`timescale 1ns/1ps
module tb_hetero_npu_shell;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic host_cmd_valid, host_cmd_ready;
  logic [127:0] host_cmd_data;
  logic control_cmd_valid, dma_cmd_valid, matrix_cmd_valid;
  logic sfu_cmd_valid, kv_cmd_valid, collective_cmd_valid;
  logic control_cmd_ready, dma_cmd_ready, matrix_cmd_ready;
  logic sfu_cmd_ready, kv_cmd_ready, collective_cmd_ready;
  logic [127:0] control_cmd_data, dma_cmd_data, matrix_cmd_data;
  logic [127:0] sfu_cmd_data, kv_cmd_data, collective_cmd_data;
  logic [5:0] engine_event_valid, engine_event_ready;
  logic [6*56-1:0] engine_event_data;
  logic event_valid, event_ready;
  logic [55:0] event_data;
  logic illegal_engine;
  logic [127:0] expected_matrix_cmd;

  hetero_npu_shell dut (
    .clk_i(clk), .rst_ni(rst_n),
    .host_cmd_valid_i(host_cmd_valid), .host_cmd_ready_o(host_cmd_ready),
    .host_cmd_data_i(host_cmd_data),
    .control_cmd_valid_o(control_cmd_valid), .control_cmd_ready_i(control_cmd_ready),
    .control_cmd_data_o(control_cmd_data),
    .dma_cmd_valid_o(dma_cmd_valid), .dma_cmd_ready_i(dma_cmd_ready),
    .dma_cmd_data_o(dma_cmd_data),
    .matrix_cmd_valid_o(matrix_cmd_valid), .matrix_cmd_ready_i(matrix_cmd_ready),
    .matrix_cmd_data_o(matrix_cmd_data),
    .sfu_cmd_valid_o(sfu_cmd_valid), .sfu_cmd_ready_i(sfu_cmd_ready),
    .sfu_cmd_data_o(sfu_cmd_data),
    .kv_cmd_valid_o(kv_cmd_valid), .kv_cmd_ready_i(kv_cmd_ready),
    .kv_cmd_data_o(kv_cmd_data),
    .collective_cmd_valid_o(collective_cmd_valid),
    .collective_cmd_ready_i(collective_cmd_ready),
    .collective_cmd_data_o(collective_cmd_data),
    .engine_event_valid_i(engine_event_valid),
    .engine_event_ready_o(engine_event_ready),
    .engine_event_data_i(engine_event_data),
    .event_valid_o(event_valid), .event_ready_i(event_ready),
    .event_data_o(event_data), .illegal_engine_o(illegal_engine)
  );

  task automatic send_command(input logic [2:0] engine, input logic [127:0] payload);
    begin
      @(negedge clk);
      host_cmd_data = payload;
      host_cmd_data[10:8] = engine;
      host_cmd_valid = 1'b1;
      do @(posedge clk); while (!host_cmd_ready);
      @(negedge clk);
      host_cmd_valid = 1'b0;
    end
  endtask

  initial begin
    host_cmd_valid = 1'b0;
    host_cmd_data = '0;
    expected_matrix_cmd = 128'h0123_4567_89ab_cdef;
    expected_matrix_cmd[10:8] = 3'd2;
    control_cmd_ready = 1'b1;
    dma_cmd_ready = 1'b1;
    matrix_cmd_ready = 1'b1;
    sfu_cmd_ready = 1'b1;
    kv_cmd_ready = 1'b1;
    collective_cmd_ready = 1'b1;
    engine_event_valid = '0;
    engine_event_data = '0;
    event_ready = 1'b1;

    repeat (3) @(posedge clk);
    rst_n = 1'b1;

    send_command(3'd2, 128'h0123_4567_89ab_cdef);
    wait (matrix_cmd_valid);
    if (matrix_cmd_data != expected_matrix_cmd)
      $fatal(1, "matrix dispatch payload mismatch");
    @(posedge clk);

    send_command(3'd7, 128'hdead_beef);
    wait (illegal_engine);
    @(posedge clk);

    engine_event_data[0*56 +: 56] = 56'h0001_02_003;
    engine_event_data[2*56 +: 56] = 56'h0002_04_005;
    engine_event_valid[0] = 1'b1;
    engine_event_valid[2] = 1'b1;
    #1;
    if (!event_valid || event_data != 56'h0001_02_003 || !engine_event_ready[0])
      $fatal(1, "event priority/ready mismatch");
    engine_event_valid[0] = 1'b0;
    #1;
    if (!event_valid || event_data != 56'h0002_04_005 || !engine_event_ready[2])
      $fatal(1, "event second source mismatch");

    $display("TB_SHELL_PASS");
    $finish;
  end

  initial begin
    repeat (150) @(posedge clk);
    $fatal(1, "shell test timeout");
  end
endmodule
