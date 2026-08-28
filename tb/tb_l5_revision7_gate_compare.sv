`timescale 1ns/1ps
module tb_l5_revision7_gate_compare;
  localparam integer WARMUP_CYCLES = 16;
  localparam integer RECURRENCE_CYCLES = 100000;
  localparam integer RANDOM_CYCLES = 20000;
  localparam integer DRAIN_CYCLES = 16;
  logic clk, rst_n;
  logic pre_write, mul_write, post_write, output_write;
  logic [15:0] a, b;
  logic [1:0] issue_context, completion_context;
  logic issue_clear, issue_bypass, issue_use_bank, completion_fire;
  logic [31:0] out;
  logic [4:0] flags;
  logic [31:0] lfsr;
  integer trace_fd, sampled_cycles;
  string trace_path;

  always #0.5 clk = ~clk;

  bf16_context_fma_pipeline_lane4 dut (
    .clk_i(clk), .rst_ni(rst_n),
    .pre_write_i(pre_write), .mul_write_i(mul_write),
    .post_write_i(post_write), .output_write_i(output_write),
    .a_i(a), .b_i(b), .issue_context_i(issue_context),
    .issue_clear_i(issue_clear), .issue_bypass_i(issue_bypass),
    .issue_use_bank_i(issue_use_bank),
    .completion_fire_i(completion_fire),
    .completion_context_i(completion_context),
    .out_o(out), .flags_o(flags)
  );

  task automatic sample_cycle;
    begin
      @(posedge clk);
      #0.20;
      if ((^out === 1'bx) || (^flags === 1'bx))
        $fatal(1, "unknown output cycle=%0d out=%h flags=%h", sampled_cycles, out, flags);
      $fwrite(trace_fd,
        "%0d %b%b%b%b %04x %04x %0d %b%b%b %b %0d %08x %02x\n",
        sampled_cycles, pre_write, mul_write, post_write, output_write,
        a, b, issue_context, issue_clear, issue_bypass, issue_use_bank,
        completion_fire, completion_context, out, flags);
      sampled_cycles = sampled_cycles + 1;
    end
  endtask

  initial begin
    if (!$value$plusargs("TRACE=%s", trace_path))
      $fatal(1, "missing +TRACE=<path>");
    trace_fd = $fopen(trace_path, "w");
    if (!trace_fd) $fatal(1, "cannot open trace");
    clk = 0;
    rst_n = 0;
    pre_write = 0;
    mul_write = 0;
    post_write = 0;
    output_write = 0;
    a = 0;
    b = 0;
    issue_context = 0;
    issue_clear = 1;
    issue_bypass = 0;
    issue_use_bank = 0;
    completion_fire = 0;
    completion_context = 0;
    lfsr = 32'h7a51_c39d;
    sampled_cycles = 0;
    repeat (6) @(posedge clk);
    @(negedge clk);
    rst_n = 1;

    for (integer i = 0; i < WARMUP_CYCLES; i++) begin
      pre_write = 1;
      mul_write = 1;
      post_write = 1;
      output_write = 1;
      a = 16'h3f80;
      b = 16'h3f80;
      issue_context = i[1:0];
      issue_clear = 1;
      issue_bypass = 0;
      issue_use_bank = 0;
      completion_fire = i >= 4;
      completion_context = (i - 4) & 3;
      sample_cycle();
      @(negedge clk);
    end

    for (integer i = 0; i < RECURRENCE_CYCLES; i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      pre_write = 1;
      mul_write = 1;
      post_write = 1;
      output_write = 1;
      a = lfsr[15:0];
      b = lfsr[31:16];
      issue_context = i[1:0];
      issue_clear = 0;
      issue_bypass = 1;
      issue_use_bank = 1;
      completion_fire = 1;
      completion_context = i[1:0];
      sample_cycle();
      @(negedge clk);
    end

    for (integer i = 0; i < RANDOM_CYCLES; i++) begin
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[28] ^ lfsr[7] ^ lfsr[0]};
      pre_write = lfsr[0] | lfsr[5];
      mul_write = lfsr[1] | lfsr[6];
      post_write = lfsr[2] | lfsr[7];
      output_write = lfsr[3] | lfsr[8];
      a = lfsr[15:0];
      b = {lfsr[23:16], lfsr[31:24]};
      issue_context = lfsr[10:9];
      issue_clear = &lfsr[13:11];
      issue_bypass = lfsr[14];
      issue_use_bank = lfsr[15];
      completion_fire = lfsr[16] | lfsr[20];
      completion_context = lfsr[18:17];
      sample_cycle();
      @(negedge clk);
    end

    for (integer i = 0; i < DRAIN_CYCLES; i++) begin
      pre_write = 1;
      mul_write = 1;
      post_write = 1;
      output_write = 1;
      a = 0;
      b = 0;
      issue_context = i[1:0];
      issue_clear = 0;
      issue_bypass = 0;
      issue_use_bank = 1;
      completion_fire = 1;
      completion_context = i[1:0];
      sample_cycle();
      @(negedge clk);
    end

    $fclose(trace_fd);
    $display("REV7_GATE_COMPARE_TRACE_PASS cycles=%0d", sampled_cycles);
    $finish;
  end

  initial begin
    repeat (150000) @(posedge clk);
    $fatal(1, "timeout");
  end
endmodule
