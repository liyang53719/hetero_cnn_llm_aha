`timescale 1ns/1ps
module tb_fp32_dot128_scaled;
  parameter integer COUNT = 10000;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic in_valid, in_ready, out_valid, out_ready;
  logic [4095:0] a, b;
  logic [31:0] scale, result;
  logic [4:0] flags, flags_or;
  logic [31:0] accepted, completed;
  logic [8255:0] vectors [0:COUNT-1];
  logic [63:0] hash;
  logic stalled;
  logic [31:0] held;
  integer cycles, seen;

  always #5 clk = ~clk;
  always_comb out_ready = (cycles % 7) != 2;

  fp32_dot128_scaled dut(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(in_valid), .in_ready_o(in_ready),
    .a_i(a), .b_i(b), .scale_i(scale),
    .out_valid_o(out_valid), .out_ready_i(out_ready),
    .result_o(result), .exception_flags_o(flags),
    .accepted_o(accepted), .completed_o(completed)
  );

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      seen <= 0;
      flags_or <= '0;
      hash <= 64'hcbf29ce484222325;
      stalled <= 0;
      held <= '0;
    end else begin
      cycles <= cycles + 1;
      if (stalled && (!out_valid || result !== held))
        $fatal(1, "dot128 output changed while stalled");
      stalled <= out_valid && !out_ready;
      if (out_valid && !out_ready) held <= result;
      if (out_valid && out_ready) begin
        if (result !== vectors[seen][8255:8224])
          $fatal(1, "dot128 mismatch vector=%0d got=%h expected=%h", seen,
                 result, vectors[seen][8255:8224]);
        flags_or <= flags_or | flags;
        hash <= (hash ^ {32'd0, result}) * 64'h100000001b3;
        seen <= seen + 1;
      end
    end
  end

  initial begin
    clk = 0;
    rst_n = 0;
    in_valid = 0;
    a = '0;
    b = '0;
    scale = '0;
    $readmemh("work/results/l5_dot128/vectors.memh", vectors);
    repeat (3) @(posedge clk);
    rst_n = 1;
    for (int i = 0; i < COUNT; i++) begin
      @(negedge clk);
      a = vectors[i][4095:0];
      b = vectors[i][8191:4096];
      scale = vectors[i][8223:8192];
      in_valid = 1;
      do @(posedge clk); while (!in_ready);
      @(negedge clk);
      in_valid = 0;
      do @(posedge clk); while (!(out_valid && out_ready));
    end
    wait (seen == COUNT);
    @(negedge clk);
    if (accepted != COUNT || completed != COUNT)
      $fatal(1, "dot128 accounting accepted=%0d completed=%0d", accepted, completed);
    if (flags_or[4:1] != 0)
      $fatal(1, "dot128 unexpected flags=%h", flags_or);
    $display("FP32_DOT128_SCALED_PASS vectors=%0d cycles=%0d output_fnv64=%016h flags_or=%h",
             COUNT, cycles, hash, flags_or);
    $finish;
  end

  initial begin
    repeat (400000) @(posedge clk);
    $fatal(1, "dot128 timeout");
  end
endmodule
