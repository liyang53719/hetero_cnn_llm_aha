// SPDX-License-Identifier: Apache-2.0
// Actual shared_l2_fabric transport proof for the opt-in BF16 RoPE consumer.
// No testbench memory substitutes and no hierarchical memory writes are used.
// Vector record: 35 x 512-bit words. Metadata heads[7:0], output byte
// offset[15:8], ORed flags[23:16], in-place/overlap[24]; source[1:16],
// cos/sin[17:18], expected output[19:34]. Unused head slots are ignored.
`timescale 1ns/1ps
module tb_rope_bf16_l2_candidate;
  parameter integer COUNT = 1;
  parameter integer MODE = 1; // 0: instantiate the unmodified default parameter.
  parameter integer STALL = 1;
  localparam integer ADDR_W = 10;
  localparam integer BEATS = 1 << ADDR_W;
  localparam integer BYTES = BEATS * 64;
  localparam integer RECORD_WORDS = 35;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  logic start = 0, ready, done, bad;
  logic [5:0] beats_i;
  logic [9:0] heads_i, dim_i, rotary_i;
  logic [7:0] policy_i;
  logic [3:0] lane_i;
  logic [63:0] data_i, position_i, out_i, trig_i;
  logic rv, rr, rsv, rsr, wv, wr;
  logic [ADDR_W-1:0] ra, wa;
  logic [511:0] rd, wd;
  logic [63:0] be;
  logic [31:0] reads, writes, pairs, position, steps;
  logic [4:0] flags;
  logic [1:0] frv, frr, frsv, frsr;
  logic [2*ADDR_W-1:0] fra;
  logic [1023:0] frd;
  logic fwv, fwr;
  logic [ADDR_W-1:0] fwa;
  logic [511:0] fwd;
  logic [63:0] fbe;
  logic [63:0] fabric_cycles, fabric_reads, fabric_writes;
  logic [63:0] fabric_conflicts, fabric_rstall, fabric_wstall;
  logic host_mode = 1;
  logic hrv = 0, hrsr = 0, hwv = 0;
  logic [ADDR_W-1:0] hra = 0, hwa = 0;
  logic [511:0] hwd = 0;
  logic [63:0] hbe = 0;
  logic force_rsp_block = 0, force_wr_block = 0;
  logic force_open = 0, rsp_delivery_held = 0;
  logic req_gate, rsp_gate, write_gate;
  integer cycle = 0;
  logic candidate_pair_accept, candidate_pair_complete;
  integer model_pair_complete = 0, model_pair_accept = 0;

`define ROPE_PORTS \
    .clk_i(clk), .rst_ni(rst_n), .start_i(start), \
    .data_beats_i(beats_i), .heads_i(heads_i), .head_dim_i(dim_i), \
    .position_lane_i(lane_i), .data_local_i(data_i), \
    .position_local_i(position_i), .out_local_i(out_i), \
    .candidate_trig_local_i(trig_i), .candidate_rotary_dim_i(rotary_i), \
    .candidate_policy_i(policy_i), .ready_o(ready), \
    .l2_rd_valid_o(rv), .l2_rd_ready_i(rr), .l2_rd_addr_o(ra), \
    .l2_rsp_valid_i(rsv), .l2_rsp_ready_o(rsr), .l2_rsp_data_i(rd), \
    .l2_wr_valid_o(wv), .l2_wr_ready_i(wr), .l2_wr_addr_o(wa), \
    .l2_wr_data_o(wd), .l2_wr_be_o(be), .done_o(done), \
    .unsupported_position_o(bad), .read_beats_o(reads), \
    .write_beats_o(writes), .pairs_o(pairs), .position_o(position), \
    .coefficient_steps_o(steps), .exception_flags_o(flags)
  generate
    if (MODE == 0) begin : default_off
      qwen2_shared_l2_rope_payload #(.ADDR_W(ADDR_W)) dut (`ROPE_PORTS);
      assign candidate_pair_accept = 0;
      assign candidate_pair_complete = 0;
    end else begin : candidate_on
      qwen2_shared_l2_rope_payload #(
        .ADDR_W(ADDR_W), .EXPERIMENTAL_BF16_ROPE(1)
      ) dut (`ROPE_PORTS);
      assign candidate_pair_accept = dut.g_candidate.candidate.pair_in_valid && dut.g_candidate.candidate.pair_in_ready;
      assign candidate_pair_complete = dut.g_candidate.candidate.pair_out_valid && dut.g_candidate.candidate.pair_out_ready;
    end
  endgenerate
`undef ROPE_PORTS

  shared_l2_fabric #(.ADDR_W(ADDR_W), .ROWS_PER_BANK(256)) fabric (
    .clk_i(clk), .rst_ni(rst_n), .rd_valid_i(frv), .rd_ready_o(frr),
    .rd_addr_i(fra), .rd_resp_valid_o(frsv), .rd_resp_ready_i(frsr),
    .rd_data_o(frd), .wr_valid_i(fwv), .wr_ready_o(fwr),
    .wr_addr_i(fwa), .wr_data_i(fwd), .wr_be_i(fbe),
    .cycle_count_o(fabric_cycles), .read_count_o(fabric_reads),
    .write_count_o(fabric_writes), .bank_conflict_count_o(fabric_conflicts),
    .read_stall_count_o(fabric_rstall), .write_stall_count_o(fabric_wstall)
  );

  assign req_gate = !STALL || force_open || (cycle % 7 >= 2);
  assign write_gate = !force_wr_block &&
    (!STALL || force_open || (cycle % 11 >= 4));
  // Delayed responses remain in the real fabric's valid/ready register.
  // Once offered, valid cannot be retracted while its consumer is blocked.
  assign rsp_gate = !force_rsp_block &&
    (rsp_delivery_held || !STALL || force_open || (cycle % 9 >= 3));
  always_comb begin
    frv = '0; fra = '0; frsr = '0;
    fwv = 0; fwa = '0; fwd = '0; fbe = '0;
    rr = 0; rsv = 0; rd = frd[511:0]; wr = 0;
    if (host_mode) begin
      frv[0] = hrv; fra[0 +: ADDR_W] = hra; frsr[0] = hrsr;
      fwv = hwv; fwa = hwa; fwd = hwd; fbe = hbe;
    end else begin
      frv[0] = rv && req_gate;
      fra[0 +: ADDR_W] = ra;
      rr = frr[0] && req_gate;
      rsv = frsv[0] && rsp_gate;
      frsr[0] = rsr && rsp_gate;
      fwv = wv && write_gate;
      fwa = wa; fwd = wd; fbe = be;
      wr = fwr && write_gate;
    end
  end

  logic [511:0] vectors [0:COUNT*RECORD_WORDS-1];
  logic [511:0] input_beats [0:15];
  logic [511:0] expected_beats [0:15];
  logic [511:0] trig_beats [0:1];
  byte unsigned expected_memory [0:BYTES-1];
  byte unsigned observed_memory [0:BYTES-1];
  bit touched [0:BEATS-1];
  integer source_base, trig_base, destination_base;
  integer expect_heads, expect_bytes, expect_reads, expect_writes, expect_pairs;
  logic [4:0] expect_flags;
  integer transaction = -1, scoreboard_reads = 0, scoreboard_responses = 0;
  integer scoreboard_writes = 0, completions = 0, last_write_cycle = -1;
  integer last_pairs = 0, start_cycle = 0;
  bit active = 0, launched = 0, reject = 0;
  bit read_held = 0, write_held = 0, response_held = 0;
  logic [ADDR_W-1:0] held_ra, held_wa;
  logic [511:0] held_wd, held_rd;
  logic [63:0] held_be;
  longint unsigned fabric_model_reads = 0, fabric_model_writes = 0;
  longint unsigned successful = 0, main_successful = 0, rejected = 0;
  longint unsigned reset_cases = 0, masked_packets = 0, readback_bytes = 0;
  longint unsigned total_read_stalls = 0, total_write_stalls = 0;
  longint unsigned total_response_stalls = 0, completed_pair_total = 0;
  longint unsigned main_pair_total = 0, main_tail_elements = 0;
  logic [31:0] offset_coverage = 0;
  integer output_file;
  string vectors_path, outputs_path;

  // Scoreboard uses only public interfaces, including the fabric's counters.
  // Counter values at this edge must describe all preceding accepted edges.
  always @(posedge clk) begin : scoreboard
    integer expected_address, byte_address, expected_byte, n;
    logic [63:0] expected_mask;
    logic [511:0] expected_response;
    if (!rst_n) begin
      cycle <= 0;
      model_pair_complete = 0; model_pair_accept = 0;
      read_held = 0; write_held = 0; response_held = 0;
      rsp_delivery_held = 0;
      fabric_model_reads = 0; fabric_model_writes = 0;
      launched = 0;
    end else begin
      cycle <= cycle + 1;
      if (fabric_reads !== fabric_model_reads || fabric_writes !== fabric_model_writes)
        $fatal(1, "fabric counter/handshake mismatch cycle=%0d r=%0d/%0d w=%0d/%0d",
          cycle, fabric_reads, fabric_model_reads, fabric_writes, fabric_model_writes);
      fabric_model_reads += (frv[0] && frr[0]) + (frv[1] && frr[1]);
      fabric_model_writes += fwv && fwr;
      if (!host_mode) begin
        if (frsv[0] && rsp_gate && !rsr) rsp_delivery_held = 1;
        if (frsv[0] && frsr[0]) rsp_delivery_held = 0;
      end
      if (host_mode && (rv || wv || done))
        $fatal(1, "DUT activity while host owns the idle fabric txn=%0d", transaction);
      if (response_held && (!frsv[0] || frd[511:0] !== held_rd))
        $fatal(1, "real fabric response changed while held txn=%0d", transaction);
      response_held = frsv[0] && !frsr[0];
      if (response_held) held_rd = frd[511:0];
      if (read_held && (!rv || ra !== held_ra))
        $fatal(1, "DUT read request changed under backpressure txn=%0d", transaction);
      if (write_held && (!wv || wa !== held_wa || wd !== held_wd || be !== held_be))
        $fatal(1, "DUT write address/data/mask changed under backpressure txn=%0d", transaction);
      read_held = !host_mode && rv && !rr;
      write_held = !host_mode && wv && !wr;
      if (read_held) held_ra = ra;
      if (write_held) begin held_wa = wa; held_wd = wd; held_be = be; end
      if (!active && (candidate_pair_accept || candidate_pair_complete))
        $fatal(1, "late arithmetic handshake outside a transaction");
      if (!active && !host_mode && (rv || wv || done || rsv))
        $fatal(1, "unexpected or post-completion I/O txn=%0d", transaction);
      if (active && start && ready) begin
        if (launched) $fatal(1, "busy start was accepted txn=%0d", transaction);
        launched = 1; start_cycle = cycle;
        scoreboard_reads = 0; scoreboard_responses = 0; scoreboard_writes = 0;
        completions = 0; last_pairs = 0; last_write_cycle = -1;
        model_pair_complete = 0; model_pair_accept = 0;
      end else if (active && launched) begin
        if (cycle - start_cycle > 20000) $fatal(1, "transaction timed out txn=%0d", transaction);
        if (MODE != 0) begin
          if (reads !== scoreboard_reads || writes !== scoreboard_writes)
            $fatal(1, "candidate counters not accepted transfers txn=%0d reads=%0d/%0d writes=%0d/%0d",
              transaction, reads, scoreboard_reads, writes, scoreboard_writes);
          if (pairs !== model_pair_complete)
            $fatal(1, "pair counter does not count real completed handshakes txn=%0d", transaction);
          if (candidate_pair_accept) model_pair_accept++;
          if (candidate_pair_complete) model_pair_complete++;
          if (model_pair_complete > model_pair_accept) $fatal(1, "pair completed without acceptance");
          if (pairs < last_pairs || pairs > last_pairs + 1 || pairs > expect_pairs)
            $fatal(1, "completed-pair counter jumped txn=%0d pairs=%0d old=%0d", transaction, pairs, last_pairs);
          if (pairs > 0 && scoreboard_responses != expect_reads)
            $fatal(1, "pair completed before source/trig responses txn=%0d", transaction);
          last_pairs = pairs;
        end
        if (completions == 0 && ready)
          $fatal(1, "ready asserted while transaction busy txn=%0d", transaction);
        if (read_held) total_read_stalls++;
        if (write_held) total_write_stalls++;
        if (frsv[0] && !frsr[0]) total_response_stalls++;
        if (rv && rr) begin
          if (reject || scoreboard_reads >= expect_reads)
            $fatal(1, "rejected/extra read txn=%0d read=%0d", transaction, scoreboard_reads);
          if (scoreboard_reads < expect_heads * (MODE == 0 ? 4 : 8))
            expected_address = source_base/64 + scoreboard_reads;
          else
            expected_address = trig_base/64 + scoreboard_reads - expect_heads*(MODE == 0 ? 4 : 8);
          if (ra != expected_address)
            $fatal(1, "read address mismatch txn=%0d index=%0d got=%h expected=%h",
              transaction, scoreboard_reads, ra, expected_address);
          if (scoreboard_writes != 0) $fatal(1, "read after writing txn=%0d", transaction);
          scoreboard_reads++;
        end
        if (rsv && rsr) begin
          if (reject || scoreboard_responses >= scoreboard_reads)
            $fatal(1, "unrequested response txn=%0d", transaction);
          if (scoreboard_responses < expect_heads * (MODE == 0 ? 4 : 8))
            expected_response = input_beats[scoreboard_responses];
          else
            expected_response = trig_beats[scoreboard_responses-expect_heads*(MODE == 0 ? 4 : 8)];
          if (rd !== expected_response)
            $fatal(1, "fabric response payload mismatch txn=%0d index=%0d", transaction, scoreboard_responses);
          scoreboard_responses++;
        end
        if (wv && wr) begin
          if (reject || scoreboard_writes >= expect_writes)
            $fatal(1, "rejected/extra write txn=%0d index=%0d", transaction, scoreboard_writes);
          if (scoreboard_reads != expect_reads || scoreboard_responses != expect_reads || pairs != expect_pairs)
            $fatal(1, "write before all reads/pairs complete txn=%0d", transaction);
          expected_address = destination_base/64 + scoreboard_writes;
          if (wa != expected_address)
            $fatal(1, "write address mismatch txn=%0d index=%0d got=%h expected=%h",
              transaction, scoreboard_writes, wa, expected_address);
          expected_mask = 0;
          for (n=0; n<64; n++) begin
            byte_address = expected_address*64 + n;
            if (byte_address >= destination_base && byte_address < destination_base+expect_bytes) begin
              expected_mask[n] = 1;
              expected_byte = expected_memory[byte_address];
              if (wd[n*8 +: 8] !== 8'(expected_byte))
                $fatal(1, "store byte mismatch txn=%0d packet=%0d byte=%0d got=%h expected=%h",
                  transaction, scoreboard_writes, byte_address, wd[n*8 +: 8], expected_byte);
            end
          end
          if (be !== expected_mask || be == 0)
            $fatal(1, "write byte mask mismatch txn=%0d got=%h expected=%h", transaction, be, expected_mask);
          for (n=0; n<32; n++)
            if (be[n*2 +: 2] != 2'b00 && be[n*2 +: 2] != 2'b11)
              $fatal(1, "torn BF16 byte enable txn=%0d lane=%0d", transaction, n);
          for (n=0; n<64; n++) if (be[n]) observed_memory[wa*64+n] = wd[n*8 +: 8];
          $fwrite(output_file, "W %0d %03h %016h %0128h\n", transaction, wa, be, wd);
          scoreboard_writes++; masked_packets++; last_write_cycle = cycle;
        end
        if (done) begin
          if (completions != 0) $fatal(1, "more than one completion txn=%0d", transaction);
          if (reject) begin
            if (!bad || scoreboard_reads || scoreboard_writes || pairs || flags || steps)
              $fatal(1, "rejection was not fail-closed txn=%0d", transaction);
          end else begin
            if (bad || scoreboard_reads != expect_reads || scoreboard_responses != expect_reads ||
                scoreboard_writes != expect_writes || pairs != expect_pairs || flags !== expect_flags)
              $fatal(1, "completion mismatch txn=%0d bad=%0d reads=%0d writes=%0d pairs=%0d flags=%h expected=%h",
                transaction, bad, reads, writes, pairs, flags, expect_flags);
            if (cycle != last_write_cycle + 1)
              $fatal(1, "done not one cycle after final accepted write txn=%0d", transaction);
            if (steps != 0 || position != 0)
              $fatal(1, "unexpected position/coefficient activity txn=%0d", transaction);
          end
          completions++;
          $fwrite(output_file, "D %0d %0d %0d %0d %0d\n", transaction, reads, pairs, writes, flags);
        end
      end
    end
  end

  task automatic host_write(input integer address, input logic [511:0] payload);
    begin
      if (!host_mode || !ready) $fatal(1, "host write requires idle DUT");
      @(negedge clk); hwa = ADDR_W'(address); hwd = payload; hbe = '1; hwv = 1;
      do @(posedge clk); while (!fwr);
      @(negedge clk); hwv = 0;
      for (integer b=0; b<64; b++) begin
        expected_memory[address*64+b] = payload[b*8 +: 8];
        observed_memory[address*64+b] = payload[b*8 +: 8];
      end
      touched[address] = 1;
    end
  endtask

  task automatic host_read(input integer address, output logic [511:0] payload);
    begin
      if (!host_mode || !ready) $fatal(1, "host read requires idle DUT");
      @(negedge clk); hra = ADDR_W'(address); hrv = 1; hrsr = 0;
      do @(posedge clk); while (!frr[0]);
      @(negedge clk); hrv = 0; hrsr = 1;
      do @(posedge clk); while (!frsv[0]);
      payload = frd[511:0];
      @(negedge clk); hrsr = 0;
    end
  endtask

  task automatic poison_range(input integer first, input integer last);
    logic [511:0] poison;
    begin
      for (integer a=first; a<=last; a++) if (a>=0 && a<BEATS) begin
        for (integer b=0; b<64; b++)
          poison[b*8 +: 8] = 8'((a*17) ^ (b*13) ^ 8'ha7);
        host_write(a, poison);
      end
    end
  endtask

  task automatic load_record(input integer record_index);
    begin
      expect_heads = vectors[record_index*RECORD_WORDS][7:0];
      if (expect_heads < 1 || expect_heads > 2) $fatal(1, "bad vector heads");
      expect_flags = vectors[record_index*RECORD_WORDS][20:16];
      for (integer b=0; b<16; b++) begin
        input_beats[b] = vectors[record_index*RECORD_WORDS+1+b];
        expected_beats[b] = vectors[record_index*RECORD_WORDS+19+b];
      end
      trig_beats[0] = vectors[record_index*RECORD_WORDS+17];
      trig_beats[1] = vectors[record_index*RECORD_WORDS+18];
      source_base = 'h1000; trig_base = 'h2000;
      destination_base = (vectors[record_index*RECORD_WORDS][24] ? source_base : 'h3000)
        + int'(vectors[record_index*RECORD_WORDS][15:8]);
      if ((destination_base & 1) || (destination_base & 63)>62)
        $fatal(1, "invalid vector output offset");
    end
  endtask

  task automatic prepare_memory;
    integer tensor_beats;
    begin
      if (!ready) $fatal(1, "prepare while busy");
      host_mode = 1;
      tensor_beats = expect_heads * (MODE == 0 ? 4 : 8);
      expect_bytes = tensor_beats*64;
      expect_reads = tensor_beats + (MODE == 0 ? 1 : 2);
      expect_pairs = expect_heads * (MODE == 0 ? 64 : 32);
      expect_writes = tensor_beats + ((destination_base & 63) != 0);
      for (integer b=0; b<BEATS; b++) touched[b] = 0;
      poison_range(source_base/64-1, source_base/64+tensor_beats);
      poison_range(trig_base/64-1, trig_base/64+(MODE == 0 ? 1 : 2));
      poison_range(destination_base/64-1, (destination_base+expect_bytes-1)/64+1);
      // Source data are loaded after poison, so overlap reads have genuine
      // source bytes rather than the eventual expected output.
      for (integer b=0; b<tensor_beats; b++) host_write(source_base/64+b, input_beats[b]);
      host_write(trig_base/64, trig_beats[0]);
      if (MODE != 0) host_write(trig_base/64+1, trig_beats[1]);
      for (integer b=0; b<expect_bytes; b++)
        expected_memory[destination_base+b] = expected_beats[b/64][(b%64)*8 +: 8];
      data_i = 64'(source_base); trig_i = 64'(trig_base);
      position_i = 64'(trig_base); out_i = 64'(destination_base);
      beats_i = 6'(tensor_beats); heads_i = 10'(expect_heads);
      dim_i = MODE == 0 ? 128 : 256; rotary_i = 64;
      policy_i = MODE == 0 ? 8'h00 : 8'hb1; lane_i = 0;
    end
  endtask

  task automatic readback;
    logic [511:0] actual;
    begin
      host_mode = 1;
      for (integer a=0; a<BEATS; a++) if (touched[a]) begin
        host_read(a, actual);
        for (integer b=0; b<64; b++) begin
          if (actual[b*8 +: 8] !== expected_memory[a*64+b])
            $fatal(1, "readback/poison mismatch txn=%0d byte=%0d got=%h expected=%h",
              transaction, a*64+b, actual[b*8 +: 8], expected_memory[a*64+b]);
          readback_bytes++;
        end
      end
    end
  endtask

  task automatic launch(input bit bad_config);
    begin
      repeat ((transaction & 3)+1) @(negedge clk); // deterministic input bubbles
      if (!ready || done || frsv[0]) $fatal(1, "not cleanly idle before start txn=%0d", transaction);
      host_mode = 0; active = 1; launched = 0; reject = bad_config;
      @(negedge clk); start = 1;
      @(negedge clk); start = 0;
    end
  endtask

  task automatic perturb_busy_inputs;
    begin
      // Mutating every configuration field immediately after the accepting
      // edge catches use of live addresses, dimensions, policy, or lane.
      data_i = 64'hffff_ffff_ffff_fffe;
      trig_i = 64'h8000_0000_0000_0001;
      out_i = 64'hffff_ffff_ffff_ffff;
      position_i = 64'hffff_ffff_ffff_ffc0;
      beats_i = 1; heads_i = 3; dim_i = 17; rotary_i = 65;
      policy_i = 8'hff; lane_i = 15;
      repeat (3) @(negedge clk);
      start = 1;
      repeat (2) @(negedge clk);
      start = 0;
    end
  endtask

  task automatic wait_completion;
    begin
      while (!done) @(negedge clk);
      @(negedge clk);
      if (completions != 1 || done || !ready)
        $fatal(1, "completion pulse/idle recovery failed txn=%0d", transaction);
      active = 0; launched = 0;
      repeat (8) @(negedge clk);
      if (rv || wv || done || frsv[0]) $fatal(1, "late transaction after drain txn=%0d", transaction);
      host_mode = 1;
    end
  endtask

  task automatic execute_valid(input integer txid);
    begin
      transaction = txid;
      prepare_memory(); launch(0);
      if (MODE != 0) perturb_busy_inputs();
      wait_completion(); readback();
      successful++; completed_pair_total += expect_pairs;
      if (txid >= 0) begin
        main_successful++; main_pair_total += expect_pairs;
        if (MODE != 0) begin
          offset_coverage[(destination_base & 63)/2] = 1;
          main_tail_elements += expect_heads*192;
        end
      end
    end
  endtask

  task automatic reset_together;
    begin
      rst_n = 0; start = 0;
      active = 0; launched = 0; host_mode = 0;
      hrv = 0; hwv = 0; hrsr = 0;
      repeat (3) @(posedge clk);
      @(negedge clk); rst_n = 1;
      force_rsp_block = 0; force_wr_block = 0; force_open = 0;
      repeat (8) @(negedge clk);
      if (!ready || done || rv || wv || frsv[0] || reads || writes || pairs || flags || bad)
        $fatal(1, "reset failed to flush transport/arithmetic");
      host_mode = 1;
    end
  endtask

  task automatic run_reset_case(input integer phase);
    begin
      load_record(0); transaction = -100-phase;
      prepare_memory(); force_open = 1;
      if (phase == 0) force_rsp_block = 1;
      launch(0);
      case (phase)
        0: begin
          while (!frsv[0]) @(negedge clk);
          if (scoreboard_reads != 1 || scoreboard_responses != 0)
            $fatal(1, "reset pending-read phase was not reached");
        end
        1: begin
          while (scoreboard_responses != expect_reads) @(negedge clk);
          // A registered pair takes nine cycles. Three edges after the last
          // response place the first pair in flight, before any completion.
          repeat (3) @(negedge clk);
          if (pairs != 0 || wv || model_pair_accept != 1 || model_pair_complete != 0) $fatal(1, "reset pair-inflight phase was not reached");
        end
        2: begin
          while (scoreboard_writes < 2) @(negedge clk);
          force_wr_block = 1;
          while (!wv) @(negedge clk);
          repeat (4) @(negedge clk);
          if (scoreboard_writes != 2 || done) $fatal(1, "reset stalled-write phase was not reached");
        end
        3: begin
          while (!done) @(negedge clk);
        end
      endcase
      // Abort semantics are intentionally non-atomic: committed writes stay,
      // while the buffered/stalled write must not appear after fabric reset.
      for (integer a=0; a<BEATS; a++) if (touched[a])
        for (integer b=0; b<64; b++) expected_memory[a*64+b] = observed_memory[a*64+b];
      reset_together(); reset_cases++; readback();
      load_record(0); execute_valid(-200-phase); // immediate verified recovery
    end
  endtask

  task automatic run_rejection(input integer which);
    begin
      load_record(0); transaction = -1000-which;
      // Use a known one-head shape even if record zero happens to have two.
      expect_heads = 1; prepare_memory();
      case (which)
        0: policy_i=0;
        1: policy_i=8'hb0;
        2: policy_i=8'hff;
        3: heads_i=0;
        4: heads_i=3;
        5: dim_i=0;
        6: dim_i=128;
        7: dim_i=255;
        8: dim_i=257;
        9: rotary_i=0;
        10: rotary_i=32;
        11: rotary_i=65;
        12: rotary_i=128;
        13: beats_i=0;
        14: beats_i=7;
        15: beats_i=9;
        16: beats_i=16;
        17: begin heads_i=2; beats_i=8; end
        18: begin heads_i=2; beats_i=15; end
        19: begin heads_i=2; beats_i=17; end
        20: data_i=data_i+2;
        21: data_i=data_i+63;
        22: trig_i=trig_i+2;
        23: trig_i=trig_i+63;
        24: out_i=out_i+1;
        25: out_i=64'h303f;
        26: data_i=64'h1_0000;
        27: trig_i=64'h1_0000;
        28: out_i=64'h1_0000;
        29: data_i=64'hffff_ffff_ffff_ffc0;
        30: trig_i=64'hffff_ffff_ffff_ffc0;
        31: out_i=64'hffff_ffff_ffff_fffe;
        32: data_i=BYTES-448;
        33: begin heads_i=2; beats_i=16; data_i=BYTES-960; end
        34: trig_i=BYTES-64;
        35: out_i=BYTES-510;
        36: out_i=64'h8000_0000_0000_3000;
        37: begin data_i=BYTES-512; heads_i=2; beats_i=16; end
        default: $fatal(1, "unknown negative case");
      endcase
      // Rejected transactions must leave even output bytes at their original
      // values, as independently verified by a complete public readback.
      for (integer a=0; a<BEATS; a++) if (touched[a])
        for (integer b=0; b<64; b++) expected_memory[a*64+b] = observed_memory[a*64+b];
      expect_reads=0; expect_writes=0; expect_pairs=0; expect_flags=0;
      launch(1); wait_completion(); readback(); rejected++;
    end
  endtask

  initial begin : run
    logic [15:0] val;
    start=0; beats_i=0; heads_i=0; dim_i=0; rotary_i=0;
    policy_i=0; lane_i=0; data_i=0; position_i=0; out_i=0; trig_i=0;
    if (!$value$plusargs("OUTPUTS=%s", outputs_path)) outputs_path="rope_bf16_l2_actual.txt";
    output_file=$fopen(outputs_path,"w");
    if (!output_file) $fatal(1,"cannot open output trace");
    if (MODE != 0) begin
      if (!$value$plusargs("VECTORS=%s", vectors_path)) $fatal(1,"VECTORS is required");
      $readmemh(vectors_path, vectors);
    end
    reset_together();
    if (MODE == 0) begin
      expect_heads=1; expect_flags=0;
      source_base='h1000; trig_base='h2000; destination_base='h3000;
      for (integer b=0; b<16; b++) begin input_beats[b]=0; expected_beats[b]=0; end
      for (integer e=0; e<128; e++) begin
        val=16'h3e80+16'(e);
        input_beats[e/32][(e%32)*16 +: 16]=val;
        expected_beats[e/32][(e%32)*16 +: 16]=val;
      end
      trig_beats[0]=0; trig_beats[1]=0;
      execute_valid(0);
      execute_valid(1);
      $display("ROPE_BF16_L2_PASS mode=0 transactions=%0d pairs=%0d masked_packets=%0d readback_bytes=%0d",
        main_successful, main_pair_total, masked_packets, readback_bytes);
    end else begin
      for (integer c=0; c<COUNT; c++) begin
        load_record(c); execute_valid(c);
      end
      for (integer c=0; c<38; c++) run_rejection(c);
      for (integer phase=0; phase<4; phase++) run_reset_case(phase);
      // Range-edge positives distinguish true range validation from blanket
      // high-address rejection. All source accesses still use the real fabric.
      for (integer edge_case=0; edge_case<5; edge_case++) begin
        load_record(0); expect_heads=1;
        case (edge_case)
          0: source_base=BYTES-512;
          1: trig_base=BYTES-128;
          2: destination_base=BYTES-512;
          3: destination_base=BYTES-514;
          4: destination_base=0;
        endcase
        execute_valid(-300-edge_case);
      end
      // Explicit backward overlap as well as metadata-driven forward/in-place.
      load_record(0); destination_base=source_base-62; execute_valid(-400);
      if (COUNT>=32 && offset_coverage!==32'hffff_ffff)
        $fatal(1,"all 32 BF16-aligned offsets were not covered mask=%h",offset_coverage);
      if (STALL && (!total_read_stalls || !total_write_stalls || !total_response_stalls))
        $fatal(1,"requested request/write/response stalls not exercised");
      if (main_successful!=COUNT || rejected!=38 || reset_cases!=4)
        $fatal(1,"suite accounting mismatch");
      $display("ROPE_BF16_L2_PASS mode=1 transactions=%0d successful=%0d main_pairs=%0d main_tail_bf16=%0d rejects=%0d resets=%0d packets=%0d readback_bytes=%0d rd_stalls=%0d wr_stalls=%0d rsp_stalls=%0d offsets=%08h actual_shared_l2=1 no_memory_pokes=1",
        main_successful,successful,main_pair_total,main_tail_elements,rejected,reset_cases,
        masked_packets,readback_bytes,total_read_stalls,total_write_stalls,total_response_stalls,offset_coverage);
    end
    $fclose(output_file); $finish;
  end

  initial begin
    repeat ((COUNT+100)*25000) @(posedge clk);
    $fatal(1,"global timeout txn=%0d",transaction);
  end
endmodule
