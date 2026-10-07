// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Exact transaction and arithmetic replay for the experimental Q/K producer.
// +VECTORS=<memh> +RECORDS=<n> +TRACE=<text> [+DEBUG=<text>]
// Each vector occupies FIVE 8192-bit hexadecimal lines, low lane first:
//   0 packed input; 1 weights; 2 expected norm; 3 expected gate;
//   4 metadata: tag[31:0], role[33:32], head_dim[49:34], policy[57:50],
//     epsilon[89:58], status[93:90], flags[98:94], mean_eps[130:99],
//     inv[162:131]. Unused high bits must be zero.
// Golden arithmetic is external; this bench contains no numerical model.
// Text trace: kind(R replay/N directed), id(dec), tag, role, status, flags,
// mean_eps, inv, norm(1024 hex), gate(1024 hex). All other fields are hex.
module tb_qk_norm256_bf16_candidate;
  parameter integer MAX_RECORDS = 8192;
  localparam integer MAX_WAIT = 4096;
  localparam integer DRAIN_CYCLES = 512;
  localparam integer PAYLOAD_BITS = 8297; // norm+gate+tag+status+flags+mean+inv

  logic clk = 0;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n = 0;
  /* verilator lint_on SYNCASYNCNET */
  always #5 clk = ~clk;
  logic iv = 0, ir, ov, ready = 0;
  logic [8191:0] packed_data = '0;
  logic [4095:0] weight = '0, norm, gate;
  logic [1:0] role = 0;
  logic [15:0] head_dim = 256;
  logic [7:0] policy = 8'hc1;
  logic [31:0] epsilon = 32'h358637bd, tag = 0, tag_out;
  logic [3:0] status;
  logic [4:0] flags;
  logic [31:0] mean_eps, inv, accepted, completed;
  logic [8191:0] vector_lines [0:MAX_RECORDS*5-1];
  logic [4095:0] expected_norm, expected_gate;
  logic [1:0] expected_role;
  logic [3:0] expected_status;
  logic [4:0] expected_flags;
  logic [31:0] expected_tag, expected_mean, expected_inv;
  logic [PAYLOAD_BITS-1:0] output_payload, held_payload;
  logic held_valid = 0, expect_active = 0, probe_phase = 0;
  integer records, trace_file = 0, debug_file = 0;
  integer cycles = 0, accepted_model = 0, completed_model = 0;
  integer replay_seen = 0, directed_seen = 0, active_id = 0;
  integer output_stalls = 0, busy_valid_cycles = 0, input_mutations = 0;
  integer reset_reduction = 0, reset_rsqrt = 0, reset_output = 0, reset_blocked = 0;
  string vectors_path, trace_path, debug_path, active_kind = "P";

  qk_norm256_bf16_candidate #(.TAG_WIDTH(32)) dut (
    .clk_i(clk), .rst_ni(rst_n), .in_valid_i(iv), .in_ready_o(ir),
    .packed_i(packed_data), .weight_i(weight), .role_i(role),
    .head_dim_i(head_dim), .policy_i(policy), .epsilon_i(epsilon), .tag_i(tag),
    .out_valid_o(ov), .out_ready_i(ready), .norm_o(norm), .gate_o(gate),
    .status_o(status), .tag_o(tag_out), .exception_flags_o(flags),
    .mean_eps_o(mean_eps), .inv_o(inv), .accepted_o(accepted), .completed_o(completed)
  );

  assign output_payload = {norm, gate, tag_out, status, flags, mean_eps, inv};

  // Check handshakes before NBA updates, including every cycle spent stalled.
  always @(posedge clk) begin
    if (!rst_n) begin
      accepted_model = 0;
      completed_model = 0;
      held_valid = 0;
      held_payload = {4096'b0, 4096'b0, 105'b0};
    end else begin
      cycles = cycles + 1;
      if (accepted !== 32'(accepted_model) || completed !== 32'(completed_model))
        $fatal(1, "counter mismatch cycle=%0d accepted=%0d/%0d completed=%0d/%0d",
          cycles, accepted, accepted_model, completed, completed_model);
      if (held_valid && (!ov || output_payload !== held_payload))
        $fatal(1, "output changed under backpressure kind=%s id=%0d", active_kind, active_id);
      if (accepted_model > completed_model && ir)
        $fatal(1, "input ready asserted while previous transaction is outstanding");
      held_valid = ov && !ready;
      if (held_valid) begin
        held_payload = output_payload;
        output_stalls = output_stalls + 1;
      end
      if (iv && !ir) busy_valid_cycles = busy_valid_cycles + 1;
      if (iv && ir) begin
        if (!expect_active) $fatal(1, "unexpected input acceptance");
        accepted_model = accepted_model + 1;
      end
      if (ov && ready) begin
        if (probe_phase || !expect_active || completed_model >= accepted_model)
          $fatal(1, "ghost or duplicate output kind=%s id=%0d", active_kind, active_id);
        if (tag_out !== expected_tag || status !== expected_status ||
            flags !== expected_flags || mean_eps !== expected_mean || inv !== expected_inv)
          $fatal(1, "metadata mismatch kind=%s id=%0d tag=%08h/%08h status=%h/%h flags=%h/%h mean=%08h/%08h inv=%08h/%08h",
            active_kind, active_id, tag_out, expected_tag, status, expected_status,
            flags, expected_flags, mean_eps, expected_mean, inv, expected_inv);
        for (integer lane = 0; lane < 256; lane++) begin
          if (norm[lane*16 +: 16] !== expected_norm[lane*16 +: 16])
            $fatal(1, "norm mismatch kind=%s id=%0d lane=%0d got=%04h expected=%04h",
              active_kind, active_id, lane, norm[lane*16 +: 16], expected_norm[lane*16 +: 16]);
          if (gate[lane*16 +: 16] !== expected_gate[lane*16 +: 16])
            $fatal(1, "gate mismatch kind=%s id=%0d lane=%0d got=%04h expected=%04h",
              active_kind, active_id, lane, gate[lane*16 +: 16], expected_gate[lane*16 +: 16]);
        end
        $fdisplay(trace_file, "%s %0d %08h %h %h %02h %08h %08h %01024h %01024h",
          active_kind, active_id, tag_out, expected_role, status, flags, mean_eps, inv, norm, gate);
        completed_model = completed_model + 1;
        expect_active = 0;
        if (active_kind == "R") replay_seen = replay_seen + 1;
        else directed_seen = directed_seen + 1;
      end

      // Observe actual hardware arithmetic nodes, never force or replace them.
      // C: chunk, red_sum, preceding serial sum, next sum, mean, mean_eps,
      //    square flags(80), reduction/sum/mean/epsilon flags, squares(512).
      if (debug_file != 0 && expect_active && !probe_phase) begin
        if (dut.norm_core.red_ov && dut.norm_core.red_or)
          $fdisplay(debug_file, "C %s %0d %08h %0d %08h %08h %08h %08h %08h %020h %02h %02h %02h %02h %0128h",
            active_kind, active_id, expected_tag, dut.norm_core.chunk,
            dut.norm_core.red_sum, dut.norm_core.sumq, dut.norm_core.sum_next,
            dut.norm_core.mean, dut.norm_core.mean_eps, dut.norm_core.sf,
            dut.norm_core.red_f, dut.norm_core.f_sum, dut.norm_core.f_mean,
            dut.norm_core.f_eps, dut.norm_core.sq);
        // S: captured x, normalized x, scale, LUT index, m,b,mx,y0,y2,
        //    xy2,half,term,y1,scaled, and all eight arithmetic flags(40).
        if (dut.norm_core.rs.iq && dut.norm_core.rs.oready)
          $fdisplay(debug_file, "S %s %0d %08h %08h %08h %08h %02h %08h %08h %08h %08h %08h %08h %08h %08h %08h %08h %010h",
            active_kind, active_id, expected_tag, dut.norm_core.rs.xq,
            dut.norm_core.rs.norm, dut.norm_core.rs.scale, dut.norm_core.rs.index,
            dut.norm_core.rs.m, dut.norm_core.rs.b, dut.norm_core.rs.mx,
            dut.norm_core.rs.y0, dut.norm_core.rs.y2, dut.norm_core.rs.xy2,
            dut.norm_core.rs.half, dut.norm_core.rs.term, dut.norm_core.rs.y1,
            dut.norm_core.rs.scaled, dut.norm_core.rs.flags);
        // O: chunk, gamma(512), gamma flags(80), scaled x(512), y(512),
        //    interleaved scale/output multiplication flags(160).
        if (dut.norm_core.st == 3'd5)
          $fdisplay(debug_file, "O %s %0d %08h %0d %0128h %020h %0128h %0128h %040h",
            active_kind, active_id, expected_tag, dut.norm_core.chunk,
            dut.norm_core.gamma, dut.norm_core.gamma_f, dut.norm_core.scaled,
            dut.norm_core.chunk_out, dut.norm_core.of);
        // Y: actual final FP32 result, before the terminal BF16 conversion.
        if (dut.core_valid && dut.state_q == 2'd2)
          $fdisplay(debug_file, "Y %s %0d %08h %08h %08h %02h %02048h",
            active_kind, active_id, expected_tag, dut.norm_core.mean_eps_q,
            dut.norm_core.invq, dut.core_flags, dut.core_y);
      end
    end
  end

  task automatic load_record(input integer index);
    logic [8191:0] meta;
    begin
      packed_data = vector_lines[index*5];
      weight = vector_lines[index*5+1][4095:0];
      expected_norm = vector_lines[index*5+2][4095:0];
      expected_gate = vector_lines[index*5+3][4095:0];
      meta = vector_lines[index*5+4];
      tag = meta[31:0]; role = meta[33:32]; head_dim = meta[49:34];
      policy = meta[57:50]; epsilon = meta[89:58];
      expected_tag = tag; expected_role = role;
      expected_status = meta[93:90]; expected_flags = meta[98:94];
      expected_mean = meta[130:99]; expected_inv = meta[162:131];
    end
  endtask

  task automatic mutate_inputs;
    begin
      packed_data = ~packed_data;
      weight = ~weight;
      role = ~role;
      head_dim = ~head_dim;
      policy = ~policy;
      epsilon = ~epsilon;
      tag = ~tag;
      input_mutations = input_mutations + 1;
    end
  endtask

  // Caller has loaded the next request at a falling edge. Hold the original
  // fields through its handshake, then mutate EVERY descriptor and data field.
  task automatic accept_current;
    integer waited;
    begin
      expect_active = 1;
      ready = 0;
      iv = 1;
      waited = 0;
      do begin
        @(posedge clk);
        waited = waited + 1;
        if (waited > MAX_WAIT) $fatal(1, "input acceptance timeout");
      end while (!ir);
      @(negedge clk);
      iv = 0;
      mutate_inputs();
    end
  endtask

  task automatic finish_current(input integer hold_cycles);
    integer waited;
    begin
      // Assert a distinct request during busy cycles. It cannot be accepted.
      iv = 1;
      repeat (2) begin
        @(negedge clk);
        if (ir || accepted !== 32'(accepted_model))
          $fatal(1, "busy input was accepted");
      end
      iv = 0;
      waited = 0;
      while (!ov) begin
        @(negedge clk);
        waited = waited + 1;
        if (waited > MAX_WAIT) $fatal(1, "result timeout kind=%s id=%0d", active_kind, active_id);
      end
      repeat (hold_cycles) begin
        @(negedge clk);
        if (!ov || ir) $fatal(1, "blocked output not held");
        mutate_inputs();
      end
      ready = 1;
      @(negedge clk);
      ready = 0;
      if (expect_active || accepted !== 32'(accepted_model) || completed !== 32'(completed_model))
        $fatal(1, "completion/counter handshake failed");
    end
  endtask

  task automatic reject_current(input integer test_id, input logic [3:0] reject_status);
    begin
      active_kind = "N"; active_id = test_id;
      tag = 32'('he0000000 + test_id); expected_tag = tag;
      expected_role = role; expected_status = reject_status;
      expected_norm = '0; expected_gate = '0; expected_flags = '0;
      expected_mean = '0; expected_inv = '0;
      accept_current();
      finish_current(3);
    end
  endtask

  task automatic reset_and_check_flush;
    begin
      // Every call is at a falling edge, away from sampled handshakes.
      rst_n = 0; iv = 0; ready = 0; expect_active = 0;
      repeat (3) @(negedge clk);
      if (ov !== 0 || accepted !== 0 || completed !== 0 || (|output_payload) !== 1'b0)
        $fatal(1, "reset did not clear output and counters");
      rst_n = 1;
      ready = 1;
      repeat (DRAIN_CYCLES) begin
        @(negedge clk);
        if (ov !== 0 || accepted !== 0 || completed !== 0 || (|output_payload) !== 1'b0)
          $fatal(1, "ghost transaction survived reset");
      end
      ready = 0;
    end
  endtask

  task automatic reset_core_phase(input logic [2:0] core_state);
    integer waited;
    begin
      load_record(0); active_kind = "P"; active_id = int'(core_state);
      probe_phase = 1;
      accept_current();
      waited = 0;
      while ((dut.norm_core.st != core_state) ||
             ((core_state == 3'd2 || core_state == 3'd5) && dut.norm_core.chunk != 4'd7)) begin
        @(negedge clk);
        waited = waited + 1;
        if (waited > MAX_WAIT) $fatal(1, "reset phase not reached state=%0d", core_state);
      end
      if (ov || accepted !== 1 || completed !== 0)
        $fatal(1, "in-flight reset precondition failed state=%0d", core_state);
      reset_and_check_flush();
      probe_phase = 0;
      // Each reset must recover through a complete, checked transaction.
      load_record(0); active_kind = "N"; active_id = 900 + int'(core_state);
      accept_current(); finish_current(2);
      reset_and_check_flush();
    end
  endtask

  function automatic logic [15:0] gate_pattern(input integer lane);
    case (lane % 16)
      0: gate_pattern=16'h0000; 1: gate_pattern=16'h8000;
      2: gate_pattern=16'h0001; 3: gate_pattern=16'h807f;
      4: gate_pattern=16'h0080; 5: gate_pattern=16'h8080;
      6: gate_pattern=16'h7f7f; 7: gate_pattern=16'hff7f;
      8: gate_pattern=16'h7f80; 9: gate_pattern=16'hff80;
      10: gate_pattern=16'h7f81; 11: gate_pattern=16'hff81;
      12: gate_pattern=16'h7fc0; 13: gate_pattern=16'hffc1;
      14: gate_pattern=16'h3f80; default: gate_pattern=16'hbf80;
    endcase
  endfunction

  initial begin : test_sequence
    integer n, case_id;
    logic [15:0] bad_operand;
    if (!$value$plusargs("VECTORS=%s", vectors_path)) $fatal(1, "missing +VECTORS");
    if (!$value$plusargs("RECORDS=%d", records)) records = 5120;
    if (!$value$plusargs("TRACE=%s", trace_path)) $fatal(1, "missing +TRACE");
    if (records < 1 || records > MAX_RECORDS) $fatal(1, "invalid record count=%0d", records);
    $readmemh(vectors_path, vector_lines, 0, records*5-1);
    trace_file = $fopen(trace_path, "w");
    if (trace_file == 0) $fatal(1, "cannot open trace");
    if ($value$plusargs("DEBUG=%s", debug_path)) begin
      debug_file = $fopen(debug_path, "w");
      if (debug_file == 0) $fatal(1, "cannot open debug trace");
    end
    repeat (3) @(negedge clk);
    rst_n = 1;
    load_record(0);
    if (expected_status != 0) $fatal(1, "record zero must be a valid reset/recovery seed");

    reset_core_phase(3'd2); reset_reduction = 1;
    reset_core_phase(3'd4); reset_rsqrt = 1;
    reset_core_phase(3'd5); reset_output = 1;
    load_record(0); active_kind = "P"; active_id = 99; probe_phase = 1;
    accept_current();
    n = 0;
    while (!ov) begin
      @(negedge clk); n = n + 1;
      if (n > MAX_WAIT) $fatal(1, "blocked-reset timeout");
    end
    // A blocked result must have survived at least two rising edges first.
    repeat (3) @(negedge clk);
    if (!ov || accepted !== 1 || completed !== 0) $fatal(1, "blocked-reset precondition");
    reset_and_check_flush(); reset_blocked = 1; probe_phase = 0;
    load_record(0); active_kind = "N"; active_id = 999;
    accept_current(); finish_current(2);
    reset_and_check_flush();

    // Frozen replay retains file order. Distinct bubbles and result holds are
    // deterministic and do not depend on the implementation's compute latency.
    for (n = 0; n < records; n++) begin
      repeat (n % 4) @(negedge clk);
      load_record(n); active_kind = "R"; active_id = n;
      accept_current(); finish_current(2 + n % 5);
    end
    if (replay_seen != records) $fatal(1, "replay count mismatch");

    // Alternate Q/K while exercising every gate encoding class, including
    // infinities, signaling/quiet NaNs and subnormals. Arithmetic is unchanged.
    for (n = 0; n < 8; n++) begin
      load_record(0); active_kind = "N"; active_id = 1000 + n;
      role = 2'(n % 2); expected_role = role;
      tag = 32'('hd0000000 + n); expected_tag = tag;
      for (integer lane = 0; lane < 256; lane++)
        packed_data[4096+lane*16 +: 16] = gate_pattern(lane+n);
      expected_gate = role == 0 ? packed_data[8191:4096] : 4096'b0;
      accept_current(); finish_current(3);
    end

    case_id = 0;
    // No partial head or tail is silently normalized.
    for (n = 0; n < 6; n++) begin
      load_record(0);
      case (n)
        0: head_dim=0; 1: head_dim=1; 2: head_dim=255;
        3: head_dim=257; 4: head_dim=512; default: head_dim=16'hffff;
      endcase
      reject_current(case_id, 4'd1); case_id = case_id + 1;
    end
    for (n = 2; n < 4; n++) begin
      load_record(0); role = 2'(n);
      reject_current(case_id, 4'd1); case_id = case_id + 1;
    end
    for (n = 0; n < 4; n++) begin
      load_record(0);
      case (n)
        0: policy=0; 1: policy=8'hc0; 2: policy=8'hc2; default: policy=8'hff;
      endcase
      reject_current(case_id, 4'd1); case_id = case_id + 1;
    end
    for (n = 0; n < 6; n++) begin
      load_record(0);
      case (n)
        0: epsilon=0; 1: epsilon=32'h80000000; 2: epsilon=32'h358637bc;
        3: epsilon=32'h358637be; 4: epsilon=32'h7f800000; default: epsilon=32'h7fc00000;
      endcase
      reject_current(case_id, 4'd1); case_id = case_id + 1;
    end
    // Both arithmetic vectors and both ends of the head are validated.
    for (n = 0; n < 12; n++) begin
      load_record(0);
      case (n % 6)
        0: bad_operand=16'h7f80; 1: bad_operand=16'hff80;
        2: bad_operand=16'h7f81; 3: bad_operand=16'hff81;
        4: bad_operand=16'h7fc0; default: bad_operand=16'hffc1;
      endcase
      if (n < 6) packed_data[(n%2 == 0 ? 0 : 255)*16 +: 16] = bad_operand;
      else weight[(n%2 == 0 ? 0 : 255)*16 +: 16] = bad_operand;
      reject_current(case_id, 4'd2); case_id = case_id + 1;
    end
    for (n = 0; n < 16; n++) begin
      load_record(0);
      case (n % 8)
        0: bad_operand=16'h0001; 1: bad_operand=16'h807f;
        2: bad_operand=16'h0080; 3: bad_operand=16'h2f7f;
        4: bad_operand=16'haf7f; 5: bad_operand=16'h4f80;
        6: bad_operand=16'hcf80; default: bad_operand=16'h7f7f;
      endcase
      if (n < 8) packed_data[(n%2 == 0 ? 1 : 254)*16 +: 16] = bad_operand;
      else weight[(n%2 == 0 ? 1 : 254)*16 +: 16] = bad_operand;
      reject_current(case_id, 4'd3); case_id = case_id + 1;
    end
    // Error priority is descriptor > nonfinite > unsupported finite.
    load_record(0); head_dim=255; packed_data[15:0]=16'h7fc0; weight[15:0]=16'h0001;
    reject_current(case_id, 4'd1); case_id = case_id + 1;
    load_record(0); packed_data[15:0]=16'h0001; weight[4095 -: 16]=16'h7f80;
    reject_current(case_id, 4'd2); case_id = case_id + 1;

    iv = 0; ready = 1;
    repeat (DRAIN_CYCLES) @(negedge clk);
    if (accepted !== completed || accepted !== 32'(records + 8 + case_id))
      $fatal(1, "final transaction accounting mismatch");
    if (busy_valid_cycles == 0 || output_stalls < records*2 || input_mutations < records)
      $fatal(1, "protocol stimulus coverage was not exercised");
    $fclose(trace_file);
    if (debug_file != 0) $fclose(debug_file);
    $display("QK_NORM256_BF16_CANDIDATE_PASS replay=%0d directed=%0d rejected=%0d accepted=%0d completed=%0d stalls=%0d busy_valid=%0d mutations=%0d reset_reduction=%0d reset_rsqrt=%0d reset_output=%0d reset_blocked=%0d cycles=%0d",
      replay_seen, directed_seen, case_id, accepted, completed, output_stalls,
      busy_valid_cycles, input_mutations, reset_reduction, reset_rsqrt,
      reset_output, reset_blocked, cycles);
    $finish;
  end
endmodule
