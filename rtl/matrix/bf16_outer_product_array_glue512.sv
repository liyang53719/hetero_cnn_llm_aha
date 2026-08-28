// SPDX-License-Identifier: Apache-2.0
// Fixed production fanout/reduction glue; combinational and cycle-neutral.
`timescale 1ns/1ps
module bf16_outer_product_array_glue512 (
  input  logic rst_ni,
  input  logic [512*5-1:0] lane_flags_i,
  output logic [511:0] lane_rst_ni_o,
  output logic [4:0] flags_o
);
  integer lane;
  assign lane_rst_ni_o = {512{rst_ni}};
  always_comb begin
    flags_o = '0;
    for (lane = 0; lane < 512; lane++)
      flags_o |= lane_flags_i[lane*5 +: 5];
  end
endmodule
