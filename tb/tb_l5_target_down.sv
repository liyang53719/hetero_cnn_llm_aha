`timescale 1ns/1ps
module tb_l5_target_down;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic in_valid, in_ready, out_valid, out_ready;
  logic [255:0] a;
  logic [511:0] b;
  logic [16383:0] accumulator, array_out;
  logic [4:0] flags, flags_or;
  logic [31:0] accepted, completed;
  logic [511:0] vector_a, vector_b, vector_out;
  logic [4:0] vector_flags, vector_flags_or;
  logic [15:0] weights [0:13762559];
  logic [31:0] input_product [0:8959], input_residual [0:1535];
  logic [31:0] expected_down [0:1535], expected_final [0:1535];
  logic [49151:0] down, final_value;
  integer cycles, matrix_cycles, residual_cycles;

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;

  bf16_outer_product_array #(.ROWS(16), .COLS(32)) matrix(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(in_valid), .in_ready_o(in_ready),
    .a_i(a), .b_i(b), .acc_i(accumulator),
    .out_valid_o(out_valid), .out_ready_i(out_ready),
    .acc_o(array_out), .exception_flags_o(flags),
    .accepted_steps_o(accepted), .completed_steps_o(completed)
  );
  fp32_vector_alu #(.LANES(16)) add16(
    .op_i(1'b0), .a_i(vector_a), .b_i(vector_b),
    .out_o(vector_out), .exception_flags_o(vector_flags)
  );

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

  task automatic clear512(output logic [16383:0] bus);
    for (int i = 0; i < 512; i++) bus[i * 32 +: 32] = 32'd0;
  endtask

  initial begin
    logic [16383:0] current;
    integer start;
    clk = 0;
    rst_n = 0;
    cycles = 0;
    matrix_cycles = 0;
    residual_cycles = 0;
    in_valid = 0;
    out_ready = 1;
    a = '0;
    b = '0;
    clear512(accumulator);
    flags_or = '0;
    vector_a = '0;
    vector_b = '0;
    vector_flags_or = '0;
    $readmemh("work/results/l5_target_down/vectors/weights_bf16.memh", weights);
    $readmemh("work/results/l5_target_silu_product/vectors/product.memh", input_product);
    $readmemh("work/results/l5_target_oproj/vectors/residual1.memh", input_residual);
    $readmemh("work/results/l5_target_down/vectors/down.memh", expected_down);
    $readmemh("work/results/l5_target_down/vectors/final.memh", expected_final);
    repeat (3) @(posedge clk);
    rst_n = 1;
    start = cycles;
    for (int tile = 0; tile < 48; tile++) begin
      clear512(current);
      for (int k = 0; k < 8960; k++) begin
        a = '0;
        b = '0;
        a[15:0] = to_bf16(input_product[k]);
        for (int column = 0; column < 32; column++)
          b[column * 16 +: 16] = weights[k * 1536 + tile * 32 + column];
        accumulator = current;
        @(negedge clk);
        in_valid = 1;
        do @(posedge clk); while (!in_ready);
        @(negedge clk);
        in_valid = 0;
        do @(posedge clk); while (!(out_valid && out_ready));
        @(negedge clk);
        current = array_out;
        flags_or |= flags;
      end
      for (int column = 0; column < 32; column++)
        down[(tile * 32 + column) * 32 +: 32] = current[column * 32 +: 32];
    end
    matrix_cycles = cycles - start;
    for (int lane = 0; lane < 1536; lane++)
      if (down[lane * 32 +: 32] !== expected_down[lane])
        $fatal(1, "target down mismatch lane=%0d", lane);
    start = cycles;
    for (int chunk = 0; chunk < 96; chunk++) begin
      @(negedge clk);
      vector_a = down[chunk * 512 +: 512];
      for (int lane = 0; lane < 16; lane++)
        vector_b[lane * 32 +: 32] = input_residual[chunk * 16 + lane];
      #1;
      final_value[chunk * 512 +: 512] = vector_out;
      vector_flags_or |= vector_flags;
    end
    residual_cycles = cycles - start;
    for (int lane = 0; lane < 1536; lane++)
      if (final_value[lane * 32 +: 32] !== expected_final[lane])
        $fatal(1, "target final mismatch lane=%0d", lane);
    if (accepted != 430080 || completed != 430080 ||
        flags_or[4:1] != 0 || vector_flags_or[4:1] != 0)
      $fatal(1, "target down accounting accepted=%0d completed=%0d flags=%h/%h",
             accepted, completed, flags_or, vector_flags_or);
    $display(
      "L5_TARGET_DOWN_PASS shape=8960x1536 array_steps=430080 residual_chunks=96 total_cycles=%0d matrix_cycles=%0d residual_cycles=%0d down_fnv64=%016h final_fnv64=%016h",
      cycles, matrix_cycles, residual_cycles, hash1536(down), hash1536(final_value)
    );
    $finish;
  end

  initial begin
    repeat (2000000) @(posedge clk);
    $fatal(1, "target down timeout");
  end
endmodule
