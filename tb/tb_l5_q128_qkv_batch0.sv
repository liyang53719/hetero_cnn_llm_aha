`timescale 1ns/1ps
module tb_l5_q128_qkv_batch0;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  integer cycles, rms_cycles, matrix_cycles, bias_cycles;

  logic rms_in_valid, rms_in_ready, rms_out_valid, rms_out_ready;
  logic [49151:0] rms_x, rms_weight, rms_y;
  logic [31:0] rms_epsilon;
  logic [4:0] rms_flags, rms_flags_or;
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

  logic array_in_valid, array_in_ready, array_out_valid, array_out_ready;
  logic [255:0] array_a;
  logic [511:0] array_b;
  logic [16383:0] array_acc, array_out;
  logic [4:0] array_flags, array_flags_or;
  logic [31:0] array_accepted, array_completed;
  bf16_outer_product_array #(.ROWS(16), .COLS(32)) matrix(
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(array_in_valid), .in_ready_o(array_in_ready),
    .a_i(array_a), .b_i(array_b), .acc_i(array_acc),
    .out_valid_o(array_out_valid), .out_ready_i(array_out_ready),
    .acc_o(array_out), .exception_flags_o(array_flags),
    .accepted_steps_o(array_accepted), .completed_steps_o(array_completed)
  );

  logic [511:0] vector_a, vector_b, vector_out;
  logic [4:0] vector_flags, vector_flags_or;
  fp32_vector_alu #(.LANES(16)) add16(
    .op_i(1'b0), .a_i(vector_a), .b_i(vector_b),
    .out_o(vector_out), .exception_flags_o(vector_flags)
  );

  logic [15:0] weights [0:3145727];
  logic [31:0] norm_weight_mem [0:1535];
  logic [31:0] q_bias [0:1535], k_bias [0:255], v_bias [0:255];
  logic [31:0] in_batch [0:24575], ex_norm [0:24575], ex_q [0:24575];
  logic [31:0] ex_k [0:4095], ex_v [0:4095];
  logic [786431:0] input_bus, norm_bus, q_raw, q_result;
  logic [131071:0] k_raw, v_raw, k_result, v_result;

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

  function automatic [63:0] hash_q(input logic [786431:0] data);
    logic [63:0] value;
    begin
      value = 64'hcbf29ce484222325;
      for (int lane = 0; lane < 24576; lane++)
        value = (value ^ {32'd0, data[lane * 32 +: 32]}) * 64'h100000001b3;
      hash_q = value;
    end
  endfunction

  function automatic [63:0] hash_kv(input logic [131071:0] data);
    logic [63:0] value;
    begin
      value = 64'hcbf29ce484222325;
      for (int lane = 0; lane < 4096; lane++)
        value = (value ^ {32'd0, data[lane * 32 +: 32]}) * 64'h100000001b3;
      hash_kv = value;
    end
  endfunction

  task automatic clear512(output logic [16383:0] bus);
    for (int i = 0; i < 512; i++) bus[i * 32 +: 32] = 32'd0;
  endtask

  task automatic run_rms_batch;
    integer start;
    begin
      start = cycles;
      for (int token = 0; token < 16; token++) begin
        @(negedge clk);
        rms_x = input_bus[token * 49152 +: 49152];
        rms_in_valid = 1;
        do @(posedge clk); while (!rms_in_ready);
        @(negedge clk);
        rms_in_valid = 0;
        do @(posedge clk); while (!(rms_out_valid && rms_out_ready));
        @(negedge clk);
        norm_bus[token * 49152 +: 49152] = rms_y;
        rms_flags_or |= rms_flags;
      end
      rms_cycles += cycles - start;
    end
  endtask

  task automatic run_matrix_batch(
    input integer output_count,
    input integer weight_offset,
    output logic [786431:0] result
  );
    logic [16383:0] current;
    integer start;
    begin
      start = cycles;
      for (int tile = 0; tile < output_count / 32; tile++) begin
        clear512(current);
        for (int k = 0; k < 1536; k++) begin
          for (int row = 0; row < 16; row++)
            array_a[row * 16 +: 16] =
              to_bf16(norm_bus[(row * 1536 + k) * 32 +: 32]);
          for (int column = 0; column < 32; column++)
            array_b[column * 16 +: 16] =
              weights[weight_offset + k * output_count + tile * 32 + column];
          array_acc = current;
          @(negedge clk);
          array_in_valid = 1;
          do @(posedge clk); while (!array_in_ready);
          @(negedge clk);
          array_in_valid = 0;
          do @(posedge clk); while (!(array_out_valid && array_out_ready));
          @(negedge clk);
          current = array_out;
          array_flags_or |= array_flags;
        end
        for (int row = 0; row < 16; row++)
          for (int column = 0; column < 32; column++)
            result[(row * output_count + tile * 32 + column) * 32 +: 32] =
              current[(row * 32 + column) * 32 +: 32];
      end
      matrix_cycles += cycles - start;
    end
  endtask

  task automatic apply_bias_q;
    integer start;
    begin
      start = cycles;
      for (int token = 0; token < 16; token++)
        for (int chunk = 0; chunk < 96; chunk++) begin
          @(negedge clk);
          vector_a = q_raw[(token * 1536 + chunk * 16) * 32 +: 512];
          for (int lane = 0; lane < 16; lane++)
            vector_b[lane * 32 +: 32] = q_bias[chunk * 16 + lane];
          #1;
          q_result[(token * 1536 + chunk * 16) * 32 +: 512] = vector_out;
          vector_flags_or |= vector_flags;
        end
      bias_cycles += cycles - start;
    end
  endtask

  task automatic apply_bias_kv(
    input logic [131071:0] raw,
    input logic choose_v,
    output logic [131071:0] result
  );
    integer start;
    begin
      start = cycles;
      for (int token = 0; token < 16; token++)
        for (int chunk = 0; chunk < 16; chunk++) begin
          @(negedge clk);
          vector_a = raw[(token * 256 + chunk * 16) * 32 +: 512];
          for (int lane = 0; lane < 16; lane++)
            vector_b[lane * 32 +: 32] =
              choose_v ? v_bias[chunk * 16 + lane] : k_bias[chunk * 16 + lane];
          #1;
          result[(token * 256 + chunk * 16) * 32 +: 512] = vector_out;
          vector_flags_or |= vector_flags;
        end
      bias_cycles += cycles - start;
    end
  endtask

  initial begin
    logic [786431:0] matrix_temp;
    clk = 0;
    rst_n = 0;
    cycles = 0;
    rms_cycles = 0;
    matrix_cycles = 0;
    bias_cycles = 0;
    rms_in_valid = 0;
    rms_out_ready = 1;
    rms_epsilon = 32'h358637bd;
    rms_flags_or = '0;
    array_in_valid = 0;
    array_out_ready = 1;
    array_flags_or = '0;
    clear512(array_acc);
    vector_a = '0;
    vector_b = '0;
    vector_flags_or = '0;
    $readmemh("work/results/l5_target_qkv_segment/vectors/weights_bf16.memh", weights);
    $readmemh("work/results/l5_target_qkv_segment/vectors/norm_weight.memh", norm_weight_mem);
    $readmemh("work/results/l5_target_qkv_segment/vectors/q_bias.memh", q_bias);
    $readmemh("work/results/l5_target_qkv_segment/vectors/k_bias.memh", k_bias);
    $readmemh("work/results/l5_target_qkv_segment/vectors/v_bias.memh", v_bias);
    $readmemh("work/results/l5_q128_qkv/batch0/input.memh", in_batch);
    $readmemh("work/results/l5_q128_qkv/batch0/norm.memh", ex_norm);
    $readmemh("work/results/l5_q128_qkv/batch0/q.memh", ex_q);
    $readmemh("work/results/l5_q128_qkv/batch0/k.memh", ex_k);
    $readmemh("work/results/l5_q128_qkv/batch0/v.memh", ex_v);
    for (int i = 0; i < 1536; i++) rms_weight[i * 32 +: 32] = norm_weight_mem[i];
    for (int i = 0; i < 24576; i++) input_bus[i * 32 +: 32] = in_batch[i];
    repeat (3) @(posedge clk);
    rst_n = 1;
    run_rms_batch();
    for (int i = 0; i < 24576; i++)
      if (norm_bus[i * 32 +: 32] !== ex_norm[i])
        $fatal(1, "q128 batch0 norm mismatch lane=%0d", i);
    run_matrix_batch(1536, 0, q_raw);
    apply_bias_q();
    for (int i = 0; i < 24576; i++)
      if (q_result[i * 32 +: 32] !== ex_q[i])
        $fatal(1, "q128 batch0 Q mismatch lane=%0d", i);
    run_matrix_batch(256, 2359296, matrix_temp);
    k_raw = matrix_temp[131071:0];
    apply_bias_kv(k_raw, 0, k_result);
    for (int i = 0; i < 4096; i++)
      if (k_result[i * 32 +: 32] !== ex_k[i])
        $fatal(1, "q128 batch0 K mismatch lane=%0d", i);
    run_matrix_batch(256, 2752512, matrix_temp);
    v_raw = matrix_temp[131071:0];
    apply_bias_kv(v_raw, 1, v_result);
    for (int i = 0; i < 4096; i++)
      if (v_result[i * 32 +: 32] !== ex_v[i])
        $fatal(1, "q128 batch0 V mismatch lane=%0d", i);
    if (array_accepted != 98304 || array_completed != 98304 ||
        rms_accepted != 16 || rms_completed != 16 ||
        array_flags_or[4:1] != 0 || rms_flags_or[4:1] != 0 ||
        vector_flags_or[4:1] != 0)
      $fatal(1, "q128 batch0 accounting array=%0d/%0d rms=%0d/%0d",
             array_accepted, array_completed, rms_accepted, rms_completed);
    $display(
      "L5_Q128_QKV_BATCH0_PASS tokens=0-15 rows=16 array_steps=98304 total_cycles=%0d matrix_cycles=%0d rms_cycles=%0d bias_cycles=%0d q_fnv64=%016h k_fnv64=%016h v_fnv64=%016h",
      cycles, matrix_cycles, rms_cycles, bias_cycles,
      hash_q(q_result), hash_kv(k_result), hash_kv(v_result)
    );
    $finish;
  end

  initial begin
    repeat (600000) @(posedge clk);
    $fatal(1, "q128 QKV batch0 timeout");
  end
endmodule
