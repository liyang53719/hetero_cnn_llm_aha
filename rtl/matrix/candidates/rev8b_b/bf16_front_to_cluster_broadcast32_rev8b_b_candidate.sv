// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_front_to_cluster_broadcast32_rev8b_b_candidate #(
  parameter integer BUNDLE_WIDTH=15,
  localparam integer BRANCHES=4,LEAVES_PER_BRANCH=8,LEAVES=32
)(input wire[BUNDLE_WIDTH-1:0]control_i,output wire[LEAVES*BUNDLE_WIDTH-1:0]cluster_control_o);
  wire[BUNDLE_WIDTH-1:0]branch_control[0:BRANCHES-1];
  generate
    for(genvar branch=0;branch<BRANCHES;branch++)begin:g_branch
      for(genvar bit_index=0;bit_index<BUNDLE_WIDTH;bit_index++)begin:g_branch_bit
        buf u_branch_buffer(branch_control[branch][bit_index],control_i[bit_index]);
      end
      for(genvar leaf=0;leaf<LEAVES_PER_BRANCH;leaf++)begin:g_leaf
        localparam integer CLUSTER=branch*LEAVES_PER_BRANCH+leaf;
        for(genvar bit_index=0;bit_index<BUNDLE_WIDTH;bit_index++)begin:g_leaf_bit
          buf u_leaf_buffer(cluster_control_o[CLUSTER*BUNDLE_WIDTH+bit_index],branch_control[branch][bit_index]);
        end
      end
    end
  endgenerate
endmodule
