// SPDX-License-Identifier: Apache-2.0
// Sixteen canonical RMSNorm rows followed by token-major to K-major transpose.
`timescale 1ns/1ps
module qwen2_shared_l2_rms_tile16_stager #(parameter integer ADDR_W=15)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[63:0]hidden_local_i,weight_local_i,norm_token_local_i,norm_kmajor_local_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic done_o,output logic[31:0]read_beats_o,write_beats_o,rms_vectors_o,transpose_values_o,output logic[4:0]exception_flags_o
);
 typedef enum logic[3:0]{I,WQ,WP,XQ,XP,RQ,RP,NW,TQ,TP,TW,D}st_e;st_e st;logic[6:0]beat_q;logic[3:0]token_q;logic[10:0]k_q;logic[49151:0]x_q,weight_q,y_q;logic[511:0]transpose_q;logic riv,rir,rov,ror;logic[4:0]rflags,flags_q;logic[31:0]ra,rc,qc,oc;integer comb_lane,seq_lane;
 function automatic[15:0]bf16(input logic[31:0]v);logic[31:0]r;begin r=v+32'h7fff+v[16];return r[31:16];end endfunction
 fp32_rmsnorm1536_chunked #(.REFINE_RSQRT(1'b1))rms(.clk_i,.rst_ni,.in_valid_i(riv),.in_ready_o(rir),.x_i(x_q),.weight_i(weight_q),.epsilon_i(32'h358637bd),.out_valid_o(rov),.out_ready_i(ror),.y_o(y_q),.exception_flags_o(rflags),.accepted_o(ra),.completed_o(rc),.reduction_cycles_o(qc),.rsqrt_cycles_o(),.output_cycles_o(oc));
 assign l2_rd_valid_o=st==WQ||st==XQ||st==TQ;assign l2_rsp_ready_o=st==WP||st==XP||st==TP;assign riv=st==RQ;assign ror=st==RP;assign l2_wr_valid_o=st==NW||st==TW;assign l2_wr_be_o='1;assign done_o=st==D;assign exception_flags_o=flags_q;
 always_comb begin l2_rd_addr_o=0;if(st==WQ)l2_rd_addr_o=ADDR_W'(weight_local_i[ADDR_W+5:6]+beat_q);if(st==XQ)l2_rd_addr_o=ADDR_W'(hidden_local_i[ADDR_W+5:6]+token_q*48+beat_q);if(st==TQ)l2_rd_addr_o=ADDR_W'(norm_token_local_i[ADDR_W+5:6]+token_q*48+(k_q>>5));l2_wr_addr_o=0;l2_wr_data_o=0;if(st==NW)begin l2_wr_addr_o=ADDR_W'(norm_token_local_i[ADDR_W+5:6]+token_q*48+beat_q);for(comb_lane=0;comb_lane<32;comb_lane++)l2_wr_data_o[comb_lane*16+:16]=bf16(y_q[(beat_q*32+comb_lane)*32+:32]);end if(st==TW)begin l2_wr_addr_o=ADDR_W'(norm_kmajor_local_i[ADDR_W+5:6]+k_q);l2_wr_data_o=transpose_q;end end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;beat_q<=0;token_q<=0;k_q<=0;x_q<=0;weight_q<=0;transpose_q<=0;flags_q<=0;read_beats_o<=0;write_beats_o<=0;rms_vectors_o<=0;transpose_values_o<=0;end else case(st)
  I:if(start_i)begin beat_q<=0;token_q<=0;k_q<=0;flags_q<=0;read_beats_o<=0;write_beats_o<=0;rms_vectors_o<=0;transpose_values_o<=0;st<=WQ;end
  WQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=WP;WP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin for(seq_lane=0;seq_lane<16;seq_lane++)weight_q[(beat_q*16+seq_lane)*32+:32]<=l2_rsp_data_i[seq_lane*32+:32];read_beats_o<=read_beats_o+1;if(beat_q==95)begin beat_q<=0;st<=XQ;end else begin beat_q<=beat_q+1;st<=WQ;end end
  XQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=XP;XP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin for(seq_lane=0;seq_lane<32;seq_lane++)x_q[(beat_q*32+seq_lane)*32+:32]<={l2_rsp_data_i[seq_lane*16+:16],16'd0};read_beats_o<=read_beats_o+1;if(beat_q==47)begin beat_q<=0;st<=RQ;end else begin beat_q<=beat_q+1;st<=XQ;end end
  RQ:if(riv&&rir)st<=RP;RP:if(rov&&ror)begin flags_q<=flags_q|rflags;rms_vectors_o<=rms_vectors_o+1;beat_q<=0;st<=NW;end
  NW:if(l2_wr_valid_o&&l2_wr_ready_i)begin write_beats_o<=write_beats_o+1;if(beat_q==47)begin beat_q<=0;if(token_q==15)begin token_q<=0;k_q<=0;transpose_q<=0;st<=TQ;end else begin token_q<=token_q+1;st<=XQ;end end else beat_q<=beat_q+1;end
  TQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=TP;TP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin transpose_q[token_q*16+:16]<=l2_rsp_data_i[(k_q[4:0])*16+:16];read_beats_o<=read_beats_o+1;transpose_values_o<=transpose_values_o+1;if(token_q==15)begin token_q<=0;st<=TW;end else begin token_q<=token_q+1;st<=TQ;end end
  TW:if(l2_wr_valid_o&&l2_wr_ready_i)begin write_beats_o<=write_beats_o+1;transpose_q<=0;if(k_q==1535)st<=D;else begin k_q<=k_q+1;st<=TQ;end end D:st<=I;default:st<=I;endcase end
endmodule
