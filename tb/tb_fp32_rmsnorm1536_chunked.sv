`timescale 1ns/1ps
module tb_fp32_rmsnorm1536_chunked;
  parameter integer COUNT = 1000;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic in_valid, in_ready, out_valid, out_ready;
  logic [49151:0] x, weight, y;
  logic [31:0] epsilon;
  logic [4:0] flags, flags_or;
  logic [31:0] accepted, completed, reduction_cycles, rsqrt_cycles, output_cycles;
  logic [147487:0] vectors [0:COUNT-1];
  logic [63:0] hash;
  logic stalled;
  logic [49151:0] held;
  integer cycles, seen;

  always #5 clk = ~clk;
  always_comb out_ready = (cycles % 5) != 1;

  fp32_rmsnorm1536_chunked dut(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(in_valid), .in_ready_o(in_ready),
    .x_i(x), .weight_i(weight), .epsilon_i(epsilon),
    .out_valid_o(out_valid), .out_ready_i(out_ready),
    .y_o(y), .exception_flags_o(flags),
    .accepted_o(accepted), .completed_o(completed),
    .reduction_cycles_o(reduction_cycles), .rsqrt_cycles_o(rsqrt_cycles),
    .output_cycles_o(output_cycles)
  );

  function automatic [63:0] hash1536(
    input logic [63:0] seed, input logic [49151:0] data
  );
    logic [63:0] value;
    begin
      value = seed;
      for (int lane = 0; lane < 1536; lane++)
        value = (value ^ {32'd0, data[lane * 32 +: 32]}) * 64'h100000001b3;
      hash1536 = value;
    end
  endfunction

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      seen <= 0;
      flags_or <= '0;
      hash <= 64'hcbf29ce484222325;
      stalled <= 0;
    end else begin
      cycles <= cycles + 1;
      if (stalled && (!out_valid || y !== held))
        $fatal(1, "RMS1536 output changed while stalled");
      stalled <= out_valid && !out_ready;
      if (out_valid && !out_ready) held <= y;
      if (out_valid && out_ready) begin
        if (y !== vectors[seen][147487:98336])
          $fatal(1, "RMS1536 mismatch vector=%0d flags=%h", seen, flags);
        flags_or <= flags_or | flags;
        hash <= hash1536(hash, y);
        seen <= seen + 1;
      end
    end
  end

  initial begin
    clk = 0;
    rst_n = 0;
    in_valid = 0;
    epsilon = '0;
    $readmemh("work/results/l5_rmsnorm1536/vectors.memh", vectors);
    repeat (3) @(posedge clk);
    rst_n = 1;
    for (int i = 0; i < COUNT; i++) begin
      @(negedge clk);
      x = vectors[i][49151:0];
      weight = vectors[i][98303:49152];
      epsilon = vectors[i][98335:98304];
      in_valid = 1;
      do @(posedge clk); while (!in_ready);
      @(negedge clk);
      in_valid = 0;
      do @(posedge clk); while (!(out_valid && out_ready));
    end
    wait (seen == COUNT);
    @(negedge clk);
    if (accepted != COUNT || completed != COUNT)
      $fatal(1, "RMS1536 counters accepted=%0d completed=%0d", accepted, completed);
    if (flags_or[4:1] != 0)
      $fatal(1, "RMS1536 unexpected flags=%h", flags_or);
    $display(
      "FP32_RMSNORM1536_CHUNKED_PASS vectors=%0d cycles=%0d reduction_cycles=%0d rsqrt_cycles=%0d output_cycles=%0d output_fnv64=%016h flags_or=%h",
      COUNT, cycles, reduction_cycles, rsqrt_cycles, output_cycles, hash, flags_or
    );
    $finish;
  end

  initial begin
    repeat (1000000) @(posedge clk);
    $fatal(1, "RMS1536 timeout");
  end
endmodule
