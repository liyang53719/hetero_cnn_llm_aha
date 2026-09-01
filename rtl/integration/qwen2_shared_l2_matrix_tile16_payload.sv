// SPDX-License-Identifier: Apache-2.0
// One 16-token x 32-column BF16 Matrix tile from K-major Shared-L2 staging.
`timescale 1ns/1ps
module qwen2_shared_l2_matrix_tile16_payload #(parameter integer ADDR_W=15)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[63:0]activation_local_i,weight_local_i,output_local_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic matrix_step_valid_o,input logic matrix_step_ready_i,output logic[2:0]matrix_context_o,output logic matrix_clear_o,matrix_last_o,output logic[255:0]matrix_a_o,output logic[511:0]matrix_b_o,
 input logic matrix_out_valid_i,output logic matrix_out_ready_o,input logic matrix_out_last_i,input logic[16383:0]matrix_acc_i,
 output logic done_o,output logic[31:0]read_beats_o,write_beats_o,matrix_steps_o
);
 typedef enum logic[3:0]{I,ARQ,ARP,WRQ,WRP,MQ,MWAIT,OW,D}st_e;st_e st;logic[10:0]k_q;logic[3:0]row_q;logic[511:0]a_q,w_q;logic[16383:0]acc_q;logic final_seen_q;integer c;
 function automatic[15:0]bf16(input logic[31:0]v);logic[31:0]r;begin r=v+32'h7fff+v[16];return r[31:16];end endfunction
 assign l2_rd_valid_o=st==ARQ||st==WRQ;assign l2_rsp_ready_o=st==ARP||st==WRP;assign l2_rd_addr_o=st==ARQ?ADDR_W'(activation_local_i[ADDR_W+5:6]+k_q):ADDR_W'(weight_local_i[ADDR_W+5:6]+k_q);assign matrix_step_valid_o=st==MQ;assign matrix_context_o=0;assign matrix_clear_o=k_q==0;assign matrix_last_o=k_q==1535;assign matrix_a_o=a_q[255:0];assign matrix_b_o=w_q;assign matrix_out_ready_o=1;assign l2_wr_valid_o=st==OW;assign l2_wr_addr_o=ADDR_W'(output_local_i[ADDR_W+5:6]+row_q);assign l2_wr_be_o='1;assign done_o=st==D;
 always_comb begin l2_wr_data_o=0;for(c=0;c<32;c++)l2_wr_data_o[c*16+:16]=bf16(acc_q[(row_q*32+c)*32+:32]);end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;k_q<=0;row_q<=0;a_q<=0;w_q<=0;acc_q<=0;final_seen_q<=0;read_beats_o<=0;write_beats_o<=0;matrix_steps_o<=0;end else begin if(matrix_out_valid_i&&matrix_out_ready_o&&matrix_out_last_i)begin acc_q<=matrix_acc_i;final_seen_q<=1;end case(st)
  I:if(start_i)begin k_q<=0;row_q<=0;final_seen_q<=0;read_beats_o<=0;write_beats_o<=0;matrix_steps_o<=0;st<=ARQ;end
  ARQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=ARP;ARP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin a_q<=l2_rsp_data_i;read_beats_o<=read_beats_o+1;st<=WRQ;end
  WRQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=WRP;WRP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin w_q<=l2_rsp_data_i;read_beats_o<=read_beats_o+1;st<=MQ;end
  MQ:if(matrix_step_valid_o&&matrix_step_ready_i)begin matrix_steps_o<=matrix_steps_o+1;if(k_q==1535)st<=MWAIT;else begin k_q<=k_q+1;st<=ARQ;end end
  MWAIT:if(final_seen_q)begin row_q<=0;st<=OW;end OW:if(l2_wr_valid_o&&l2_wr_ready_i)begin write_beats_o<=write_beats_o+1;if(row_q==15)st<=D;else row_q<=row_q+1;end D:st<=I;default:st<=I;endcase end end
endmodule
