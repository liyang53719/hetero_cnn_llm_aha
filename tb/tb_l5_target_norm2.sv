`timescale 1ns/1ps
module tb_l5_target_norm2;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic in_valid, in_ready, out_valid, out_ready;
  logic [49151:0] x, weight, y;
  logic [31:0] epsilon;
  logic [4:0] flags;
  logic [31:0] accepted, completed, reduction_cycles, rsqrt_cycles, output_cycles;
  logic [31:0] in_residual [0:1535], in_weight [0:1535], ex_norm2 [0:1535];
  integer cycles;

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;

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

  function automatic [63:0] hash1536(input logic [49151:0] data);
    logic [63:0] value;
    begin
      value = 64'hcbf29ce484222325;
      for (int lane = 0; lane < 1536; lane++)
        value = (value ^ {32'd0, data[lane * 32 +: 32]}) * 64'h100000001b3;
      hash1536 = value;
    end
  endfunction

  initial begin
    clk = 0;
    rst_n = 0;
    in_valid = 0;
    out_ready = 1;
    epsilon = 32'h358637bd;
    $readmemh("work/results/l5_target_oproj/vectors/residual1.memh", in_residual);
    $readmemh("work/results/l5_target_norm2/vectors/weight.memh", in_weight);
    $readmemh("work/results/l5_target_norm2/vectors/norm2.memh", ex_norm2);
    repeat (3) @(posedge clk);
    rst_n = 1;
    for (int i = 0; i < 1536; i++) begin
      x[i * 32 +: 32] = in_residual[i];
      weight[i * 32 +: 32] = in_weight[i];
    end
    @(negedge clk);
    in_valid = 1;
    do @(posedge clk); while (!in_ready);
    @(negedge clk);
    in_valid = 0;
    do @(posedge clk); while (!(out_valid && out_ready));
    @(negedge clk);
    for (int i = 0; i < 1536; i++)
      if (y[i * 32 +: 32] !== ex_norm2[i])
        $fatal(1, "target norm2 mismatch lane=%0d", i);
    if (accepted != 1 || completed != 1 || flags[4:1] != 0)
      $fatal(1, "target norm2 counters/flags");
    $display(
      "L5_TARGET_NORM2_PASS lanes=1536 chunks=96 total_cycles=%0d reduction_cycles=%0d rsqrt_cycles=%0d output_cycles=%0d norm2_fnv64=%016h",
      cycles, reduction_cycles, rsqrt_cycles, output_cycles, hash1536(y)
    );
    $finish;
  end

  initial begin
    repeat (2000) @(posedge clk);
    $fatal(1, "target norm2 timeout");
  end
endmodule
