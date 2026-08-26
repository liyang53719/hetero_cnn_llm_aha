// Lint-only boundary declaration for the generated ARM Control SRAM model.
// Real simulation gates always compile the vendor model instead of this file.
`timescale 1ns/1ps
/* verilator lint_off DECLFILENAME */
module ctsp4096x128wm (
  output logic [127:0] q,
  input logic clk,
  input logic cen,
  input logic gwen,
  input logic [11:0] a,
  input logic [127:0] d,
  input logic [127:0] wen,
  input logic stov,
  input logic [2:0] ema,
  input logic [1:0] emaw,
  input logic emas,
  input logic ret1n,
  input logic rawl,
  input logic [1:0] rawlm,
  input logic wabl,
  input logic [1:0] wablm
);
  always_comb begin
    q = 0;
    if (clk || cen || gwen || stov || emas || ret1n || rawl || wabl ||
        a != 0 || d != 0 || wen != 0 || ema != 0 || emaw != 0 ||
        rawlm != 0 || wablm != 0)
      q = 0;
  end
endmodule
/* verilator lint_on DECLFILENAME */
