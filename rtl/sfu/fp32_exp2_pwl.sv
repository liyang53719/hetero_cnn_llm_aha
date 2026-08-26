// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module fp32_exp2_pwl(
 input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[31:0]x_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]y_o,output logic[12:0]exception_flags_o,
 output logic[31:0]accepted_o,output logic[31:0]completed_o);
 `include "rtl/sfu/fp32_exp2_coeffs.svh"
 logic input_valid_q,output_valid_q,output_ready;logic[31:0]x_q,y_q;
 logic[15:0]scaled_floor;logic[7:0]convert_flags;logic signed[15:0]floor_signed;
 logic[7:0]index;logic[63:0]coeff;logic[31:0]m,b,mx,pwl;logic[4:0]mul_flags,add_flags;
 logic[31:0]result_comb;logic[12:0]flags_comb,flags_q;logic is_nan,is_inf;
 HeteroFP32Scale16Floor u_floor(.io_x(x_q),.io_out(scaled_floor),.io_exceptionFlags(convert_flags));
 assign floor_signed=$signed(scaled_floor);assign index=8'($signed(floor_signed)+16'sd256);
 assign coeff=exp2_pwl_coeff(index);assign m=coeff[63:32];assign b=coeff[31:0];
 HeteroFP32Alu u_mul(.io_op(1'b1),.io_x(m),.io_y(x_q),.io_out(mx),.io_exceptionFlags(mul_flags));
 HeteroFP32Alu u_add(.io_op(1'b0),.io_x(mx),.io_y(b),.io_out(pwl),.io_exceptionFlags(add_flags));
 assign is_nan=&x_q[30:23]&&|x_q[22:0];assign is_inf=&x_q[30:23]&&!(|x_q[22:0]);
 always_comb begin flags_comb={convert_flags,mul_flags|add_flags};
  if(is_nan)result_comb=0;else if(is_inf)result_comb=x_q[31]?32'd0:32'h3f800000;
  else if(floor_signed< -16'sd256)result_comb=0;
  else if(floor_signed>=0)result_comb=32'h3f800000;else result_comb=pwl;end
 assign output_ready=!output_valid_q||out_ready_i;assign in_ready_o=!input_valid_q||output_ready;
 assign out_valid_o=output_valid_q;assign y_o=y_q;assign exception_flags_o=flags_q;
 always_ff @(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin input_valid_q<=0;output_valid_q<=0;x_q<=0;y_q<=0;flags_q<=0;accepted_o<=0;completed_o<=0;end else begin
  if(output_valid_q&&out_ready_i)completed_o<=completed_o+1'b1;
  if(output_ready)begin output_valid_q<=input_valid_q;if(input_valid_q)begin y_q<=result_comb;flags_q<=flags_comb;end end
  if(in_ready_o)begin input_valid_q<=in_valid_i;if(in_valid_i)begin x_q<=x_i;accepted_o<=accepted_o+1'b1;end end
 end end
endmodule
