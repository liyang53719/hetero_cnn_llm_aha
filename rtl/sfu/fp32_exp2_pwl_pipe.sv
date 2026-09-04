// SPDX-License-Identifier: Apache-2.0
module fp32_exp2_pwl_pipe(input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[31:0]x_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]y_o,output logic[12:0]exception_flags_o,output logic[31:0]accepted_o,completed_o);
 `include "rtl/sfu/fp32_exp2_coeffs.svh"
 localparam logic[2:0]S_IDLE=0,S_PREP=1,S_MUL_ISSUE=2,S_MUL_WAIT=3,S_ADD_ISSUE=4,S_ADD_WAIT=5,S_OUT=6;logic[2:0]state_q;
 logic[31:0]x_q,m_q,b_q,tmp_q,y_q;logic[12:0]flags_q;logic[15:0]scaled_floor;logic[7:0]convert_flags,index;logic signed[15:0]floor_signed;logic[63:0]coeff;
 logic is_nan,is_inf,special;logic[31:0]special_result;logic miv,mir,mov,mor,aiv,air,aov,aor,mu,au;logic[31:0]mo,ao;logic[4:0]mf,af;
 HeteroFP32Scale16Floor floor(.io_x(x_q),.io_out(scaled_floor),.io_exceptionFlags(convert_flags));assign floor_signed=$signed(scaled_floor);assign index=8'($signed(floor_signed)+16'sd256);assign coeff=exp2_pwl_coeff(index);
 assign is_nan=&x_q[30:23]&&|x_q[22:0];assign is_inf=&x_q[30:23]&&!(|x_q[22:0]);assign special=is_nan||is_inf||floor_signed< -16'sd256||floor_signed>=0;
 always_comb if(is_nan)special_result=0;else if(is_inf)special_result=x_q[31]?0:32'h3f800000;else if(floor_signed< -16'sd256)special_result=0;else special_result=32'h3f800000;
 assign miv=state_q==S_MUL_ISSUE;assign mor=state_q==S_MUL_WAIT;assign aiv=state_q==S_ADD_ISSUE;assign aor=state_q==S_ADD_WAIT;
 HeteroFP32MulPipeBit1 mul(.clock(clk_i),.reset(!rst_ni),.io_inValid(miv),.io_inReady(mir),.io_x(m_q),.io_y(x_q),.io_userIn(0),.io_outValid(mov),.io_outReady(mor),.io_out(mo),.io_exceptionFlags(mf),.io_userOut(mu));
 HeteroFP32AddPipeBit1 add(.clock(clk_i),.reset(!rst_ni),.io_inValid(aiv),.io_inReady(air),.io_x(tmp_q),.io_y(b_q),.io_userIn(0),.io_outValid(aov),.io_outReady(aor),.io_out(ao),.io_exceptionFlags(af),.io_userOut(au));
 assign in_ready_o=state_q==S_IDLE;assign out_valid_o=state_q==S_OUT;assign y_o=y_q;assign exception_flags_o=flags_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin state_q<=S_IDLE;x_q<=0;m_q<=0;b_q<=0;tmp_q<=0;y_q<=0;flags_q<=0;accepted_o<=0;completed_o<=0;end else case(state_q)
  S_IDLE:if(in_valid_i)begin x_q<=x_i;accepted_o<=accepted_o+1'b1;flags_q<=0;state_q<=S_PREP;end
  S_PREP:begin flags_q<={5'd0,convert_flags};if(special)begin y_q<=special_result;state_q<=S_OUT;end else begin m_q<=coeff[63:32];b_q<=coeff[31:0];state_q<=S_MUL_ISSUE;end end
  S_MUL_ISSUE:if(mir)state_q<=S_MUL_WAIT;S_MUL_WAIT:if(mov)begin tmp_q<=mo;flags_q<=flags_q|{8'd0,mf};state_q<=S_ADD_ISSUE;end
  S_ADD_ISSUE:if(air)state_q<=S_ADD_WAIT;S_ADD_WAIT:if(aov)begin y_q<=ao;flags_q<=flags_q|{8'd0,af};state_q<=S_OUT;end
  S_OUT:if(out_ready_i)begin completed_o<=completed_o+1'b1;state_q<=S_IDLE;end default:state_q<=S_IDLE;endcase end
endmodule
