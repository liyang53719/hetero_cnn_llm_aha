// SOURCE MODEL: combinational state-cut projection, not a replacement endpoint.
// Exact scalar equations from pinned endpoint:28, scheduler:31-42, array-control:13-14.
module leaf_transparent (
  input logic cmd_valid_i, step_valid_i, out_ready_i, completion_ready_i,
  input logic active_q, pending_q, seed_active,
  input logic [3:0] fifo_count_q, completion_tokens_q,
  input logic [4:0] busy_q,
  input logic [2:0] completion_context_q, context_i,
  output logic cmd_ready_o, step_ready_o, out_valid_o, completion_valid_o
);
  logic fifo_not_full, fifo_not_empty, context_legal, context_available;
  logic array_in_ready, array_out_valid, moutv, moutr, minr;
  logic array_out_ready, completion_fire, completion_same_context;
  logic [2:0] completion_context;
  assign fifo_not_full = fifo_count_q < 8;
  assign fifo_not_empty = fifo_count_q != 0;
  assign array_in_ready = completion_tokens_q < 8;
  assign array_out_valid = completion_tokens_q != 0;
  assign context_legal = context_i < 3'd5;
  assign moutv = array_out_valid && fifo_not_empty;
  assign moutr = active_q && out_ready_i;
  assign array_out_ready = moutr && fifo_not_empty;
  assign completion_fire = array_out_valid && array_out_ready;
  assign completion_context = fifo_not_empty ? completion_context_q : '0;
  assign completion_same_context = completion_fire && completion_context == context_i;
  assign context_available = context_legal && (!busy_q[context_i] || completion_same_context);
  assign minr = context_available && fifo_not_full && array_in_ready && !seed_active;
  assign cmd_ready_o = !active_q && !pending_q && !seed_active;
  assign step_ready_o = active_q && minr;
  assign out_valid_o = active_q && moutv;
  assign completion_valid_o = pending_q;
endmodule
