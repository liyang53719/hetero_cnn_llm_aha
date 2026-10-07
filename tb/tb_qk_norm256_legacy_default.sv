// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Non-regression guard for the opt-in candidate parameter. The reference is
// the original, hash-pinned RTL fixture, with ONLY its module name changed by
// the runner. No numerical model or candidate arithmetic is used as an oracle.
module tb_qk_norm256_legacy_default;
  parameter integer COUNT = 64;
  logic clk = 0;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n = 0;
  /* verilator lint_on SYNCASYNCNET */
  always #5 clk = ~clk;
  logic iv = 0, ready = 0;
  logic [8191:0] x = '0, w = '0;
  logic [31:0] epsilon = 32'h3727c5ac;
  logic default_ir, default_ov, explicit_ir, explicit_ov, reference_ir, reference_ov;
  logic [8191:0] default_y, explicit_y, reference_y;
  logic [4:0] default_flags, explicit_flags, reference_flags;
  logic [31:0] default_a, default_c, default_rc, default_qc, default_oc;
  logic [31:0] explicit_a, explicit_c, explicit_rc, explicit_qc, explicit_oc;
  logic [31:0] reference_a, reference_c, reference_rc, reference_qc, reference_oc;
  logic unused_default_domain, unused_explicit_domain;
  logic [31:0] unused_default_mean, unused_default_inv, unused_explicit_mean, unused_explicit_inv;
  logic [31:0] rng = 32'h716bc531;
  integer accepted_model = 0, completed_model = 0, cycles = 0, stalls = 0;
  logic held_valid = 0;
  logic [8191:0] held_y;
  logic [4:0] held_flags;

  // Intentionally no parameter override: existing named-port callers continue
  // to select historical arithmetic. The added diagnostic ports are optional.
  fp32_rmsnorm256_chunked dut_default (
    .clk_i(clk), .rst_ni(rst_n), .in_valid_i(iv), .in_ready_o(default_ir),
    .x_i(x), .weight_i(w), .epsilon_i(epsilon),
    .out_valid_o(default_ov), .out_ready_i(ready), .y_o(default_y),
    .exception_flags_o(default_flags), .accepted_o(default_a), .completed_o(default_c),
    .reduction_cycles_o(default_rc), .rsqrt_cycles_o(default_qc), .output_cycles_o(default_oc),
    .domain_error_o(unused_default_domain), .mean_eps_o(unused_default_mean), .inv_o(unused_default_inv)
  );
  fp32_rmsnorm256_chunked #(.QK_CANDIDATE(1'b0)) dut_explicit_zero (
    .clk_i(clk), .rst_ni(rst_n), .in_valid_i(iv), .in_ready_o(explicit_ir),
    .x_i(x), .weight_i(w), .epsilon_i(epsilon),
    .out_valid_o(explicit_ov), .out_ready_i(ready), .y_o(explicit_y),
    .exception_flags_o(explicit_flags), .accepted_o(explicit_a), .completed_o(explicit_c),
    .reduction_cycles_o(explicit_rc), .rsqrt_cycles_o(explicit_qc), .output_cycles_o(explicit_oc),
    .domain_error_o(unused_explicit_domain), .mean_eps_o(unused_explicit_mean), .inv_o(unused_explicit_inv)
  );
  fp32_rmsnorm256_chunked_legacy_reference historical_reference (
    .clk_i(clk), .rst_ni(rst_n), .in_valid_i(iv), .in_ready_o(reference_ir),
    .x_i(x), .weight_i(w), .epsilon_i(epsilon),
    .out_valid_o(reference_ov), .out_ready_i(ready), .y_o(reference_y),
    .exception_flags_o(reference_flags), .accepted_o(reference_a), .completed_o(reference_c),
    .reduction_cycles_o(reference_rc), .rsqrt_cycles_o(reference_qc), .output_cycles_o(reference_oc)
  );

  // Equality is cycle-by-cycle, including historical exception-flag timing and
  // intermediate output writes, rather than checking final rounded lanes only.
  always @(posedge clk) begin
    if (!rst_n) begin
      accepted_model = 0;
      completed_model = 0;
      held_valid = 0;
    end else begin
      cycles = cycles + 1;
      if ({default_ir,default_ov,default_y,default_flags,default_a,default_c,
           default_rc,default_qc,default_oc} !==
          {reference_ir,reference_ov,reference_y,reference_flags,reference_a,reference_c,
           reference_rc,reference_qc,reference_oc})
        $fatal(1, "default legacy behavior changed cycle=%0d transaction=%0d", cycles, completed_model);
      if ({explicit_ir,explicit_ov,explicit_y,explicit_flags,explicit_a,explicit_c,
           explicit_rc,explicit_qc,explicit_oc} !==
          {reference_ir,reference_ov,reference_y,reference_flags,reference_a,reference_c,
           reference_rc,reference_qc,reference_oc})
        $fatal(1, "explicit QK_CANDIDATE=0 behavior changed cycle=%0d", cycles);
      if (default_a !== 32'(accepted_model) || default_c !== 32'(completed_model))
        $fatal(1, "legacy counter accounting failed");
      if (held_valid && (!default_ov || default_y !== held_y || default_flags !== held_flags))
        $fatal(1, "legacy output changed while blocked");
      held_valid = default_ov && !ready;
      if (held_valid) begin
        held_y = default_y;
        held_flags = default_flags;
        stalls = stalls + 1;
      end
      if (iv && default_ir) accepted_model = accepted_model + 1;
      if (default_ov && ready) begin
        if (completed_model >= accepted_model) $fatal(1, "legacy ghost output");
        completed_model = completed_model + 1;
      end
    end
  end

  task automatic next_random(output logic [31:0] value);
    begin
      rng = rng ^ (rng << 13);
      rng = rng ^ (rng >> 17);
      rng = rng ^ (rng << 5);
      value = rng;
    end
  endtask

  task automatic make_vector(input integer index);
    logic [31:0] rx, rw;
    logic [7:0] ex, ew;
    begin
      epsilon = index % 3 == 0 ? 32'h358637bd : 32'h3727c5ac;
      for (integer lane = 0; lane < 256; lane++) begin
        next_random(rx); next_random(rw);
        ex = 8'(110 + int'(rx[7:0]) % 36);
        ew = 8'(110 + int'(rw[7:0]) % 36);
        x[lane*32 +: 32] = {rx[31], ex, rx[22:0]};
        w[lane*32 +: 32] = {rw[31], ew, rw[22:0]};
        case (index)
          0: begin x[lane*32 +: 32]=0; w[lane*32 +: 32]=0; end
          1: begin x[lane*32 +: 32]=32'h3f800000; w[lane*32 +: 32]=32'h3f800000; end
          2: begin x[lane*32 +: 32]=lane%2 == 0 ? 32'h42000000 : 32'hc2000000;
                   w[lane*32 +: 32]=32'h3f000000; end
          3: begin x[lane*32 +: 32]=32'h3a83126f; w[lane*32 +: 32]=32'h3fc00000; end
          4: w[lane*32 +: 32]=32'hbf800000;
          5: begin x[lane*32 +: 32]=lane%2 == 0 ? 32'h00000000 : 32'h80000000;
                   w[lane*32 +: 32]=lane%2 == 0 ? 32'h80000000 : 32'h00000000; end
          6: begin x[lane*32 +: 32]=32'h5f7fffff; w[lane*32 +: 32]=32'h3f800000; end
          7: begin x[lane*32 +: 32]=lane == 255 ? 32'h7fc00001 : 32'h3f800000;
                   w[lane*32 +: 32]=lane == 0 ? 32'h7f800000 : 32'h3f800000; end
          8: begin x[lane*32 +: 32]=32'h00000001; w[lane*32 +: 32]=32'h3f800000; end
          9: begin x[lane*32 +: 32]=32'h7f7fffff; w[lane*32 +: 32]=32'h00800000; end
          default: begin end
        endcase
      end
    end
  endtask

  initial begin : sequence_main
    integer waited;
    if (COUNT < 42) $fatal(1, "legacy regression needs ten directed plus at least 32 random vectors");
    repeat (3) @(negedge clk);
    rst_n = 1;
    for (integer n = 0; n < COUNT; n++) begin
      repeat (n % 3) @(negedge clk);
      make_vector(n); iv = 1; ready = 0;
      do @(posedge clk); while (!default_ir);
      @(negedge clk); iv = 0;
      // Inputs are owned by the bench after acceptance and may change freely.
      x = ~x; w = ~w; epsilon = ~epsilon;
      waited = 0;
      while (!default_ov) begin
        @(negedge clk); waited = waited + 1;
        if (waited > 4096) $fatal(1, "legacy result timeout");
      end
      repeat (2 + n % 7) @(negedge clk);
      ready = 1;
      @(negedge clk); ready = 0;
    end
    ready = 1;
    repeat (512) @(negedge clk);
    if (accepted_model != COUNT || completed_model != COUNT || default_a != COUNT || default_c != COUNT || stalls < COUNT*2)
      $fatal(1, "legacy final count/coverage failed");
    $display("QK_NORM256_LEGACY_DEFAULT_PASS vectors=%0d random=%0d cycles=%0d stalls=%0d default_equals_explicit_zero=1 original_rtl_bitexact=1",
      COUNT, COUNT-10, cycles, stalls);
    $finish;
  end
endmodule
