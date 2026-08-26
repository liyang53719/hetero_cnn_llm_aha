`timescale 1ns/1ps
module tb_l5_q128_count_controller;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic start, command_valid, command_ready, latency_valid, score_matrix;
  logic engine_done, done;
  logic [4:0] operation;
  logic [2:0] engine;
  logic [31:0] work_items, matrix_steps;
  logic [31:0] commands, matrix_total, rope_total, dot_total, online_total;
  logic [31:0] reciprocal_total, normalize_total, silu_total, product_total, score_total;
  logic [63:0] command_hash;
  integer cycles;

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;

  l5_q128_count_controller dut(
    .clk_i(clk), .rst_ni(rst_n), .start_i(start),
    .command_valid_o(command_valid), .command_ready_i(command_ready),
    .operation_o(operation), .engine_o(engine), .work_items_o(work_items),
    .matrix_steps_o(matrix_steps), .measured_latency_valid_o(latency_valid),
    .score_matrix_o(score_matrix), .engine_done_i(engine_done), .done_o(done),
    .commands_issued_o(commands), .matrix_steps_total_o(matrix_total),
    .rope_pairs_total_o(rope_total), .dot_operations_total_o(dot_total),
    .online_updates_total_o(online_total), .reciprocals_total_o(reciprocal_total),
    .normalization_chunks_total_o(normalize_total), .silu_scalars_total_o(silu_total),
    .product_chunks_total_o(product_total), .score_matrix_commands_o(score_total)
  );

  function automatic [63:0] hash_command(
    input logic [63:0] seed,
    input logic [4:0] op,
    input logic [2:0] eng,
    input logic [31:0] work,
    input logic [31:0] steps
  );
    logic [63:0] value;
    begin
      value = (seed ^ {59'd0, op}) * 64'h100000001b3;
      value = (value ^ {61'd0, eng}) * 64'h100000001b3;
      value = (value ^ {32'd0, work}) * 64'h100000001b3;
      value = (value ^ {32'd0, steps}) * 64'h100000001b3;
      hash_command = value;
    end
  endfunction

  initial begin
    static int op [0:23] = '{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,0,17,18,19,20,21,22};
    static int eng [0:23] = '{1,0,0,0,2,2,2,3,3,3,3,4,4,4,4,0,5,1,0,0,5,5,0,5};
    static int work [0:23] = '{12288,589824,98304,98304,12288,2048,2048,98304,16384,12288,12288,99072,99072,1536,12288,589824,12288,12288,3440640,3440640,1146880,71680,3440640,12288};
    static int steps [0:23] = '{0,589824,98304,98304,0,0,0,0,0,0,0,0,0,0,0,589824,0,0,3440640,3440640,0,0,3440640,0};
    clk = 0;
    rst_n = 0;
    start = 0;
    command_ready = 0;
    engine_done = 0;
    command_hash = 64'hcbf29ce484222325;
    repeat (3) @(posedge clk);
    rst_n = 1;
    @(negedge clk);
    start = 1;
    @(posedge clk);
    @(negedge clk);
    start = 0;
    for (int index = 0; index < 24; index++) begin
      do @(negedge clk); while (!command_valid);
      if (operation != op[index][4:0] || engine != eng[index][2:0] ||
          work_items != work[index] || matrix_steps != steps[index] ||
          latency_valid || score_matrix)
        $fatal(1, "q128 count command mismatch index=%0d", index);
      command_hash = hash_command(command_hash, operation, engine, work_items, matrix_steps);
      command_ready = 1;
      @(posedge clk);
      @(negedge clk);
      command_ready = 0;
      engine_done = 1;
      @(posedge clk);
      @(negedge clk);
      engine_done = 0;
    end
    if (!done || commands != 24 || matrix_total != 11698176 ||
        rope_total != 114688 || dot_total != 99072 || online_total != 99072 ||
        reciprocal_total != 1536 || normalize_total != 12288 ||
        silu_total != 1146880 || product_total != 71680 || score_total != 0)
      $fatal(1, "q128 count totals commands=%0d matrix=%0d rope=%0d dot=%0d online=%0d",
             commands, matrix_total, rope_total, dot_total, online_total);
    $display(
      "L5_Q128_COUNT_CONTROLLER_PASS commands=24 matrix_steps=11698176 rope_pairs=114688 dot_ops=99072 online_updates=99072 reciprocals=1536 normalization_chunks=12288 silu_scalars=1146880 product_chunks=71680 score_matrix_commands=0 measured_latency_valid=0 command_fnv64=%016h cycles=%0d",
      command_hash, cycles
    );
    $finish;
  end

  initial begin
    repeat (1000) @(posedge clk);
    $fatal(1, "q128 count controller timeout");
  end
endmodule
