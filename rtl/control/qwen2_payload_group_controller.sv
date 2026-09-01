// SPDX-License-Identifier: Apache-2.0
module qwen2_payload_group_controller(
 input logic clk_i,rst_ni,start_i,input logic[2:0]group_i,input logic reference_inject_i,
 output logic busy_o,done_o,op_valid_o,input logic op_ready_i,output logic[4:0]layer_o,output logic[2:0]phase_o,output logic[7:0]tag_o,
 input logic op_done_valid_i,output logic op_done_ready_o,input logic[7:0]op_done_tag_i,
 output logic[31:0]commands_o,completions_o,command_stalls_o,event_wait_cycles_o,reference_injections_o,output logic protocol_error_o,output logic[63:0]trace_hash_o);
 logic busy_q,waiting_q;logic[2:0]group_q,phase_q;logic[1:0]layer_in_group_q;logic[31:0]commands_q,completions_q,command_stalls_q,event_wait_q,injections_q;logic error_q;logic[63:0]hash_q;
 assign layer_o={group_q,2'b00}+layer_in_group_q;assign phase_o=phase_q;assign tag_o={layer_o,phase_o};assign op_valid_o=busy_q&&!waiting_q;assign op_done_ready_o=busy_q&&waiting_q;assign busy_o=busy_q;assign commands_o=commands_q;assign completions_o=completions_q;assign command_stalls_o=command_stalls_q;assign event_wait_cycles_o=event_wait_q;assign reference_injections_o=injections_q;assign protocol_error_o=error_q;assign trace_hash_o=hash_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin busy_q<=0;waiting_q<=0;group_q<=0;phase_q<=0;layer_in_group_q<=0;done_o<=0;commands_q<=0;completions_q<=0;command_stalls_q<=0;event_wait_q<=0;injections_q<=0;error_q<=0;hash_q<=64'hcbf29ce484222325;end else begin done_o<=0;
   if(start_i&&!busy_q)begin if(group_i>6)error_q<=1;else begin busy_q<=1;waiting_q<=0;group_q<=group_i;phase_q<=0;layer_in_group_q<=0;commands_q<=0;completions_q<=0;command_stalls_q<=0;event_wait_q<=0;injections_q<=0;error_q<=0;hash_q<=64'hcbf29ce484222325;end end
   if(busy_q&&reference_inject_i)begin injections_q<=injections_q+1'b1;error_q<=1;end
   if(op_valid_o&&!op_ready_i)command_stalls_q<=command_stalls_q+1'b1;
   if(waiting_q&&!op_done_valid_i)event_wait_q<=event_wait_q+1'b1;
   if(op_valid_o&&op_ready_i)begin waiting_q<=1;commands_q<=commands_q+1'b1;hash_q<=(hash_q^{56'd0,tag_o})*64'h100000001b3;end
   if(op_done_valid_i&&op_done_ready_o)begin if(op_done_tag_i!=tag_o)error_q<=1;waiting_q<=0;completions_q<=completions_q+1'b1;
    if(phase_q==5)begin phase_q<=0;if(layer_in_group_q==3)begin busy_q<=0;done_o<=1;end else layer_in_group_q<=layer_in_group_q+1'b1;end else phase_q<=phase_q+1'b1;end
  end
 end
endmodule
