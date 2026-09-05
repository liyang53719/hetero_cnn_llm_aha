`timescale 1ns/1ps
module tb_fp32_ieee_real;
 `include "fp32_ieee_real.svh"
 integer checked=0;
 task automatic check(input logic[31:0] bits,input logic[63:0] expected);
  begin
   if(fp32_ieee_to_fp64_bits(bits)!==expected||$realtobits(fp32_ieee_real(bits))!==expected)$fatal(1,"FP32 widening bits=%h",bits);
   checked++;
  end
 endtask
 initial begin
  check(32'h00000000,64'h0000000000000000);
  check(32'h80000000,64'h8000000000000000);
  check(32'h00000001,64'h36a0000000000000);
  check(32'h80000001,64'hb6a0000000000000);
  check(32'h007fffff,64'h380fffffc0000000);
  check(32'h00800000,64'h3810000000000000);
  check(32'h3f800000,64'h3ff0000000000000);
  check(32'hbf800000,64'hbff0000000000000);
  check(32'h40000000,64'h4000000000000000);
  check(32'hc0200000,64'hc004000000000000);
  check(32'h7f7fffff,64'h47efffffe0000000);
  check(32'hff7fffff,64'hc7efffffe0000000);
  check(32'h3b03126f,64'h3f60624de0000000);
  check(32'h7f800000,64'h7ff0000000000000);
  check(32'hff800000,64'hfff0000000000000);
  if(fp32_ieee_to_fp64_bits(32'h7fc00001)!==64'h7ff8000020000000)$fatal(1,"NaN payload");
  if(fp32_ieee_real(32'h40000000)-fp32_ieee_real(32'h3f800000)<=0.002)$fatal(1,"broken positive error sentinel");
  if(fp32_ieee_real(32'hbf800000)-fp32_ieee_real(32'hc0000000)<=0.002)$fatal(1,"broken negative error sentinel");
  $display("FP32_IEEE_REAL_PASS edge_cases=%0d nonzero_error_sentinels=2",checked);$finish;
 end
endmodule
