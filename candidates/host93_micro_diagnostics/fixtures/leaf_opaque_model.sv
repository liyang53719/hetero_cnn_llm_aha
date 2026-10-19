// MODEL ONLY. Hand-authored reduced unclocked ProtectLib boundary shape.
// Not the actual generated Host wrapper; no DPI implementation or simulation is supplied.
// Each DPI output's intended functional contract is leaf_transparent.sv.
// ONE combo_update call, all inputs DIRECT, all outputs COMBO_RESULT.
// Templates: DERIVED_V3ProtectLib.cpp:193-199,256-265,291-304,454-463,473-500.
module leaf_opaque_model (
  input logic cmd_valid_i, step_valid_i, out_ready_i, completion_ready_i,
  input logic active_q, pending_q, seed_active,
  input logic [3:0] fifo_count_q, completion_tokens_q,
  input logic [4:0] busy_q,
  input logic [2:0] completion_context_q, context_i,
  output logic cmd_ready_o, step_ready_o, out_valid_o, completion_valid_o
);
  import "DPI-C" function chandle micro_protectlib_create(input string scope__V);
  import "DPI-C" function longint micro_protectlib_combo_update(
    input chandle handle__V,
  input logic cmd_valid_i, step_valid_i, out_ready_i, completion_ready_i,
  input logic active_q, pending_q, seed_active,
  input logic [3:0] fifo_count_q, completion_tokens_q,
  input logic [4:0] busy_q,
  input logic [2:0] completion_context_q, context_i,
  output logic cmd_ready_o, step_ready_o, out_valid_o, completion_valid_o
  );
  import "DPI-C" function void micro_protectlib_final(input chandle handle__V);
  chandle handle__V;
  time last_combo_seqnum__V;
  logic cmd_ready_o_combo__V, step_ready_o_combo__V;
  logic out_valid_o_combo__V, completion_valid_o_combo__V;
  initial handle__V = micro_protectlib_create($sformatf("%m"));
  always_comb begin
    last_combo_seqnum__V = micro_protectlib_combo_update(
      handle__V,
      cmd_valid_i,
      step_valid_i,
      out_ready_i,
      completion_ready_i,
      active_q,
      pending_q,
      seed_active,
      fifo_count_q,
      completion_tokens_q,
      busy_q,
      completion_context_q,
      context_i,
      cmd_ready_o_combo__V,
      step_ready_o_combo__V,
      out_valid_o_combo__V,
      completion_valid_o_combo__V
    );
  end
  always_comb begin
    cmd_ready_o = cmd_ready_o_combo__V;
    step_ready_o = step_ready_o_combo__V;
    out_valid_o = out_valid_o_combo__V;
    completion_valid_o = completion_valid_o_combo__V;
  end
  final micro_protectlib_final(handle__V);
endmodule
