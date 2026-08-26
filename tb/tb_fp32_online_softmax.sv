`timescale 1ns/1ps
module tb_fp32_online_softmax;parameter integer COUNT=10000;logic clk;/* verilator lint_off SYNCASYNCNET */logic rst_n;/* verilator lint_on SYNCASYNCNET */always #5 clk=~clk;
 logic clear,iv,ir,ov,orr;logic[31:0]score,m,l;logic[127:0]value,o;logic[4:0]flags,flags_or;logic[31:0]accepted,completed;logic[352:0]v[0:COUNT-1];integer cycles,seen;logic[63:0]hash;logic stalled;logic[191:0]held;
 fp32_online_softmax #(.LANES(4))dut(.clk_i(clk),.rst_ni(rst_n),.clear_i(clear),.in_valid_i(iv),.in_ready_o(ir),.score_i(score),.value_i(value),.out_valid_o(ov),.out_ready_i(orr),.m_o(m),.l_o(l),.o_o(o),.exception_flags_o(flags),.accepted_tokens_o(accepted),.completed_tokens_o(completed));
 always_comb orr=(cycles%5)!=1;
 always @(posedge clk)begin if(!rst_n)begin cycles<=0;seen<=0;flags_or<=0;hash<=64'hcbf29ce484222325;stalled<=0;held<=0;end else begin cycles<=cycles+1;if(stalled&&(!ov||{o,l,m}!==held))$fatal(1,"softmax stalled");stalled<=ov&&!orr;if(ov&&!orr)held<={o,l,m};
  if(ov&&orr)begin if({o,l,m}!==v[seen][352:161])$fatal(1,"softmax mismatch i=%0d",seen);flags_or<=flags_or|flags;hash<=((hash^{32'd0,m})*64'h100000001b3^{32'd0,l})*64'h100000001b3;seen<=seen+1;end end end
 initial begin clk=0;rst_n=0;clear=0;iv=0;score=0;value=0;$readmemh("work/results/l5_online_softmax/vectors.memh",v);repeat(3)@(posedge clk);rst_n=1;
  for(int i=0;i<COUNT;i++)begin @(negedge clk);clear=v[i][0];score=v[i][32:1];value=v[i][160:33];iv=1;do @(posedge clk);while(!ir);@(negedge clk);iv=0;do @(posedge clk);while(!(ov&&orr));end
  wait(seen==COUNT);@(negedge clk);if(accepted!=COUNT||completed!=COUNT)$fatal(1,"softmax counters");$display("FP32_ONLINE_SOFTMAX_PASS tokens=%0d cycles=%0d output_fnv64=%016h flags_or=%h",COUNT,cycles,hash,flags_or);$finish;end
endmodule
