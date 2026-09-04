// SPDX-License-Identifier: Apache-2.0
module operator_sfu_rope_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic payload_valid_i,output logic payload_ready_o,input logic[511:0]payload_data_i,payload_trig_i,
 output logic result_valid_o,input logic result_ready_i,output logic[511:0]result_data_o,output logic[4:0]exception_flags_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
 localparam logic[2:0]IDLE=0,PAYLOAD=1,ISSUE=2,WAIT=3,RESULT=4,COMPLETE=5;
 logic[2:0]st;logic[2:0]pair_q;logic[511:0]data_q,trig_q,result_q;logic[4:0]flags_q;
 logic[15:0]tag_q;logic[7:0]parent_q,terminal_q,status_q;logic pv,pr,pov,por;logic[31:0]pe,po;logic[4:0]pf;
 assign pv=st==ISSUE;assign por=st==WAIT;
 fp32_rope_pair_pipe pair(.clk_i,.rst_ni,.in_valid_i(pv),.in_ready_o(pr),.even_i(data_q[(pair_q*2)*32+:32]),.odd_i(data_q[(pair_q*2+1)*32+:32]),.cos_i(trig_q[(pair_q*2)*32+:32]),.sin_i(trig_q[(pair_q*2+1)*32+:32]),.out_valid_o(pov),.out_ready_i(por),.even_o(pe),.odd_o(po),.exception_flags_o(pf));
 assign req_ready_o=st==IDLE;assign payload_ready_o=st==PAYLOAD;assign result_valid_o=st==RESULT;assign result_data_o=result_q;assign exception_flags_o=flags_q;
 assign completion_valid_o=st==COMPLETE;assign completion_tag_o=tag_q;assign completion_parent_phase_o=parent_q;assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;pair_q<=0;data_q<=0;trig_q<=0;result_q<=0;flags_q<=0;tag_q<=0;parent_q<=0;terminal_q<=0;status_q<=0;end else case(st)
  IDLE:if(req_valid_i)begin tag_q<=req_tag_i;parent_q<=req_parent_phase_i;terminal_q<=req_terminal_phase_i;status_q<=0;if(req_opcode_i==8'h3f)st<=PAYLOAD;else begin status_q<=4;st<=COMPLETE;end end
  PAYLOAD:if(payload_valid_i)begin data_q<=payload_data_i;trig_q<=payload_trig_i;pair_q<=0;flags_q<=0;st<=ISSUE;end
  ISSUE:if(pr)st<=WAIT;
  WAIT:if(pov)begin result_q[(pair_q*2)*32+:32]<=pe;result_q[(pair_q*2+1)*32+:32]<=po;flags_q<=flags_q|pf;if(pair_q==7)st<=RESULT;else begin pair_q<=pair_q+1'b1;st<=ISSUE;end end
  RESULT:if(result_ready_i)st<=COMPLETE;COMPLETE:if(completion_ready_i)st<=IDLE;default:st<=IDLE;endcase end
endmodule
