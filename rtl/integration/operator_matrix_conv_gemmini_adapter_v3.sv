// SPDX-License-Identifier: Apache-2.0
module operator_matrix_conv_gemmini_adapter_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,
 input logic[7:0]req_opcode_i,input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic[15:0]req_flags_i,input logic[23:0]req_src0_i,req_src1_i,req_dst_i,
 output logic command_valid_o,input logic command_ready_i,output logic[127:0]command_data_o,
 input logic event_valid_i,output logic event_ready_o,input logic[55:0]event_data_i,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
 localparam logic[1:0]S_IDLE=0,S_ISSUE=1,S_WAIT=2,S_REPORT=3;logic[1:0]state_q;
 logic[127:0]command_q;logic[15:0]tag_q;logic[7:0]parent_q,terminal_q,status_q;
 assign req_ready_o=state_q==S_IDLE;assign command_valid_o=state_q==S_ISSUE;assign command_data_o=command_q;
 assign event_ready_o=state_q==S_WAIT;assign completion_valid_o=state_q==S_REPORT;
 assign completion_tag_o=tag_q;assign completion_parent_phase_o=parent_q;
 assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=S_IDLE;command_q<=0;tag_q<=0;parent_q<=0;terminal_q<=0;status_q<=0;end
  else case(state_q)
   S_IDLE:if(req_valid_i&&req_ready_o)begin tag_q<=req_tag_i;parent_q<=req_parent_phase_i;terminal_q<=req_terminal_phase_i;status_q<=0;
    command_q<={req_dst_i,req_src1_i,req_src0_i,req_tag_i,16'd0,req_flags_i[12:0],3'd2,8'h22};
    if(req_opcode_i==8'h25)state_q<=S_ISSUE;else begin status_q<=8'd4;state_q<=S_REPORT;end end
   S_ISSUE:if(command_valid_o&&command_ready_i)state_q<=S_WAIT;
   S_WAIT:if(event_valid_i&&event_ready_o)begin
    if(event_data_i[55:40]!=tag_q)status_q<=8'he1;
    else if(event_data_i[31:29]!=3'd2)status_q<=8'he2;
    else status_q<=event_data_i[39:32];state_q<=S_REPORT;end
   S_REPORT:if(completion_valid_o&&completion_ready_i)state_q<=S_IDLE;
  endcase
 end
endmodule
