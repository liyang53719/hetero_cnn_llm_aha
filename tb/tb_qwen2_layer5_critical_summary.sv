`timescale 1ns/1ps
module tb_qwen2_layer5_critical_summary;
 logic clk,rst_n,start,hiv,hir,biv,bir,blast,hov,hor,bov,bor,bol,busy,done,perr;logic[3:0]count;logic[31:0]mi,li,mo,lo,merges,lfsr;logic[127:0]oi,oo;logic[63:0]headers[0:6],expected_header[0:0];logic[127:0]beats[0:223],expected_beats[0:31];integer output_count,stalls;
 always #0.5 clk=~clk;always_ff@(posedge clk)if(!rst_n)lfsr<=32'h5c17a1;else lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
 fp32_mlo_balanced_summary_scheduler dut(.clk_i(clk),.rst_ni(rst_n),.start_i(start),.summary_count_i(count),.header_valid_i(hiv),.header_ready_o(hir),.m_i(mi),.l_i(li),.beat_valid_i(biv),.beat_ready_o(bir),.o_i(oi),.beat_last_i(blast),.header_valid_o(hov),.header_ready_i(hor),.m_o(mo),.l_o(lo),.beat_valid_o(bov),.beat_ready_i(bor),.o_o(oo),.beat_last_o(bol),.busy_o(busy),.done_o(done),.protocol_error_o(perr),.merges_completed_o(merges));
 task automatic send_header(input logic[63:0]x);begin @(negedge clk);mi=x[31:0];li=x[63:32];hiv=1;do@(posedge clk);while(!hir);@(negedge clk);hiv=0;end endtask
 task automatic send_beat(input logic[127:0]x,input logic last);begin @(negedge clk);oi=x;blast=last;biv=1;do@(posedge clk);while(!bir);@(negedge clk);biv=0;end endtask
 initial begin clk=0;rst_n=0;start=0;hiv=0;biv=0;blast=0;hor=0;bor=0;mi=0;li=0;oi=0;count=7;output_count=0;stalls=0;$readmemh("work/results/qwen2_layer5_critical_summary/headers.memh",headers);$readmemh("work/results/qwen2_layer5_critical_summary/beats.memh",beats);$readmemh("work/results/qwen2_layer5_critical_summary/expected_header.memh",expected_header);$readmemh("work/results/qwen2_layer5_critical_summary/expected_beats.memh",expected_beats);repeat(6)@(posedge clk);rst_n=1;@(negedge clk);start=1;@(posedge clk);@(negedge clk);start=0;for(integer s=0;s<7;s++)begin send_header(headers[s]);for(integer b=0;b<32;b++)send_beat(beats[s*32+b],b==31);end
  while(!hov)@(posedge clk);@(negedge clk);hor=1;@(posedge clk);if({lo,mo}!==expected_header[0])$fatal(1,"header");@(negedge clk);hor=0;
  while(output_count<32)begin @(negedge clk);bor=lfsr[0]||lfsr[5];if(bov&&!bor)stalls++;@(posedge clk);if(bov&&bor)begin if(oo!==expected_beats[output_count]||bol!==(output_count==31))$fatal(1,"beat=%0d",output_count);output_count++;end end @(negedge clk);bor=0;if(perr||merges!=6)$fatal(1,"accounting");$display("QWEN2_LAYER5_CRITICAL_BALANCED_RTL_PASS query=848 head=2 blocks=7 merges=6 beats=32 stalls=%0d",stalls);$finish;
 end
 initial begin repeat(200000)@(posedge clk);$fatal(1,"timeout");end
endmodule
