// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module tb_rope_bf16_candidate;
  parameter integer PIPE = 0;
  parameter integer COUNT = 1;
  parameter integer STALL = 1;
  localparam integer TRACE_WORDS = 25;
  localparam integer TRACE_BITS = TRACE_WORDS * 32;
  localparam integer VECTOR_BITS = (4 + TRACE_WORDS) * 32;
  localparam integer DRAIN_CYCLES = 64;

  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;
  logic iv, ir, ov, ready;
  logic [31:0] even_i, odd_i, cos_i, sin_i;
  logic [15:0] even_o, odd_o;
  logic [4:0] flags;
  logic [31:0] accepted, completed;
  logic [127:0] product_fp32;
  logic [63:0] product_bf16, sum_fp32;
  logic [19:0] mul_flags, product_conversion_flags;
  logic [9:0] add_flags, terminal_conversion_flags;
  logic [VECTOR_BITS-1:0] vectors [0:COUNT-1];
  logic [TRACE_BITS-1:0] trace_words, held_trace;
  logic [127:0] held_input;
  logic held_valid = 0, input_held_valid = 0;
  logic main_phase = 0;
  // ready_mode: 0=blocked, 1=always ready, 2=deterministic stalls.
  integer ready_mode = 0;
  integer cycles = 0, seen = 0, model_accepted = 0, model_completed = 0;
  integer output_file;
  integer main_output_stalls = 0, main_input_stalls = 0;
  integer total_output_stalls = 0, total_input_stalls = 0;
  integer first_accept_cycle = -1, last_accept_cycle = -1;
  integer first_complete_cycle = -1, last_complete_cycle = -1;
  integer acceptance_gap_min = 0, acceptance_gap_max = 0;
  integer completion_gap_min = 0, completion_gap_max = 0;
  integer acceptance_nonunit_gaps = 0, completion_nonunit_gaps = 0;
  integer gap;
  integer blocked_stall_start;
  logic reset_inflight_checked = 0, reset_blocked_checked = 0;
  string vectors_path, outputs_path;

  generate
    if (PIPE == 0) begin : single
      fp32_rope_pair_bf16_candidate dut (
        .clk_i(clk), .rst_ni(rst_n), .in_valid_i(iv), .in_ready_o(ir),
        .even_i, .odd_i, .cos_i, .sin_i,
        .out_valid_o(ov), .out_ready_i(ready), .even_o, .odd_o,
        .exception_flags_o(flags), .accepted_pairs_o(accepted),
        .completed_pairs_o(completed), .product_fp32_o(product_fp32),
        .product_bf16_o(product_bf16), .sum_fp32_o(sum_fp32),
        .mul_flags_o(mul_flags),
        .product_conversion_flags_o(product_conversion_flags),
        .add_flags_o(add_flags),
        .terminal_conversion_flags_o(terminal_conversion_flags)
      );
    end else begin : pipeline
      fp32_rope_pair_bf16_pipe_candidate dut (
        .clk_i(clk), .rst_ni(rst_n), .in_valid_i(iv), .in_ready_o(ir),
        .even_i, .odd_i, .cos_i, .sin_i,
        .out_valid_o(ov), .out_ready_i(ready), .even_o, .odd_o,
        .exception_flags_o(flags), .accepted_pairs_o(accepted),
        .completed_pairs_o(completed), .product_fp32_o(product_fp32),
        .product_bf16_o(product_bf16), .sum_fp32_o(sum_fp32),
        .mul_flags_o(mul_flags),
        .product_conversion_flags_o(product_conversion_flags),
        .add_flags_o(add_flags),
        .terminal_conversion_flags_o(terminal_conversion_flags)
      );
    end
  endgenerate

  assign ready = (ready_mode == 1) ||
    ((ready_mode == 2) && ((cycles % 13) >= 4));

  // BF16 data are widened to binary32 ({bf16,16'b0}); flags are zero
  // extended to 32 bits. Lane order, low to high:
  // products ec/os/es/oc; sums and terminal results even/odd.
  always_comb begin
    trace_words = '0;
    for (integer lane = 0; lane < 4; lane = lane + 1) begin
      trace_words[(0+lane)*32 +: 32] = product_fp32[lane*32 +: 32];
      trace_words[(4+lane)*32 +: 32] = {27'd0, mul_flags[lane*5 +: 5]};
      trace_words[(8+lane)*32 +: 32] = {product_bf16[lane*16 +: 16], 16'd0};
      trace_words[(12+lane)*32 +: 32] =
        {27'd0, product_conversion_flags[lane*5 +: 5]};
    end
    for (integer lane = 0; lane < 2; lane = lane + 1) begin
      trace_words[(16+lane)*32 +: 32] = sum_fp32[lane*32 +: 32];
      trace_words[(18+lane)*32 +: 32] = {27'd0, add_flags[lane*5 +: 5]};
      trace_words[(22+lane)*32 +: 32] =
        {27'd0, terminal_conversion_flags[lane*5 +: 5]};
    end
    trace_words[20*32 +: 32] = {even_o, 16'd0};
    trace_words[21*32 +: 32] = {odd_o, 16'd0};
    trace_words[24*32 +: 32] = {27'd0, flags};
  end

  // Sample handshakes before DUT nonblocking updates. The counter comparison
  // therefore uses the scoreboard totals from the preceding clock edge.
  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      seen = 0;
      model_accepted = 0;
      model_completed = 0;
      held_valid = 0;
      input_held_valid = 0;
      held_trace = '0;
      held_input = '0;
      main_output_stalls = 0;
      main_input_stalls = 0;
      first_accept_cycle = -1;
      last_accept_cycle = -1;
      first_complete_cycle = -1;
      last_complete_cycle = -1;
      acceptance_gap_min = 0;
      acceptance_gap_max = 0;
      completion_gap_min = 0;
      completion_gap_max = 0;
      acceptance_nonunit_gaps = 0;
      completion_nonunit_gaps = 0;
    end else begin
      if (accepted !== model_accepted || completed !== model_completed)
        $fatal(1, "counter mismatch cycle=%0d accepted=%0d/%0d completed=%0d/%0d",
          cycles, accepted, model_accepted, completed, model_completed);
      if (held_valid && (!ov || trace_words !== held_trace))
        $fatal(1, "full output trace changed under backpressure cycle=%0d", cycles);
      if (input_held_valid && (!iv || {sin_i, cos_i, odd_i, even_i} !== held_input))
        $fatal(1, "testbench input changed before acceptance cycle=%0d", cycles);
      held_valid = ov && !ready;
      input_held_valid = iv && !ir;
      if (ov && !ready) begin
        held_trace = trace_words;
        total_output_stalls = total_output_stalls + 1;
        if (main_phase) main_output_stalls = main_output_stalls + 1;
      end
      if (iv && !ir) begin
        held_input = {sin_i, cos_i, odd_i, even_i};
        total_input_stalls = total_input_stalls + 1;
        if (main_phase) main_input_stalls = main_input_stalls + 1;
      end
      if (iv && ir) begin
        model_accepted = model_accepted + 1;
        if (main_phase) begin
          if (model_accepted > COUNT) $fatal(1, "extra input accepted");
          if (first_accept_cycle < 0) first_accept_cycle = cycles;
          if (last_accept_cycle >= 0) begin
            gap = cycles - last_accept_cycle;
            if (acceptance_gap_min == 0 || gap < acceptance_gap_min)
              acceptance_gap_min = gap;
            if (gap > acceptance_gap_max) acceptance_gap_max = gap;
            if (gap != 1) acceptance_nonunit_gaps = acceptance_nonunit_gaps + 1;
          end
          last_accept_cycle = cycles;
        end
      end
      if (ov && ready) begin
        if (model_completed >= model_accepted)
          $fatal(1, "output without an accepted input cycle=%0d", cycles);
        model_completed = model_completed + 1;
        if (!main_phase) $fatal(1, "unexpected output during reset/drain pretest");
        if (seen >= COUNT) $fatal(1, "extra or late output after expected pairs");
        for (integer word_index = 0; word_index < TRACE_WORDS; word_index = word_index + 1) begin
          if (trace_words[word_index*32 +: 32] !==
              vectors[seen][(4+word_index)*32 +: 32])
            $fatal(1, "trace mismatch pipe=%0d pair=%0d word=%0d got=%08h expected=%08h",
              PIPE, seen, word_index, trace_words[word_index*32 +: 32],
              vectors[seen][(4+word_index)*32 +: 32]);
          if (word_index != 0) $fwrite(output_file, " ");
          $fwrite(output_file, "%08h", trace_words[word_index*32 +: 32]);
        end
        $fwrite(output_file, "\n");
        if (first_complete_cycle < 0) first_complete_cycle = cycles;
        if (last_complete_cycle >= 0) begin
          gap = cycles - last_complete_cycle;
          if (completion_gap_min == 0 || gap < completion_gap_min)
            completion_gap_min = gap;
          if (gap > completion_gap_max) completion_gap_max = gap;
          if (gap != 1) completion_nonunit_gaps = completion_nonunit_gaps + 1;
        end
        last_complete_cycle = cycles;
        seen = seen + 1;
      end
      cycles <= cycles + 1;
    end
  end

  task automatic drive_first_pair;
    begin
      @(negedge clk);
      {sin_i, cos_i, odd_i, even_i} = vectors[0][127:0];
      iv = 1;
      do @(posedge clk); while (!ir);
      @(negedge clk);
      iv = 0;
    end
  endtask

  task automatic reset_and_check_flush;
    begin
      // Called on a falling edge, so reset never races a sampled handshake.
      rst_n = 0;
      iv = 0;
      ready_mode = 0;
      repeat (3) @(negedge clk);
      if (ov !== 1'b0 || accepted !== 0 || completed !== 0 || trace_words !== '0)
        $fatal(1, "reset failed to clear output valid and counters");
      rst_n = 1;
      ready_mode = 1;
      // A stale operation must not reappear after reset is released.
      repeat (DRAIN_CYCLES) begin
        @(negedge clk);
        if (ov !== 1'b0 || accepted !== 0 || completed !== 0 || trace_words !== '0)
          $fatal(1, "stale transaction survived reset");
      end
      ready_mode = 0;
    end
  endtask

  initial begin
    iv = 0;
    even_i = 0;
    odd_i = 0;
    cos_i = 0;
    sin_i = 0;
    if (COUNT < 1) $fatal(1, "COUNT must be positive");
    if (PIPE != 0 && PIPE != 1) $fatal(1, "PIPE must be 0 or 1");
    if (STALL != 0 && STALL != 1) $fatal(1, "STALL must be 0 or 1");
    if (!$value$plusargs("VECTORS=%s", vectors_path))
      $fatal(1, "missing +VECTORS=<memory file>");
    if (!$value$plusargs("OUTPUTS=%s", outputs_path))
      $fatal(1, "missing +OUTPUTS=<output file>");
    $readmemh(vectors_path, vectors);
    output_file = $fopen(outputs_path, "w");
    if (!output_file) $fatal(1, "cannot open outputs: %s", outputs_path);
    repeat (3) @(negedge clk);
    rst_n = 1;

    // Reset an accepted operation before completion. For the registered
    // primitive wrapper, also let MISSUE issue the multiply before resetting.
    drive_first_pair();
    if (PIPE) @(negedge clk);
    if (ov !== 1'b0) $fatal(1, "in-flight reset already has a visible output");
    if (accepted !== 1 || completed !== 0)
      $fatal(1, "in-flight reset precondition failed");
    reset_and_check_flush();
    reset_inflight_checked = 1;

    // Build a blocked output, then fill the bounded pipeline behind it. Every
    // visible trace bit must stay stable, even while additional inputs arrive.
    drive_first_pair();
    do @(posedge clk); while (!ov);
    @(negedge clk);
    if (trace_words !== vectors[0][VECTOR_BITS-1:128])
      $fatal(1, "blocked-output pretest trace mismatch");
    blocked_stall_start = total_input_stalls;
    // A different offered pair can expose sidebands accidentally driven by
    // live inputs or a later transaction instead of the blocked output slot.
    if (COUNT > 1)
      {sin_i, cos_i, odd_i, even_i} = vectors[1][127:0];
    else
      even_i = even_i ^ 32'h80000000;
    iv = 1;
    repeat (32) @(negedge clk);
    if (ov !== 1'b1 || completed !== 0 || total_input_stalls == blocked_stall_start)
      $fatal(1, "blocked-output/input-backpressure reset precondition failed");
    reset_and_check_flush();
    reset_blocked_checked = 1;

    // Start measurements from a clean reset. Pretest rows are never written.
    rst_n = 0;
    repeat (3) @(negedge clk);
    if (ov !== 1'b0 || accepted !== 0 || completed !== 0 || trace_words !== '0)
      $fatal(1, "final clean reset failed");
    rst_n = 1;
    main_phase = 1;
    ready_mode = STALL ? 2 : 1;
    for (integer i = 0; i < COUNT; i = i + 1) begin
      @(negedge clk);
      iv = 0;
      if (STALL && i % 17 == 3) repeat (2) @(negedge clk);
      {sin_i, cos_i, odd_i, even_i} = vectors[i][127:0];
      iv = 1;
      do @(posedge clk); while (!ir);
    end
    @(negedge clk);
    iv = 0;
    while (seen < COUNT) @(negedge clk);
    ready_mode = 1;
    repeat (DRAIN_CYCLES) @(negedge clk);
    if (accepted !== COUNT || completed !== COUNT ||
        model_accepted != COUNT || model_completed != COUNT)
      $fatal(1, "final accepted/completed counts do not match COUNT");
    if (!reset_inflight_checked || !reset_blocked_checked || total_output_stalls == 0)
      $fatal(1, "required reset/stall coverage missing");
    if (!STALL && main_output_stalls != 0)
      $fatal(1, "no-stall measurement unexpectedly blocked an output");
    $fclose(output_file);
    $display("ROPE_BF16_CANDIDATE_PASS pipe=%0d pairs=%0d stalls=%0d stall=%0d cycles=%0d first_latency=%0d min_accept_gap=%0d max_accept_gap=%0d min_complete_gap=%0d max_complete_gap=%0d acceptance_nonunit_gaps=%0d completion_nonunit_gaps=%0d first_accept_cycle=%0d last_accept_cycle=%0d first_complete_cycle=%0d last_complete_cycle=%0d transfer_cycles=%0d drain_cycles=%0d input_stalls=%0d reset_checks=%0d reset_inflight=%0d reset_blocked=%0d accepted=%0d completed=%0d",
      PIPE, COUNT, main_output_stalls, STALL, cycles,
      first_complete_cycle - first_accept_cycle,
      acceptance_gap_min, acceptance_gap_max, completion_gap_min, completion_gap_max,
      acceptance_nonunit_gaps, completion_nonunit_gaps,
      first_accept_cycle, last_accept_cycle, first_complete_cycle, last_complete_cycle,
      last_complete_cycle - first_accept_cycle + 1, DRAIN_CYCLES, main_input_stalls,
      int'(reset_inflight_checked) + int'(reset_blocked_checked),
      reset_inflight_checked, reset_blocked_checked, accepted, completed);
    $finish;
  end

  initial begin
    repeat (COUNT * 100 + 5000) @(posedge clk);
    $fatal(1, "timeout pipe=%0d stall=%0d seen=%0d accepted=%0d completed=%0d",
      PIPE, STALL, seen, accepted, completed);
  end
endmodule
