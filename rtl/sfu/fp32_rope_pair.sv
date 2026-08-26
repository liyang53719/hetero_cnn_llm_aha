// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_rope_pair(
 input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,
 input logic[31:0]even_i,odd_i,cos_i,sin_i,output logic out_valid_o,input logic out_ready_i,
 output logic[31:0]even_o,odd_o,output logic[4:0]exception_flags_o,
 output logic[31:0]accepted_pairs_o,output logic[31:0]completed_pairs_o);
 logic input_valid_q,output_valid_q,output_ready;logic[31:0]e_q,o_q,c_q,s_q;
 logic[31:0]ec,os,es,oc,er,orr,er_q,or_q;logic[6*5-1:0]flags;logic[4:0]flags_comb,flags_q;
 always_comb begin flags_comb=0;for(int i=0;i<6;i++)flags_comb|=flags[i*5 +:5];end
 HeteroFP32Alu m0(.io_op(1'b1),.io_x(e_q),.io_y(c_q),.io_out(ec),.io_exceptionFlags(flags[0+:5]));
 HeteroFP32Alu m1(.io_op(1'b1),.io_x(o_q),.io_y(s_q),.io_out(os),.io_exceptionFlags(flags[5+:5]));
 HeteroFP32Alu m2(.io_op(1'b1),.io_x(e_q),.io_y(s_q),.io_out(es),.io_exceptionFlags(flags[10+:5]));
 HeteroFP32Alu m3(.io_op(1'b1),.io_x(o_q),.io_y(c_q),.io_out(oc),.io_exceptionFlags(flags[15+:5]));
 HeteroFP32Alu a0(.io_op(1'b0),.io_x(ec),.io_y({~os[31],os[30:0]}),.io_out(er),.io_exceptionFlags(flags[20+:5]));
 HeteroFP32Alu a1(.io_op(1'b0),.io_x(es),.io_y(oc),.io_out(orr),.io_exceptionFlags(flags[25+:5]));
 assign output_ready=!output_valid_q||out_ready_i;assign in_ready_o=!input_valid_q||output_ready;
 assign out_valid_o=output_valid_q;assign even_o=er_q;assign odd_o=or_q;assign exception_flags_o=flags_q;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin input_valid_q<=0;output_valid_q<=0;e_q<=0;o_q<=0;c_q<=0;s_q<=0;er_q<=0;or_q<=0;flags_q<=0;accepted_pairs_o<=0;completed_pairs_o<=0;end else begin
  if(output_valid_q&&out_ready_i)completed_pairs_o<=completed_pairs_o+1'b1;
  if(output_ready)begin output_valid_q<=input_valid_q;if(input_valid_q)begin er_q<=er;or_q<=orr;flags_q<=flags_comb;end end
  if(in_ready_o)begin input_valid_q<=in_valid_i;if(in_valid_i)begin e_q<=even_i;o_q<=odd_i;c_q<=cos_i;s_q<=sin_i;accepted_pairs_o<=accepted_pairs_o+1'b1;end end
 end end
endmodule
