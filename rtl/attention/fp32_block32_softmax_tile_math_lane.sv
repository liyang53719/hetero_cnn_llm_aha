// SPDX-License-Identifier: Apache-2.0
module fp32_block32_softmax_tile_math_lane(
 input logic clk_i,rst_ni,
 input logic sub_valid_i,output logic sub_ready_o,input logic[31:0]sub_x_i,sub_y_i,output logic sub_valid_o,input logic sub_ready_i,output logic[31:0]sub_z_o,output logic[4:0]sub_flags_o,
 output logic scale_ready_o,output logic scale_valid_o,input logic scale_ready_i,output logic[31:0]scale_z_o,output logic[4:0]scale_flags_o,
 output logic exp_ready_o,output logic exp_valid_o,input logic exp_ready_i,output logic[31:0]exp_z_o,output logic[12:0]exp_flags_o,
 input logic add_valid_i,output logic add_ready_o,input logic[31:0]add_x_i,add_y_i,output logic add_valid_o,input logic add_ready_i,output logic[31:0]add_z_o,output logic[4:0]add_flags_o
);
 logic sub_user,scale_user,add_user;logic[31:0]exp_accepted,exp_completed;
 HeteroFP32AddPipeBit1 sub(.clock(clk_i),.reset(!rst_ni),.io_inValid(sub_valid_i),.io_inReady(sub_ready_o),.io_x(sub_x_i),.io_y(sub_y_i),.io_userIn(1'b0),.io_outValid(sub_valid_o),.io_outReady(sub_ready_i),.io_out(sub_z_o),.io_exceptionFlags(sub_flags_o),.io_userOut(sub_user));
 HeteroFP32MulPipeBit1 scale(.clock(clk_i),.reset(!rst_ni),.io_inValid(sub_valid_o&&sub_ready_i),.io_inReady(scale_ready_o),.io_x(sub_z_o),.io_y(32'h3fb8aa3b),.io_userIn(1'b0),.io_outValid(scale_valid_o),.io_outReady(scale_ready_i),.io_out(scale_z_o),.io_exceptionFlags(scale_flags_o),.io_userOut(scale_user));
 fp32_exp2_pwl_i1_candidate exp(.clk_i,.rst_ni,.in_valid_i(scale_valid_o&&scale_ready_i),.in_ready_o(exp_ready_o),.x_i(scale_z_o),.out_valid_o(exp_valid_o),.out_ready_i(exp_ready_i),.y_o(exp_z_o),.exception_flags_o(exp_flags_o),.accepted_o(exp_accepted),.completed_o(exp_completed));
 HeteroFP32AddPipeBit1 reduce(.clock(clk_i),.reset(!rst_ni),.io_inValid(add_valid_i),.io_inReady(add_ready_o),.io_x(add_x_i),.io_y(add_y_i),.io_userIn(1'b0),.io_outValid(add_valid_o),.io_outReady(add_ready_i),.io_out(add_z_o),.io_exceptionFlags(add_flags_o),.io_userOut(add_user));
endmodule
