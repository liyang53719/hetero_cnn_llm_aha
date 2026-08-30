// SPDX-License-Identifier: Apache-2.0
// Revision 8B-A cycle-neutral front-to-cluster distribution candidate.
// Two combinational fanout levels make the intended 1->4->32 physical tree
// explicit.  The DC flow must prove that these boundaries map to real buffer
// cells and that H3 max-transition/max-capacitance violations are zero.
`timescale 1ns/1ps
module bf16_front_to_cluster_broadcast32_rev8b_a_candidate #(
  parameter integer BUNDLE_WIDTH = 11,
  parameter integer BRANCHES = 4,
  parameter integer LEAVES_PER_BRANCH = 8,
  localparam integer LEAVES = BRANCHES * LEAVES_PER_BRANCH
)(
  input  wire [BUNDLE_WIDTH-1:0] control_i,
  output wire [LEAVES*BUNDLE_WIDTH-1:0] cluster_control_o
);
  wire [BUNDLE_WIDTH-1:0] branch_control [0:BRANCHES-1];

  generate
    for (genvar branch = 0; branch < BRANCHES; branch++) begin : g_branch
      for (genvar bit_index = 0; bit_index < BUNDLE_WIDTH; bit_index++) begin : g_branch_bit
        buf u_branch_buffer(branch_control[branch][bit_index], control_i[bit_index]);
      end
      for (genvar leaf = 0; leaf < LEAVES_PER_BRANCH; leaf++) begin : g_leaf
        localparam integer CLUSTER = branch * LEAVES_PER_BRANCH + leaf;
        for (genvar bit_index = 0; bit_index < BUNDLE_WIDTH; bit_index++) begin : g_leaf_bit
          buf u_leaf_buffer(
            cluster_control_o[CLUSTER*BUNDLE_WIDTH + bit_index],
            branch_control[branch][bit_index]
          );
        end
      end
    end
  endgenerate

`ifndef SYNTHESIS
  initial begin
    if (BUNDLE_WIDTH != 11 || BRANCHES != 4 || LEAVES_PER_BRANCH != 8)
      $fatal(1, "Revision 8B-A broadcast requires 11-bit 1-to-4-to-32 geometry");
  end
`endif
endmodule
