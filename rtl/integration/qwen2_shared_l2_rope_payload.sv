// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module qwen2_shared_l2_rope_payload #(parameter integer ADDR_W=15)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[5:0]data_beats_i,input logic[9:0]heads_i,head_dim_i,
 input logic[63:0]data_local_i,position_local_i,out_local_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic done_o,output logic unsupported_position_o,output logic[31:0]read_beats_o,write_beats_o,pairs_o,output logic[4:0]exception_flags_o
);
 typedef enum logic[3:0]{I,DRQ,DRP,PRQ,PRP,FQ,FP,OW,D}st_e;st_e st;logic[5:0]idx,data_beats;logic[9:0]heads,head_dim;logic[15:0]pair_idx,total_pairs;logic[511:0]data_mem[0:47],out_mem[0:47];logic riv,rir,rov,ror;logic[31:0]re,ro,rcos,rsin,roe,roo;logic[4:0]rflags;logic[31:0]accepted,completed;integer element_even,element_odd;
 function automatic[15:0]bf16(input logic[31:0]v);logic[31:0]r;begin r=v+32'h7fff+v[16];return r[31:16];end endfunction
 fp32_rope_pair rope(.clk_i,.rst_ni,.in_valid_i(riv),.in_ready_o(rir),.even_i(re),.odd_i(ro),.cos_i(rcos),.sin_i(rsin),.out_valid_o(rov),.out_ready_i(ror),.even_o(roe),.odd_o(roo),.exception_flags_o(rflags),.accepted_pairs_o(accepted),.completed_pairs_o(completed));
 always_comb begin element_even=(pair_idx/64)*head_dim+(pair_idx%64);element_odd=element_even+64;re={data_mem[element_even/32][(element_even%32)*16+:16],16'd0};ro={data_mem[element_odd/32][(element_odd%32)*16+:16],16'd0};end
 assign rcos=32'h3f800000;assign rsin=0;assign l2_rd_valid_o=st==DRQ||st==PRQ;assign l2_rsp_ready_o=st==DRP||st==PRP;assign l2_rd_addr_o=st==DRQ?ADDR_W'(data_local_i[ADDR_W+5:6]+idx):ADDR_W'(position_local_i[ADDR_W+5:6]);assign riv=st==FQ;assign ror=st==FP;assign l2_wr_valid_o=st==OW;assign l2_wr_addr_o=ADDR_W'(out_local_i[ADDR_W+5:6]+idx);assign l2_wr_data_o=out_mem[idx];assign l2_wr_be_o='1;assign done_o=st==D;assign pairs_o=total_pairs;assign exception_flags_o=rflags;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;idx<=0;data_beats<=0;heads<=0;head_dim<=0;pair_idx<=0;total_pairs<=0;unsupported_position_o<=0;read_beats_o<=0;write_beats_o<=0;end else case(st)
  I:if(start_i)begin idx<=0;data_beats<=data_beats_i;heads<=heads_i;head_dim<=head_dim_i;total_pairs<=heads_i*64;pair_idx<=0;unsupported_position_o<=0;read_beats_o<=0;write_beats_o<=0;st<=DRQ;end
  DRQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=DRP;DRP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin data_mem[idx]<=l2_rsp_data_i;read_beats_o<=read_beats_o+1;if(idx+1==data_beats)begin idx<=0;st<=PRQ;end else begin idx<=idx+1;st<=DRQ;end end
  PRQ:if(l2_rd_valid_o&&l2_rd_ready_i)st<=PRP;PRP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin read_beats_o<=read_beats_o+1;if(l2_rsp_data_i[31:0]!=0)begin unsupported_position_o<=1;st<=D;end else begin pair_idx<=0;st<=FQ;end end
  FQ:if(riv&&rir)st<=FP;FP:if(rov&&ror)begin out_mem[element_even/32][(element_even%32)*16+:16]<=bf16(roe);out_mem[element_odd/32][(element_odd%32)*16+:16]<=bf16(roo);if(pair_idx+1==total_pairs)begin idx<=0;st<=OW;end else begin pair_idx<=pair_idx+1;st<=FQ;end end
  OW:if(l2_wr_valid_o&&l2_wr_ready_i)begin write_beats_o<=write_beats_o+1;if(idx+1==data_beats)st<=D;else begin idx<=idx+1;st<=OW;end end D:st<=I;default:st<=I;endcase end
endmodule
