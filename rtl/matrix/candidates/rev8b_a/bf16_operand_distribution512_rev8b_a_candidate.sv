// SPDX-License-Identifier: Apache-2.0
// Cycle-neutral A/B operand distribution for the 16x32 array. Each A row
// element uses a 1->4->32 tree; each B column element uses a 1->4->16 tree.
`timescale 1ns/1ps
module bf16_operand_distribution512_rev8b_a_candidate (
  input  wire [16*16-1:0] a_i,
  input  wire [32*16-1:0] b_i,
  output wire [512*16-1:0] lane_a_o,
  output wire [512*16-1:0] lane_b_o
);
  wire [16*16*4-1:0] a_branch;
  wire [32*16*4-1:0] b_branch;

  generate
    for (genvar row = 0; row < 16; row++) begin : g_a_row
      for (genvar bit_index = 0; bit_index < 16; bit_index++) begin : g_a_bit
        localparam integer SOURCE = row*16 + bit_index;
        for (genvar branch = 0; branch < 4; branch++) begin : g_a_branch
          localparam integer BRANCH_INDEX = SOURCE*4 + branch;
          buf u_a_branch(a_branch[BRANCH_INDEX], a_i[SOURCE]);
          for (genvar leaf = 0; leaf < 8; leaf++) begin : g_a_leaf
            localparam integer COL = branch*8 + leaf;
            localparam integer LANE_BIT = (row*32 + COL)*16 + bit_index;
            buf u_a_leaf(lane_a_o[LANE_BIT], a_branch[BRANCH_INDEX]);
          end
        end
      end
    end

    for (genvar col = 0; col < 32; col++) begin : g_b_col
      for (genvar bit_index = 0; bit_index < 16; bit_index++) begin : g_b_bit
        localparam integer SOURCE = col*16 + bit_index;
        for (genvar branch = 0; branch < 4; branch++) begin : g_b_branch
          localparam integer BRANCH_INDEX = SOURCE*4 + branch;
          buf u_b_branch(b_branch[BRANCH_INDEX], b_i[SOURCE]);
          for (genvar leaf = 0; leaf < 4; leaf++) begin : g_b_leaf
            localparam integer ROW = branch*4 + leaf;
            localparam integer LANE_BIT = (ROW*32 + col)*16 + bit_index;
            buf u_b_leaf(lane_b_o[LANE_BIT], b_branch[BRANCH_INDEX]);
          end
        end
      end
    end
  endgenerate
endmodule
