`timescale 1ns/1ps
module tb_fp32_block32_softmax_weights;
  logic clk,rst_n,start,sv,sr,mask,hv,hr,wv,wr,wl,busy;logic[31:0]score,m,l,w;logic[4:0]flags;integer outputs;
  always #0.5 clk=~clk;
  fp32_block32_softmax_weights dut(.clk_i(clk),.rst_ni(rst_n),.start_i(start),.score_valid_i(sv),.score_ready_o(sr),.score_i(score),.mask_i(mask),.summary_valid_o(hv),.summary_ready_i(hr),.m_o(m),.l_o(l),.weight_valid_o(wv),.weight_ready_i(wr),.weight_o(w),.weight_last_o(wl),.exception_flags_o(flags),.busy_o(busy));
  task automatic run_row(input integer valid_scores);
    begin
      @(negedge clk);start=1;@(posedge clk);@(negedge clk);start=0;
      for(integer i=0;i<32;i++)begin sv=1;score=0;mask=i>=valid_scores;do@(posedge clk);while(!sr);@(negedge clk);end
      sv=0;while(!hv)@(posedge clk);if(m!==0||l!==(valid_scores==32?32'h42000000:32'h41800000))$fatal(1,"summary m=%h l=%h",m,l);
      @(negedge clk);hr=1;@(posedge clk);@(negedge clk);hr=0;outputs=0;wr=1;
      while(outputs<32)begin @(posedge clk);if(wv&&wr)begin if(w!==(outputs<valid_scores?32'h3f800000:0))$fatal(1,"weight %0d=%h",outputs,w);if(wl!==(outputs==31))$fatal(1,"last");outputs++;end end
      @(negedge clk);wr=0;if(flags[4:1]!=0)$fatal(1,"flags=%h",flags);while(busy)@(posedge clk);
    end
  endtask
  initial begin clk=0;rst_n=0;start=0;sv=0;score=0;mask=0;hr=0;wr=0;repeat(6)@(posedge clk);rst_n=1;run_row(32);run_row(16);$display("BLOCK32_SOFTMAX_WEIGHT_PASS rows=2 weights=64");$finish;end
endmodule
