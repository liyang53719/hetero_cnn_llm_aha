// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_reciprocal_nr(input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[31:0]x_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]y_o,output logic[4:0]exception_flags_o,output logic domain_error_o,
 output logic[31:0]accepted_o,output logic[31:0]completed_o);
 `include "rtl/sfu/fp32_recip_coeffs.svh"
 logic iq,oq,oready;logic[31:0]xq,yq;logic deq;logic[4:0]fq;
 logic[7:0]exp;logic[31:0]norm,scale;logic[63:0]coeff;logic[31:0]m,b,mx,y0,t,u,y1,scaled;
 logic[6*5-1:0]flags;logic[4:0]fc;logic normal,zero,pinf;
 assign exp=xq[30:23];assign norm={1'b0,8'd127,xq[22:0]};assign scale={1'b0,8'(8'd254-exp),23'd0};
 assign coeff=recip_pwl_coeff(xq[22:19]);assign m=coeff[63:32];assign b=coeff[31:0];
 HeteroFP32Alu m0(.io_op(1'b1),.io_x(m),.io_y(norm),.io_out(mx),.io_exceptionFlags(flags[0+:5]));
 HeteroFP32Alu a0(.io_op(1'b0),.io_x(mx),.io_y(b),.io_out(y0),.io_exceptionFlags(flags[5+:5]));
 HeteroFP32Alu m1(.io_op(1'b1),.io_x(norm),.io_y(y0),.io_out(t),.io_exceptionFlags(flags[10+:5]));
 HeteroFP32Alu a1(.io_op(1'b0),.io_x(32'h40000000),.io_y({~t[31],t[30:0]}),.io_out(u),.io_exceptionFlags(flags[15+:5]));
 HeteroFP32Alu m2(.io_op(1'b1),.io_x(y0),.io_y(u),.io_out(y1),.io_exceptionFlags(flags[20+:5]));
 HeteroFP32Alu m3(.io_op(1'b1),.io_x(y1),.io_y(scale),.io_out(scaled),.io_exceptionFlags(flags[25+:5]));
 always_comb begin fc=0;for(int i=0;i<6;i++)fc|=flags[i*5+:5];zero=!xq[31]&&exp==0&&xq[22:0]==0;
  pinf=!xq[31]&&exp==8'hff&&xq[22:0]==0;normal=!xq[31]&&exp>=2&&exp<=253;
  if(zero)begin yq_comb=32'h7f800000;de_comb=0;end else if(pinf)begin yq_comb=0;de_comb=0;end
  else if(normal)begin yq_comb=scaled;de_comb=0;end else begin yq_comb=32'h7fc00000;de_comb=1;end end
 logic[31:0]yq_comb;logic de_comb;
 assign oready=!oq||out_ready_i;assign in_ready_o=!iq||oready;assign out_valid_o=oq;assign y_o=yq;
 assign exception_flags_o=fq;assign domain_error_o=deq;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin iq<=0;oq<=0;xq<=0;yq<=0;deq<=0;fq<=0;accepted_o<=0;completed_o<=0;end else begin
  if(oq&&out_ready_i)completed_o<=completed_o+1'b1;if(oready)begin oq<=iq;if(iq)begin yq<=yq_comb;deq<=de_comb;fq<=fc;end end
  if(in_ready_o)begin iq<=in_valid_i;if(in_valid_i)begin xq<=x_i;accepted_o<=accepted_o+1'b1;end end end end
endmodule
