// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_online_softmax #(parameter integer LANES=4)(
 input logic clk_i,input logic rst_ni,input logic clear_i,input logic in_valid_i,output logic in_ready_o,
 input logic[31:0]score_i,input logic[LANES*32-1:0]value_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]m_o,l_o,
 output logic[LANES*32-1:0]o_o,output logic[4:0]exception_flags_o,
 output logic[31:0]accepted_tokens_o,output logic[31:0]completed_tokens_o);
 typedef enum logic[1:0]{S_IDLE,S_ISSUE,S_WAIT,S_OUT}state_e;state_e state_q;
 logic initialized_q;logic[31:0]m_q,l_q,score_q,m_new_q;logic[LANES*32-1:0]o_q,value_q;
 logic[31:0]sub_m,sub_s,delta_m,delta_s;logic[4:0]f_subm,f_subs,f_dm,f_ds;
 logic expa_iv,expa_ir,expa_ov,expa_or,expb_iv,expb_ir,expb_ov,expb_or;
 /* verilator lint_off UNUSEDSIGNAL */logic[31:0]expa_accepted,expa_completed,expb_accepted,expb_completed;/* verilator lint_on UNUSEDSIGNAL */
 logic[31:0]alpha,beta;logic[12:0]fa,fb;
 logic[31:0]lmul,lnew;logic[4:0]f_lmul,f_ladd;logic[LANES*32-1:0]omul,vmul,onew;
 logic[LANES*15-1:0]lane_flags;logic[4:0]flags_comb;logic[4:0]flags_q;integer fi;
 function automatic logic fp32_gt(input logic[31:0]a,input logic[31:0]b);begin
  if(a[31]!=b[31])fp32_gt=!a[31];else if(!a[31])fp32_gt=a[30:0]>b[30:0];else fp32_gt=a[30:0]<b[30:0];end endfunction
 HeteroFP32Alu a_subm(.io_op(1'b0),.io_x(m_q),.io_y({~m_new_q[31],m_new_q[30:0]}),.io_out(sub_m),.io_exceptionFlags(f_subm));
 HeteroFP32Alu a_subs(.io_op(1'b0),.io_x(score_q),.io_y({~m_new_q[31],m_new_q[30:0]}),.io_out(sub_s),.io_exceptionFlags(f_subs));
 HeteroFP32Alu m_dm(.io_op(1'b1),.io_x(sub_m),.io_y(32'h3fb8aa3b),.io_out(delta_m),.io_exceptionFlags(f_dm));
 HeteroFP32Alu m_ds(.io_op(1'b1),.io_x(sub_s),.io_y(32'h3fb8aa3b),.io_out(delta_s),.io_exceptionFlags(f_ds));
 fp32_exp2_pwl expa(.clk_i,.rst_ni,.in_valid_i(expa_iv),.in_ready_o(expa_ir),.x_i(delta_m),
  .out_valid_o(expa_ov),.out_ready_i(expa_or),.y_o(alpha),.exception_flags_o(fa),.accepted_o(expa_accepted),.completed_o(expa_completed));
 fp32_exp2_pwl expb(.clk_i,.rst_ni,.in_valid_i(expb_iv),.in_ready_o(expb_ir),.x_i(delta_s),
  .out_valid_o(expb_ov),.out_ready_i(expb_or),.y_o(beta),.exception_flags_o(fb),.accepted_o(expb_accepted),.completed_o(expb_completed));
 assign expa_iv=state_q==S_ISSUE;assign expb_iv=state_q==S_ISSUE;
 assign expa_or=state_q==S_WAIT&&expa_ov&&expb_ov;assign expb_or=expa_or;
 HeteroFP32Alu m_l(.io_op(1'b1),.io_x(l_q),.io_y(alpha),.io_out(lmul),.io_exceptionFlags(f_lmul));
 HeteroFP32Alu a_l(.io_op(1'b0),.io_x(lmul),.io_y(beta),.io_out(lnew),.io_exceptionFlags(f_ladd));
 genvar lane;generate for(lane=0;lane<LANES;lane++)begin:g_lane
  HeteroFP32Alu m_o(.io_op(1'b1),.io_x(o_q[lane*32+:32]),.io_y(alpha),.io_out(omul[lane*32+:32]),.io_exceptionFlags(lane_flags[lane*15+:5]));
  HeteroFP32Alu m_v(.io_op(1'b1),.io_x(value_q[lane*32+:32]),.io_y(beta),.io_out(vmul[lane*32+:32]),.io_exceptionFlags(lane_flags[lane*15+5+:5]));
  HeteroFP32Alu a_o(.io_op(1'b0),.io_x(omul[lane*32+:32]),.io_y(vmul[lane*32+:32]),.io_out(onew[lane*32+:32]),.io_exceptionFlags(lane_flags[lane*15+10+:5]));
 end endgenerate
 always_comb begin flags_comb=f_subm|f_subs|f_dm|f_ds|f_lmul|f_ladd|fa[4:0]|fb[4:0];
  for(fi=0;fi<LANES;fi++)flags_comb|=lane_flags[fi*15+:5]|lane_flags[fi*15+5+:5]|lane_flags[fi*15+10+:5];end
 assign in_ready_o=state_q==S_IDLE;assign out_valid_o=state_q==S_OUT;
 assign m_o=m_q;assign l_o=l_q;assign o_o=o_q;assign exception_flags_o=flags_q;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin state_q<=S_IDLE;initialized_q<=0;
  m_q<=0;l_q<=0;o_q<=0;score_q<=0;m_new_q<=0;value_q<=0;flags_q<=0;accepted_tokens_o<=0;completed_tokens_o<=0;end else begin
  if(clear_i&&state_q==S_IDLE)initialized_q<=0;
  case(state_q)
   S_IDLE:if(in_valid_i)begin accepted_tokens_o<=accepted_tokens_o+1'b1;
    if(!initialized_q||clear_i)begin initialized_q<=1;m_q<=score_i;l_q<=32'h3f800000;o_q<=value_i;flags_q<=0;state_q<=S_OUT;end
    else begin score_q<=score_i;value_q<=value_i;m_new_q<=fp32_gt(score_i,m_q)?score_i:m_q;state_q<=S_ISSUE;end end
   S_ISSUE:if(expa_ir&&expb_ir)state_q<=S_WAIT;
   S_WAIT:if(expa_ov&&expb_ov)begin m_q<=m_new_q;l_q<=lnew;o_q<=onew;flags_q<=flags_comb;state_q<=S_OUT;end
   S_OUT:if(out_ready_i)begin completed_tokens_o<=completed_tokens_o+1'b1;state_q<=S_IDLE;end
   default:state_q<=S_IDLE;
  endcase end end
endmodule
