// SPDX-License-Identifier: Apache-2.0
// Canonical q1024 KV-append descriptor parser. All four metadata records and
// the referenced DDR page-table tensor are fetched before context issue.
`timescale 1ns/1ps
module qwen2_kv_append_descriptor_v3_context(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[127:0]command_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,output logic[23:0]descriptor_req_index_o,
 input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
 output logic context_valid_o,input logic context_ready_i,output logic context_legal_o,output logic[7:0]context_status_o,
 output logic[63:0]k_address_o,v_address_o,table_address_o,data_address_o,
 output logic[31:0]sequence_id_o,token_start_o,token_count_o,generation_o,logical_page_count_o,
 output logic[11:0]layer_id_o,output logic[9:0]kv_heads_o,head_dim_o,
 output logic[23:0]physical_page_limit_o,output logic[5:0]page_id_bits_o,
 output logic[4:0]page_tokens_log2_o,output logic[3:0]pte_bytes_log2_o
);
 localparam logic[23:0]NULL_INDEX=24'hffffff;localparam logic[7:0]OK=0,MAL=2,FETCH=3,UNSUP=4;
 typedef enum logic[2:0]{I,RQ,RR,V,C}st_e;st_e st;logic[2:0]slot;logic[2:0]depth;logic[7:0]status;logic[23:0]roots[0:2],current,table_root,next_index;logic[7:0]rtype,expected_type;logic expected_last;logic[71:0]shape_k,shape_v,shape_table;logic[3:0]dtype_k,dtype_v,dtype_table,rank_k,rank_v,rank_table;logic[11:0]kv_head_id;logic[2:0]levels;logic[5:0]table_flags;logic[7:0]context_flags,range_flags,epoch_flags;
 assign descriptor_req_valid_o=st==RQ;assign descriptor_req_index_o=current;assign descriptor_rsp_ready_o=st==RR;assign context_valid_o=st==C;assign context_legal_o=status==OK;assign context_status_o=status;assign rtype=descriptor_rsp_data_i[7:0];assign next_index=descriptor_rsp_data_i[55:32];
 always_comb begin expected_type=0;expected_last=0;if(slot==2)begin case(depth)0:expected_type=8'h32;1:expected_type=8'h33;2:expected_type=8'h34;3:begin expected_type=8'h35;expected_last=1;end default:expected_type=0;endcase end else begin case(depth)0:expected_type=8'h01;1:expected_type=8'h02;2:begin expected_type=8'h03;expected_last=1;end default:expected_type=0;endcase end end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;slot<=0;depth<=0;status<=OK;current<=NULL_INDEX;table_root<=NULL_INDEX;k_address_o<=0;v_address_o<=0;table_address_o<=0;data_address_o<=0;sequence_id_o<=0;token_start_o<=0;token_count_o<=0;generation_o<=0;logical_page_count_o<=0;layer_id_o<=0;kv_head_id<=0;kv_heads_o<=0;head_dim_o<=0;physical_page_limit_o<=0;page_id_bits_o<=0;levels<=0;page_tokens_log2_o<=0;pte_bytes_log2_o<=0;shape_k<=0;shape_v<=0;shape_table<=0;dtype_k<=0;dtype_v<=0;dtype_table<=0;rank_k<=0;rank_v<=0;rank_table<=0;context_flags<=0;range_flags<=0;table_flags<=0;epoch_flags<=0;roots[0]<=NULL_INDEX;roots[1]<=NULL_INDEX;roots[2]<=NULL_INDEX;end else case(st)
  I:if(start_i)begin roots[0]<=command_i[79:56];roots[1]<=command_i[103:80];roots[2]<=command_i[127:104];slot<=0;depth<=0;status<=OK;current<=command_i[79:56];if(command_i[7:0]!=8'h41||command_i[10:8]!=3'd4||command_i[79:56]==NULL_INDEX||command_i[103:80]==NULL_INDEX||command_i[127:104]==NULL_INDEX)begin status<=MAL;st<=C;end else st<=RQ;end
  RQ:if(descriptor_req_valid_o&&descriptor_req_ready_i)st<=RR;
  RR:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin
   if(descriptor_rsp_error_i)begin status<=FETCH;st<=C;end else if(descriptor_rsp_data_i[31:8]!=0||rtype!=expected_type||expected_type==0||(expected_last&&(next_index!=NULL_INDEX))||(!expected_last&&(next_index==NULL_INDEX)))begin status<=MAL;st<=C;end else begin
    case(slot)
     0:case(depth)0:begin k_address_o<={8'd0,descriptor_rsp_data_i[127:120],descriptor_rsp_data_i[103:56]};dtype_k<=descriptor_rsp_data_i[111:108];rank_k<=descriptor_rsp_data_i[119:116];end 1:shape_k<=descriptor_rsp_data_i[127:56];default:begin end endcase
     1:case(depth)0:begin v_address_o<={8'd0,descriptor_rsp_data_i[127:120],descriptor_rsp_data_i[103:56]};dtype_v<=descriptor_rsp_data_i[111:108];rank_v<=descriptor_rsp_data_i[119:116];end 1:shape_v<=descriptor_rsp_data_i[127:56];default:begin end endcase
     2:case(depth)
       0:begin sequence_id_o<=descriptor_rsp_data_i[87:56];layer_id_o<=descriptor_rsp_data_i[99:88];kv_head_id<=descriptor_rsp_data_i[111:100];context_flags<=descriptor_rsp_data_i[119:112]|descriptor_rsp_data_i[127:120];end
       1:begin token_start_o<=descriptor_rsp_data_i[87:56];token_count_o<=descriptor_rsp_data_i[119:88];range_flags<=descriptor_rsp_data_i[127:120];end
       2:begin table_root<=descriptor_rsp_data_i[79:56];physical_page_limit_o<=descriptor_rsp_data_i[103:80];page_id_bits_o<=descriptor_rsp_data_i[109:104];levels<=descriptor_rsp_data_i[112:110];page_tokens_log2_o<=descriptor_rsp_data_i[117:113];pte_bytes_log2_o<=descriptor_rsp_data_i[121:118];table_flags<=descriptor_rsp_data_i[127:122];end
       3:begin generation_o<=descriptor_rsp_data_i[87:56];logical_page_count_o<=descriptor_rsp_data_i[119:88];epoch_flags<=descriptor_rsp_data_i[127:120];end default:begin end endcase
     3:case(depth)0:begin table_address_o<={8'd0,descriptor_rsp_data_i[127:120],descriptor_rsp_data_i[103:56]};dtype_table<=descriptor_rsp_data_i[111:108];rank_table<=descriptor_rsp_data_i[119:116];end 1:shape_table<=descriptor_rsp_data_i[127:56];default:begin end endcase
     default:begin end
    endcase
    if(expected_last)begin depth<=0;if(slot==0)begin slot<=1;current<=roots[1];st<=RQ;end else if(slot==1)begin slot<=2;current<=roots[2];st<=RQ;end else if(slot==2)begin if(table_root==NULL_INDEX)begin status<=MAL;st<=C;end else begin slot<=3;current<=table_root;st<=RQ;end end else st<=V;end else begin depth<=depth+1;current<=next_index;st<=RQ;end
   end
  end
  V:begin data_address_o<=table_address_o+64'h8000;kv_heads_o<=shape_k[35:18];head_dim_o<=shape_k[53:36];if(dtype_k!=5||rank_k!=3||shape_k[17:0]!=1024||shape_k[35:18]!=2||shape_k[53:36]!=128||dtype_v!=5||rank_v!=2||shape_v[17:0]!=1024||shape_v[35:18]!=256||dtype_table!=4||rank_table!=3||shape_table[17:0]!=2||shape_table[35:18]!=1024||shape_table[53:36]!=4||sequence_id_o!=0||layer_id_o>=28||kv_head_id!=0||token_start_o!=0||token_count_o!=1024||generation_o!=0||logical_page_count_o!=64||physical_page_limit_o!=4096||page_id_bits_o!=32||levels!=2||page_tokens_log2_o!=4||pte_bytes_log2_o!=4||context_flags!=0||range_flags!=0||table_flags!=0||epoch_flags!=0)status<=UNSUP;st<=C;end
  C:if(context_valid_o&&context_ready_i)st<=I;default:st<=I;endcase end
endmodule
