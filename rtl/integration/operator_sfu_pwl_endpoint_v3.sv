// SPDX-License-Identifier: Apache-2.0
module operator_sfu_pwl_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,req_variant_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic payload_valid_i,output logic payload_ready_o,input logic[511:0]payload_x_i,
 output logic result_valid_o,input logic result_ready_i,output logic[511:0]result_y_o,output logic[4:0]exception_flags_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
 localparam logic[2:0]IDLE=0,PAYLOAD=1,ISSUE=2,WAIT=3,RESULT=4,COMPLETE=5;logic[2:0]st;logic[3:0]lane_q;logic[7:0]variant_q,status_q;
 logic[511:0]xq,yq;logic[4:0]flags_q;logic[15:0]tag_q;logic[7:0]parent_q,terminal_q;logic pv,pr,pov,por;logic[31:0]py;logic[4:0]pf;
 assign pv=st==ISSUE;assign por=st==WAIT;fp32_pwl_nonlinear_pipe core(.clk_i,.rst_ni,.in_valid_i(pv),.in_ready_o(pr),.variant_i(variant_q),.x_i(xq[lane_q*32+:32]),.out_valid_o(pov),.out_ready_i(por),.y_o(py),.exception_flags_o(pf));
 assign req_ready_o=st==IDLE;assign payload_ready_o=st==PAYLOAD;assign result_valid_o=st==RESULT;assign result_y_o=yq;assign exception_flags_o=flags_q;
 assign completion_valid_o=st==COMPLETE;assign completion_tag_o=tag_q;assign completion_parent_phase_o=parent_q;assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;lane_q<=0;variant_q<=0;status_q<=0;xq<=0;yq<=0;flags_q<=0;tag_q<=0;parent_q<=0;terminal_q<=0;end else case(st)
  IDLE:if(req_valid_i)begin tag_q<=req_tag_i;parent_q<=req_parent_phase_i;terminal_q<=req_terminal_phase_i;status_q<=0;variant_q<=req_variant_i;if(req_opcode_i!=8'h47||!(req_variant_i inside {8'd1,8'd2}))begin status_q<=4;st<=COMPLETE;end else st<=PAYLOAD;end
  PAYLOAD:if(payload_valid_i)begin xq<=payload_x_i;lane_q<=0;flags_q<=0;st<=ISSUE;end
  ISSUE:if(pr)st<=WAIT;WAIT:if(pov)begin yq[lane_q*32+:32]<=py;flags_q<=flags_q|pf;if(lane_q==15)st<=RESULT;else begin lane_q<=lane_q+1'b1;st<=ISSUE;end end
  RESULT:if(result_ready_i)st<=COMPLETE;COMPLETE:if(completion_ready_i)st<=IDLE;default:st<=IDLE;endcase end
endmodule
