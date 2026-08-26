`timescale 1ns/1ps
module tb_l5_hidden256_block;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  integer cycles, matrix_cycles, sfu_cycles;

  logic array_in_valid, array_in_ready, array_out_valid, array_out_ready;
  logic [255:0] array_a;
  logic [511:0] array_b;
  logic [16383:0] array_acc, array_out;
  logic [4:0] array_flags, matrix_flags_or;
  logic [31:0] array_accepted, array_completed;
  bf16_outer_product_array #(.ROWS(16), .COLS(32)) matrix(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(array_in_valid), .in_ready_o(array_in_ready),
    .a_i(array_a), .b_i(array_b), .acc_i(array_acc),
    .out_valid_o(array_out_valid), .out_ready_i(array_out_ready),
    .acc_o(array_out), .exception_flags_o(array_flags),
    .accepted_steps_o(array_accepted), .completed_steps_o(array_completed)
  );

  logic rms_in_valid, rms_in_ready, rms_out_valid, rms_out_ready;
  logic [8191:0] rms_x, rms_weight, rms_y;
  logic [31:0] rms_epsilon;
  logic [4:0] rms_flags;
  logic [31:0] rms_accepted, rms_completed, rms_reduce_cycles;
  logic [31:0] rms_rsqrt_cycles, rms_output_cycles;
  fp32_rmsnorm256_chunked rms(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(rms_in_valid), .in_ready_o(rms_in_ready),
    .x_i(rms_x), .weight_i(rms_weight), .epsilon_i(rms_epsilon),
    .out_valid_o(rms_out_valid), .out_ready_i(rms_out_ready),
    .y_o(rms_y), .exception_flags_o(rms_flags),
    .accepted_o(rms_accepted), .completed_o(rms_completed),
    .reduction_cycles_o(rms_reduce_cycles),
    .rsqrt_cycles_o(rms_rsqrt_cycles), .output_cycles_o(rms_output_cycles)
  );

  logic rope_in_valid, rope_in_ready, rope_out_valid, rope_out_ready;
  logic [31:0] rope_even, rope_odd, rope_cos, rope_sin;
  logic [31:0] rope_even_out, rope_odd_out;
  logic [4:0] rope_flags;
  logic [31:0] rope_accepted, rope_completed;
  fp32_rope_pair rope(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(rope_in_valid), .in_ready_o(rope_in_ready),
    .even_i(rope_even), .odd_i(rope_odd),
    .cos_i(rope_cos), .sin_i(rope_sin),
    .out_valid_o(rope_out_valid), .out_ready_i(rope_out_ready),
    .even_o(rope_even_out), .odd_o(rope_odd_out),
    .exception_flags_o(rope_flags),
    .accepted_pairs_o(rope_accepted), .completed_pairs_o(rope_completed)
  );

  logic dot_in_valid, dot_in_ready, dot_out_valid, dot_out_ready;
  logic [2047:0] dot_a, dot_b;
  logic [31:0] dot_scale, dot_result;
  logic [4:0] dot_flags;
  logic [31:0] dot_accepted, dot_completed;
  fp32_dot64_scaled dot(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(dot_in_valid), .in_ready_o(dot_in_ready),
    .a_i(dot_a), .b_i(dot_b), .scale_i(dot_scale),
    .out_valid_o(dot_out_valid), .out_ready_i(dot_out_ready),
    .result_o(dot_result), .exception_flags_o(dot_flags),
    .accepted_o(dot_accepted), .completed_o(dot_completed)
  );

  logic soft_clear, soft_in_valid, soft_in_ready, soft_out_valid, soft_out_ready;
  logic [31:0] soft_score, soft_m, soft_l;
  logic [2047:0] soft_value, soft_o;
  logic [4:0] soft_flags;
  logic [31:0] soft_accepted, soft_completed;
  fp32_online_softmax #(.LANES(64)) softmax(
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
  logic [4:0] recip_flags;
  logic recip_domain_error;
  logic [31:0] recip_accepted, recip_completed;
  fp32_reciprocal_nr reciprocal(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(recip_in_valid), .in_ready_o(recip_in_ready), .x_i(recip_x),
    .out_valid_o(recip_out_valid), .out_ready_i(recip_out_ready), .y_o(recip_y),
    .exception_flags_o(recip_flags), .domain_error_o(recip_domain_error),
    .accepted_o(recip_accepted), .completed_o(recip_completed)
  );

  logic silu_in_valid, silu_in_ready, silu_out_valid, silu_out_ready;
  logic [31:0] silu_x, silu_y;
  logic [4:0] silu_flags;
  logic [31:0] silu_accepted, silu_completed;
  fp32_silu silu(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(silu_in_valid), .in_ready_o(silu_in_ready), .x_i(silu_x),
    .out_valid_o(silu_out_valid), .out_ready_i(silu_out_ready), .y_o(silu_y),
    .exception_flags_o(silu_flags), .accepted_o(silu_accepted),
    .completed_o(silu_completed)
  );

  logic vector_op;
  logic [511:0] vector_a, vector_b, vector_out;
  logic [4:0] vector_flags;
  fp32_vector_alu #(.LANES(16)) vector16(
    .op_i(vector_op), .a_i(vector_a), .b_i(vector_b),
    .out_o(vector_out), .exception_flags_o(vector_flags)
  );

  logic [15:0] weights [0:655359];
  logic [31:0] norm_weight1_mem [0:255], norm_weight2_mem [0:255];
  logic [31:0] rope_coeff_mem [0:511];
  logic [31:0] ex_x_previous [0:255], ex_x_current [0:255];
  logic [31:0] ex_norm_previous [0:255], ex_norm_current [0:255];
  logic [31:0] ex_q [0:255], ex_k [0:511], ex_v [0:511];
  logic [31:0] ex_q_rope [0:255], ex_k_rope [0:511];
  logic [31:0] ex_softmax_m [0:3], ex_softmax_l [0:3];
  logic [31:0] ex_softmax_o [0:255], ex_attention [0:255];
  logic [31:0] ex_oproj [0:255], ex_residual1 [0:255], ex_norm2 [0:255];
  logic [31:0] ex_gate [0:511], ex_up [0:511], ex_silu [0:511];
  logic [31:0] ex_product [0:511], ex_down [0:255], ex_final [0:255];
  logic [4:0] sfu_flags_or;

  always #5 clk = ~clk;
  always @(posedge clk)
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;

  function automatic [15:0] to_bf16(input logic [31:0] value);
    logic [31:0] rounded;
    begin
      rounded = value + 32'h00007fff + value[16];
      to_bf16 = rounded[31:16];
    end
  endfunction

  function automatic [63:0] hash256(input logic [8191:0] data);
    logic [63:0] hash;
    begin
      hash = 64'hcbf29ce484222325;
      for (int i = 0; i < 256; i++)
        hash = (hash ^ {32'd0, data[i * 32 +: 32]}) * 64'h100000001b3;
      hash256 = hash;
    end
  endfunction

  task automatic load256(
    input logic [31:0] memory [0:255], output logic [8191:0] bus
  );
    for (int i = 0; i < 256; i++) bus[i * 32 +: 32] = memory[i];
  endtask

  task automatic clear512(output logic [16383:0] bus);
    for (int i = 0; i < 512; i++) bus[i * 32 +: 32] = 32'd0;
  endtask

  task automatic check256(
    input logic [8191:0] bus, input logic [31:0] memory [0:255], input string name
  );
    for (int i = 0; i < 256; i++)
      if (bus[i * 32 +: 32] !== memory[i])
        $fatal(1, "hidden256 node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[i]);
  endtask

  task automatic check512(
    input logic [16383:0] bus, input logic [31:0] memory [0:511], input string name
  );
    for (int i = 0; i < 512; i++)
      if (bus[i * 32 +: 32] !== memory[i])
        $fatal(1, "hidden256 node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[i]);
  endtask

  task automatic check512_slice(
    input logic [8191:0] bus, input logic [31:0] memory [0:511],
    input integer offset, input string name
  );
    for (int i = 0; i < 256; i++)
      if (bus[i * 32 +: 32] !== memory[offset + i])
        $fatal(1, "hidden256 node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[offset + i]);
  endtask

  task automatic run_rms256(
    input logic [8191:0] x, input logic [8191:0] weight,
    output logic [8191:0] y
  );
    integer start;
    begin
      start = cycles;
      @(negedge clk);
      rms_x = x;
      rms_weight = weight;
      rms_epsilon = 32'h3727c5ac;
      rms_in_valid = 1;
      do @(posedge clk); while (!rms_in_ready);
      @(negedge clk);
      rms_in_valid = 0;
      do @(posedge clk); while (!(rms_out_valid && rms_out_ready));
      @(negedge clk);
      y = rms_y;
      sfu_flags_or |= rms_flags;
      sfu_cycles += cycles - start;
    end
  endtask

  task automatic run_gemv(
    input logic [16383:0] x, input integer input_count,
    input integer output_count, input integer weight_offset,
    output logic [16383:0] y
  );
    logic [16383:0] current_accumulator;
    integer start;
    begin
      start = cycles;
      clear512(y);
      for (int tile = 0; tile < output_count / 32; tile++) begin
        clear512(current_accumulator);
        for (int k = 0; k < input_count; k++) begin
          array_a = '0;
          array_b = '0;
          array_a[15:0] = to_bf16(x[k * 32 +: 32]);
          for (int j = 0; j < 32; j++)
            array_b[j * 16 +: 16] =
              weights[weight_offset + k * output_count + tile * 32 + j];
          array_acc = current_accumulator;
          @(negedge clk);
          array_in_valid = 1;
          do @(posedge clk); while (!array_in_ready);
          @(negedge clk);
          array_in_valid = 0;
          do @(posedge clk); while (!(array_out_valid && array_out_ready));
          @(negedge clk);
          current_accumulator = array_out;
          matrix_flags_or |= array_flags;
        end
        for (int j = 0; j < 32; j++)
          y[(tile * 32 + j) * 32 +: 32] = current_accumulator[j * 32 +: 32];
      end
      matrix_cycles += cycles - start;
    end
  endtask

  task automatic run_rope256(
    input logic [8191:0] x, input integer position,
    output logic [8191:0] y
  );
    integer start;
    begin
      start = cycles;
      y = '0;
      for (int pair = 0; pair < 128; pair++) begin
        @(negedge clk);
        rope_even = x[(2 * pair) * 32 +: 32];
        rope_odd = x[(2 * pair + 1) * 32 +: 32];
        rope_cos = rope_coeff_mem[position * 256 + 2 * pair];
        rope_sin = rope_coeff_mem[position * 256 + 2 * pair + 1];
        rope_in_valid = 1;
        do @(posedge clk); while (!rope_in_ready);
        @(negedge clk);
        rope_in_valid = 0;
        do @(posedge clk); while (!(rope_out_valid && rope_out_ready));
        @(negedge clk);
        y[(2 * pair) * 32 +: 32] = rope_even_out;
        y[(2 * pair + 1) * 32 +: 32] = rope_odd_out;
        sfu_flags_or |= rope_flags;
      end
      sfu_cycles += cycles - start;
    end
  endtask

  task automatic run_dot64(
    input logic [2047:0] a, input logic [2047:0] b, output logic [31:0] result
  );
    begin
      @(negedge clk);
      dot_a = a;
      dot_b = b;
      dot_scale = 32'h3e000000;
      dot_in_valid = 1;
      do @(posedge clk); while (!dot_in_ready);
      @(negedge clk);
      dot_in_valid = 0;
      do @(posedge clk); while (!(dot_out_valid && dot_out_ready));
      @(negedge clk);
      result = dot_result;
      sfu_flags_or |= dot_flags;
    end
  endtask

  task automatic run_vector(
    input logic op, input logic [16383:0] a, input logic [16383:0] b,
    input integer count, output logic [16383:0] result
  );
    integer start;
    begin
      start = cycles;
      clear512(result);
      vector_op = op;
      for (int chunk = 0; chunk < count / 16; chunk++) begin
        @(negedge clk);
        vector_a = a[chunk * 512 +: 512];
        vector_b = b[chunk * 512 +: 512];
        #1;
        result[chunk * 512 +: 512] = vector_out;
        sfu_flags_or |= vector_flags;
      end
      sfu_cycles += cycles - start;
    end
  endtask

  task automatic run_attention_head(
    input logic [2047:0] query,
    input logic [2047:0] key0, input logic [2047:0] value0,
    input logic [2047:0] key1, input logic [2047:0] value1,
    output logic [31:0] final_m, output logic [31:0] final_l,
    output logic [2047:0] final_o, output logic [2047:0] attention
  );
    logic [31:0] score;
    logic [31:0] inverse_l;
    integer start;
    begin
      start = cycles;
      run_dot64(query, key0, score);
      @(negedge clk);
      soft_clear = 1;
      soft_score = score;
      soft_value = value0;
      soft_in_valid = 1;
      do @(posedge clk); while (!soft_in_ready);
      @(negedge clk);
      soft_in_valid = 0;
      soft_clear = 0;
      do @(posedge clk); while (!(soft_out_valid && soft_out_ready));

      run_dot64(query, key1, score);
      @(negedge clk);
      soft_score = score;
      soft_value = value1;
      soft_in_valid = 1;
      do @(posedge clk); while (!soft_in_ready);
      @(negedge clk);
      soft_in_valid = 0;
      do @(posedge clk); while (!(soft_out_valid && soft_out_ready));
      @(negedge clk);
      final_m = soft_m;
      final_l = soft_l;
      final_o = soft_o;
      sfu_flags_or |= soft_flags;

      recip_x = final_l;
      recip_in_valid = 1;
      do @(posedge clk); while (!recip_in_ready);
      @(negedge clk);
      recip_in_valid = 0;
      do @(posedge clk); while (!(recip_out_valid && recip_out_ready));
      @(negedge clk);
      inverse_l = recip_y;
      if (recip_domain_error) $fatal(1, "hidden256 reciprocal domain error");
      sfu_flags_or |= recip_flags;
      attention = '0;
      vector_op = 1;
      for (int chunk = 0; chunk < 4; chunk++) begin
        @(negedge clk);
        vector_a = final_o[chunk * 512 +: 512];
        for (int lane = 0; lane < 16; lane++)
          vector_b[lane * 32 +: 32] = inverse_l;
        #1;
        attention[chunk * 512 +: 512] = vector_out;
        sfu_flags_or |= vector_flags;
      end
      sfu_cycles += cycles - start;
    end
  endtask

  task automatic run_silu512(
    input logic [16383:0] x, output logic [16383:0] y
  );
    integer start;
    begin
      start = cycles;
      clear512(y);
      for (int lane = 0; lane < 512; lane++) begin
        @(negedge clk);
        silu_x = x[lane * 32 +: 32];
        silu_in_valid = 1;
        do @(posedge clk); while (!silu_in_ready);
        @(negedge clk);
        silu_in_valid = 0;
        do @(posedge clk); while (!(silu_out_valid && silu_out_ready));
        @(negedge clk);
        y[lane * 32 +: 32] = silu_y;
        sfu_flags_or |= silu_flags;
      end
      sfu_cycles += cycles - start;
    end
  endtask

  initial begin
    logic [8191:0] x_previous, x_current, norm_weight1, norm_weight2;
    logic [8191:0] norm_previous, norm_current, query, key0, key1, value0, value1;
    logic [8191:0] query_rope, key0_rope, key1_rope, attention, soft_numerator;
    logic [8191:0] oproj, residual1, norm2, down, final_value;
    logic [16383:0] matrix_input, matrix_output, gate, up, activated, product;
    logic [16383:0] vector_input_a, vector_input_b, vector_result;
    logic [31:0] head_m, head_l;
    logic [2047:0] head_o, head_attention;

    clk = 0;
    rst_n = 0;
    cycles = 0;
    matrix_cycles = 0;
    sfu_cycles = 0;
    array_in_valid = 0;
    array_out_ready = 1;
    array_a = '0;
    array_b = '0;
    clear512(array_acc);
    matrix_flags_or = '0;
    rms_in_valid = 0;
    rms_out_ready = 1;
    rms_x = '0;
    rms_weight = '0;
    rms_epsilon = '0;
    rope_in_valid = 0;
    rope_out_ready = 1;
    dot_in_valid = 0;
    dot_out_ready = 1;
    soft_clear = 0;
    soft_in_valid = 0;
    soft_out_ready = 1;
    recip_in_valid = 0;
    recip_out_ready = 1;
    silu_in_valid = 0;
    silu_out_ready = 1;
    vector_op = 0;
    vector_a = '0;
    vector_b = '0;
    sfu_flags_or = '0;

    $readmemh("work/results/l5_hidden256_block/vectors/weights_bf16.memh", weights);
    $readmemh("work/results/l5_hidden256_block/vectors/norm_weight1.memh", norm_weight1_mem);
    $readmemh("work/results/l5_hidden256_block/vectors/norm_weight2.memh", norm_weight2_mem);
    $readmemh("work/results/l5_hidden256_block/vectors/rope_coeff.memh", rope_coeff_mem);
    $readmemh("work/results/l5_hidden256_block/vectors/x_previous.memh", ex_x_previous);
    $readmemh("work/results/l5_hidden256_block/vectors/x_current.memh", ex_x_current);
    $readmemh("work/results/l5_hidden256_block/vectors/norm_previous.memh", ex_norm_previous);
    $readmemh("work/results/l5_hidden256_block/vectors/norm_current.memh", ex_norm_current);
    $readmemh("work/results/l5_hidden256_block/vectors/q.memh", ex_q);
    $readmemh("work/results/l5_hidden256_block/vectors/k.memh", ex_k);
    $readmemh("work/results/l5_hidden256_block/vectors/v.memh", ex_v);
    $readmemh("work/results/l5_hidden256_block/vectors/q_rope.memh", ex_q_rope);
    $readmemh("work/results/l5_hidden256_block/vectors/k_rope.memh", ex_k_rope);
    $readmemh("work/results/l5_hidden256_block/vectors/softmax_m.memh", ex_softmax_m);
    $readmemh("work/results/l5_hidden256_block/vectors/softmax_l.memh", ex_softmax_l);
    $readmemh("work/results/l5_hidden256_block/vectors/softmax_o.memh", ex_softmax_o);
    $readmemh("work/results/l5_hidden256_block/vectors/attention.memh", ex_attention);
    $readmemh("work/results/l5_hidden256_block/vectors/oproj.memh", ex_oproj);
    $readmemh("work/results/l5_hidden256_block/vectors/residual1.memh", ex_residual1);
    $readmemh("work/results/l5_hidden256_block/vectors/norm2.memh", ex_norm2);
    $readmemh("work/results/l5_hidden256_block/vectors/gate.memh", ex_gate);
    $readmemh("work/results/l5_hidden256_block/vectors/up.memh", ex_up);
    $readmemh("work/results/l5_hidden256_block/vectors/silu.memh", ex_silu);
    $readmemh("work/results/l5_hidden256_block/vectors/gate_mul_up.memh", ex_product);
    $readmemh("work/results/l5_hidden256_block/vectors/down.memh", ex_down);
    $readmemh("work/results/l5_hidden256_block/vectors/final.memh", ex_final);

    repeat (3) @(posedge clk);
    rst_n = 1;
    load256(ex_x_previous, x_previous);
    load256(ex_x_current, x_current);
    load256(norm_weight1_mem, norm_weight1);
    load256(norm_weight2_mem, norm_weight2);

    run_rms256(x_previous, norm_weight1, norm_previous);
    check256(norm_previous, ex_norm_previous, "norm_previous");
    run_rms256(x_current, norm_weight1, norm_current);
    check256(norm_current, ex_norm_current, "norm_current");

    clear512(matrix_input);
    matrix_input[8191:0] = norm_current;
    run_gemv(matrix_input, 256, 256, 0, matrix_output);
    query = matrix_output[8191:0];
    check256(query, ex_q, "q");
    matrix_input[8191:0] = norm_previous;
    run_gemv(matrix_input, 256, 256, 65536, matrix_output);
    key0 = matrix_output[8191:0];
    check512_slice(key0, ex_k, 0, "k_previous");
    matrix_input[8191:0] = norm_current;
    run_gemv(matrix_input, 256, 256, 65536, matrix_output);
    key1 = matrix_output[8191:0];
    check512_slice(key1, ex_k, 256, "k_current");
    matrix_input[8191:0] = norm_previous;
    run_gemv(matrix_input, 256, 256, 131072, matrix_output);
    value0 = matrix_output[8191:0];
    check512_slice(value0, ex_v, 0, "v_previous");
    matrix_input[8191:0] = norm_current;
    run_gemv(matrix_input, 256, 256, 131072, matrix_output);
    value1 = matrix_output[8191:0];
    check512_slice(value1, ex_v, 256, "v_current");

    run_rope256(query, 1, query_rope);
    check256(query_rope, ex_q_rope, "q_rope");
    run_rope256(key0, 0, key0_rope);
    check512_slice(key0_rope, ex_k_rope, 0, "k_rope_previous");
    run_rope256(key1, 1, key1_rope);
    check512_slice(key1_rope, ex_k_rope, 256, "k_rope_current");

    attention = '0;
    soft_numerator = '0;
    for (int head = 0; head < 4; head++) begin
      run_attention_head(
        query_rope[head * 2048 +: 2048],
        key0_rope[head * 2048 +: 2048], value0[head * 2048 +: 2048],
        key1_rope[head * 2048 +: 2048], value1[head * 2048 +: 2048],
        head_m, head_l, head_o, head_attention
      );
      if (head_m !== ex_softmax_m[head] || head_l !== ex_softmax_l[head])
        $fatal(1, "hidden256 M/L mismatch head=%0d", head);
      for (int lane = 0; lane < 64; lane++)
        if (head_o[lane * 32 +: 32] !== ex_softmax_o[head * 64 + lane])
          $fatal(1, "hidden256 O mismatch head=%0d lane=%0d", head, lane);
      soft_numerator[head * 2048 +: 2048] = head_o;
      attention[head * 2048 +: 2048] = head_attention;
    end
    check256(soft_numerator, ex_softmax_o, "softmax_o");
    check256(attention, ex_attention, "attention");

    clear512(matrix_input);
    matrix_input[8191:0] = attention;
    run_gemv(matrix_input, 256, 256, 196608, matrix_output);
    oproj = matrix_output[8191:0];
    check256(oproj, ex_oproj, "oproj");
    clear512(vector_input_a);
    clear512(vector_input_b);
    vector_input_a[8191:0] = x_current;
    vector_input_b[8191:0] = oproj;
    run_vector(0, vector_input_a, vector_input_b, 256, vector_result);
    residual1 = vector_result[8191:0];
    check256(residual1, ex_residual1, "residual1");
    run_rms256(residual1, norm_weight2, norm2);
    check256(norm2, ex_norm2, "norm2");

    clear512(matrix_input);
    matrix_input[8191:0] = norm2;
    run_gemv(matrix_input, 256, 512, 262144, gate);
    check512(gate, ex_gate, "gate");
    run_gemv(matrix_input, 256, 512, 393216, up);
    check512(up, ex_up, "up");
    run_silu512(gate, activated);
    check512(activated, ex_silu, "silu");
    run_vector(1, activated, up, 512, product);
    check512(product, ex_product, "gate_mul_up");
    run_gemv(product, 512, 256, 524288, matrix_output);
    down = matrix_output[8191:0];
    check256(down, ex_down, "down");
    clear512(vector_input_a);
    clear512(vector_input_b);
    vector_input_a[8191:0] = residual1;
    vector_input_b[8191:0] = down;
    run_vector(0, vector_input_a, vector_input_b, 256, vector_result);
    final_value = vector_result[8191:0];
    check256(final_value, ex_final, "final");

    if (array_accepted != 24576 || array_completed != 24576)
      $fatal(1, "hidden256 matrix accounting accepted=%0d completed=%0d",
             array_accepted, array_completed);
    if (rms_accepted != 3 || rms_completed != 3 || rope_accepted != 384 ||
        rope_completed != 384 || dot_accepted != 8 || dot_completed != 8 ||
        soft_accepted != 8 || soft_completed != 8 || recip_accepted != 4 ||
        recip_completed != 4 || silu_accepted != 512 || silu_completed != 512)
      $fatal(1, "hidden256 SFU accounting mismatch");
    if (matrix_flags_or[4:1] != 0 || sfu_flags_or[4:1] != 0)
      $fatal(1, "hidden256 unexpected flags matrix=%h sfu=%h",
             matrix_flags_or, sfu_flags_or);
    $display(
      "L5_HIDDEN256_BLOCK_PASS hidden=256 heads=4 head_dim=64 context=2 mlp=512 nodes=22 array_steps=24576 total_cycles=%0d matrix_cycles=%0d sfu_cycles=%0d rms_reduce_cycles=%0d rms_rsqrt_cycles=%0d rms_output_cycles=%0d final_fnv64=%016h",
      cycles, matrix_cycles, sfu_cycles, rms_reduce_cycles, rms_rsqrt_cycles,
      rms_output_cycles, hash256(final_value)
    );
    $finish;
  end

  initial begin
    repeat (500000) @(posedge clk);
    $fatal(1, "hidden256 block timeout");
  end
endmodule
