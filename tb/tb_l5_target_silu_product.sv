`timescale 1ns/1ps
module tb_l5_target_silu_product;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic silu_in_valid, silu_in_ready, silu_out_valid, silu_out_ready;
  logic [31:0] silu_x, silu_y;
  logic [4:0] silu_flags, silu_flags_or;
  logic [31:0] silu_accepted, silu_completed;
  logic [511:0] vector_a, vector_b, vector_out;
  logic [4:0] vector_flags, vector_flags_or;
  logic [31:0] in_gate [0:8959], in_up [0:8959];
  logic [31:0] ex_silu [0:8959], ex_product [0:8959];
  logic [286719:0] activated, product;
  integer cycles, silu_cycles, product_cycles;

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;

  fp32_silu silu(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(silu_in_valid), .in_ready_o(silu_in_ready), .x_i(silu_x),
    .out_valid_o(silu_out_valid), .out_ready_i(silu_out_ready), .y_o(silu_y),
    .exception_flags_o(silu_flags), .accepted_o(silu_accepted),
    .completed_o(silu_completed)
  );
  fp32_vector_alu #(.LANES(16)) multiply16(
    .op_i(1'b1), .a_i(vector_a), .b_i(vector_b),
    .out_o(vector_out), .exception_flags_o(vector_flags)
  );

  function automatic [63:0] hash8960(input logic [286719:0] data);
    logic [63:0] value;
    begin
      value = 64'hcbf29ce484222325;
      for (int lane = 0; lane < 8960; lane++)
        value = (value ^ {32'd0, data[lane * 32 +: 32]}) * 64'h100000001b3;
      hash8960 = value;
    end
  endfunction

  initial begin
    integer start;
    clk = 0;
    rst_n = 0;
    cycles = 0;
    silu_cycles = 0;
    product_cycles = 0;
    silu_in_valid = 0;
    silu_out_ready = 1;
    silu_flags_or = '0;
    vector_a = '0;
    vector_b = '0;
    vector_flags_or = '0;
    $readmemh("work/results/l5_target_gate_up/vectors/gate.memh", in_gate);
    $readmemh("work/results/l5_target_gate_up/vectors/up.memh", in_up);
    $readmemh("work/results/l5_target_silu_product/vectors/silu.memh", ex_silu);
    $readmemh("work/results/l5_target_silu_product/vectors/product.memh", ex_product);
    repeat (3) @(posedge clk);
    rst_n = 1;
    start = cycles;
    for (int lane = 0; lane < 8960; lane++) begin
      @(negedge clk);
      silu_x = in_gate[lane];
      silu_in_valid = 1;
      do @(posedge clk); while (!silu_in_ready);
      @(negedge clk);
      silu_in_valid = 0;
      do @(posedge clk); while (!(silu_out_valid && silu_out_ready));
      @(negedge clk);
      if (silu_y !== ex_silu[lane])
        $fatal(1, "target SiLU mismatch lane=%0d", lane);
      activated[lane * 32 +: 32] = silu_y;
      silu_flags_or |= silu_flags;
    end
    silu_cycles = cycles - start;
    start = cycles;
    for (int chunk = 0; chunk < 560; chunk++) begin
      @(negedge clk);
      vector_a = activated[chunk * 512 +: 512];
      for (int lane = 0; lane < 16; lane++)
        vector_b[lane * 32 +: 32] = in_up[chunk * 16 + lane];
      #1;
      product[chunk * 512 +: 512] = vector_out;
      vector_flags_or |= vector_flags;
    end
    product_cycles = cycles - start;
    for (int lane = 0; lane < 8960; lane++)
      if (product[lane * 32 +: 32] !== ex_product[lane])
        $fatal(1, "target product mismatch lane=%0d", lane);
    if (silu_accepted != 8960 || silu_completed != 8960 ||
        silu_flags_or[4:1] != 0 || vector_flags_or[4:1] != 0)
      $fatal(1, "target SiLU/product accounting flags=%h/%h", silu_flags_or, vector_flags_or);
    $display(
      "L5_TARGET_SILU_PRODUCT_PASS lanes=8960 product_chunks=560 total_cycles=%0d silu_cycles=%0d product_cycles=%0d silu_fnv64=%016h product_fnv64=%016h",
      cycles, silu_cycles, product_cycles, hash8960(activated), hash8960(product)
    );
    $finish;
  end

  initial begin
    repeat (200000) @(posedge clk);
    $fatal(1, "target SiLU/product timeout");
  end
endmodule
