// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_dot4_scaled(input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,
 input logic[127:0]a_i,b_i,input logic[31:0]scale_i,output logic out_valid_o,input logic out_ready_i,
 output logic[31:0]result_o,output logic[4:0]exception_flags_o);
 logic iq,oq,oready;logic[127:0]aq,bq;logic[31:0]sq,rq,p[0:3],s0,s1,sum,res;logic[8*5-1:0]f;logic[4:0]fc,fq;
 genvar i;generate for(i=0;i<4;i++)begin:g HeteroFP32Alu m(.io_op(1'b1),.io_x(aq[i*32+:32]),.io_y(bq[i*32+:32]),.io_out(p[i]),.io_exceptionFlags(f[i*5+:5]));end endgenerate
 HeteroFP32Alu a0(.io_op(0),.io_x(p[0]),.io_y(p[1]),.io_out(s0),.io_exceptionFlags(f[20+:5]));
 HeteroFP32Alu a1(.io_op(0),.io_x(p[2]),.io_y(p[3]),.io_out(s1),.io_exceptionFlags(f[25+:5]));
 HeteroFP32Alu a2(.io_op(0),.io_x(s0),.io_y(s1),.io_out(sum),.io_exceptionFlags(f[30+:5]));
 HeteroFP32Alu m4(.io_op(1),.io_x(sum),.io_y(sq),.io_out(res),.io_exceptionFlags(f[35+:5]));
 always_comb begin fc=0;for(int j=0;j<8;j++)fc|=f[j*5+:5];end
 assign oready=!oq||out_ready_i;assign in_ready_o=!iq||oready;assign out_valid_o=oq;assign result_o=rq;assign exception_flags_o=fq;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin iq<=0;oq<=0;aq<=0;bq<=0;sq<=0;rq<=0;fq<=0;end else begin
  if(oready)begin oq<=iq;if(iq)begin rq<=res;fq<=fc;end end
  if(in_ready_o)begin iq<=in_valid_i;if(in_valid_i)begin aq<=a_i;bq<=b_i;sq<=scale_i;end end end end
endmodule
