// Shared harness; paired cases differ ONLY by -GOPAQUE=0 or -GOPAQUE=1.
// Exactly eight leaves, selected-mask identity terms, and atomic all-leaf gating.
// State encodings follow MatrixPipeline Enum(7): idle=0, command=1, running=2,
// ending=3, finish=4, draining=5, locked=6. State/register inputs are cutpoints.
module host_handshake_micro #(parameter bit OPAQUE = 1'b0) (
  input logic [7:0] selected,
  input logic [2:0] state_q,
  input logic end_issued_q, abort_i, seed_blocks, seed_poison,
  input logic tags_deq_valid, tags_emit, values_enq_ready, tags_full_q,
  input logic legal_step, step_valid_i,
  input logic [2:0] context_i,
  input logic [7:0] active_q, pending_q, seed_active,
  input logic [7:0][3:0] fifo_count_q, completion_tokens_q,
  input logic [7:0][4:0] busy_q,
  input logic [7:0][2:0] completion_context_q,
  output wire [7:0] cmd_valid, step_valid, out_ready, completion_ready,
  output wire [7:0] cmd_ready, step_ready, out_valid, completion_valid,
  output wire all_command_ready, all_step_ready, all_out_valid, all_completion,
  output wire consume_output, upstream_step_ready
);
  wire work, tags_enq_ready;
  // MatrixPipeline:73-76. Do not replace atomic gating with individual readiness.
  assign all_command_ready = &(~selected | cmd_ready);
  assign all_step_ready = &(~selected | step_ready);
  assign all_out_valid = &(~selected | out_valid);
  assign all_completion = &(~selected | completion_valid);
  // MatrixPipeline:80,83-84. Current-state/service cutpoints stay independent.
  assign work = (state_q == 3'd2) && !end_issued_q && !abort_i && !seed_blocks && !seed_poison;
  assign consume_output = ((state_q == 3'd2) || (state_q == 3'd3) || (state_q == 3'd5)) && tags_deq_valid && all_out_valid && ((state_q == 3'd5) || !tags_emit || values_enq_ready);
  // tags Queue(pipe=true): current full state plus actual downstream readiness.
  assign tags_enq_ready = !tags_full_q || consume_output;
  // MatrixPipeline:166. Invalid-step acceptance branch is retained verbatim in shape.
  assign upstream_step_ready = work && (legal_step ? (tags_enq_ready && all_step_ready) : 1'b1);
  for (genvar i = 0; i < 8; i++) begin : leaves
    // MatrixPipeline:147,149,160-161, unchanged for both paired cases.
    assign cmd_valid[i] = (state_q == 3'd1) && selected[i] && all_command_ready;
    assign step_valid[i] = work && legal_step && step_valid_i && tags_enq_ready && all_step_ready && selected[i];
    assign out_ready[i] = consume_output && selected[i];
    assign completion_ready[i] = (state_q == 3'd3) && all_completion && selected[i];
    if (OPAQUE) begin : opaque
      leaf_opaque_model leaf (
        .cmd_valid_i(cmd_valid[i]),
        .step_valid_i(step_valid[i]),
        .out_ready_i(out_ready[i]),
        .completion_ready_i(completion_ready[i]),
        .active_q(active_q[i]),
        .pending_q(pending_q[i]),
        .seed_active(seed_active[i]),
        .fifo_count_q(fifo_count_q[i]),
        .completion_tokens_q(completion_tokens_q[i]),
        .busy_q(busy_q[i]),
        .completion_context_q(completion_context_q[i]),
        .context_i(context_i),
        .cmd_ready_o(cmd_ready[i]),
        .step_ready_o(step_ready[i]),
        .out_valid_o(out_valid[i]),
        .completion_valid_o(completion_valid[i])
      );
    end else begin : transparent
      leaf_transparent leaf (
        .cmd_valid_i(cmd_valid[i]),
        .step_valid_i(step_valid[i]),
        .out_ready_i(out_ready[i]),
        .completion_ready_i(completion_ready[i]),
        .active_q(active_q[i]),
        .pending_q(pending_q[i]),
        .seed_active(seed_active[i]),
        .fifo_count_q(fifo_count_q[i]),
        .completion_tokens_q(completion_tokens_q[i]),
        .busy_q(busy_q[i]),
        .completion_context_q(completion_context_q[i]),
        .context_i(context_i),
        .cmd_ready_o(cmd_ready[i]),
        .step_ready_o(step_ready[i]),
        .out_valid_o(out_valid[i]),
        .completion_valid_o(completion_valid[i])
      );
    end
  end
endmodule
