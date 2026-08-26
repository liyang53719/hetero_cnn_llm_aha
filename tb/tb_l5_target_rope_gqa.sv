`timescale 1ns/1ps
module tb_l5_target_rope_gqa;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  integer cycles, rope_cycles, multicast_cycles;

  logic rope_in_valid, rope_in_ready, rope_out_valid, rope_out_ready;
  logic [31:0] rope_first, rope_second, rope_cos, rope_sin;
  logic [31:0] rope_first_out, rope_second_out;
  logic [4:0] rope_flags, rope_flags_or;
  logic [31:0] rope_accepted, rope_completed;
  fp32_rope_pair rope(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(rope_in_valid), .in_ready_o(rope_in_ready),
    .even_i(rope_first), .odd_i(rope_second),
    .cos_i(rope_cos), .sin_i(rope_sin),
    .out_valid_o(rope_out_valid), .out_ready_i(rope_out_ready),
    .even_o(rope_first_out), .odd_o(rope_second_out),
    .exception_flags_o(rope_flags),
    .accepted_pairs_o(rope_accepted), .completed_pairs_o(rope_completed)
  );

  logic gqa_in_valid, gqa_in_ready, gqa_out_valid, gqa_out_ready;
  logic [1:0] gqa_role_in, gqa_role_out;
  logic gqa_kv_head_in, gqa_kv_head_out;
  logic [2:0] gqa_head_chunk_in, gqa_head_chunk_out;
  logic gqa_last_in, gqa_last_out;
  logic [15:0] gqa_tag_in, gqa_tag_out;
  logic [511:0] gqa_data_in, gqa_data_out;
  logic [3:0] gqa_query_head_out;
  logic gqa_illegal;
  logic [31:0] gqa_accepted, gqa_completed, gqa_illegal_inputs;
  qwen_gqa_multicast16 multicast(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(gqa_in_valid), .in_ready_o(gqa_in_ready),
    .role_i(gqa_role_in), .kv_head_i(gqa_kv_head_in),
    .head_chunk_i(gqa_head_chunk_in), .last_i(gqa_last_in),
    .tag_i(gqa_tag_in), .data_i(gqa_data_in),
    .out_valid_o(gqa_out_valid), .out_ready_i(gqa_out_ready),
    .role_o(gqa_role_out), .query_head_o(gqa_query_head_out),
    .kv_head_o(gqa_kv_head_out), .head_chunk_o(gqa_head_chunk_out),
    .last_o(gqa_last_out), .tag_o(gqa_tag_out), .data_o(gqa_data_out),
    .illegal_o(gqa_illegal), .accepted_inputs_o(gqa_accepted),
    .completed_outputs_o(gqa_completed), .illegal_inputs_o(gqa_illegal_inputs)
  );

  logic [31:0] in_q [0:1535], in_k [0:511], coefficients [0:255];
  logic [31:0] ex_q_rope [0:1535], ex_k_rope [0:511];
  logic [31:0] ex_k_rope_gqa [0:3071];

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;

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

  task automatic load1536(
    input logic [31:0] memory [0:1535], output logic [49151:0] bus
  );
    for (int i = 0; i < 1536; i++) bus[i * 32 +: 32] = memory[i];
  endtask

  task automatic load512(
    input logic [31:0] memory [0:511], output logic [49151:0] bus
  );
    begin
      clear1536(bus);
      for (int i = 0; i < 512; i++) bus[i * 32 +: 32] = memory[i];
    end
  endtask

  task automatic check1536(
    input logic [49151:0] bus,
    input logic [31:0] memory [0:1535], input string name
  );
    for (int i = 0; i < 1536; i++)
      if (bus[i * 32 +: 32] !== memory[i])
        $fatal(1, "target RoPE node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[i]);
  endtask

  task automatic check512(
    input logic [49151:0] bus,
    input logic [31:0] memory [0:511], input string name
  );
    for (int i = 0; i < 512; i++)
      if (bus[i * 32 +: 32] !== memory[i])
        $fatal(1, "target RoPE node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[i]);
  endtask

  task automatic check3072(
    input logic [49151:0] previous,
    input logic [49151:0] current,
    input logic [31:0] memory [0:3071]
  );
    begin
      for (int i = 0; i < 1536; i++) begin
        if (previous[i * 32 +: 32] !== memory[i])
          $fatal(1, "target rotated K GQA previous lane=%0d", i);
        if (current[i * 32 +: 32] !== memory[1536 + i])
          $fatal(1, "target rotated K GQA current lane=%0d", i);
      end
    end
  endtask

  task automatic run_split_half_rope(
    input logic [49151:0] source,
    input integer heads,
    input integer position,
    output logic [49151:0] result
  );
    integer start, base;
    begin
      start = cycles;
      clear1536(result);
      for (int head = 0; head < heads; head++) begin
        base = head * 128;
        for (int pair = 0; pair < 64; pair++) begin
          @(negedge clk);
          rope_first = source[(base + pair) * 32 +: 32];
          rope_second = source[(base + 64 + pair) * 32 +: 32];
          rope_cos = coefficients[position * 128 + pair * 2];
          rope_sin = coefficients[position * 128 + pair * 2 + 1];
          rope_in_valid = 1;
          do @(posedge clk); while (!rope_in_ready);
          @(negedge clk);
          rope_in_valid = 0;
          do @(posedge clk); while (!(rope_out_valid && rope_out_ready));
          @(negedge clk);
          result[(base + pair) * 32 +: 32] = rope_first_out;
          result[(base + 64 + pair) * 32 +: 32] = rope_second_out;
          rope_flags_or |= rope_flags;
        end
      end
      rope_cycles += cycles - start;
    end
  endtask

  task automatic run_k_multicast(
    input logic [49151:0] rotated_k,
    input logic [7:0] token,
    output logic [49151:0] expanded
  );
    logic [511:0] held_data;
    logic [15:0] expected_tag;
    logic [3:0] held_query_head;
    integer start;
    begin
      start = cycles;
      expected_tag = {8'd0, token};
      clear1536(expanded);
      for (int chunk = 0; chunk < 16; chunk++) begin
        @(negedge clk);
        gqa_role_in = 2'd1;
        gqa_kv_head_in = chunk >= 8;
        gqa_head_chunk_in = chunk[2:0];
        gqa_last_in = chunk[2:0] == 3'd7;
        gqa_tag_in = expected_tag;
        gqa_data_in = rotated_k[chunk * 512 +: 512];
        gqa_in_valid = 1;
        do @(posedge clk); while (!gqa_in_ready);
        @(negedge clk);
        gqa_in_valid = 0;
        for (int replica = 0; replica < 6; replica++) begin
          if (!gqa_out_valid || gqa_illegal)
            $fatal(1, "post-RoPE GQA output missing");
          if (gqa_role_out != 2'd1 || gqa_kv_head_out != (chunk >= 8) ||
              gqa_head_chunk_out != chunk[2:0] ||
              gqa_last_out != (chunk[2:0] == 3'd7) ||
              gqa_tag_out != expected_tag ||
              int'(gqa_query_head_out) != (chunk >= 8 ? 6 : 0) + replica)
            $fatal(1, "post-RoPE GQA sideband mismatch chunk=%0d replica=%0d",
                   chunk, replica);
          if ((chunk + replica) % 5 == 0) begin
            held_data = gqa_data_out;
            held_query_head = gqa_query_head_out;
            @(posedge clk);
            @(negedge clk);
            if (!gqa_out_valid || gqa_data_out !== held_data ||
                gqa_query_head_out != held_query_head)
              $fatal(1, "post-RoPE GQA changed under backpressure");
          end
          expanded[gqa_query_head_out * 4096 + gqa_head_chunk_out * 512 +: 512] =
            gqa_data_out;
          gqa_out_ready = 1;
          @(posedge clk);
          @(negedge clk);
          gqa_out_ready = 0;
        end
      end
      multicast_cycles += cycles - start;
    end
  endtask

  initial begin
    logic [49151:0] q_biased, k_biased;
    logic [49151:0] q_rope, k_previous_rope, k_current_rope, k_rope_all;
    logic [49151:0] k_previous_gqa, k_current_gqa;

    clk = 0;
    rst_n = 0;
    cycles = 0;
    rope_cycles = 0;
    multicast_cycles = 0;
    rope_in_valid = 0;
    rope_out_ready = 1;
    rope_flags_or = '0;
    gqa_in_valid = 0;
    gqa_out_ready = 0;

    $readmemh("work/results/l5_target_qkv_segment/vectors/q_biased.memh", in_q);
    $readmemh("work/results/l5_target_qkv_segment/vectors/k_biased.memh", in_k);
    $readmemh("work/results/l5_target_rope_gqa/vectors/rope_coeff.memh", coefficients);
    $readmemh("work/results/l5_target_rope_gqa/vectors/q_rope.memh", ex_q_rope);
    $readmemh("work/results/l5_target_rope_gqa/vectors/k_rope.memh", ex_k_rope);
    $readmemh("work/results/l5_target_rope_gqa/vectors/k_rope_gqa.memh", ex_k_rope_gqa);

    repeat (3) @(posedge clk);
    rst_n = 1;
    load1536(in_q, q_biased);
    load512(in_k, k_biased);
    run_split_half_rope(q_biased, 12, 1, q_rope);
    check1536(q_rope, ex_q_rope, "q_rope");
    run_split_half_rope(k_biased, 2, 0, k_previous_rope);
    run_split_half_rope(k_biased >> 8192, 2, 1, k_current_rope);
    clear1536(k_rope_all);
    k_rope_all[8191:0] = k_previous_rope[8191:0];
    k_rope_all[16383:8192] = k_current_rope[8191:0];
    check512(k_rope_all, ex_k_rope, "k_rope");
    run_k_multicast(k_previous_rope, 0, k_previous_gqa);
    run_k_multicast(k_current_rope, 1, k_current_gqa);
    check3072(k_previous_gqa, k_current_gqa, ex_k_rope_gqa);

    if (rope_accepted != 1024 || rope_completed != 1024 ||
        gqa_accepted != 32 || gqa_completed != 192 || gqa_illegal_inputs != 0)
      $fatal(1, "target RoPE/GQA counters rope=%0d/%0d gqa=%0d/%0d illegal=%0d",
             rope_accepted, rope_completed, gqa_accepted, gqa_completed,
             gqa_illegal_inputs);
    if (rope_flags_or[4:1] != 0)
      $fatal(1, "target RoPE flags=%h", rope_flags_or);
    $display(
      "L5_TARGET_ROPE_GQA_PASS rope_pairs=1024 multicast_inputs=32 multicast_outputs=192 total_cycles=%0d rope_cycles=%0d multicast_cycles=%0d q_rope_fnv64=%016h k0_gqa_fnv64=%016h k1_gqa_fnv64=%016h",
      cycles, rope_cycles, multicast_cycles, hash1536(q_rope),
      hash1536(k_previous_gqa), hash1536(k_current_gqa)
    );
    $finish;
  end

  initial begin
    repeat (20000) @(posedge clk);
    $fatal(1, "target RoPE/GQA timeout");
  end
endmodule
