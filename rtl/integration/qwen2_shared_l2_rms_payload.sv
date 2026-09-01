// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module qwen2_shared_l2_rms_payload #(parameter integer ADDR_W=15)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[63:0]hidden_local_i,weight_local_i,norm_local_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,
 input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,
 output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic sfu_payload_valid_o,input logic sfu_payload_ready_i,output logic[49151:0]sfu_x_o,sfu_weight_o,
 input logic sfu_out_valid_i,output logic sfu_out_ready_o,input logic[49151:0]sfu_y_i,
 output logic done_o,output logic[31:0]read_beats_o,write_beats_o
);
 typedef enum logic[3:0]{I,XRQ,XRP,WRQ,WRP,FQ,FP,NW,D}st_e;st_e st;logic[6:0]beat;logic[49151:0]x,w,y;integer c,s;
 function automatic[15:0]bf(input[31:0]v);logic[31:0]r;begin r=v+32'h7fff+v[16];return r[31:16];end endfunction
 assign sfu_x_o=x;assign sfu_weight_o=w;assign l2_rd_valid_o=st==XRQ||st==WRQ;assign l2_rsp_ready_o=st==XRP||st==WRP;
 always_comb begin l2_rd_addr_o=0;if(st==XRQ)l2_rd_addr_o=ADDR_W'(hidden_local_i[ADDR_W+5:6]+beat);if(st==WRQ)l2_rd_addr_o=ADDR_W'(weight_local_i[ADDR_W+5:6]+beat);l2_wr_valid_o=st==NW;l2_wr_addr_o=ADDR_W'(norm_local_i[ADDR_W+5:6]+beat);l2_wr_data_o=0;l2_wr_be_o='1;for(c=0;c<32;c++)l2_wr_data_o[c*16+:16]=bf(y[(beat*32+c)*32+:32]);sfu_payload_valid_o=st==FQ;sfu_out_ready_o=st==FP;done_o=st==D;end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;beat<=0;x<=0;w<=0;y<=0;read_beats_o<=0;write_beats_o<=0;end else case(st)
  I:if(start_i)begin beat<=0;read_beats_o<=0;write_beats_o<=0;st<=XRQ;end
  XRQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=XRP;
  XRP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin for(s=0;s<32;s++)x[(beat*32+s)*32+:32]<={l2_rsp_data_i[s*16+:16],16'd0};read_beats_o<=read_beats_o+1;if(beat==47)begin beat<=0;st<=WRQ;end else begin beat<=beat+1;st<=XRQ;end end
  WRQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=WRP;
  WRP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin for(s=0;s<16;s++)w[(beat*16+s)*32+:32]<=l2_rsp_data_i[s*32+:32];read_beats_o<=read_beats_o+1;if(beat==95)begin beat<=0;st<=FQ;end else begin beat<=beat+1;st<=WRQ;end end
  FQ:if(sfu_payload_valid_o&&sfu_payload_ready_i)st<=FP;
  FP:if(sfu_out_valid_i&&sfu_out_ready_o)begin y<=sfu_y_i;beat<=0;st<=NW;end
  NW:if(l2_wr_valid_o&&l2_wr_ready_i)begin write_beats_o<=write_beats_o+1;if(beat==47)st<=D;else beat<=beat+1;end
  D:st<=I;default:st<=I;endcase end
endmodule
