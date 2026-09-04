`timescale 1ns/1ps
module tb_fp32_reciprocal_nr2;parameter COUNT=10000;logic clk=0,rst_n=0;always #5 clk=~clk;logic iv,ir,ov,orr,de;logic[31:0]x,y;logic[4:0]flags;logic[31:0]accepted,completed;logic[64:0]v[0:COUNT-1];integer seen,cycles;logic stalled;logic[32:0]held;
 fp32_reciprocal_nr2 dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.x_i(x),.out_valid_o(ov),.out_ready_i(orr),.y_o(y),.exception_flags_o(flags),.domain_error_o(de),.accepted_o(accepted),.completed_o(completed));always_comb orr=cycles%5!=1;
 always@(posedge clk)if(!rst_n)begin seen<=0;cycles<=0;stalled<=0;held<=0;end else begin cycles<=cycles+1;if(stalled&&(!ov||{de,y}!==held))$fatal(1,"stalled");stalled<=ov&&!orr;if(ov&&!orr)held<={de,y};if(ov&&orr)begin if({de,y}!==v[seen][64:32])$fatal(1,"mismatch %0d",seen);seen<=seen+1;end end
 initial begin iv=0;x=0;$readmemh("work/results/l5_recip/vectors.memh",v);repeat(3)@(posedge clk);rst_n=1;for(int i=0;i<COUNT;i++)begin @(negedge clk);x=v[i][31:0];iv=1;do @(posedge clk);while(!ir);end @(negedge clk);iv=0;wait(seen==COUNT);if(accepted!=COUNT||completed!=COUNT)$fatal(1,"count");$display("FP32_RECIPROCAL_NR2_PASS vectors=10000");$finish;end
endmodule
