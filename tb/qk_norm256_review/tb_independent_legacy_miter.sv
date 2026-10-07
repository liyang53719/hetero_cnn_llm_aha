`timescale 1ns/1ps
module tb_independent_legacy_miter;
logic clk=0;always #5 clk=~clk;
logic rst=0,iv=0,orr=0,ir1,ir2,ov1,ov2;
logic[8191:0] x=0,w=0,y1,y2;logic[31:0] eps=0,a1,a2,c1,c2,r1,r2,s1,s2,o1,o2;logic[4:0] f1,f2;
integer cycles=0,checked=0;
fp32_rmsnorm256_chunked current_core(.clk_i(clk),.rst_ni(rst),.in_valid_i(iv),.in_ready_o(ir1),.x_i(x),.weight_i(w),.epsilon_i(eps),.out_valid_o(ov1),.out_ready_i(orr),.y_o(y1),.exception_flags_o(f1),.accepted_o(a1),.completed_o(c1),.reduction_cycles_o(r1),.rsqrt_cycles_o(s1),.output_cycles_o(o1),.domain_error_o(),.mean_eps_o(),.inv_o());
fp32_rmsnorm256_chunked_legacy_review legacy_core(.clk_i(clk),.rst_ni(rst),.in_valid_i(iv),.in_ready_o(ir2),.x_i(x),.weight_i(w),.epsilon_i(eps),.out_valid_o(ov2),.out_ready_i(orr),.y_o(y2),.exception_flags_o(f2),.accepted_o(a2),.completed_o(c2),.reduction_cycles_o(r2),.rsqrt_cycles_o(s2),.output_cycles_o(o2));
always @(negedge clk)begin
 cycles++;
 if({ir1,ov1,y1,f1,a1,c1,r1,s1,o1}!=={ir2,ov2,y2,f2,a2,c2,r2,s2,o2})$fatal(1,"legacy cycle mismatch cycles=%0d checked=%0d",cycles,checked);
end
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(integer k=0;k<64;k++)begin
  @(negedge clk);eps=$random;for(integer l=0;l<256;l++)begin x[l*32+:32]=$random;w[l*32+:32]=$random;end
  case(k%8)
   0:begin x=0;w=0;eps=32'h358637bd;end
   1:begin x={256{32'h7f800000}};eps=32'h3f800000;end
   2:begin x={256{32'h00000001}};w={256{32'h80000001}};eps=32'h00000001;end
   3:begin x={256{32'h7f7fffff}};w={256{32'h7fa00000}};eps=32'hbf800000;end
   4:begin x={256{32'h3f800000}};w={256{32'hbf800000}};eps=32'h358637bd;end
   default:begin end
  endcase
  iv=1;@(negedge clk);iv=0;
  while(!ov1)@(negedge clk);
  repeat(11)begin @(negedge clk);x=$random;w=$random;eps=$random;end
  orr=1;@(negedge clk);orr=0;checked++;
  if(k%7==6)begin rst=0;repeat(3)@(negedge clk);rst=1;end
 end
 $display("INDEPENDENT_DEFAULT_LEGACY_MITER_PASS transactions=%0d cycles=%0d",checked,cycles);$finish;
end
initial begin #20000000;$fatal(1,"watchdog");end
endmodule
