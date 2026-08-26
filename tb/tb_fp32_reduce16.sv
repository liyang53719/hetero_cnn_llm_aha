`timescale 1ns/1ps
module tb_fp32_reduce16;parameter integer COUNT=10000;logic clk;/* verilator lint_off SYNCASYNCNET */logic rst_n;/* verilator lint_on SYNCASYNCNET */always #5 clk=~clk;
  logic iv,ir,ov,orr;logic[511:0]data;logic[31:0]sum;logic[4:0]flags,flags_or;logic[31:0]accepted,completed;logic[543:0]v[0:COUNT-1];integer cycles,seen;logic[63:0]hash;logic stalled;logic[31:0]held;
  fp32_reduce16 dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.data_i(data),.out_valid_o(ov),.out_ready_i(orr),.sum_o(sum),.exception_flags_o(flags),.accepted_vectors_o(accepted),.completed_vectors_o(completed));
  always_comb orr=(cycles%5)!=1;
  always @(posedge clk)begin if(!rst_n)begin cycles<=0;seen<=0;hash<=64'hcbf29ce484222325;flags_or<=0;stalled<=0;held<=0;end else begin cycles<=cycles+1;
    if(stalled&&(!ov||sum!==held))$fatal(1,"FP32 reduce stalled");stalled<=ov&&!orr;if(ov&&!orr)held<=sum;
    if(ov&&orr)begin if(sum!==v[seen][543:512]||flags[4:1]!=0)$fatal(1,"FP32 reduce mismatch i=%0d flags=%h",seen,flags);flags_or<=flags_or|flags;hash<=(hash^{32'd0,sum})*64'h00000100000001b3;seen<=seen+1;end end end
  initial begin clk=0;rst_n=0;iv=0;data=0;$readmemh("work/results/l5_fp32_reduce/vectors.memh",v);repeat(3)@(posedge clk);rst_n=1;
    for(int i=0;i<COUNT;i++)begin @(negedge clk);data=v[i][511:0];iv=1;do @(posedge clk);while(!ir);end
    @(negedge clk);iv=0;wait(seen==COUNT);@(negedge clk);if(accepted!=COUNT||completed!=COUNT)$fatal(1,"FP32 reduce counters");
    $display("FP32_REDUCE16_PASS vectors=%0d cycles=%0d accept_interval=1 output_fnv64=%016h flags_or=%h",COUNT,cycles,hash,flags_or);$finish;end
endmodule
