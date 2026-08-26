`timescale 1ns/1ps
module tb_l5_target_qkv_segment;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  integer cycles, matrix_cycles, rms_cycles, qkv_cycles;

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
  logic [49151:0] rms_x, rms_weight, rms_y;
  logic [31:0] rms_epsilon;
  logic [4:0] rms_flags;
  logic [31:0] rms_accepted, rms_completed, rms_reduce_cycles;
  logic [31:0] rms_rsqrt_cycles, rms_output_cycles;
  fp32_rmsnorm1536_chunked rms(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(rms_in_valid), .in_ready_o(rms_in_ready),
    .x_i(rms_x), .weight_i(rms_weight), .epsilon_i(rms_epsilon),
    .out_valid_o(rms_out_valid), .out_ready_i(rms_out_ready),
    .y_o(rms_y), .exception_flags_o(rms_flags),
    .accepted_o(rms_accepted), .completed_o(rms_completed),
    .reduction_cycles_o(rms_reduce_cycles),
    .rsqrt_cycles_o(rms_rsqrt_cycles), .output_cycles_o(rms_output_cycles)
  );

  logic qkv_in_valid, qkv_in_ready, qkv_out_valid, qkv_out_ready;
  logic [1:0] qkv_role_in, qkv_role_out;
  logic [6:0] qkv_chunk_in, qkv_chunk_out;
  logic [15:0] qkv_tag_in, qkv_tag_out;
  logic [511:0] qkv_data_in, qkv_bias_in, qkv_data_out;
  logic [3:0] qkv_query_head;
  logic qkv_kv_head;
  logic [2:0] qkv_head_chunk;
  logic qkv_last, qkv_illegal;
  logic [4:0] qkv_flags, qkv_flags_or;
  logic [31:0] qkv_accepted, qkv_completed, qkv_illegal_inputs;
  qwen_qkv_bias_gqa16 qkv(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(qkv_in_valid), .in_ready_o(qkv_in_ready),
    .role_i(qkv_role_in), .chunk_i(qkv_chunk_in), .tag_i(qkv_tag_in),
    .data_i(qkv_data_in), .bias_i(qkv_bias_in),
    .out_valid_o(qkv_out_valid), .out_ready_i(qkv_out_ready),
    .role_o(qkv_role_out), .chunk_o(qkv_chunk_out), .tag_o(qkv_tag_out),
    .query_head_o(qkv_query_head), .kv_head_o(qkv_kv_head),
    .head_chunk_o(qkv_head_chunk), .last_o(qkv_last),
    .illegal_o(qkv_illegal), .data_o(qkv_data_out),
    .exception_flags_o(qkv_flags), .accepted_inputs_o(qkv_accepted),
    .completed_outputs_o(qkv_completed), .illegal_inputs_o(qkv_illegal_inputs)
  );

  logic [15:0] weights [0:3145727];
  logic [31:0] ex_x_previous [0:1535], ex_x_current [0:1535];
  logic [31:0] ex_norm_weight [0:1535];
  logic [31:0] ex_norm_previous [0:1535], ex_norm_current [0:1535];
  logic [31:0] ex_q_bias [0:1535], ex_k_bias [0:255], ex_v_bias [0:255];
  logic [31:0] ex_q_raw [0:1535], ex_k_raw [0:511], ex_v_raw [0:511];
  logic [31:0] ex_q_biased [0:1535], ex_k_biased [0:511], ex_v_biased [0:511];
  logic [31:0] ex_k_gqa [0:3071], ex_v_gqa [0:3071];

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

  task automatic clear512(output logic [16383:0] bus);
    for (int i = 0; i < 512; i++) bus[i * 32 +: 32] = 32'd0;
  endtask

  task automatic load1536(
    input logic [31:0] memory [0:1535], output logic [49151:0] bus
  );
    for (int i = 0; i < 1536; i++) bus[i * 32 +: 32] = memory[i];
  endtask

  task automatic load256(
    input logic [31:0] memory [0:255], output logic [49151:0] bus
  );
    begin
      clear1536(bus);
      for (int i = 0; i < 256; i++) bus[i * 32 +: 32] = memory[i];
    end
  endtask

  task automatic check1536(
    input logic [49151:0] bus,
    input logic [31:0] memory [0:1535], input string name
  );
    for (int i = 0; i < 1536; i++)
      if (bus[i * 32 +: 32] !== memory[i])
        $fatal(1, "target QKV node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[i]);
  endtask

  task automatic check512_slice(
    input logic [49151:0] bus,
    input logic [31:0] memory [0:511], input integer offset, input string name
  );
    for (int i = 0; i < 256; i++)
      if (bus[i * 32 +: 32] !== memory[offset + i])
        $fatal(1, "target QKV node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[offset + i]);
  endtask

  task automatic check3072_slice(
    input logic [49151:0] bus,
    input logic [31:0] memory [0:3071], input integer offset, input string name
  );
    for (int i = 0; i < 1536; i++)
      if (bus[i * 32 +: 32] !== memory[offset + i])
        $fatal(1, "target QKV node %s lane=%0d got=%h expected=%h", name, i,
               bus[i * 32 +: 32], memory[offset + i]);
  endtask

  task automatic run_rms1536(
    input logic [49151:0] x, input logic [49151:0] weight,
    output logic [49151:0] y
  );
    integer start;
    begin
      start = cycles;
      @(negedge clk);
      rms_x = x;
      rms_weight = weight;
      rms_epsilon = 32'h358637bd;
      rms_in_valid = 1;
      do @(posedge clk); while (!rms_in_ready);
      @(negedge clk);
      rms_in_valid = 0;
      do @(posedge clk); while (!(rms_out_valid && rms_out_ready));
      @(negedge clk);
      y = rms_y;
      rms_cycles += cycles - start;
    end
  endtask

  task automatic run_gemv(
    input logic [49151:0] x, input integer output_count,
    input integer weight_offset, output logic [49151:0] y
  );
    logic [16383:0] current_accumulator;
    integer start;
    begin
      start = cycles;
      clear1536(y);
      for (int tile = 0; tile < output_count / 32; tile++) begin
        clear512(current_accumulator);
        for (int k = 0; k < 1536; k++) begin
          array_a = '0;
          array_b = '0;
          array_a[15:0] = to_bf16(x[k * 32 +: 32]);
          for (int column = 0; column < 32; column++)
            array_b[column * 16 +: 16] =
              weights[weight_offset + k * output_count + tile * 32 + column];
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
        for (int column = 0; column < 32; column++)
          y[(tile * 32 + column) * 32 +: 32] =
            current_accumulator[column * 32 +: 32];
      end
      matrix_cycles += cycles - start;
    end
  endtask

  task automatic run_qkv_stream(
    input logic [1:0] role,
    input logic [7:0] token,
    input logic [49151:0] raw,
    input logic [49151:0] bias,
    input integer chunks,
    output logic [49151:0] biased,
    output logic [49151:0] expanded
  );
    integer start, replicas;
    logic [15:0] expected_tag;
    begin
      start = cycles;
      expected_tag = {6'd0, token, role};
      clear1536(biased);
      clear1536(expanded);
      for (int chunk = 0; chunk < chunks; chunk++) begin
        @(negedge clk);
        qkv_role_in = role;
        qkv_chunk_in = chunk[6:0];
        qkv_tag_in = expected_tag;
        qkv_data_in = raw[chunk * 512 +: 512];
        qkv_bias_in = bias[chunk * 512 +: 512];
        qkv_in_valid = 1;
        do @(posedge clk); while (!qkv_in_ready);
        @(negedge clk);
        qkv_in_valid = 0;
        replicas = role == 0 ? 1 : 6;
        for (int replica = 0; replica < replicas; replica++) begin
          if (!qkv_out_valid) $fatal(1, "target QKV output missing");
          if (qkv_role_out != role || qkv_chunk_out != chunk[6:0] ||
              qkv_tag_out != expected_tag || qkv_illegal)
            $fatal(1, "target QKV sideband mismatch role=%0d chunk=%0d", role, chunk);
          if (qkv_head_chunk != chunk[2:0] || qkv_last != (chunk[2:0] == 3'd7))
            $fatal(1, "target QKV chunk sideband mismatch");
          if (role == 0) begin
            if (int'(qkv_query_head) != chunk / 8 ||
                qkv_kv_head != (chunk / 8 >= 6))
              $fatal(1, "target Q mapping mismatch chunk=%0d", chunk);
            biased[chunk * 512 +: 512] = qkv_data_out;
          end else begin
            if (int'(qkv_query_head) != (chunk >= 8 ? 6 : 0) + replica ||
                qkv_kv_head != (chunk >= 8))
              $fatal(1, "target GQA mapping mismatch chunk=%0d replica=%0d", chunk, replica);
            if (replica == 0) biased[chunk * 512 +: 512] = qkv_data_out;
            expanded[qkv_query_head * 4096 + qkv_head_chunk * 512 +: 512] = qkv_data_out;
          end
          qkv_flags_or |= qkv_flags;
          qkv_out_ready = 1;
          @(posedge clk);
          @(negedge clk);
          qkv_out_ready = 0;
        end
      end
      qkv_cycles += cycles - start;
    end
  endtask

  initial begin
    logic [49151:0] x_previous, x_current, norm_weight;
    logic [49151:0] norm_previous, norm_current;
    logic [49151:0] q_raw, k_previous_raw, k_current_raw;
    logic [49151:0] v_previous_raw, v_current_raw;
    logic [49151:0] q_bias, k_bias, v_bias;
    logic [49151:0] q_biased, q_expanded;
    logic [49151:0] k_previous_biased, k_current_biased;
    logic [49151:0] v_previous_biased, v_current_biased;
    logic [49151:0] k_previous_gqa, k_current_gqa;
    logic [49151:0] v_previous_gqa, v_current_gqa;

    clk = 0;
    rst_n = 0;
    cycles = 0;
    matrix_cycles = 0;
    rms_cycles = 0;
    qkv_cycles = 0;
    array_in_valid = 0;
    array_out_ready = 1;
    array_a = '0;
    array_b = '0;
    clear512(array_acc);
    matrix_flags_or = '0;
    rms_in_valid = 0;
    rms_out_ready = 1;
    rms_epsilon = '0;
    qkv_in_valid = 0;
    qkv_out_ready = 0;
    qkv_flags_or = '0;

    $readmemh("work/results/l5_target_qkv_segment/vectors/weights_bf16.memh", weights);
    $readmemh("work/results/l5_target_qkv_segment/vectors/x_previous.memh", ex_x_previous);
    $readmemh("work/results/l5_target_qkv_segment/vectors/x_current.memh", ex_x_current);
    $readmemh("work/results/l5_target_qkv_segment/vectors/norm_weight.memh", ex_norm_weight);
    $readmemh("work/results/l5_target_qkv_segment/vectors/norm_previous.memh", ex_norm_previous);
    $readmemh("work/results/l5_target_qkv_segment/vectors/norm_current.memh", ex_norm_current);
    $readmemh("work/results/l5_target_qkv_segment/vectors/q_bias.memh", ex_q_bias);
    $readmemh("work/results/l5_target_qkv_segment/vectors/k_bias.memh", ex_k_bias);
    $readmemh("work/results/l5_target_qkv_segment/vectors/v_bias.memh", ex_v_bias);
    $readmemh("work/results/l5_target_qkv_segment/vectors/q_raw.memh", ex_q_raw);
    $readmemh("work/results/l5_target_qkv_segment/vectors/k_raw.memh", ex_k_raw);
    $readmemh("work/results/l5_target_qkv_segment/vectors/v_raw.memh", ex_v_raw);
    $readmemh("work/results/l5_target_qkv_segment/vectors/q_biased.memh", ex_q_biased);
    $readmemh("work/results/l5_target_qkv_segment/vectors/k_biased.memh", ex_k_biased);
    $readmemh("work/results/l5_target_qkv_segment/vectors/v_biased.memh", ex_v_biased);
    $readmemh("work/results/l5_target_qkv_segment/vectors/k_gqa.memh", ex_k_gqa);
    $readmemh("work/results/l5_target_qkv_segment/vectors/v_gqa.memh", ex_v_gqa);

    repeat (3) @(posedge clk);
    rst_n = 1;
    load1536(ex_x_previous, x_previous);
    load1536(ex_x_current, x_current);
    load1536(ex_norm_weight, norm_weight);
    load1536(ex_q_bias, q_bias);
    load256(ex_k_bias, k_bias);
    load256(ex_v_bias, v_bias);

    run_rms1536(x_previous, norm_weight, norm_previous);
    check1536(norm_previous, ex_norm_previous, "norm_previous");
    run_rms1536(x_current, norm_weight, norm_current);
    check1536(norm_current, ex_norm_current, "norm_current");

    run_gemv(norm_current, 1536, 0, q_raw);
    check1536(q_raw, ex_q_raw, "q_raw");
    run_gemv(norm_previous, 256, 2359296, k_previous_raw);
    check512_slice(k_previous_raw, ex_k_raw, 0, "k_previous_raw");
    run_gemv(norm_current, 256, 2359296, k_current_raw);
    check512_slice(k_current_raw, ex_k_raw, 256, "k_current_raw");
    run_gemv(norm_previous, 256, 2752512, v_previous_raw);
    check512_slice(v_previous_raw, ex_v_raw, 0, "v_previous_raw");
    run_gemv(norm_current, 256, 2752512, v_current_raw);
    check512_slice(v_current_raw, ex_v_raw, 256, "v_current_raw");

    run_qkv_stream(0, 1, q_raw, q_bias, 96, q_biased, q_expanded);
    check1536(q_biased, ex_q_biased, "q_biased");
    run_qkv_stream(1, 0, k_previous_raw, k_bias, 16,
                   k_previous_biased, k_previous_gqa);
    check512_slice(k_previous_biased, ex_k_biased, 0, "k_previous_biased");
    check3072_slice(k_previous_gqa, ex_k_gqa, 0, "k_previous_gqa");
    run_qkv_stream(1, 1, k_current_raw, k_bias, 16,
                   k_current_biased, k_current_gqa);
    check512_slice(k_current_biased, ex_k_biased, 256, "k_current_biased");
    check3072_slice(k_current_gqa, ex_k_gqa, 1536, "k_current_gqa");
    run_qkv_stream(2, 0, v_previous_raw, v_bias, 16,
                   v_previous_biased, v_previous_gqa);
    check512_slice(v_previous_biased, ex_v_biased, 0, "v_previous_biased");
    check3072_slice(v_previous_gqa, ex_v_gqa, 0, "v_previous_gqa");
    run_qkv_stream(2, 1, v_current_raw, v_bias, 16,
                   v_current_biased, v_current_gqa);
    check512_slice(v_current_biased, ex_v_biased, 256, "v_current_biased");
    check3072_slice(v_current_gqa, ex_v_gqa, 1536, "v_current_gqa");

    if (array_accepted != 122880 || array_completed != 122880)
      $fatal(1, "target QKV array steps accepted=%0d completed=%0d",
             array_accepted, array_completed);
    if (rms_accepted != 2 || rms_completed != 2 ||
        qkv_accepted != 160 || qkv_completed != 480 || qkv_illegal_inputs != 0)
      $fatal(1, "target QKV endpoint counters RMS=%0d/%0d QKV=%0d/%0d illegal=%0d",
             rms_accepted, rms_completed, qkv_accepted, qkv_completed,
             qkv_illegal_inputs);
    if (matrix_flags_or[4:1] != 0 || rms_flags[4:1] != 0 || qkv_flags_or[4:1] != 0)
      $fatal(1, "target QKV flags matrix=%h rms=%h qkv=%h",
             matrix_flags_or, rms_flags, qkv_flags_or);
    $display(
      "L5_TARGET_QKV_SEGMENT_PASS tokens=2 hidden=1536 q_width=1536 kv_width=256 array_steps=122880 total_cycles=%0d matrix_cycles=%0d rms_cycles=%0d qkv_cycles=%0d q_fnv64=%016h k0_gqa_fnv64=%016h k1_gqa_fnv64=%016h v0_gqa_fnv64=%016h v1_gqa_fnv64=%016h",
      cycles, matrix_cycles, rms_cycles, qkv_cycles, hash1536(q_biased),
      hash1536(k_previous_gqa), hash1536(k_current_gqa),
      hash1536(v_previous_gqa), hash1536(v_current_gqa)
    );
    $finish;
  end

  initial begin
    repeat (2000000) @(posedge clk);
    $fatal(1, "target QKV segment timeout");
  end
endmodule
