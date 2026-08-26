`timescale 1ns/1ps
module tb_fp32_exp2_pwl;parameter integer COUNT=10000;logic clk;/* verilator lint_off SYNCASYNCNET */logic rst_n;/* verilator lint_on SYNCASYNCNET */always #5 clk=~clk;
 logic iv,ir,ov,orr;logic[31:0]x,y;logic[12:0]flags,flags_or;logic[31:0]accepted,completed;logic[63:0]v[0:COUNT-1];integer cycles,seen;logic[63:0]hash;logic stalled;logic[31:0]held;
 fp32_exp2_pwl dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.x_i(x),.out_valid_o(ov),.out_ready_i(orr),.y_o(y),.exception_flags_o(flags),.accepted_o(accepted),.completed_o(completed));
 always_comb orr=(cycles%5)!=1;
 always @(posedge clk)begin if(!rst_n)begin cycles<=0;seen<=0;flags_or<=0;hash<=64'hcbf29ce484222325;stalled<=0;held<=0;end else begin cycles<=cycles+1;if(stalled&&(!ov||y!==held))$fatal(1,"exp2 stalled");stalled<=ov&&!orr;if(ov&&!orr)held<=y;
  if(ov&&orr)begin if(y!==v[seen][63:32])$fatal(1,"exp2 mismatch i=%0d x=%h got=%h exp=%h flags=%h",seen,v[seen][31:0],y,v[seen][63:32],flags);flags_or<=flags_or|flags;hash<=(hash^{32'd0,y})*64'h100000001b3;seen<=seen+1;end end end
 initial begin clk=0;rst_n=0;iv=0;x=0;$readmemh("work/results/l5_exp2/vectors.memh",v);repeat(3)@(posedge clk);rst_n=1;
  for(int i=0;i<COUNT;i++)begin @(negedge clk);x=v[i][31:0];iv=1;do @(posedge clk);while(!ir);end @(negedge clk);iv=0;wait(seen==COUNT);@(negedge clk);if(accepted!=COUNT||completed!=COUNT)$fatal(1,"exp2 counters");
  $display("FP32_EXP2_PWL_PASS vectors=%0d cycles=%0d accept_interval=1 output_fnv64=%016h flags_or=%h",COUNT,cycles,hash,flags_or);$finish;end
endmodule
