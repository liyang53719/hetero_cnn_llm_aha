// SPDX-License-Identifier: Apache-2.0
module operator_sfu_gate_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic payload_valid_i,output logic payload_ready_o,input logic[127:0]payload_gate_bf16_i,payload_up_bf16_i,input logic payload_last_i,
 output logic result_valid_o,input logic result_ready_i,output logic[127:0]result_bf16_o,output logic result_last_o,output logic[4:0]exception_flags_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
 localparam logic[2:0]IDLE=0,PAYLOAD=1,ISSUE=2,WAIT=3,COMPLETE=4;logic[2:0]st;logic[15:0]tag_q,front_tag_q;logic[7:0]parent_q,terminal_q,status_q,front_opcode_q,front_parent_q,front_terminal_q;logic[127:0]gate_q,up_q;logic last_q,front_valid_q;
 logic av,ar,aov,aor,al;logic[127:0]ao;logic[11:0]at;logic[4:0]af;
 assign av=st==ISSUE;assign aor=st==WAIT&&result_ready_i;
 bf16_silu_mul_lut_array8_fixed gate8(.clk_i,.rst_ni,.in_valid_i(av),.in_ready_o(ar),.gate_bf16_i(gate_q),.up_bf16_i(up_q),.tag_i(tag_q[11:0]),.last_i(last_q),.out_valid_o(aov),.out_ready_i(aor),.result_bf16_o(ao),.tag_o(at),.last_o(al),.exception_flags_o(af));
 assign req_ready_o=st==IDLE&&!front_valid_q;assign payload_ready_o=st==PAYLOAD;assign result_valid_o=st==WAIT&&aov;assign result_bf16_o=ao;assign result_last_o=al;assign exception_flags_o=af;
 assign completion_valid_o=st==COMPLETE;assign completion_tag_o=tag_q;assign completion_parent_phase_o=parent_q;assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;tag_q<=0;parent_q<=0;terminal_q<=0;status_q<=0;gate_q<=0;up_q<=0;last_q<=0;front_valid_q<=0;front_opcode_q<=0;front_tag_q<=0;front_parent_q<=0;front_terminal_q<=0;end else begin
  if(req_valid_i&&req_ready_o)begin front_valid_q<=1;front_opcode_q<=req_opcode_i;front_tag_q<=req_tag_i;front_parent_q<=req_parent_phase_i;front_terminal_q<=req_terminal_phase_i;end
  case(st)
  IDLE:if(front_valid_q)begin front_valid_q<=0;tag_q<=front_tag_q;parent_q<=front_parent_q;terminal_q<=front_terminal_q;status_q<=0;if(front_opcode_q==8'h41)st<=PAYLOAD;else begin status_q<=4;st<=COMPLETE;end end
  PAYLOAD:if(payload_valid_i)begin gate_q<=payload_gate_bf16_i;up_q<=payload_up_bf16_i;last_q<=payload_last_i;st<=ISSUE;end ISSUE:if(ar)st<=WAIT;WAIT:if(aov&&result_ready_i)begin if(at!=tag_q[11:0])status_q<=7;st<=COMPLETE;end
  COMPLETE:if(completion_ready_i)st<=IDLE;default:st<=IDLE;endcase end end
endmodule
