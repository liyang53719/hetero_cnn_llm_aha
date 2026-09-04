// SPDX-License-Identifier: Apache-2.0
module fp32_reduce_max16(
 input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[511:0]data_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]max_o,output logic[3:0]index_o);
 logic input_valid_q,output_valid_q;logic[511:0]input_q;logic[31:0]max_q;logic[3:0]index_q;
 logic[31:0]l1v[0:7],l2v[0:3],l3v[0:1],l4v;logic[3:0]l1i[0:7],l2i[0:3],l3i[0:1],l4i;
 function automatic logic isnan(input logic[31:0]v);return &v[30:23]&&|v[22:0];endfunction
 function automatic logic better(input logic[31:0]a,input logic[3:0]ai,input logic[31:0]b,input logic[3:0]bi);begin
  if(isnan(a)!=isnan(b))better=!isnan(a);else if(isnan(a))better=ai<bi;
  else if(a[30:0]==0&&b[30:0]==0)better=ai<bi;else if(a[31]!=b[31])better=!a[31];
  else if(!a[31])better=a[30:0]>b[30:0]||(a[30:0]==b[30:0]&&ai<bi);
  else better=a[30:0]<b[30:0]||(a[30:0]==b[30:0]&&ai<bi);end endfunction
 genvar i;generate for(i=0;i<8;i++)begin:g1
  always_comb if(better(input_q[i*64+:32],4'(2*i),input_q[i*64+32+:32],4'(2*i+1)))begin l1v[i]=input_q[i*64+:32];l1i[i]=4'(2*i);end else begin l1v[i]=input_q[i*64+32+:32];l1i[i]=4'(2*i+1);end
 end for(i=0;i<4;i++)begin:g2 always_comb if(better(l1v[2*i],l1i[2*i],l1v[2*i+1],l1i[2*i+1]))begin l2v[i]=l1v[2*i];l2i[i]=l1i[2*i];end else begin l2v[i]=l1v[2*i+1];l2i[i]=l1i[2*i+1];end end
 for(i=0;i<2;i++)begin:g3 always_comb if(better(l2v[2*i],l2i[2*i],l2v[2*i+1],l2i[2*i+1]))begin l3v[i]=l2v[2*i];l3i[i]=l2i[2*i];end else begin l3v[i]=l2v[2*i+1];l3i[i]=l2i[2*i+1];end end endgenerate
 always_comb if(better(l3v[0],l3i[0],l3v[1],l3i[1]))begin l4v=l3v[0];l4i=l3i[0];end else begin l4v=l3v[1];l4i=l3i[1];end
 wire output_ready=!output_valid_q||out_ready_i;assign in_ready_o=!input_valid_q||output_ready;
 assign out_valid_o=output_valid_q;assign max_o=max_q;assign index_o=index_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin input_valid_q<=0;output_valid_q<=0;input_q<=0;max_q<=0;index_q<=0;end else begin
  if(output_ready)begin output_valid_q<=input_valid_q;if(input_valid_q)begin max_q<=l4v;index_q<=l4i;end end
  if(in_ready_o)begin input_valid_q<=in_valid_i;if(in_valid_i)input_q<=data_i;end end end
endmodule
