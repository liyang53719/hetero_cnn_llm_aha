`timescale 1ns/1ps
module tb_l5_target_mlo;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  integer cycles, dot_cycles, online_cycles, reciprocal_cycles, normalization_cycles;

  logic dot_in_valid, dot_in_ready, dot_out_valid, dot_out_ready;
  logic [4095:0] dot_a, dot_b;
  logic [31:0] dot_scale, dot_result;
  logic [4:0] dot_flags, dot_flags_or;
  logic [31:0] dot_accepted, dot_completed;
  fp32_dot128_scaled dot(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(dot_in_valid), .in_ready_o(dot_in_ready),
    .a_i(dot_a), .b_i(dot_b), .scale_i(dot_scale),
    .out_valid_o(dot_out_valid), .out_ready_i(dot_out_ready),
    .result_o(dot_result), .exception_flags_o(dot_flags),
    .accepted_o(dot_accepted), .completed_o(dot_completed)
  );

  logic soft_clear, soft_in_valid, soft_in_ready, soft_out_valid, soft_out_ready;
  logic [31:0] soft_score, soft_m, soft_l;
  logic [4095:0] soft_value, soft_o;
  logic [4:0] soft_flags, soft_flags_or;
  logic [31:0] soft_accepted, soft_completed;
  fp32_online_softmax #(.LANES(128)) softmax(
    .clk_i(clk), .rst_ni(rst_n), .clear_i(soft_clear),
    .in_valid_i(soft_in_valid), .in_ready_o(soft_in_ready),
    .score_i(soft_score), .value_i(soft_value),
    .out_valid_o(soft_out_valid), .out_ready_i(soft_out_ready),
    .m_o(soft_m), .l_o(soft_l), .o_o(soft_o),
    .exception_flags_o(soft_flags),
    .accepted_tokens_o(soft_accepted), .completed_tokens_o(soft_completed)
  );

  logic recip_in_valid, recip_in_ready, recip_out_valid, recip_out_ready;
  logic [31:0] recip_x, recip_y;
  logic [4:0] recip_flags, recip_flags_or;
  logic recip_domain_error;
  logic [31:0] recip_accepted, recip_completed;
  fp32_reciprocal_nr reciprocal(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(recip_in_valid), .in_ready_o(recip_in_ready), .x_i(recip_x),
    .out_valid_o(recip_out_valid), .out_ready_i(recip_out_ready), .y_o(recip_y),
    .exception_flags_o(recip_flags), .domain_error_o(recip_domain_error),
    .accepted_o(recip_accepted), .completed_o(recip_completed)
  );

  logic [511:0] vector_a, vector_b, vector_out;
  logic [4:0] vector_flags, vector_flags_or;
  fp32_vector_alu #(.LANES(16)) vector16(
    .op_i(1'b1), .a_i(vector_a), .b_i(vector_b),
    .out_o(vector_out), .exception_flags_o(vector_flags)
  );

  logic [31:0] in_q [0:1535], in_k [0:3071], in_v [0:3071];
  logic [31:0] ex_m [0:11], ex_l [0:11];
  logic [31:0] ex_o [0:1535], ex_attention [0:1535];

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

  task automatic load3072(
    input logic [31:0] memory [0:3071],
    output logic [49151:0] previous, output logic [49151:0] current
  );
    for (int i = 0; i < 1536; i++) begin
      previous[i * 32 +: 32] = memory[i];
      current[i * 32 +: 32] = memory[1536 + i];
    end
  endtask

  task automatic run_dot128(
    input logic [4095:0] a, input logic [4095:0] b,
    output logic [31:0] result
  );
    integer start;
    begin
      start = cycles;
      @(negedge clk);
      dot_a = a;
      dot_b = b;
      dot_scale = 32'h3db504f3;
      dot_in_valid = 1;
      do @(posedge clk); while (!dot_in_ready);
      @(negedge clk);
      dot_in_valid = 0;
      do @(posedge clk); while (!(dot_out_valid && dot_out_ready));
      @(negedge clk);
      result = dot_result;
      dot_flags_or |= dot_flags;
      dot_cycles += cycles - start;
    end
  endtask

  task automatic run_online_token(
    input logic clear,
    input logic [31:0] score,
    input logic [4095:0] value
  );
    integer start;
    begin
      start = cycles;
      @(negedge clk);
      soft_clear = clear;
      soft_score = score;
      soft_value = value;
      soft_in_valid = 1;
      do @(posedge clk); while (!soft_in_ready);
      @(negedge clk);
      soft_in_valid = 0;
      soft_clear = 0;
      do @(posedge clk); while (!(soft_out_valid && soft_out_ready));
      @(negedge clk);
      soft_flags_or |= soft_flags;
      online_cycles += cycles - start;
    end
  endtask

  task automatic run_reciprocal(
    input logic [31:0] x, output logic [31:0] result
  );
    integer start;
    begin
      start = cycles;
      @(negedge clk);
      recip_x = x;
      recip_in_valid = 1;
      do @(posedge clk); while (!recip_in_ready);
      @(negedge clk);
      recip_in_valid = 0;
      do @(posedge clk); while (!(recip_out_valid && recip_out_ready));
      @(negedge clk);
      result = recip_y;
      if (recip_domain_error) $fatal(1, "target MLO reciprocal domain error");
      recip_flags_or |= recip_flags;
      reciprocal_cycles += cycles - start;
    end
  endtask

  task automatic normalize_o(
    input logic [4095:0] numerator,
    input logic [31:0] inverse_l,
    output logic [4095:0] result
  );
    integer start;
    begin
      start = cycles;
      result = '0;
      for (int chunk = 0; chunk < 8; chunk++) begin
        @(negedge clk);
        vector_a = numerator[chunk * 512 +: 512];
        for (int lane = 0; lane < 16; lane++)
          vector_b[lane * 32 +: 32] = inverse_l;
        #1;
        result[chunk * 512 +: 512] = vector_out;
        vector_flags_or |= vector_flags;
      end
      normalization_cycles += cycles - start;
    end
  endtask

  initial begin
    logic [49151:0] q, k_previous, k_current, v_previous, v_current;
    logic [49151:0] final_o, attention;
    logic [31:0] score, inverse_l;
    logic [4095:0] head_o, head_attention;

    clk = 0;
    rst_n = 0;
    cycles = 0;
    dot_cycles = 0;
    online_cycles = 0;
    reciprocal_cycles = 0;
    normalization_cycles = 0;
    dot_in_valid = 0;
    dot_out_ready = 1;
    dot_flags_or = '0;
    soft_clear = 0;
    soft_in_valid = 0;
    soft_out_ready = 1;
    soft_flags_or = '0;
    recip_in_valid = 0;
    recip_out_ready = 1;
    recip_flags_or = '0;
    vector_a = '0;
    vector_b = '0;
    vector_flags_or = '0;

    $readmemh("work/results/l5_target_rope_gqa/vectors/q_rope.memh", in_q);
    $readmemh("work/results/l5_target_rope_gqa/vectors/k_rope_gqa.memh", in_k);
    $readmemh("work/results/l5_target_qkv_segment/vectors/v_gqa.memh", in_v);
    $readmemh("work/results/l5_target_mlo/vectors/m.memh", ex_m);
    $readmemh("work/results/l5_target_mlo/vectors/l.memh", ex_l);
    $readmemh("work/results/l5_target_mlo/vectors/o.memh", ex_o);
    $readmemh("work/results/l5_target_mlo/vectors/attention.memh", ex_attention);

    repeat (3) @(posedge clk);
    rst_n = 1;
    load1536(in_q, q);
    load3072(in_k, k_previous, k_current);
    load3072(in_v, v_previous, v_current);
    clear1536(final_o);
    clear1536(attention);
    for (int head = 0; head < 12; head++) begin
      run_dot128(q[head * 4096 +: 4096],
                 k_previous[head * 4096 +: 4096], score);
      run_online_token(1, score, v_previous[head * 4096 +: 4096]);
      run_dot128(q[head * 4096 +: 4096],
                 k_current[head * 4096 +: 4096], score);
      run_online_token(0, score, v_current[head * 4096 +: 4096]);
      if (soft_m !== ex_m[head] || soft_l !== ex_l[head])
        $fatal(1, "target M/L mismatch head=%0d", head);
      head_o = soft_o;
      for (int lane = 0; lane < 128; lane++)
        if (head_o[lane * 32 +: 32] !== ex_o[head * 128 + lane])
          $fatal(1, "target O mismatch head=%0d lane=%0d", head, lane);
      run_reciprocal(soft_l, inverse_l);
      normalize_o(head_o, inverse_l, head_attention);
      for (int lane = 0; lane < 128; lane++)
        if (head_attention[lane * 32 +: 32] !== ex_attention[head * 128 + lane])
          $fatal(1, "target attention mismatch head=%0d lane=%0d", head, lane);
      final_o[head * 4096 +: 4096] = head_o;
      attention[head * 4096 +: 4096] = head_attention;
    end

    if (dot_accepted != 24 || dot_completed != 24 ||
        soft_accepted != 24 || soft_completed != 24 ||
        recip_accepted != 12 || recip_completed != 12)
      $fatal(1, "target MLO counters dot=%0d/%0d soft=%0d/%0d recip=%0d/%0d",
             dot_accepted, dot_completed, soft_accepted, soft_completed,
             recip_accepted, recip_completed);
    if (dot_flags_or[4:1] != 0 || soft_flags_or[4:1] != 0 ||
        recip_flags_or[4:1] != 0 || vector_flags_or[4:1] != 0)
      $fatal(1, "target MLO flags dot=%h soft=%h recip=%h vector=%h",
             dot_flags_or, soft_flags_or, recip_flags_or, vector_flags_or);
    $display(
      "L5_TARGET_MLO_PASS heads=12 tokens=2 scores_streamed=24 score_matrix=0 total_cycles=%0d dot_cycles=%0d online_cycles=%0d reciprocal_cycles=%0d normalization_cycles=%0d o_fnv64=%016h attention_fnv64=%016h",
      cycles, dot_cycles, online_cycles, reciprocal_cycles,
      normalization_cycles, hash1536(final_o), hash1536(attention)
    );
    $finish;
  end

  initial begin
    repeat (20000) @(posedge clk);
    $fatal(1, "target MLO timeout");
  end
endmodule
