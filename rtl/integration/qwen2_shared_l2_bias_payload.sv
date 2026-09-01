// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module qwen2_shared_l2_bias_payload #(parameter integer ADDR_W=15)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[5:0]data_beats_i,input logic[6:0]bias_beats_i,
 input logic[63:0]raw_local_i,bias_local_i,out_local_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic done_o,output logic[31:0]read_beats_o,write_beats_o,output logic[4:0]exception_flags_o
);
 typedef enum logic[3:0]{I,RRQ,RRP,BRQ,BRP,AQ,AP,OW,D}st_e;st_e st;logic[6:0]idx;logic[5:0]outidx,data_beats;logic[6:0]bias_beats;logic[511:0]raw[0:47],bias[0:95],addout,out_q;logic addv,addrdy,addov,addor;logic[4:0]addflags;logic[31:0]aa,ac;
 bf16_bias_add_tile32 add(.clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(addv),.in_ready_o(addrdy),.data_i(raw[outidx]),.bias_i({bias[outidx*2+1],bias[outidx*2]}),.out_valid_o(addov),.out_ready_i(addor),.data_o(addout),.exception_flags_o(addflags),.accepted_o(aa),.completed_o(ac));
 assign l2_rd_valid_o=st==RRQ||st==BRQ;assign l2_rsp_ready_o=st==RRP||st==BRP;assign l2_rd_addr_o=st==RRQ?ADDR_W'(raw_local_i[ADDR_W+5:6]+idx):ADDR_W'(bias_local_i[ADDR_W+5:6]+idx);assign addv=st==AQ;assign addor=st==AP;assign l2_wr_valid_o=st==OW;assign l2_wr_addr_o=ADDR_W'(out_local_i[ADDR_W+5:6]+outidx);assign l2_wr_data_o=out_q;assign l2_wr_be_o='1;assign done_o=st==D;assign exception_flags_o=addflags;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;idx<=0;outidx<=0;data_beats<=0;bias_beats<=0;out_q<=0;read_beats_o<=0;write_beats_o<=0;end else case(st)
  I:if(start_i)begin idx<=0;outidx<=0;data_beats<=data_beats_i;bias_beats<=bias_beats_i;read_beats_o<=0;write_beats_o<=0;st<=RRQ;end
  RRQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=RRP;RRP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin raw[idx]<=l2_rsp_data_i;read_beats_o<=read_beats_o+1;if(idx+1==data_beats)begin idx<=0;st<=BRQ;end else begin idx<=idx+1;st<=RRQ;end end
  BRQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=BRP;BRP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin bias[idx]<=l2_rsp_data_i;read_beats_o<=read_beats_o+1;if(idx+1==bias_beats)begin outidx<=0;st<=AQ;end else begin idx<=idx+1;st<=BRQ;end end
  AQ:if(addv&&addrdy)st<=AP;AP:if(addov&&addor)begin out_q<=addout;st<=OW;end OW:if(l2_wr_valid_o&&l2_wr_ready_i)begin write_beats_o<=write_beats_o+1;if(outidx+1==data_beats)st<=D;else begin outidx<=outidx+1;st<=AQ;end end D:st<=I;default:st<=I;endcase end
endmodule
