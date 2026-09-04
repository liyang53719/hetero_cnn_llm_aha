// SPDX-License-Identifier: Apache-2.0
// Logic-equivalent reset branch used to prevent cross-hierarchy reset-net
// merging. Physical implementation may replace this with the reset-tree flow.
(* keep_hierarchy = "yes" *)
module operator_reset_fanout_branch_v3(
  input  logic rst_ni,
  output wire  rst_branch_ni
);
  (* keep = "true", dont_touch = "true" *) wire rst_stage_n;
`ifdef SYNTHESIS
  INV_X1M_A6P5PP140ZTS_C35 u_inv0(.Y(rst_stage_n), .A(rst_ni));
  INV_X4M_A6P5PP140ZTS_C35 u_inv1(.Y(rst_branch_ni), .A(rst_stage_n));
`else
  assign rst_stage_n = ~rst_ni;
  assign rst_branch_ni = ~rst_stage_n;
`endif
endmodule
