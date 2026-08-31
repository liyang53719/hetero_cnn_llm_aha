// SPDX-License-Identifier: Apache-2.0
// Two-pass 32-score row engine. score_i is already scaled by 1/sqrt(head_dim).
// Selected-score, subtract and log2(e) multiply boundaries are registered.
`timescale 1ns/1ps
module fp32_block32_softmax_weights(
  input logic clk_i,rst_ni,start_i,
  input logic score_valid_i,output logic score_ready_o,
  input logic[31:0]score_i,input logic mask_i,
  output logic summary_valid_o,input logic summary_ready_i,
  output logic[31:0]m_o,l_o,
  output logic weight_valid_o,input logic weight_ready_i,
  output logic[31:0]weight_o,output logic weight_last_o,
  output logic[4:0]exception_flags_o,output logic busy_o
);
  typedef enum logic[3:0]{S_IDLE,S_LOAD,S_SELECT,S_SUB_ISSUE,S_SUB_WAIT,S_LOG_ISSUE,S_LOG_WAIT,S_EXP_ISSUE,S_EXP_WAIT,S_L_ISSUE,S_L_WAIT,S_HEADER,S_OUTPUT}state_e;
  state_e state_q;
  logic[31:0]score_mem[0:31],weight_mem[0:31];logic[4:0]load_index_q,exp_index_q,output_index_q;
  logic[31:0]max_q,l_acc_q,final_l_q,selected_score_q,delta_value_q,delta_log2e_q,exp_weight_q;
  logic[4:0]flags_q;
  logic sub_iv,sub_ir,sub_ov,sub_or,sub_user_unused;logic[31:0]sub_out;logic[4:0]sub_flags;
  logic log_iv,log_ir,log_ov,log_or,log_user_unused;logic[31:0]log_out;logic[4:0]log_flags;
  logic exp_iv,exp_ir,exp_ov,exp_or;logic[31:0]exp_weight,exp_accepted_unused,exp_completed_unused;logic[12:0]exp_flags;
  logic l_iv,l_ir,l_ov,l_or,l_user_unused;logic[31:0]l_out;logic[4:0]l_flags;
  function automatic logic fp32_gt(input logic[31:0]a,input logic[31:0]b);
    if(a[31]!=b[31])fp32_gt=!a[31];else if(!a[31])fp32_gt=a[30:0]>b[30:0];else fp32_gt=a[30:0]<b[30:0];
  endfunction
  HeteroFP32AddPipeBit1 sub_pipe(.clock(clk_i),.reset(!rst_ni),.io_inValid(sub_iv),.io_inReady(sub_ir),.io_x(selected_score_q),.io_y({~max_q[31],max_q[30:0]}),.io_userIn(1'b0),.io_outValid(sub_ov),.io_outReady(sub_or),.io_out(sub_out),.io_exceptionFlags(sub_flags),.io_userOut(sub_user_unused));
  HeteroFP32MulPipeBit1 log_pipe(.clock(clk_i),.reset(!rst_ni),.io_inValid(log_iv),.io_inReady(log_ir),.io_x(delta_value_q),.io_y(32'h3fb8aa3b),.io_userIn(1'b0),.io_outValid(log_ov),.io_outReady(log_or),.io_out(log_out),.io_exceptionFlags(log_flags),.io_userOut(log_user_unused));
  fp32_exp2_pwl_rawpipe exp2(.clk_i,.rst_ni,.in_valid_i(exp_iv),.in_ready_o(exp_ir),.x_i(delta_log2e_q),.out_valid_o(exp_ov),.out_ready_i(exp_or),.y_o(exp_weight),.exception_flags_o(exp_flags),.accepted_o(exp_accepted_unused),.completed_o(exp_completed_unused));
  HeteroFP32AddPipeBit1 l_acc_add(.clock(clk_i),.reset(!rst_ni),.io_inValid(l_iv),.io_inReady(l_ir),.io_x(l_acc_q),.io_y(exp_weight_q),.io_userIn(1'b0),.io_outValid(l_ov),.io_outReady(l_or),.io_out(l_out),.io_exceptionFlags(l_flags),.io_userOut(l_user_unused));
  assign score_ready_o=state_q==S_LOAD;assign sub_iv=state_q==S_SUB_ISSUE;assign sub_or=state_q==S_SUB_WAIT;assign log_iv=state_q==S_LOG_ISSUE;assign log_or=state_q==S_LOG_WAIT;assign exp_iv=state_q==S_EXP_ISSUE;assign exp_or=state_q==S_EXP_WAIT;assign l_iv=state_q==S_L_ISSUE;assign l_or=state_q==S_L_WAIT;
  assign summary_valid_o=state_q==S_HEADER;assign weight_valid_o=state_q==S_OUTPUT;assign weight_o=weight_mem[output_index_q];assign weight_last_o=output_index_q==31;assign m_o=max_q;assign l_o=final_l_q;assign exception_flags_o=flags_q;assign busy_o=state_q!=S_IDLE;
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin state_q<=S_IDLE;load_index_q<=0;exp_index_q<=0;output_index_q<=0;max_q<=32'hff800000;l_acc_q<=0;final_l_q<=0;selected_score_q<=0;delta_value_q<=0;delta_log2e_q<=0;exp_weight_q<=0;flags_q<=0;end
    else case(state_q)
      S_IDLE:if(start_i)begin state_q<=S_LOAD;load_index_q<=0;max_q<=32'hff800000;l_acc_q<=0;flags_q<=0;end
      S_LOAD:if(score_valid_i)begin score_mem[load_index_q]<=mask_i?32'hff800000:score_i;if(!mask_i&&(max_q==32'hff800000||fp32_gt(score_i,max_q)))max_q<=score_i;if(load_index_q==31)begin exp_index_q<=0;state_q<=S_SELECT;end else load_index_q<=load_index_q+1'b1;end
      S_SELECT:begin selected_score_q<=score_mem[exp_index_q];state_q<=S_SUB_ISSUE;end
      S_SUB_ISSUE:if(sub_ir)state_q<=S_SUB_WAIT;
      S_SUB_WAIT:if(sub_ov)begin delta_value_q<=sub_out;flags_q<=flags_q|sub_flags;state_q<=S_LOG_ISSUE;end
      S_LOG_ISSUE:if(log_ir)state_q<=S_LOG_WAIT;
      S_LOG_WAIT:if(log_ov)begin delta_log2e_q<=log_out;flags_q<=flags_q|log_flags;state_q<=S_EXP_ISSUE;end
      S_EXP_ISSUE:if(exp_ir)state_q<=S_EXP_WAIT;
      S_EXP_WAIT:if(exp_ov)begin exp_weight_q<=exp_weight;flags_q<=flags_q|exp_flags[4:0];state_q<=S_L_ISSUE;end
      S_L_ISSUE:if(l_ir)state_q<=S_L_WAIT;
      S_L_WAIT:if(l_ov)begin weight_mem[exp_index_q]<=exp_weight_q;l_acc_q<=l_out;flags_q<=flags_q|l_flags;if(exp_index_q==31)begin final_l_q<=l_out;state_q<=S_HEADER;end else begin exp_index_q<=exp_index_q+1'b1;state_q<=S_SELECT;end end
      S_HEADER:if(summary_ready_i)begin output_index_q<=0;state_q<=S_OUTPUT;end
      S_OUTPUT:if(weight_ready_i)begin if(output_index_q==31)state_q<=S_IDLE;else output_index_q<=output_index_q+1'b1;end
      default:state_q<=S_IDLE;
    endcase
  end
endmodule
