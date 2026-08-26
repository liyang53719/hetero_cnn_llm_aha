`timescale 1ns/1ps
module tb_l5_target_trace_controller;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic start;
  logic command_valid, command_ready, engine_done, active, done;
  logic [4:0] operation;
  logic [2:0] engine;
  logic [31:0] work_items, matrix_steps, latency;
  logic score_matrix;
  logic [31:0] commands_issued, matrix_steps_total, score_matrix_commands;
  logic [63:0] busy_cycles, command_hash;
  logic [4:0] expected_operation [0:22];
  logic [2:0] expected_engine [0:22];
  logic [31:0] expected_work [0:22], expected_steps [0:22], expected_latency [0:22];
  integer wall_cycles;

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) wall_cycles <= 0;
    else wall_cycles <= wall_cycles + 1;

  l5_target_trace_controller dut(
    .clk_i(clk), .rst_ni(rst_n), .start_i(start),
    .command_valid_o(command_valid), .command_ready_i(command_ready),
    .operation_o(operation), .engine_o(engine), .work_items_o(work_items),
    .matrix_steps_o(matrix_steps), .measured_latency_o(latency),
    .score_matrix_o(score_matrix), .engine_done_i(engine_done),
    .active_o(active), .done_o(done), .commands_issued_o(commands_issued),
    .matrix_steps_total_o(matrix_steps_total), .busy_cycles_o(busy_cycles),
    .score_matrix_commands_o(score_matrix_commands)
  );

  function automatic [63:0] hash_command(
    input logic [63:0] seed,
    input logic [4:0] op,
    input logic [2:0] eng,
    input logic [31:0] work,
    input logic [31:0] steps,
    input logic [31:0] delay_cycles
  );
    logic [63:0] value;
    begin
      value = (seed ^ {59'd0, op}) * 64'h100000001b3;
      value = (value ^ {61'd0, eng}) * 64'h100000001b3;
      value = (value ^ {32'd0, work}) * 64'h100000001b3;
      value = (value ^ {32'd0, steps}) * 64'h100000001b3;
      value = (value ^ {32'd0, delay_cycles}) * 64'h100000001b3;
      hash_command = value;
    end
  endfunction

  initial begin
    static int op_values [0:22] = '{0,0,1,2,2,3,3,4,5,6,7,8,9,10,11,12,0,13,14,15,16,17,18};
    static int eng_values [0:22] = '{1,1,0,0,0,0,0,2,3,3,4,4,4,4,0,5,1,0,0,5,5,0,5};
    static int work_values [0:22] = '{96,96,73728,12288,12288,12288,12288,480,1024,192,24,24,12,96,73728,96,96,430080,430080,8960,560,430080,96};
    static int step_values [0:22] = '{0,0,73728,12288,12288,12288,12288,0,0,0,0,0,0,0,73728,0,0,430080,430080,0,0,430080,0};
    static int latency_values [0:22] = '{390,390,294912,49152,49152,49152,49152,800,4096,296,648,108,48,96,294912,96,390,1720320,1720320,80640,560,1720320,96};
    for (int i = 0; i < 23; i++) begin
      expected_operation[i] = op_values[i][4:0];
      expected_engine[i] = eng_values[i][2:0];
      expected_work[i] = work_values[i];
      expected_steps[i] = step_values[i];
      expected_latency[i] = latency_values[i];
    end
  end

  initial begin
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
    for (int command = 0; command < 23; command++) begin
      do @(negedge clk); while (!command_valid);
      if (operation != expected_operation[command] ||
          engine != expected_engine[command] ||
          work_items != expected_work[command] ||
          matrix_steps != expected_steps[command] ||
          latency != expected_latency[command] || score_matrix)
        $fatal(1, "target trace command mismatch index=%0d", command);
      command_hash = hash_command(
        command_hash, operation, engine, work_items, matrix_steps, latency
      );
      command_ready = 1;
      @(posedge clk);
      @(negedge clk);
      command_ready = 0;
      for (int busy = 0; busy < expected_latency[command]; busy++) begin
        engine_done = busy == expected_latency[command] - 1;
        @(posedge clk);
        @(negedge clk);
      end
      engine_done = 0;
    end
    if (!done || active || commands_issued != 23 ||
        matrix_steps_total != 1486848 || busy_cycles != 64'd6036046 ||
        score_matrix_commands != 0)
      $fatal(1, "target trace totals commands=%0d steps=%0d busy=%0d score=%0d",
             commands_issued, matrix_steps_total, busy_cycles,
             score_matrix_commands);
    $display(
      "L5_TARGET_TRACE_CONTROLLER_PASS commands=23 matrix_steps=1486848 busy_cycles=6036046 wall_cycles=%0d score_matrix_commands=0 command_fnv64=%016h",
      wall_cycles, command_hash
    );
    $finish;
  end

  initial begin
    repeat (6100000) @(posedge clk);
    $fatal(1, "target trace controller timeout");
  end
endmodule
