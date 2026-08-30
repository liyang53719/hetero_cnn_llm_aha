// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_cluster_flags_glue32_rev8b_b_candidate(
  input logic [32*5-1:0] cluster_flags_i,
  output logic [4:0] flags_o
);
  always_comb begin
    flags_o='0;
    for(integer cluster=0;cluster<32;cluster++)flags_o|=cluster_flags_i[cluster*5+:5];
  end
endmodule
