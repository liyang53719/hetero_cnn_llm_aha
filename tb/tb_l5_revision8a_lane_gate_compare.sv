`timescale 1ns/1ps
module tb_l5_revision8a_lane_gate_compare;
  localparam integer WARMUP_CYCLES = 16;
  localparam integer RECURRENCE_CYCLES = 100000;
  localparam integer RANDOM_CYCLES = 20000;
  localparam integer DRAIN_CYCLES = 16;
  logic clk, rst_n;
  logic pre_write, mul_write, post_write, output_write;
  logic [15:0] a, b;
  logic [1:0] issue_context, early_commit_context, output_context;
  logic issue_clear;
  logic [31:0] out;
  logic [4:0] flags;
  logic [3:0] bank_valid;
  logic [31:0] lfsr;
  integer trace_fd, sampled_cycles;
  string trace_path;

  always #0.5 clk = ~clk;

  bf16_context_fma_pipeline_lane4_rev8_candidate dut (
    .clk_i(clk), .rst_ni(rst_n),
    .pre_write_i(pre_write), .mul_write_i(mul_write),
    .post_write_i(post_write), .output_write_i(output_write),
    .a_i(a), .b_i(b), .issue_context_i(issue_context),
    .issue_clear_i(issue_clear),
    .early_commit_context_i(early_commit_context),
    .output_context_i(output_context),
    .out_o(out), .flags_o(flags), .bank_valid_o(bank_valid)
  );

  task automatic sample_cycle;
    begin
      @(posedge clk);
      #0.20;
      if ((^out === 1'bx) || (^flags === 1'bx) || (^bank_valid === 1'bx))
        $fatal(1, "unknown output cycle=%0d", sampled_cycles);
      $fwrite(trace_fd,
        "%0d %b%b%b%b %04x %04x %0d %b %0d %0d %08x %02x %x\n",
        sampled_cycles, pre_write, mul_write, post_write, output_write,
        a, b, issue_context, issue_clear, early_commit_context,
        output_context, out, flags, bank_valid);
      sampled_cycles = sampled_cycles + 1;
    end
  endtask

  initial begin
    if (!$value$plusargs("TRACE=%s", trace_path)) $fatal(1, "missing +TRACE=<path>");
    trace_fd = $fopen(trace_path, "w");
    if (!trace_fd) $fatal(1, "cannot open trace");
    clk=0; rst_n=0; pre_write=0; mul_write=0; post_write=0; output_write=0;
    a=0; b=0; issue_context=0; issue_clear=1;
    early_commit_context=0; output_context=0;
    lfsr=32'h8a52_c39d; sampled_cycles=0;
    repeat(6) @(posedge clk); @(negedge clk); rst_n=1;

    for (integer i=0;i<WARMUP_CYCLES;i++) begin
      pre_write=1;mul_write=1;post_write=1;output_write=1;
      a=16'h3f80;b=16'h3f80;issue_context=i[1:0];issue_clear=1;
      early_commit_context=(i-3)&3;output_context=(i-3)&3;
      sample_cycle();@(negedge clk);
    end
    for (integer i=0;i<RECURRENCE_CYCLES;i++) begin
      lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
      pre_write=1;mul_write=1;post_write=1;output_write=1;
      a=lfsr[15:0];b=lfsr[31:16];issue_context=i[1:0];issue_clear=0;
      early_commit_context=(i-3)&3;output_context=(i-3)&3;
      sample_cycle();@(negedge clk);
    end
    for (integer i=0;i<RANDOM_CYCLES;i++) begin
      lfsr={lfsr[30:0],lfsr[31]^lfsr[28]^lfsr[7]^lfsr[0]};
      pre_write=lfsr[0]|lfsr[5];mul_write=lfsr[1]|lfsr[6];
      post_write=lfsr[2]|lfsr[7];output_write=lfsr[3]|lfsr[8];
      a=lfsr[15:0];b={lfsr[23:16],lfsr[31:24]};
      issue_context=lfsr[10:9];issue_clear=&lfsr[13:11];
      early_commit_context=lfsr[18:17];output_context=lfsr[20:19];
      sample_cycle();@(negedge clk);
    end
    for (integer i=0;i<DRAIN_CYCLES;i++) begin
      pre_write=1;mul_write=1;post_write=1;output_write=1;
      a=0;b=0;issue_context=i[1:0];issue_clear=0;
      early_commit_context=(i-3)&3;output_context=(i-3)&3;
      sample_cycle();@(negedge clk);
    end
    $fclose(trace_fd);
    $display("REV8A_GATE_COMPARE_TRACE_PASS cycles=%0d",sampled_cycles);
    $finish;
  end
  initial begin repeat(150000) @(posedge clk); $fatal(1,"timeout"); end
endmodule
