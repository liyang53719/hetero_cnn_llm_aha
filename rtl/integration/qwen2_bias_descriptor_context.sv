// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module qwen2_bias_descriptor_context(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[127:0]command_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,output logic[23:0]descriptor_req_index_o,
 input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
 output logic context_valid_o,input logic context_ready_i,output logic context_legal_o,output logic[7:0]context_status_o,
 output logic[3*56-1:0]tensor_address_o,output logic[17:0]elements_o,output logic[5:0]data_beats_o,output logic[6:0]bias_beats_o
);
 localparam logic[7:0]OK=0,MAL=2,FETCH=3,UNSUP=4;typedef enum logic[2:0]{I,RQ,RR,SQ,SR,V,C}st_e;st_e st;logic[1:0]slot;logic[7:0]status;logic[23:0]roots[0:2],next;logic[55:0]addr[0:2];logic[71:0]shape[0:2];integer ci,si;
 assign descriptor_req_valid_o=st==RQ||st==SQ;assign descriptor_req_index_o=st==RQ?roots[slot]:next;assign descriptor_rsp_ready_o=st==RR||st==SR;assign context_valid_o=st==C;assign context_legal_o=status==OK;assign context_status_o=status;assign elements_o=shape[2][35:18];assign data_beats_o=6'((elements_o+31)/32);assign bias_beats_o=7'((elements_o+15)/16);
 always_comb begin tensor_address_o=0;for(ci=0;ci<3;ci++)tensor_address_o[ci*56+:56]=addr[ci];end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;slot<=0;status<=OK;next<=0;for(si=0;si<3;si++)begin roots[si]<=24'hffffff;addr[si]<=0;shape[si]<=0;end end else case(st)
  I:if(start_i)begin roots[0]<=command_i[79:56];roots[1]<=command_i[103:80];roots[2]<=command_i[127:104];slot<=0;status<=OK;if(command_i[7:0]!=8'h30||command_i[10:8]!=3'd3||command_i[79:56]==24'hffffff||command_i[103:80]==24'hffffff||command_i[127:104]==24'hffffff)begin status<=MAL;st<=C;end else st<=RQ;end
  RQ:if(descriptor_req_valid_o&&descriptor_req_ready_i)st<=RR;
  RR:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin if(descriptor_rsp_error_i)begin status<=FETCH;st<=C;end else if(descriptor_rsp_data_i[31:8]!=0)begin status<=MAL;st<=C;end else if(descriptor_rsp_data_i[7:0]!=1||descriptor_rsp_data_i[107:104]!=0||descriptor_rsp_data_i[115:112]!=0||descriptor_rsp_data_i[55:32]==24'hffffff||((slot==1)&&descriptor_rsp_data_i[111:108]!=7)||((slot!=1)&&descriptor_rsp_data_i[111:108]!=5))begin status<=UNSUP;st<=C;end else begin addr[slot]<={descriptor_rsp_data_i[127:120],descriptor_rsp_data_i[103:56]};next<=descriptor_rsp_data_i[55:32];st<=SQ;end end
  SQ:if(descriptor_req_valid_o&&descriptor_req_ready_i)st<=SR;
  SR:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin if(descriptor_rsp_error_i)begin status<=FETCH;st<=C;end else if(descriptor_rsp_data_i[31:8]!=0)begin status<=MAL;st<=C;end else if(descriptor_rsp_data_i[7:0]!=2)begin status<=UNSUP;st<=C;end else begin shape[slot]<=descriptor_rsp_data_i[127:56];if(slot==2)st<=V;else begin slot<=slot+1;st<=RQ;end end end
  V:begin if(shape[0][17:0]!=1024||shape[0][35:18]==0||shape[0][22:18]!=0||shape[1][17:0]!=shape[0][35:18]||shape[2]!=shape[0])status<=UNSUP;st<=C;end
  C:if(context_valid_o&&context_ready_i)st<=I;default:st<=I;endcase end
endmodule
