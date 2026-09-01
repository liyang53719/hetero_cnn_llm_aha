// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module qwen2_rope_descriptor_context(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[127:0]command_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,output logic[23:0]descriptor_req_index_o,
 input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
 output logic context_valid_o,input logic context_ready_i,output logic context_legal_o,output logic[7:0]context_status_o,
 output logic[3*56-1:0]tensor_address_o,output logic[17:0]elements_o,output logic[9:0]heads_o,head_dim_o,output logic[5:0]data_beats_o
);
 localparam logic[23:0]NULL_INDEX=24'hffffff;localparam logic[7:0]OK=0,MAL=2,FETCH=3,UNSUP=4;
 typedef enum logic[2:0]{I,RQ,RR,V,C}st_e;st_e st;logic[1:0]slot;logic[4:0]depth;logic[7:0]status;logic[23:0]roots[0:2],current,visited[0:15];logic[55:0]addr[0:2];logic[71:0]shape[0:2];logic saw_base,saw_shape,saw_stride,saw_program;integer ci,si,vi;logic[7:0]rtype;logic[23:0]next_index;logic cycle_hit;
 assign descriptor_req_valid_o=st==RQ;assign descriptor_req_index_o=current;assign descriptor_rsp_ready_o=st==RR;assign context_valid_o=st==C;assign context_legal_o=status==OK;assign context_status_o=status;assign rtype=descriptor_rsp_data_i[7:0];assign next_index=descriptor_rsp_data_i[55:32];assign elements_o=shape[0][35:18];assign heads_o=shape[2][35:18];assign head_dim_o=shape[2][53:36];assign data_beats_o=6'((elements_o+31)/32);
 always_comb begin tensor_address_o=0;cycle_hit=0;for(ci=0;ci<3;ci++)tensor_address_o[ci*56+:56]=addr[ci];for(vi=0;vi<16;vi++)if(vi<=depth&&visited[vi]==next_index)cycle_hit=1;end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;slot<=0;depth<=0;status<=OK;current<=NULL_INDEX;saw_base<=0;saw_shape<=0;saw_stride<=0;saw_program<=0;for(si=0;si<3;si++)begin roots[si]<=NULL_INDEX;addr[si]<=0;shape[si]<=0;end for(si=0;si<16;si++)visited[si]<=NULL_INDEX;end else case(st)
  I:if(start_i)begin roots[0]<=command_i[79:56];roots[1]<=command_i[103:80];roots[2]<=command_i[127:104];slot<=0;depth<=0;status<=OK;current<=command_i[79:56];visited[0]<=command_i[79:56];saw_base<=0;saw_shape<=0;saw_stride<=0;saw_program<=0;if(command_i[7:0]!=8'h34||command_i[10:8]!=3'd3||command_i[79:56]==NULL_INDEX||command_i[103:80]==NULL_INDEX||command_i[127:104]==NULL_INDEX)begin status<=MAL;st<=C;end else st<=RQ;end
  RQ:if(descriptor_req_valid_o&&descriptor_req_ready_i)st<=RR;
  RR:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin
   if(descriptor_rsp_error_i)begin status<=FETCH;st<=C;end else if(descriptor_rsp_data_i[31:8]!=0||depth>=16)begin status<=MAL;st<=C;end
   else if((depth==0&&rtype!=8'h01)||(rtype==8'h01&&saw_base)||(rtype==8'h02&&saw_shape)||(rtype==8'h03&&saw_stride)||(rtype==8'h20&&(slot!=0||saw_program))||!(rtype inside {8'h01,8'h02,8'h03,8'h20}))begin status<=MAL;st<=C;end
   else if(rtype==8'h01&&((descriptor_rsp_data_i[107:104]!=0)||(descriptor_rsp_data_i[115:112]!=0)||((slot==1)&&(descriptor_rsp_data_i[111:108]!=4))||((slot!=1)&&(descriptor_rsp_data_i[111:108]!=5))))begin status<=UNSUP;st<=C;end
   else if(rtype==8'h20&&descriptor_rsp_data_i[127:56]!={8'd0,8'd0,8'd0,8'd16,4'd5,4'd5,8'd1,8'd2,16'h0034})begin status<=UNSUP;st<=C;end
   else begin
    if(rtype==8'h01)begin saw_base<=1;addr[slot]<={descriptor_rsp_data_i[127:120],descriptor_rsp_data_i[103:56]};end
    if(rtype==8'h02)begin saw_shape<=1;shape[slot]<=descriptor_rsp_data_i[127:56];end
    if(rtype==8'h03)saw_stride<=1;if(rtype==8'h20)saw_program<=1;
    if(next_index==NULL_INDEX)begin
     if(!(saw_base||rtype==8'h01)||!(saw_shape||rtype==8'h02)||!(saw_stride||rtype==8'h03)||(slot==0&&!(saw_program||rtype==8'h20)))begin status<=MAL;st<=C;end
     else if(slot==2)st<=V;
     else begin slot<=slot+1;depth<=0;current<=roots[slot+1];visited[0]<=roots[slot+1];saw_base<=0;saw_shape<=0;saw_stride<=0;saw_program<=0;st<=RQ;end
    end else if(cycle_hit)begin status<=MAL;st<=C;end else begin depth<=depth+1;current<=next_index;visited[depth+1]<=next_index;st<=RQ;end
   end
  end
  V:begin if(shape[0][17:0]!=1024||shape[0][35:18]==0||shape[0][22:18]!=0||shape[1][17:0]!=1024||shape[2][17:0]!=1024||shape[2][35:18]*shape[2][53:36]!=shape[0][35:18]||shape[2][53:36]!=128||shape[0][35:18]>1536)status<=UNSUP;st<=C;end
  C:if(context_valid_o&&context_ready_i)st<=I;default:st<=I;endcase end
endmodule
