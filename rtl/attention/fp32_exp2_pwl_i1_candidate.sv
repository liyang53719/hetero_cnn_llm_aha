// SPDX-License-Identifier: Apache-2.0
// II=1 exp2 PWL with generated elastic FP32 mul/add pipelines.
module fp32_exp2_pwl_i1_candidate(
 input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[31:0]x_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]y_o,output logic[12:0]exception_flags_o,output logic[31:0]accepted_o,completed_o
);
 `include "rtl/sfu/fp32_exp2_coeffs.svh"
 logic x_valid_q,x_ready;logic[31:0]x_q;
 logic[15:0]scaled_floor;logic[7:0]floor_flags,index;logic signed[15:0]floor_signed;logic[63:0]coeff;logic special;logic[31:0]special_result;
 logic p0_valid_q,p0_ready;logic[31:0]p0_x;logic signed[15:0]p0_floor;logic[7:0]p0_flags;
 logic p1_iv,p1_ir,p1_ov,p1_or;logic[141:0]p1_i,p1_o;logic[31:0]p1_x,p1_m,p1_b,p1_result;logic p1_special;logic[12:0]p1_flags;logic[2:0]p1_level;
 logic mul_iv,mul_ir,mul_ov,mul_or,mul_user;logic[31:0]mul_z;logic[4:0]mul_flags;
 localparam M0W=78;logic m0_iv,m0_ir,m0_ov,m0_or;logic[M0W-1:0]m0_i,m0_o;logic m0_special;logic[31:0]m0_result,m0_b;logic[12:0]m0_flags;logic[3:0]m0_level;
 logic add_iv,add_ir,add_ov,add_or,add_user;logic[31:0]add_z;logic[4:0]add_flags;
 localparam M1W=46;logic m1_iv,m1_ir,m1_ov,m1_or;logic[M1W-1:0]m1_i,m1_o;logic m1_special;logic[31:0]m1_result;logic[12:0]m1_flags;logic[3:0]m1_level;
 logic o_iv,o_ir,o_ov,o_or;logic[44:0]o_i,o_o;logic[3:0]o_level;
 assign p0_ready=!p0_valid_q||p1_ir;assign x_ready=!x_valid_q||p0_ready;assign in_ready_o=x_ready;
 HeteroFP32Scale16Floor floor(.io_x(x_q),.io_out(scaled_floor),.io_exceptionFlags(floor_flags));assign floor_signed=$signed(scaled_floor);
 assign index=8'($signed(p0_floor)+16'sd256);assign coeff=exp2_pwl_coeff(index);assign special=(&p0_x[30:23])||(p0_floor < -16'sd256)||(p0_floor>=0);
 always_comb begin if((&p0_x[30:23])&&|p0_x[22:0])special_result=0;else if((&p0_x[30:23])&&!(|p0_x[22:0]))special_result=p0_x[31]?0:32'h3f800000;else if(p0_floor < -16'sd256)special_result=0;else special_result=32'h3f800000;end
 assign p1_i={p0_x,coeff[63:32],coeff[31:0],special,special_result,p0_flags,5'd0};assign p1_iv=p0_valid_q;
 rv_fifo#(.WIDTH(142),.DEPTH(4))p1(.clk_i,.rst_ni,.in_valid_i(p1_iv),.in_ready_o(p1_ir),.in_data_i(p1_i),.out_valid_o(p1_ov),.out_ready_i(p1_or),.out_data_o(p1_o),.level_o(p1_level));assign{p1_x,p1_m,p1_b,p1_special,p1_result,p1_flags}=p1_o;
 assign mul_iv=p1_ov&&m0_ir;assign m0_iv=p1_ov&&mul_ir;assign p1_or=mul_ir&&m0_ir;assign m0_i={p1_special,p1_result,p1_b,p1_flags};
 HeteroFP32MulPipeBit1 mul(.clock(clk_i),.reset(!rst_ni),.io_inValid(mul_iv),.io_inReady(mul_ir),.io_x(p1_m),.io_y(p1_x),.io_userIn(1'b0),.io_outValid(mul_ov),.io_outReady(mul_or),.io_out(mul_z),.io_exceptionFlags(mul_flags),.io_userOut(mul_user));
 rv_fifo#(.WIDTH(M0W),.DEPTH(8))m0(.clk_i,.rst_ni,.in_valid_i(m0_iv),.in_ready_o(m0_ir),.in_data_i(m0_i),.out_valid_o(m0_ov),.out_ready_i(m0_or),.out_data_o(m0_o),.level_o(m0_level));assign{m0_special,m0_result,m0_b,m0_flags}=m0_o;
 assign add_iv=mul_ov&&m0_ov&&m1_ir;assign m1_iv=mul_ov&&m0_ov&&add_ir;assign mul_or=m0_ov&&add_ir&&m1_ir;assign m0_or=mul_ov&&add_ir&&m1_ir;assign m1_i={m0_special,m0_result,m0_flags|{8'd0,mul_flags}};
 HeteroFP32AddPipeBit1 add(.clock(clk_i),.reset(!rst_ni),.io_inValid(add_iv),.io_inReady(add_ir),.io_x(mul_z),.io_y(m0_b),.io_userIn(1'b0),.io_outValid(add_ov),.io_outReady(add_or),.io_out(add_z),.io_exceptionFlags(add_flags),.io_userOut(add_user));
 rv_fifo#(.WIDTH(M1W),.DEPTH(8))m1(.clk_i,.rst_ni,.in_valid_i(m1_iv),.in_ready_o(m1_ir),.in_data_i(m1_i),.out_valid_o(m1_ov),.out_ready_i(m1_or),.out_data_o(m1_o),.level_o(m1_level));assign{m1_special,m1_result,m1_flags}=m1_o;
 assign o_iv=add_ov&&m1_ov;assign add_or=m1_ov&&o_ir;assign m1_or=add_ov&&o_ir;assign o_i={m1_flags|{8'd0,add_flags},m1_special?m1_result:add_z};
 rv_fifo#(.WIDTH(45),.DEPTH(8))of(.clk_i,.rst_ni,.in_valid_i(o_iv),.in_ready_o(o_ir),.in_data_i(o_i),.out_valid_o(o_ov),.out_ready_i(out_ready_i),.out_data_o(o_o),.level_o(o_level));assign out_valid_o=o_ov;assign{exception_flags_o,y_o}=o_o;
 always_ff@(posedge clk_i or negedge rst_ni)if(!rst_ni)begin x_valid_q<=0;p0_valid_q<=0;x_q<=0;p0_x<=0;p0_floor<=0;p0_flags<=0;accepted_o<=0;completed_o<=0;end else begin
  if(p0_ready)begin p0_valid_q<=x_valid_q;if(x_valid_q)begin p0_x<=x_q;p0_floor<=floor_signed;p0_flags<=floor_flags;end end
  if(x_ready)begin x_valid_q<=in_valid_i;if(in_valid_i)x_q<=x_i;end
  if(in_valid_i&&in_ready_o)accepted_o<=accepted_o+1;if(out_valid_o&&out_ready_i)completed_o<=completed_o+1;
 end
endmodule
