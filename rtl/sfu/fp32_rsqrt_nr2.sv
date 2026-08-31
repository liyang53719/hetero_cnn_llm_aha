// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_rsqrt_nr2(
 input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[31:0]x_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]y_o,output logic[4:0]exception_flags_o,
 output logic domain_error_o,output logic[31:0]accepted_o,completed_o);
 `include "rtl/sfu/fp32_rsqrt_coeffs.svh"
 typedef enum logic[1:0]{S_IDLE,S_ISSUE,S_WAIT,S_DONE}state_e;state_e state_q;
 logic[3:0]op_q;logic[31:0]x_q,norm_q,scale_q,m_q,b_q,tmp_q,y0_q,scaled_q,y_q;logic[4:0]flags_q;logic domain_q;
 logic is_add;logic[31:0]op_x,op_y;logic mul_iv,mul_ir,mul_ov,mul_or,mul_user,add_iv,add_ir,add_ov,add_or,add_user;logic[31:0]mul_out,add_out;logic[4:0]mul_flags,add_flags;
 logic[7:0]exp;logic signed[9:0]exponent,even_exponent,half_exponent,scale_exponent;logic odd,normal,zero,pinf;logic[4:0]index;logic[63:0]coeff;
 assign exp=x_i[30:23];assign exponent=$signed({2'b00,exp})-10'sd127;assign odd=exponent[0];assign even_exponent=odd?exponent-10'sd1:exponent;assign half_exponent=even_exponent>>>1;assign scale_exponent=10'sd127-half_exponent;assign index={odd,x_i[22:19]};assign coeff=rsqrt_pwl_coeff(index);assign normal=!x_i[31]&&exp>=2&&exp<=253;assign zero=!x_i[31]&&exp==0&&x_i[22:0]==0;assign pinf=!x_i[31]&&exp==8'hff&&x_i[22:0]==0;
 assign is_add=op_q==1||op_q==5||op_q==11;
 always_comb begin
  op_x=0;op_y=0;case(op_q)
   0:begin op_x=m_q;op_y=norm_q;end 1:begin op_x=tmp_q;op_y=b_q;end 2:begin op_x=y0_q;op_y=y0_q;end
   3:begin op_x=norm_q;op_y=tmp_q;end 4:begin op_x=32'h3f000000;op_y=tmp_q;end 5:begin op_x=32'h3fc00000;op_y={~tmp_q[31],tmp_q[30:0]};end
   6:begin op_x=y0_q;op_y=tmp_q;end 7:begin op_x=tmp_q;op_y=scale_q;end 8:begin op_x=scaled_q;op_y=scaled_q;end
   9:begin op_x=x_q;op_y=tmp_q;end 10:begin op_x=32'h3f000000;op_y=tmp_q;end 11:begin op_x=32'h3fc00000;op_y={~tmp_q[31],tmp_q[30:0]};end
   12:begin op_x=scaled_q;op_y=tmp_q;end default:begin op_x=0;op_y=0;end endcase
 end
 assign mul_iv=state_q==S_ISSUE&&!is_add;assign add_iv=state_q==S_ISSUE&&is_add;assign mul_or=state_q==S_WAIT&&!is_add;assign add_or=state_q==S_WAIT&&is_add;
 HeteroFP32MulPipeBit1 mul(.clock(clk_i),.reset(!rst_ni),.io_inValid(mul_iv),.io_inReady(mul_ir),.io_x(op_x),.io_y(op_y),.io_userIn(1'b0),.io_outValid(mul_ov),.io_outReady(mul_or),.io_out(mul_out),.io_exceptionFlags(mul_flags),.io_userOut(mul_user));
 HeteroFP32AddPipeBit1 add(.clock(clk_i),.reset(!rst_ni),.io_inValid(add_iv),.io_inReady(add_ir),.io_x(op_x),.io_y(op_y),.io_userIn(1'b0),.io_outValid(add_ov),.io_outReady(add_or),.io_out(add_out),.io_exceptionFlags(add_flags),.io_userOut(add_user));
 assign in_ready_o=state_q==S_IDLE;assign out_valid_o=state_q==S_DONE;assign y_o=y_q;assign exception_flags_o=flags_q;assign domain_error_o=domain_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=S_IDLE;op_q<=0;x_q<=0;norm_q<=0;scale_q<=0;m_q<=0;b_q<=0;tmp_q<=0;y0_q<=0;scaled_q<=0;y_q<=0;flags_q<=0;domain_q<=0;accepted_o<=0;completed_o<=0;end else begin
   case(state_q)
    S_IDLE:if(in_valid_i)begin accepted_o<=accepted_o+1'b1;flags_q<=0;domain_q<=0;x_q<=x_i;op_q<=0;
      if(zero)begin y_q<=32'h7f800000;state_q<=S_DONE;end else if(pinf)begin y_q<=0;state_q<=S_DONE;end else if(!normal)begin y_q<=32'h7fc00000;domain_q<=1;state_q<=S_DONE;end
      else begin norm_q<={1'b0,odd?8'd128:8'd127,x_i[22:0]};scale_q<={1'b0,scale_exponent[7:0],23'd0};m_q<=coeff[63:32];b_q<=coeff[31:0];state_q<=S_ISSUE;end end
    S_ISSUE:if((is_add&&add_ir)||(!is_add&&mul_ir))state_q<=S_WAIT;
    S_WAIT:if((is_add&&add_ov)||(!is_add&&mul_ov))begin
      flags_q<=flags_q|(is_add?add_flags:mul_flags);
      case(op_q)1:y0_q<=add_out;7:scaled_q<=mul_out;12:y_q<=mul_out;default:tmp_q<=is_add?add_out:mul_out;endcase
      if(op_q==12)state_q<=S_DONE;else begin op_q<=op_q+1'b1;state_q<=S_ISSUE;end
    end
    S_DONE:if(out_ready_i)begin completed_o<=completed_o+1'b1;state_q<=S_IDLE;end
    default:state_q<=S_IDLE;
   endcase
  end
 end
endmodule
