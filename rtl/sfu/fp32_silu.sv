// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_silu(input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[31:0]x_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]y_o,output logic[4:0]exception_flags_o,
 output logic[31:0]accepted_o,output logic[31:0]completed_o);
 typedef enum logic[2:0]{S_IDLE,S_EISSUE,S_EWAIT,S_RISSUE,S_RWAIT,S_OUT}st_e;st_e st;
 logic[31:0]xq,z,expq,exp_out,denom,recip,base,negout,yq;logic signq;
 logic[4:0]fz,fd,fb,fn,fq,fc;logic eiv,eir,eov,eor,riv,rir,rov,ror;logic[12:0]ef;logic[4:0]rf;
 /* verilator lint_off UNUSEDSIGNAL */logic[31:0]ea,ec,ra,rc;logic rde;/* verilator lint_on UNUSEDSIGNAL */
 HeteroFP32Alu m_z(.io_op(1'b1),.io_x({1'b1,xq[30:0]}),.io_y(32'h3fb8aa3b),.io_out(z),.io_exceptionFlags(fz));
 fp32_exp2_pwl exp(.clk_i,.rst_ni,.in_valid_i(eiv),.in_ready_o(eir),.x_i(z),.out_valid_o(eov),.out_ready_i(eor),.y_o(exp_out),.exception_flags_o(ef),.accepted_o(ea),.completed_o(ec));
 HeteroFP32Alu a_d(.io_op(1'b0),.io_x(32'h3f800000),.io_y(expq),.io_out(denom),.io_exceptionFlags(fd));
 fp32_reciprocal_nr rec(.clk_i,.rst_ni,.in_valid_i(riv),.in_ready_o(rir),.x_i(denom),.out_valid_o(rov),.out_ready_i(ror),.y_o(recip),.exception_flags_o(rf),.domain_error_o(rde),.accepted_o(ra),.completed_o(rc));
 HeteroFP32Alu m_b(.io_op(1'b1),.io_x(xq),.io_y(recip),.io_out(base),.io_exceptionFlags(fb));
 HeteroFP32Alu m_n(.io_op(1'b1),.io_x(base),.io_y(expq),.io_out(negout),.io_exceptionFlags(fn));
 assign eiv=st==S_EISSUE;assign eor=st==S_EWAIT&&eov;assign riv=st==S_RISSUE;assign ror=st==S_RWAIT&&rov;
 assign in_ready_o=st==S_IDLE;assign out_valid_o=st==S_OUT;assign y_o=yq;assign exception_flags_o=fq;
 always_comb fc=fz|fd|fb|fn|ef[4:0]|rf;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=S_IDLE;xq<=0;signq<=0;expq<=0;yq<=0;fq<=0;accepted_o<=0;completed_o<=0;end else case(st)
  S_IDLE:if(in_valid_i)begin xq<=x_i;signq<=x_i[31];accepted_o<=accepted_o+1'b1;st<=S_EISSUE;end
  S_EISSUE:if(eir)st<=S_EWAIT;
  S_EWAIT:if(eov)begin expq<=exp_out;st<=S_RISSUE;end
  S_RISSUE:if(rir)st<=S_RWAIT;
  S_RWAIT:if(rov)begin yq<=signq?negout:base;fq<=fc;st<=S_OUT;end
  S_OUT:if(out_ready_i)begin completed_o<=completed_o+1'b1;st<=S_IDLE;end
  default:st<=S_IDLE;endcase end
endmodule
