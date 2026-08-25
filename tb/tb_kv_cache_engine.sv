`timescale 1ns/1ps
module tb_kv_cache_engine;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic cmd_valid, cmd_ready;
  logic [1:0] cmd_op;
  logic [1:0] seq, layer;
  logic [15:0] token;
  logic [63:0] k_word, v_word;
  logic rsp_valid, rsp_ready;
  logic [2:0] status;
  logic [15:0] length;
  logic [63:0] rsp_k, rsp_v;

  kv_cache_engine dut (
    .clk_i(clk), .rst_ni(rst_n),
    .cmd_valid_i(cmd_valid), .cmd_ready_o(cmd_ready), .cmd_op_i(cmd_op),
    .cmd_sequence_i(seq), .cmd_layer_i(layer), .cmd_token_i(token),
    .cmd_k_i(k_word), .cmd_v_i(v_word),
    .rsp_valid_o(rsp_valid), .rsp_ready_i(rsp_ready),
    .rsp_status_o(status), .rsp_length_o(length),
    .rsp_k_o(rsp_k), .rsp_v_o(rsp_v)
  );

  task automatic command(
    input logic [1:0] operation,
    input logic [15:0] token_arg,
    input logic [63:0] k_arg,
    input logic [63:0] v_arg
  );
    begin
      @(negedge clk);
      cmd_op = operation; token = token_arg; k_word = k_arg; v_word = v_arg;
      cmd_valid = 1;
      do @(posedge clk); while (!cmd_ready);
      @(negedge clk);
      cmd_valid = 0;
      do @(posedge clk); while (!rsp_valid);
      if (status != 0) $fatal(1, "KV status=%0d", status);
    end
  endtask

  integer i;
  initial begin
    cmd_valid = 0; cmd_op = 0; seq = 0; layer = 0; token = 0;
    k_word = 0; v_word = 0; rsp_ready = 1;
    repeat (3) @(posedge clk); rst_n = 1;
    for (i = 0; i < 5; i++) begin
      command(2'd0, 0, 64'h100 + i, 64'h200 + i);
      if (length != i + 1) $fatal(1, "append length mismatch");
    end
    command(2'd1, 16'd4, 0, 0);
    if (rsp_k != 64'h104 || rsp_v != 64'h204) $fatal(1, "KV read mismatch");
    command(2'd2, 0, 0, 0);
    if (length != 0) $fatal(1, "KV free length mismatch");
    command(2'd3, 0, 0, 0);
    if (length != 0) $fatal(1, "KV length mismatch");
    $display("TB_KV_PASS");
    $finish;
  end

  initial begin
    repeat (300) @(posedge clk);
    $fatal(1, "KV test timeout");
  end
endmodule
