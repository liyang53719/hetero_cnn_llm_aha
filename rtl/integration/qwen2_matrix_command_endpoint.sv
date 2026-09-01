// SPDX-License-Identifier: Apache-2.0
module qwen2_matrix_command_endpoint(
 input logic clk_i,rst_ni,input logic cmd_valid_i,output logic cmd_ready_o,input logic[127:0]cmd_i,
 input logic step_valid_i,output logic step_ready_o,input logic[2:0]step_context_i,input logic step_clear_i,step_last_i,input logic[255:0]step_a_i,input logic[511:0]step_b_i,
 output logic out_valid_o,input logic out_ready_i,output logic[2:0]out_context_o,output logic out_last_o,output logic[16383:0]out_acc_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[55:0]completion_data_o,output logic protocol_error_o);
 logic active_q,pending_q;logic[15:0]event_q;logic[7:0]status_q;logic minr,moutv,moutr,mlast,merror;logic[2:0]mctx;logic[4:0]mflags,mbusy,mvalid;logic[31:0]maccept,mcomplete;logic[16383:0]macc;
 assign cmd_ready_o=!active_q&&!pending_q;assign step_ready_o=active_q&&minr;assign out_valid_o=active_q&&moutv;assign moutr=active_q&&out_ready_i;assign out_context_o=mctx;assign out_last_o=mlast;assign out_acc_o=macc;assign completion_valid_o=pending_q;assign completion_data_o={event_q,status_q,3'd2,29'd0};assign protocol_error_o=merror;
 bf16_outer_product_context_array_rev8b_b_candidate matrix(.clk_i,.rst_ni,.in_valid_i(step_valid_i&&active_q),.in_ready_o(minr),.context_i(step_context_i),.clear_i(step_clear_i),.last_i(step_last_i),.a_i(step_a_i),.b_i(step_b_i),.out_valid_o(moutv),.out_ready_i(moutr),.context_o(mctx),.last_o(mlast),.acc_o(macc),.exception_flags_o(mflags),.busy_o(mbusy),.accumulator_valid_o(mvalid),.accepted_steps_o(maccept),.completed_steps_o(mcomplete),.protocol_error_o(merror));
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin active_q<=0;pending_q<=0;event_q<=0;status_q<=0;end else begin if(cmd_valid_i&&cmd_ready_o)begin event_q<=cmd_i[55:40];if(cmd_i[7:0]inside{8'h20,8'h21,8'h23,8'h24})begin active_q<=1;status_q<=0;end else begin pending_q<=1;status_q<=8'd4;end end if(out_valid_o&&out_ready_i&&out_last_o)begin active_q<=0;pending_q<=1;end if(pending_q&&completion_ready_i)pending_q<=0;end end
endmodule
