// SPDX-License-Identifier: Apache-2.0
module operator_sfu_scalar_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic payload_valid_i,output logic payload_ready_o,input logic[31:0]payload_x_i,
 output logic result_valid_o,input logic result_ready_i,output logic[31:0]result_y_o,
 output logic[12:0]exception_flags_o,output logic domain_error_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
 localparam logic[2:0]S_IDLE=0,S_PAYLOAD=1,S_WAIT=2,S_RESULT=3,S_COMPLETE=4;logic[2:0]state_q;
 logic[7:0]opcode_q,status_q;logic[15:0]tag_q;logic[7:0]parent_q,terminal_q;logic[31:0]result_q;logic[12:0]flags_q;logic domain_q;
 logic rv,rr,rov,ror,rde;logic[31:0]ry,ra,rc;logic[4:0]rf;
 logic pv,pr,pov,por,pde;logic[31:0]py,pa,pc;logic[4:0]pf;
 logic ev,er,eov,eor;logic[31:0]ey,ea,ec;logic[12:0]ef;
 assign rv=state_q==S_PAYLOAD&&payload_valid_i&&opcode_q==8'h36;
 assign pv=state_q==S_PAYLOAD&&payload_valid_i&&opcode_q==8'h37;
 assign ev=state_q==S_PAYLOAD&&payload_valid_i&&opcode_q==8'h48;
 assign ror=state_q==S_WAIT&&opcode_q==8'h36;assign por=state_q==S_WAIT&&opcode_q==8'h37;assign eor=state_q==S_WAIT&&opcode_q==8'h48;
 fp32_rsqrt_nr2 rsqrt(.clk_i,.rst_ni,.in_valid_i(rv),.in_ready_o(rr),.x_i(payload_x_i),.out_valid_o(rov),.out_ready_i(ror),.y_o(ry),.exception_flags_o(rf),.domain_error_o(rde),.accepted_o(ra),.completed_o(rc));
 fp32_reciprocal_nr recip(.clk_i,.rst_ni,.in_valid_i(pv),.in_ready_o(pr),.x_i(payload_x_i),.out_valid_o(pov),.out_ready_i(por),.y_o(py),.exception_flags_o(pf),.domain_error_o(pde),.accepted_o(pa),.completed_o(pc));
 fp32_exp2_pwl exp2(.clk_i,.rst_ni,.in_valid_i(ev),.in_ready_o(er),.x_i(payload_x_i),.out_valid_o(eov),.out_ready_i(eor),.y_o(ey),.exception_flags_o(ef),.accepted_o(ea),.completed_o(ec));
 assign req_ready_o=state_q==S_IDLE;assign payload_ready_o=state_q==S_PAYLOAD&&(opcode_q == 8'h36 ? rr : opcode_q == 8'h37 ? pr : er);
 assign result_valid_o=state_q==S_RESULT;assign result_y_o=result_q;assign exception_flags_o=flags_q;assign domain_error_o=domain_q;
 assign completion_valid_o=state_q==S_COMPLETE;assign completion_tag_o=tag_q;assign completion_parent_phase_o=parent_q;assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin state_q<=S_IDLE;opcode_q<=0;status_q<=0;tag_q<=0;parent_q<=0;terminal_q<=0;result_q<=0;flags_q<=0;domain_q<=0;end else case(state_q)
  S_IDLE:if(req_valid_i&&req_ready_o)begin opcode_q<=req_opcode_i;tag_q<=req_tag_i;parent_q<=req_parent_phase_i;terminal_q<=req_terminal_phase_i;status_q<=0;
   if(req_opcode_i inside{8'h36,8'h37,8'h48})state_q<=S_PAYLOAD;else begin status_q<=8'd4;state_q<=S_COMPLETE;end end
  S_PAYLOAD:if(payload_valid_i&&payload_ready_o)state_q<=S_WAIT;
  S_WAIT:if((opcode_q==8'h36&&rov)||(opcode_q==8'h37&&pov)||(opcode_q==8'h48&&eov))begin
   result_q<=opcode_q == 8'h36 ? ry : opcode_q == 8'h37 ? py : ey;flags_q<=opcode_q == 8'h36 ? {8'd0,rf} : opcode_q == 8'h37 ? {8'd0,pf} : ef;
   domain_q<=opcode_q == 8'h36 ? rde : opcode_q == 8'h37 ? pde : 0;state_q<=S_RESULT;end
  S_RESULT:if(result_valid_o&&result_ready_i)state_q<=S_COMPLETE;
  S_COMPLETE:if(completion_valid_o&&completion_ready_i)state_q<=S_IDLE;
  default:state_q<=S_IDLE;
 endcase end
endmodule
