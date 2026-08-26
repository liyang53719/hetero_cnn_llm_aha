// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_reduce16(
  input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,
  input logic[16*32-1:0]data_i,output logic out_valid_o,input logic out_ready_i,
  output logic[31:0]sum_o,output logic[4:0]exception_flags_o,
  output logic[31:0]accepted_vectors_o,output logic[31:0]completed_vectors_o
);
  logic input_valid_q,output_valid_q,output_ready;logic[511:0]input_q;
  logic[8*32-1:0]l1;logic[4*32-1:0]l2;logic[2*32-1:0]l3;logic[31:0]l4;
  logic[15*5-1:0]flags;logic[4:0]flags_comb,flags_q;logic[31:0]sum_q;integer f;
  assign output_ready=!output_valid_q||out_ready_i;assign in_ready_o=!input_valid_q||output_ready;
  assign out_valid_o=output_valid_q;assign sum_o=sum_q;assign exception_flags_o=flags_q;
  always_comb begin flags_comb=0;for(f=0;f<15;f++)flags_comb|=flags[f*5 +:5];end
  genvar i;
  generate for(i=0;i<8;i++)begin:g_l1 HeteroFP32Alu u(.io_op(1'b0),
    .io_x(input_q[(2*i)*32 +:32]),.io_y(input_q[(2*i+1)*32 +:32]),.io_out(l1[i*32 +:32]),.io_exceptionFlags(flags[i*5 +:5]));end
    for(i=0;i<4;i++)begin:g_l2 HeteroFP32Alu u(.io_op(1'b0),
    .io_x(l1[(2*i)*32 +:32]),.io_y(l1[(2*i+1)*32 +:32]),.io_out(l2[i*32 +:32]),.io_exceptionFlags(flags[(8+i)*5 +:5]));end
    for(i=0;i<2;i++)begin:g_l3 HeteroFP32Alu u(.io_op(1'b0),
    .io_x(l2[(2*i)*32 +:32]),.io_y(l2[(2*i+1)*32 +:32]),.io_out(l3[i*32 +:32]),.io_exceptionFlags(flags[(12+i)*5 +:5]));end
  endgenerate
  HeteroFP32Alu u_l4(.io_op(1'b0),.io_x(l3[31:0]),.io_y(l3[63:32]),
    .io_out(l4),.io_exceptionFlags(flags[14*5 +:5]));
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin input_valid_q<=0;output_valid_q<=0;input_q<=0;sum_q<=0;flags_q<=0;
      accepted_vectors_o<=0;completed_vectors_o<=0;end else begin
      if(output_valid_q&&out_ready_i)completed_vectors_o<=completed_vectors_o+1'b1;
      if(output_ready)begin output_valid_q<=input_valid_q;if(input_valid_q)begin sum_q<=l4;flags_q<=flags_comb;end end
      if(in_ready_o)begin input_valid_q<=in_valid_i;if(in_valid_i)begin input_q<=data_i;accepted_vectors_o<=accepted_vectors_o+1'b1;end end
    end end
endmodule
