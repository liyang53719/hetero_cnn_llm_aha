// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_rmsnorm16(input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,
 input logic[511:0]x_i,input logic[511:0]weight_i,input logic[31:0]epsilon_i,
 output logic out_valid_o,input logic out_ready_i,output logic[511:0]y_o,
 output logic[4:0]exception_flags_o,output logic[31:0]accepted_o,output logic[31:0]completed_o);
 typedef enum logic[1:0]{S_IDLE,S_ISSUE,S_WAIT,S_OUT}st_e;st_e st;
 logic[511:0]xq,wq,yq;logic[31:0]epsq;logic[16*32-1:0]sq;
 logic[8*32-1:0]l1;logic[4*32-1:0]l2;logic[2*32-1:0]l3;logic[31:0]sum,mean,mean_eps,inv;
 logic[511:0]scaled,ycomb;logic[65*5-1:0]flags;logic[4:0]fc,fq;integer fi;
 logic riv,rir,rov,ror;logic[4:0]rf;/* verilator lint_off UNUSEDSIGNAL */logic[31:0]ra,rc;logic rde;/* verilator lint_on UNUSEDSIGNAL */
 genvar i;generate for(i=0;i<16;i++)begin:g_sq HeteroFP32Alu u(.io_op(1'b1),.io_x(xq[i*32+:32]),.io_y(xq[i*32+:32]),.io_out(sq[i*32+:32]),.io_exceptionFlags(flags[i*5+:5]));end
  for(i=0;i<8;i++)begin:g_l1 HeteroFP32Alu u(.io_op(1'b0),.io_x(sq[(2*i)*32+:32]),.io_y(sq[(2*i+1)*32+:32]),.io_out(l1[i*32+:32]),.io_exceptionFlags(flags[(16+i)*5+:5]));end
  for(i=0;i<4;i++)begin:g_l2 HeteroFP32Alu u(.io_op(1'b0),.io_x(l1[(2*i)*32+:32]),.io_y(l1[(2*i+1)*32+:32]),.io_out(l2[i*32+:32]),.io_exceptionFlags(flags[(24+i)*5+:5]));end
  for(i=0;i<2;i++)begin:g_l3 HeteroFP32Alu u(.io_op(1'b0),.io_x(l2[(2*i)*32+:32]),.io_y(l2[(2*i+1)*32+:32]),.io_out(l3[i*32+:32]),.io_exceptionFlags(flags[(28+i)*5+:5]));end endgenerate
 HeteroFP32Alu a_sum(.io_op(1'b0),.io_x(l3[31:0]),.io_y(l3[63:32]),.io_out(sum),.io_exceptionFlags(flags[30*5+:5]));
 HeteroFP32Alu m_mean(.io_op(1'b1),.io_x(sum),.io_y(32'h3d800000),.io_out(mean),.io_exceptionFlags(flags[31*5+:5]));
 HeteroFP32Alu a_eps(.io_op(1'b0),.io_x(mean),.io_y(epsq),.io_out(mean_eps),.io_exceptionFlags(flags[32*5+:5]));
 fp32_rsqrt_nr rsqrt(.clk_i,.rst_ni,.in_valid_i(riv),.in_ready_o(rir),.x_i(mean_eps),.out_valid_o(rov),.out_ready_i(ror),.y_o(inv),.exception_flags_o(rf),.domain_error_o(rde),.accepted_o(ra),.completed_o(rc));
 generate for(i=0;i<16;i++)begin:g_out HeteroFP32Alu m0(.io_op(1'b1),.io_x(xq[i*32+:32]),.io_y(inv),.io_out(scaled[i*32+:32]),.io_exceptionFlags(flags[(33+2*i)*5+:5]));
  HeteroFP32Alu m1(.io_op(1'b1),.io_x(scaled[i*32+:32]),.io_y(wq[i*32+:32]),.io_out(ycomb[i*32+:32]),.io_exceptionFlags(flags[(34+2*i)*5+:5]));end endgenerate
 always_comb begin fc=rf;for(fi=0;fi<65;fi++)fc|=flags[fi*5+:5];end
 assign riv=st==S_ISSUE;assign ror=st==S_WAIT&&rov;assign in_ready_o=st==S_IDLE;
 assign out_valid_o=st==S_OUT;assign y_o=yq;assign exception_flags_o=fq;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=S_IDLE;xq<=0;wq<=0;epsq<=0;yq<=0;fq<=0;accepted_o<=0;completed_o<=0;end else case(st)
  S_IDLE:if(in_valid_i)begin xq<=x_i;wq<=weight_i;epsq<=epsilon_i;accepted_o<=accepted_o+1'b1;st<=S_ISSUE;end
  S_ISSUE:if(rir)st<=S_WAIT;
  S_WAIT:if(rov)begin yq<=ycomb;fq<=fc;st<=S_OUT;end
  S_OUT:if(out_ready_i)begin completed_o<=completed_o+1'b1;st<=S_IDLE;end
  default:st<=S_IDLE;endcase end
endmodule
