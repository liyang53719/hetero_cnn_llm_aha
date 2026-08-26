// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_rmsnorm256_chunked(input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,
 input logic[8191:0]x_i,weight_i,input logic[31:0]epsilon_i,output logic out_valid_o,input logic out_ready_i,
 output logic[8191:0]y_o,output logic[4:0]exception_flags_o,output logic[31:0]accepted_o,completed_o,
 output logic[31:0]reduction_cycles_o,rsqrt_cycles_o,output_cycles_o);
 typedef enum logic[2:0]{S_IDLE,S_RISSUE,S_RWAIT,S_QISSUE,S_QWAIT,S_OPASS,S_OUT}st_e;st_e st;
 logic[8191:0]xq,wq,yq;logic[31:0]epsq,sumq,invq;logic[3:0]chunk;
 logic[511:0]sq,scaled,chunk_out;logic[16*5-1:0]sf;logic[4:0]sfor;
 logic red_iv,red_ir,red_ov,red_or;logic[31:0]red_sum;logic[4:0]red_f;
 /* verilator lint_off UNUSEDSIGNAL */logic[31:0]red_a,red_c,rs_a,rs_c;logic rs_de;/* verilator lint_on UNUSEDSIGNAL */
 logic[31:0]sum_next,mean,mean_eps,mean_eps_q,rs_y;logic[4:0]f_sum,f_mean,f_eps,rs_f;
 logic rs_iv,rs_ir,rs_ov,rs_or;logic[16*10-1:0]of;logic[4:0]ofor,fq;integer sf_i,of_i;
 genvar i;generate for(i=0;i<16;i++)begin:g_sq HeteroFP32Alu u(.io_op(1'b1),
  .io_x(xq[(chunk*16+i)*32+:32]),.io_y(xq[(chunk*16+i)*32+:32]),.io_out(sq[i*32+:32]),.io_exceptionFlags(sf[i*5+:5]));end endgenerate
 always_comb begin sfor=0;for(sf_i=0;sf_i<16;sf_i++)sfor|=sf[sf_i*5+:5];end
 fp32_reduce16 red(.clk_i,.rst_ni,.in_valid_i(red_iv),.in_ready_o(red_ir),.data_i(sq),.out_valid_o(red_ov),.out_ready_i(red_or),.sum_o(red_sum),.exception_flags_o(red_f),.accepted_vectors_o(red_a),.completed_vectors_o(red_c));
 HeteroFP32Alu a_sum(.io_op(0),.io_x(sumq),.io_y(red_sum),.io_out(sum_next),.io_exceptionFlags(f_sum));
 HeteroFP32Alu m_mean(.io_op(1),.io_x(sum_next),.io_y(32'h3b800000),.io_out(mean),.io_exceptionFlags(f_mean));
 HeteroFP32Alu a_eps(.io_op(0),.io_x(mean),.io_y(epsq),.io_out(mean_eps),.io_exceptionFlags(f_eps));
 fp32_rsqrt_nr rs(.clk_i,.rst_ni,.in_valid_i(rs_iv),.in_ready_o(rs_ir),.x_i(mean_eps_q),.out_valid_o(rs_ov),.out_ready_i(rs_or),.y_o(rs_y),.exception_flags_o(rs_f),.domain_error_o(rs_de),.accepted_o(rs_a),.completed_o(rs_c));
 generate for(i=0;i<16;i++)begin:g_out HeteroFP32Alu m0(.io_op(1),.io_x(xq[(chunk*16+i)*32+:32]),.io_y(invq),.io_out(scaled[i*32+:32]),.io_exceptionFlags(of[i*10+:5]));
  HeteroFP32Alu m1(.io_op(1),.io_x(scaled[i*32+:32]),.io_y(wq[(chunk*16+i)*32+:32]),.io_out(chunk_out[i*32+:32]),.io_exceptionFlags(of[i*10+5+:5]));end endgenerate
 always_comb begin ofor=0;for(of_i=0;of_i<16;of_i++)ofor|=of[of_i*10+:5]|of[of_i*10+5+:5];end
 assign red_iv=st==S_RISSUE;assign red_or=st==S_RWAIT&&red_ov;assign rs_iv=st==S_QISSUE;assign rs_or=st==S_QWAIT&&rs_ov;
 assign in_ready_o=st==S_IDLE;assign out_valid_o=st==S_OUT;assign y_o=yq;assign exception_flags_o=fq;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=S_IDLE;xq<=0;wq<=0;yq<=0;epsq<=0;sumq<=0;mean_eps_q<=0;invq<=0;chunk<=0;fq<=0;accepted_o<=0;completed_o<=0;reduction_cycles_o<=0;rsqrt_cycles_o<=0;output_cycles_o<=0;end else begin
  if(st==S_RISSUE||st==S_RWAIT)reduction_cycles_o<=reduction_cycles_o+1'b1;
  if(st==S_QISSUE||st==S_QWAIT)rsqrt_cycles_o<=rsqrt_cycles_o+1'b1;if(st==S_OPASS)output_cycles_o<=output_cycles_o+1'b1;
  case(st)
  S_IDLE:if(in_valid_i)begin xq<=x_i;wq<=weight_i;epsq<=epsilon_i;sumq<=0;mean_eps_q<=0;chunk<=0;fq<=0;accepted_o<=accepted_o+1'b1;st<=S_RISSUE;end
   S_RISSUE:if(red_ir)st<=S_RWAIT;
   S_RWAIT:if(red_ov)begin fq<=fq|sfor|red_f|f_sum;if(chunk==15)begin sumq<=sum_next;mean_eps_q<=mean_eps;st<=S_QISSUE;end else begin sumq<=sum_next;chunk<=chunk+1'b1;st<=S_RISSUE;end end
   S_QISSUE:if(rs_ir)st<=S_QWAIT;
   S_QWAIT:if(rs_ov)begin invq<=rs_y;fq<=fq|f_mean|f_eps|rs_f;chunk<=0;st<=S_OPASS;end
   S_OPASS:begin yq[chunk*512+:512]<=chunk_out;fq<=fq|ofor;if(chunk==15)st<=S_OUT;else chunk<=chunk+1'b1;end
   S_OUT:if(out_ready_i)begin completed_o<=completed_o+1'b1;st<=S_IDLE;end
   default:st<=S_IDLE;endcase end end
endmodule
