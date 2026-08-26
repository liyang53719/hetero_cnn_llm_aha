`timescale 1ns/1ps
module tb_l5_target_oproj;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  integer cycles, matrix_cycles, residual_cycles;
  logic array_in_valid, array_in_ready, array_out_valid, array_out_ready;
  logic [255:0] array_a;
  logic [511:0] array_b;
  logic [16383:0] array_acc, array_out;
  logic [4:0] array_flags, matrix_flags_or;
  logic [31:0] array_accepted, array_completed;
  bf16_outer_product_array #(.ROWS(16), .COLS(32)) matrix(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(array_in_valid), .in_ready_o(array_in_ready),
    .a_i(array_a), .b_i(array_b), .acc_i(array_acc),
    .out_valid_o(array_out_valid), .out_ready_i(array_out_ready),
    .acc_o(array_out), .exception_flags_o(array_flags),
    .accepted_steps_o(array_accepted), .completed_steps_o(array_completed)
  );

  logic [511:0] vector_a, vector_b, vector_out;
  logic [4:0] vector_flags, vector_flags_or;
  fp32_vector_alu #(.LANES(16)) add16(
    .op_i(1'b0), .a_i(vector_a), .b_i(vector_b),
    .out_o(vector_out), .exception_flags_o(vector_flags)
  );

  logic [15:0] weights [0:2359295];
  logic [31:0] in_attention [0:1535], in_current [0:1535];
  logic [31:0] ex_oproj [0:1535], ex_residual1 [0:1535];

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;

  function automatic [15:0] to_bf16(input logic [31:0] value);
    logic [31:0] rounded;
    begin
      rounded = value + 32'h00007fff + value[16];
      to_bf16 = rounded[31:16];
    end
  endfunction

  function automatic [63:0] hash1536(input logic [49151:0] data);
    logic [63:0] value;
    begin
      value = 64'hcbf29ce484222325;
      for (int lane = 0; lane < 1536; lane++)
        value = (value ^ {32'd0, data[lane * 32 +: 32]}) * 64'h100000001b3;
      hash1536 = value;
    end
  endfunction

  task automatic clear1536(output logic [49151:0] bus);
    for (int i = 0; i < 1536; i++) bus[i * 32 +: 32] = 32'd0;
  endtask

  task automatic clear512(output logic [16383:0] bus);
    for (int i = 0; i < 512; i++) bus[i * 32 +: 32] = 32'd0;
  endtask

  task automatic load1536(
    input logic [31:0] memory [0:1535], output logic [49151:0] bus
  );
    for (int i = 0; i < 1536; i++) bus[i * 32 +: 32] = memory[i];
  endtask

  task automatic check1536(
    input logic [49151:0] bus,
    input logic [31:0] memory [0:1535], input string name
  );
    for (int i = 0; i < 1536; i++)
      if (bus[i * 32 +: 32] !== memory[i])
        $fatal(1, "target OProj node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[i]);
  endtask

  task automatic run_oproj(
    input logic [49151:0] input_vector, output logic [49151:0] result
  );
    logic [16383:0] accumulator;
    integer start;
    begin
      start = cycles;
      clear1536(result);
      for (int tile = 0; tile < 48; tile++) begin
        clear512(accumulator);
        for (int k = 0; k < 1536; k++) begin
          array_a = '0;
          array_b = '0;
          array_a[15:0] = to_bf16(input_vector[k * 32 +: 32]);
          for (int column = 0; column < 32; column++)
            array_b[column * 16 +: 16] = weights[k * 1536 + tile * 32 + column];
          array_acc = accumulator;
          @(negedge clk);
          array_in_valid = 1;
          do @(posedge clk); while (!array_in_ready);
          @(negedge clk);
          array_in_valid = 0;
          do @(posedge clk); while (!(array_out_valid && array_out_ready));
          @(negedge clk);
          accumulator = array_out;
          matrix_flags_or |= array_flags;
        end
        for (int column = 0; column < 32; column++)
          result[(tile * 32 + column) * 32 +: 32] =
            accumulator[column * 32 +: 32];
      end
      matrix_cycles += cycles - start;
    end
  endtask

  task automatic run_residual(
    input logic [49151:0] original,
    input logic [49151:0] projected,
    output logic [49151:0] result
  );
    integer start;
    begin
      start = cycles;
      clear1536(result);
      for (int chunk = 0; chunk < 96; chunk++) begin
        @(negedge clk);
        vector_a = original[chunk * 512 +: 512];
        vector_b = projected[chunk * 512 +: 512];
        #1;
        result[chunk * 512 +: 512] = vector_out;
        vector_flags_or |= vector_flags;
      end
      residual_cycles += cycles - start;
    end
  endtask

  initial begin
    logic [49151:0] attention, current, oproj, residual1;
    clk = 0;
    rst_n = 0;
    cycles = 0;
    matrix_cycles = 0;
    residual_cycles = 0;
    array_in_valid = 0;
    array_out_ready = 1;
    array_a = '0;
    array_b = '0;
    clear512(array_acc);
    matrix_flags_or = '0;
    vector_a = '0;
    vector_b = '0;
    vector_flags_or = '0;

    $readmemh("work/results/l5_target_oproj/vectors/weights_bf16.memh", weights);
    $readmemh("work/results/l5_target_mlo/vectors/attention.memh", in_attention);
    $readmemh("work/results/l5_target_qkv_segment/vectors/x_current.memh", in_current);
    $readmemh("work/results/l5_target_oproj/vectors/oproj.memh", ex_oproj);
    $readmemh("work/results/l5_target_oproj/vectors/residual1.memh", ex_residual1);
    repeat (3) @(posedge clk);
    rst_n = 1;
    load1536(in_attention, attention);
    load1536(in_current, current);
    run_oproj(attention, oproj);
    check1536(oproj, ex_oproj, "oproj");
    run_residual(current, oproj, residual1);
    check1536(residual1, ex_residual1, "residual1");
    if (array_accepted != 73728 || array_completed != 73728)
      $fatal(1, "target OProj array steps accepted=%0d completed=%0d",
             array_accepted, array_completed);
    if (matrix_flags_or[4:1] != 0 || vector_flags_or[4:1] != 0)
      $fatal(1, "target OProj flags matrix=%h residual=%h",
             matrix_flags_or, vector_flags_or);
    $display(
      "L5_TARGET_OPROJ_PASS array_steps=73728 residual_chunks=96 total_cycles=%0d matrix_cycles=%0d residual_cycles=%0d oproj_fnv64=%016h residual1_fnv64=%016h",
      cycles, matrix_cycles, residual_cycles, hash1536(oproj), hash1536(residual1)
    );
    $finish;
  end

  initial begin
    repeat (1000000) @(posedge clk);
    $fatal(1, "target OProj timeout");
  end
endmodule
