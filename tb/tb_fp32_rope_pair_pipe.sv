`timescale 1ns/1ps
module tb_fp32_rope_pair_pipe;
 parameter integer COUNT=10000;logic clk;/* verilator lint_off SYNCASYNCNET */logic rst_n;/* verilator lint_on SYNCASYNCNET */initial begin clk=0;rst_n=0;end always #5 clk=~clk;
 logic iv,ir,ov,orr;logic[31:0]e,o,c,s,eo,oo;logic[4:0]flags,flags_or;logic[191:0]v[0:COUNT-1];integer cycles,seen;logic stalled;logic[63:0]held;
 fp32_rope_pair_pipe dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.even_i(e),.odd_i(o),.cos_i(c),.sin_i(s),.out_valid_o(ov),.out_ready_i(orr),.even_o(eo),.odd_o(oo),.exception_flags_o(flags));
 always_comb orr=(cycles%6)!=1;
 always@(posedge clk)begin if(!rst_n)begin cycles<=0;seen<=0;flags_or<=0;stalled<=0;held<=0;end else begin cycles<=cycles+1;if(stalled&&(!ov||{oo,eo}!==held))$fatal(1,"RoPE stalled");stalled<=ov&&!orr;if(ov&&!orr)held<={oo,eo};if(ov&&orr)begin if({oo,eo}!==v[seen][191:128]||flags[4:1]!=0)$fatal(1,"RoPE mismatch i=%0d flags=%h",seen,flags);flags_or<=flags_or|flags;seen<=seen+1;end end end
 initial begin iv=0;e=0;o=0;c=0;s=0;$readmemh("work/results/l5_rope/vectors.memh",v);repeat(3)@(posedge clk);rst_n=1;for(int i=0;i<COUNT;i++)begin @(negedge clk);e=v[i][31:0];o=v[i][63:32];c=v[i][95:64];s=v[i][127:96];iv=1;do @(posedge clk);while(!ir);end @(negedge clk);iv=0;wait(seen==COUNT);$display("FP32_ROPE_PAIR_PIPE_PASS vectors=%0d cycles=%0d flags_or=%h",COUNT,cycles,flags_or);$finish;end
 initial begin repeat(300000)@(posedge clk);$fatal(1,"timeout");end
endmodule
