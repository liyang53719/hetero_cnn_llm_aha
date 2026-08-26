`timescale 1ns/1ps
module tb_fp32_rmsnorm16;parameter integer COUNT=10000;logic clk;/* verilator lint_off SYNCASYNCNET */logic rst_n;/* verilator lint_on SYNCASYNCNET */always #5 clk=~clk;
 logic iv,ir,ov,orr;logic[511:0]x,w,y;logic[31:0]eps;logic[4:0]flags,flags_or;logic[31:0]accepted,completed;logic[1567:0]v[0:COUNT-1];integer cycles,seen;logic[63:0]hash;logic stalled;logic[511:0]held;
 fp32_rmsnorm16 dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.x_i(x),.weight_i(w),.epsilon_i(eps),.out_valid_o(ov),.out_ready_i(orr),.y_o(y),.exception_flags_o(flags),.accepted_o(accepted),.completed_o(completed));
 function automatic[63:0]hash_vec(input[63:0]seed,input[511:0]data);reg[63:0]h;begin h=seed;for(int l=0;l<16;l++)h=(h^{32'd0,data[l*32+:32]})*64'h100000001b3;hash_vec=h;end endfunction
 always_comb orr=(cycles%5)!=1;
 always @(posedge clk)begin if(!rst_n)begin cycles<=0;seen<=0;flags_or<=0;hash<=64'hcbf29ce484222325;stalled<=0;held<=0;end else begin cycles<=cycles+1;if(stalled&&(!ov||y!==held))$fatal(1,"rmsnorm stalled");stalled<=ov&&!orr;if(ov&&!orr)held<=y;
  if(ov&&orr)begin if(y!==v[seen][1567:1056])$fatal(1,"rmsnorm mismatch i=%0d flags=%h",seen,flags);flags_or<=flags_or|flags;hash<=hash_vec(hash,y);seen<=seen+1;end end end
 initial begin clk=0;rst_n=0;iv=0;x=0;w=0;eps=0;$readmemh("work/results/l5_rmsnorm/vectors.memh",v);repeat(3)@(posedge clk);rst_n=1;
  for(int i=0;i<COUNT;i++)begin @(negedge clk);x=v[i][511:0];w=v[i][1023:512];eps=v[i][1055:1024];iv=1;do @(posedge clk);while(!ir);@(negedge clk);iv=0;do @(posedge clk);while(!(ov&&orr));end
  wait(seen==COUNT);@(negedge clk);if(accepted!=COUNT||completed!=COUNT)$fatal(1,"rmsnorm counters");$display("FP32_RMSNORM16_PASS vectors=%0d cycles=%0d output_fnv64=%016h flags_or=%h",COUNT,cycles,hash,flags_or);$finish;end
endmodule
