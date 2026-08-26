`timescale 1ns/1ps
module tb_qwen_qkv_bias_gqa16;
  parameter integer INPUT_COUNT = 10000;
  parameter integer OUTPUT_COUNT = 43000;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  logic in_valid, in_ready, out_valid, out_ready;
  logic [1:0] in_role, out_role;
  logic [6:0] in_chunk, out_chunk;
  logic [15:0] in_tag, out_tag;
  logic [511:0] in_data, in_bias, out_data;
  logic [3:0] out_query_head;
  logic out_kv_head;
  logic [2:0] out_head_chunk;
  logic out_last, out_illegal;
  logic [4:0] out_flags, flags_or;
  logic [31:0] accepted, completed, illegal_inputs;
  logic [1055:0] inputs [0:INPUT_COUNT-1];
  logic [547:0] expected [0:OUTPUT_COUNT-1];
  logic [547:0] observed, held;
  logic [63:0] hash;
  logic stalled;
  integer cycles, seen;

  always #5 clk = ~clk;
  always_comb begin
    out_ready = (cycles % 11) != 3 && (cycles % 17) != 5;
    observed = '0;
    observed[511:0] = out_data;
    observed[527:512] = out_tag;
    observed[534:528] = out_chunk;
    observed[536:535] = out_role;
    observed[540:537] = out_query_head;
    observed[541] = out_kv_head;
    observed[544:542] = out_head_chunk;
    observed[545] = out_last;
    observed[546] = out_illegal;
  end

  qwen_qkv_bias_gqa16 dut(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(in_valid), .in_ready_o(in_ready),
    .role_i(in_role), .chunk_i(in_chunk), .tag_i(in_tag),
    .data_i(in_data), .bias_i(in_bias),
    .out_valid_o(out_valid), .out_ready_i(out_ready),
    .role_o(out_role), .chunk_o(out_chunk), .tag_o(out_tag),
    .query_head_o(out_query_head), .kv_head_o(out_kv_head),
    .head_chunk_o(out_head_chunk), .last_o(out_last), .illegal_o(out_illegal),
    .data_o(out_data), .exception_flags_o(out_flags),
    .accepted_inputs_o(accepted), .completed_outputs_o(completed),
    .illegal_inputs_o(illegal_inputs)
  );

  function automatic [63:0] hash_chunk(
    input logic [63:0] seed, input logic [511:0] data
  );
    logic [63:0] value;
    begin
      value = seed;
      for (int lane = 0; lane < 16; lane++)
        value = (value ^ {32'd0, data[lane * 32 +: 32]}) * 64'h100000001b3;
      hash_chunk = value;
    end
  endfunction

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
      if (stalled && (!out_valid || observed !== held))
        $fatal(1, "QKV/GQA output changed while stalled");
      stalled <= out_valid && !out_ready;
      if (out_valid && !out_ready) held <= observed;
      if (out_valid && out_ready) begin
        if (observed !== expected[seen])
          $fatal(1, "QKV/GQA mismatch output=%0d got=%h expected=%h", seen,
                 observed, expected[seen]);
        flags_or <= flags_or | out_flags;
        hash <= hash_chunk(hash, out_data);
        seen <= seen + 1;
      end
    end
  end

  initial begin
    clk = 0;
    rst_n = 0;
    in_valid = 0;
    in_role = '0;
    in_chunk = '0;
    in_tag = '0;
    in_data = '0;
    in_bias = '0;
    $readmemh("work/results/l5_qkv_bias_gqa/inputs.memh", inputs);
    $readmemh("work/results/l5_qkv_bias_gqa/expected.memh", expected);
    repeat (3) @(posedge clk);
    rst_n = 1;
    for (int i = 0; i < INPUT_COUNT; i++) begin
      @(negedge clk);
      in_data = inputs[i][511:0];
      in_bias = inputs[i][1023:512];
      in_tag = inputs[i][1039:1024];
      in_chunk = inputs[i][1046:1040];
      in_role = inputs[i][1048:1047];
      in_valid = 1;
      do @(posedge clk); while (!in_ready);
      @(negedge clk);
      in_valid = 0;
    end
    wait (seen == OUTPUT_COUNT);
    @(negedge clk);
    if (accepted != INPUT_COUNT || completed != OUTPUT_COUNT || illegal_inputs != 100)
      $fatal(1, "QKV/GQA counters accepted=%0d completed=%0d illegal=%0d",
             accepted, completed, illegal_inputs);
    if (flags_or[4:1] != 0)
      $fatal(1, "QKV/GQA unexpected flags=%h", flags_or);
    $display(
      "QWEN_QKV_BIAS_GQA16_PASS inputs=%0d outputs=%0d illegal=%0d cycles=%0d output_data_fnv64=%016h flags_or=%h",
      INPUT_COUNT, OUTPUT_COUNT, illegal_inputs, cycles, hash, flags_or
    );
    $finish;
  end

  initial begin
    repeat (200000) @(posedge clk);
    $fatal(1, "QKV/GQA timeout");
  end
endmodule
