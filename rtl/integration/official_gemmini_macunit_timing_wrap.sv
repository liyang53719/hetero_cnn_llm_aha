// SPDX-License-Identifier: Apache-2.0
// Timing wrapper for the pinned generated official Gemmini MacUnit.
// The generated primitive remains unmodified in work/upstream.
module official_gemmini_macunit_timing_wrap (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic [7:0]  a_i,
  input  logic [7:0]  b_i,
  input  logic [31:0] c_i,
  output logic [19:0] d_o
);
  wire [19:0] mac_d;

  MacUnit u_official_mac (
    .io_in_a(a_i),
    .io_in_b(b_i),
    .io_in_c(c_i),
    .io_out_d(mac_d)
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) d_o <= '0;
    else d_o <= mac_d;
  end
endmodule
