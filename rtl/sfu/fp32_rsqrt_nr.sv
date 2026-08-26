// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_rsqrt_nr(input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[31:0]x_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]y_o,output logic[4:0]exception_flags_o,output logic domain_error_o,
 output logic[31:0]accepted_o,output logic[31:0]completed_o);
 `include "rtl/sfu/fp32_rsqrt_coeffs.svh"
 logic iq,oq,oready;logic[31:0]xq,yq,ycomb;logic deq,decomb;logic[4:0]fq,fc;
 logic[7:0]exp,scale_exp;logic signed[9:0]e,e_even,e_half,scale_e;logic odd;
 logic[31:0]norm,scale;logic[4:0]index;logic[63:0]coeff;logic[31:0]m,b,mx,y0,y2,xy2,half,term,y1,scaled;
 logic[8*5-1:0]flags;logic normal,zero,pinf;
 assign exp=xq[30:23];assign e=$signed({2'b00,exp})-10'sd127;assign odd=e[0];
 assign e_even=odd?e-10'sd1:e;assign e_half=e_even>>>1;assign scale_e=10'sd127-e_half;assign scale_exp=scale_e[7:0];
 assign norm={1'b0,odd?8'd128:8'd127,xq[22:0]};assign scale={1'b0,scale_exp,23'd0};assign index={odd,xq[22:19]};
 assign coeff=rsqrt_pwl_coeff(index);assign m=coeff[63:32];assign b=coeff[31:0];
 HeteroFP32Alu u0(.io_op(1'b1),.io_x(m),.io_y(norm),.io_out(mx),.io_exceptionFlags(flags[0+:5]));
 HeteroFP32Alu u1(.io_op(1'b0),.io_x(mx),.io_y(b),.io_out(y0),.io_exceptionFlags(flags[5+:5]));
 HeteroFP32Alu u2(.io_op(1'b1),.io_x(y0),.io_y(y0),.io_out(y2),.io_exceptionFlags(flags[10+:5]));
 HeteroFP32Alu u3(.io_op(1'b1),.io_x(norm),.io_y(y2),.io_out(xy2),.io_exceptionFlags(flags[15+:5]));
 HeteroFP32Alu u4(.io_op(1'b1),.io_x(32'h3f000000),.io_y(xy2),.io_out(half),.io_exceptionFlags(flags[20+:5]));
 HeteroFP32Alu u5(.io_op(1'b0),.io_x(32'h3fc00000),.io_y({~half[31],half[30:0]}),.io_out(term),.io_exceptionFlags(flags[25+:5]));
 HeteroFP32Alu u6(.io_op(1'b1),.io_x(y0),.io_y(term),.io_out(y1),.io_exceptionFlags(flags[30+:5]));
 HeteroFP32Alu u7(.io_op(1'b1),.io_x(y1),.io_y(scale),.io_out(scaled),.io_exceptionFlags(flags[35+:5]));
 always_comb begin fc=0;for(int i=0;i<8;i++)fc|=flags[i*5+:5];zero=!xq[31]&&exp==0&&xq[22:0]==0;
  pinf=!xq[31]&&exp==8'hff&&xq[22:0]==0;normal=!xq[31]&&exp>=2&&exp<=253;
  if(zero)begin ycomb=32'h7f800000;decomb=0;end else if(pinf)begin ycomb=0;decomb=0;end
  else if(normal)begin ycomb=scaled;decomb=0;end else begin ycomb=32'h7fc00000;decomb=1;end end
 assign oready=!oq||out_ready_i;assign in_ready_o=!iq||oready;assign out_valid_o=oq;assign y_o=yq;assign exception_flags_o=fq;assign domain_error_o=deq;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin iq<=0;oq<=0;xq<=0;yq<=0;deq<=0;fq<=0;accepted_o<=0;completed_o<=0;end else begin
  if(oq&&out_ready_i)completed_o<=completed_o+1'b1;if(oready)begin oq<=iq;if(iq)begin yq<=ycomb;deq<=decomb;fq<=fc;end end
  if(in_ready_o)begin iq<=in_valid_i;if(in_valid_i)begin xq<=x_i;accepted_o<=accepted_o+1'b1;end end end end
endmodule
