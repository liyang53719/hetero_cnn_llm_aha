`timescale 1ns/1ps
module tb_bf16_context_lane_rev7_vs_rev8a;
  localparam integer TARGET = 120_000;
  logic clk = 0, rst_n = 0;
  logic in_valid, in_ready, clear, last, out_valid, out_ready, out_last;
  logic [1:0] context_in, context_out;
  logic [15:0] a, b;
  logic array_in_valid, array_in_ready, array_out_valid, array_out_ready;
  logic [1:0] issue_context, completion_context;
  logic issue_clear, issue_bypass, issue_use_bank, completion_fire;
  logic pre_write, mul_write, post_write, output_write;
  logic [31:0] accepted, completed, array_accepted, array_completed;
  logic [3:0] busy, accumulator_valid, rev8_bank_valid;
  logic protocol_error;
  logic [1:0] early_commit_context, tag_output_context;
  logic [31:0] rev7_out, rev8_out;
  logic [4:0] rev7_flags, rev8_flags;
  logic [31:0] lfsr;
  logic pending;
  logic [1:0] pending_context;
  logic pending_clear, pending_last;
  logic [15:0] pending_a, pending_b;
  integer issues, completions, cycles;

  always #0.5 clk = ~clk;

  bf16_context_scheduler4 scheduler (
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(in_valid), .in_ready_o(in_ready),
    .context_i(context_in), .clear_i(clear), .last_i(last),
    .out_valid_o(out_valid), .out_ready_i(out_ready),
    .context_o(context_out), .last_o(out_last),
    .array_in_valid_o(array_in_valid), .array_in_ready_i(array_in_ready),
    .array_out_valid_i(array_out_valid), .array_out_ready_o(array_out_ready),
    .issue_context_o(issue_context), .issue_clear_o(issue_clear),
    .issue_bypass_o(issue_bypass), .issue_use_bank_o(issue_use_bank),
    .completion_fire_o(completion_fire),
    .completion_context_o(completion_context),
    .busy_o(busy), .accumulator_valid_o(accumulator_valid),
    .accepted_steps_o(accepted), .completed_steps_o(completed),
    .protocol_error_o(protocol_error)
  );

  bf16_outer_product_array_control_rev8_candidate control (
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(array_in_valid), .in_ready_o(array_in_ready),
    .out_valid_o(array_out_valid), .out_ready_i(array_out_ready),
    .pre_write_o(pre_write), .mul_write_o(mul_write),
    .post_write_o(post_write), .output_write_o(output_write),
    .accepted_steps_o(array_accepted), .completed_steps_o(array_completed)
  );

  bf16_context_tag_pipeline4_rev8_candidate tags (
    .clk_i(clk), .rst_ni(rst_n),
    .pre_write_i(pre_write), .mul_write_i(mul_write),
    .post_write_i(post_write), .output_write_i(output_write),
    .issue_context_i(issue_context),
    .early_commit_context_o(early_commit_context),
    .output_context_o(tag_output_context)
  );

  bf16_context_fma_pipeline_lane4 rev7 (
    .clk_i(clk), .rst_ni(rst_n),
    .pre_write_i(pre_write), .mul_write_i(mul_write),
    .post_write_i(post_write), .output_write_i(output_write),
    .a_i(a), .b_i(b),
    .issue_context_i(issue_context), .issue_clear_i(issue_clear),
    .issue_bypass_i(issue_bypass), .issue_use_bank_i(issue_use_bank),
    .completion_fire_i(completion_fire),
    .completion_context_i(completion_context),
    .out_o(rev7_out), .flags_o(rev7_flags)
  );

  bf16_context_fma_pipeline_lane4_rev8_candidate rev8 (
    .clk_i(clk), .rst_ni(rst_n),
    .pre_write_i(pre_write), .mul_write_i(mul_write),
    .post_write_i(post_write), .output_write_i(output_write),
    .a_i(a), .b_i(b),
    .issue_context_i(issue_context), .issue_clear_i(issue_clear),
    .early_commit_context_i(early_commit_context),
    .output_context_i(tag_output_context),
    .out_o(rev8_out), .flags_o(rev8_flags),
    .bank_valid_o(rev8_bank_valid)
  );

  function automatic [15:0] bf16_operand(input [31:0] x, input integer which);
    begin
      case ((x + which) & 15)
        0: bf16_operand = 16'h0000;
        1: bf16_operand = 16'h8000;
        2: bf16_operand = 16'h3f80;
        3: bf16_operand = 16'hbf80;
        4: bf16_operand = 16'h3f00;
        5: bf16_operand = 16'h4000;
        6: bf16_operand = 16'h4040;
        7: bf16_operand = 16'hc000;
        8: bf16_operand = 16'h0080;
        9: bf16_operand = 16'h0001;
        10: bf16_operand = 16'h7f7f;
        11: bf16_operand = 16'hff7f;
        12: bf16_operand = 16'h3e80;
        13: bf16_operand = 16'hbe80;
        14: bf16_operand = 16'h7f80;
        default: bf16_operand = 16'h7fc1;
      endcase
    end
  endfunction

  initial begin
    in_valid = 0; out_ready = 0; context_in = 0; clear = 0; last = 0;
    a = 0; b = 0; lfsr = 32'h8a31_c0de; pending = 0;
    issues = 0; completions = 0; cycles = 0;
    repeat (8) @(posedge clk);
    rst_n = 1;
    while (completions < TARGET) begin
      @(negedge clk);
      cycles = cycles + 1;
      if (out_valid) begin
        if (tag_output_context !== context_out)
          $fatal(1, "tag/FIFO mismatch cycle=%0d tag=%0d fifo=%0d", cycles, tag_output_context, context_out);
        if (rev7_out !== rev8_out)
          $fatal(1, "data mismatch cycle=%0d context=%0d rev7=%08x rev8=%08x", cycles, context_out, rev7_out, rev8_out);
        if (rev7_flags !== rev8_flags)
          $fatal(1, "flag mismatch cycle=%0d rev7=%02x rev8=%02x", cycles, rev7_flags, rev8_flags);
      end
      lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
      if (!pending && issues < TARGET && (lfsr[2] || lfsr[7])) begin
        pending = 1;
        pending_context = lfsr[4:3];
        pending_clear = (issues < 4) || (lfsr[15:8] == 8'h00);
        pending_last = lfsr[6];
        pending_a = bf16_operand(lfsr, 0);
        pending_b = bf16_operand({lfsr[15:0], lfsr[31:16]}, 5);
      end
      in_valid = pending;
      context_in = pending_context;
      clear = pending_clear;
      last = pending_last;
      a = pending_a;
      b = pending_b;
      out_ready = lfsr[0] || lfsr[5] || lfsr[9];
      @(posedge clk);
      if (in_valid && in_ready) begin
        issues = issues + 1;
        pending = 0;
      end
      if (out_valid && out_ready)
        completions = completions + 1;
      if (protocol_error)
        $fatal(1, "scheduler protocol error cycle=%0d", cycles);
      if (cycles > 3_000_000)
        $fatal(1, "timeout issues=%0d completions=%0d", issues, completions);
    end
    @(negedge clk);
    in_valid = 0; out_ready = 1;
    repeat (8) @(posedge clk);
    if (accepted != TARGET || completed != TARGET)
      $fatal(1, "counter mismatch accepted=%0d completed=%0d", accepted, completed);
    $display("BF16_CONTEXT_REV7_VS_REV8A_PASS compared=%0d cycles=%0d contexts=4", TARGET, cycles);
    $finish;
  end
endmodule
