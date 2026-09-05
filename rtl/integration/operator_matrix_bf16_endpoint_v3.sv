// SPDX-License-Identifier: Apache-2.0
module operator_matrix_bf16_endpoint_v3 (
  input logic clk_i,rst_ni,
  input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,
  input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
  input logic[15:0]req_rows_i,req_columns_i,req_depth_i,
  input logic step_valid_i,output logic step_ready_o,input logic[2:0]step_context_i,
  input logic step_clear_i,step_last_i,input logic[255:0]step_a_i,input logic[511:0]step_b_i,
  output logic out_valid_o,input logic out_ready_i,output logic[2:0]out_context_o,
  output logic out_last_o,output logic[16383:0]out_acc_o,output logic[4:0]exception_flags_o,
  output logic completion_valid_o,input logic completion_ready_i,
  output logic[15:0]completion_tag_o,output logic[7:0]completion_parent_phase_o,
  output logic[7:0]completion_terminal_phase_o,output logic[7:0]completion_status_o,
  output logic protocol_error_o
);
  logic active_q,pending_q;logic[15:0]tag_q;logic[7:0]parent_q,terminal_q,status_q;
  logic matrix_in_ready,matrix_out_valid,matrix_out_ready,matrix_last,matrix_error;
  logic[2:0]matrix_context;logic[4:0]matrix_flags,matrix_busy,matrix_acc_valid;
  logic[31:0]accepted_steps,completed_steps;logic[16383:0]matrix_acc;
  logic supported,shape_legal;
  logic guard_allow,guard_done,guard_fault;
  assign supported=req_opcode_i==8'h20||req_opcode_i==8'h21||req_opcode_i==8'h22||
    req_opcode_i==8'h23||req_opcode_i==8'h24||req_opcode_i==8'h26;
  assign shape_legal=req_rows_i>0&&req_rows_i<=16&&req_columns_i>0&&req_columns_i<=32&&req_depth_i>0;
  assign req_ready_o=!active_q&&!pending_q&&!guard_fault;
  assign step_ready_o=active_q&&matrix_in_ready&&guard_allow;
  assign out_valid_o=active_q&&matrix_out_valid;
  assign matrix_out_ready=active_q&&out_ready_i;
  assign out_context_o=matrix_context;assign out_last_o=matrix_last;assign out_acc_o=matrix_acc;
  assign exception_flags_o=matrix_flags;assign completion_valid_o=pending_q;
  assign completion_tag_o=tag_q;assign completion_parent_phase_o=parent_q;
  assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;
  assign protocol_error_o=matrix_error||guard_fault;
  matrix_tile_step_guard step_guard(
    .clk_i,.rst_ni,.start_i(req_valid_i&&req_ready_o&&supported&&shape_legal),
    .depth_i(req_depth_i),.step_valid_i(step_valid_i&&active_q),
    .step_ready_i(matrix_in_ready),.context_i(step_context_i),
    .clear_i(step_clear_i),.last_i(step_last_i),
    .result_fire_i(out_valid_o&&out_ready_i),.result_last_i(out_last_o),
    .result_context_i(out_context_o),.allow_step_o(guard_allow),
    .done_o(guard_done),.fault_o(guard_fault));
  bf16_outer_product_context_array_rev8b_b_candidate matrix(
    .clk_i,.rst_ni,.in_valid_i(step_valid_i&&active_q&&guard_allow),.in_ready_o(matrix_in_ready),
    .context_i(step_context_i),.clear_i(step_clear_i),.last_i(step_last_i),.a_i(step_a_i),.b_i(step_b_i),
    .out_valid_o(matrix_out_valid),.out_ready_i(matrix_out_ready),.context_o(matrix_context),
    .last_o(matrix_last),.acc_o(matrix_acc),.exception_flags_o(matrix_flags),.busy_o(matrix_busy),
    .accumulator_valid_o(matrix_acc_valid),.accepted_steps_o(accepted_steps),
    .completed_steps_o(completed_steps),.protocol_error_o(matrix_error));
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin active_q<=0;pending_q<=0;tag_q<=0;parent_q<=0;terminal_q<=0;status_q<=0;end
    else begin
      if(req_valid_i&&req_ready_o)begin tag_q<=req_tag_i;parent_q<=req_parent_phase_i;terminal_q<=req_terminal_phase_i;
        if(!supported)begin status_q<=8'd4;pending_q<=1;end
        else if(!shape_legal)begin status_q<=8'd5;pending_q<=1;end
        else begin status_q<=0;active_q<=1;end
      end
      if(active_q&&(matrix_error||guard_fault))begin active_q<=0;status_q<=8'd7;pending_q<=1;end
      else if(active_q&&guard_done)begin active_q<=0;status_q<=0;pending_q<=1;end
      if(pending_q&&completion_ready_i)pending_q<=0;
    end
  end
endmodule
