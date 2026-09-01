// SPDX-License-Identifier: Apache-2.0
module qwen2_sfu_command_endpoint(
 input logic clk_i,rst_ni,input logic cmd_valid_i,output logic cmd_ready_o,input logic[127:0]cmd_i,
 input logic payload_valid_i,output logic payload_ready_o,input logic[49151:0]payload_x_i,payload_weight_i,
 output logic out_valid_o,input logic out_ready_i,output logic[49151:0]out_y_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[55:0]completion_data_o,output logic[4:0]exception_flags_o);
 logic active_q,pending_q;logic[15:0]event_q;logic[7:0]status_q;logic rinr,rov;logic[31:0]accepted,completed,rc,qc,oc;
 assign cmd_ready_o=!active_q&&!pending_q;assign payload_ready_o=active_q&&rinr;assign out_valid_o=active_q&&rov;assign completion_valid_o=pending_q;assign completion_data_o={event_q,status_q,3'd3,29'd0};
 fp32_rmsnorm1536_chunked#(.REFINE_RSQRT(1'b1))rms(.clk_i,.rst_ni,.in_valid_i(payload_valid_i&&active_q),.in_ready_o(rinr),.x_i(payload_x_i),.weight_i(payload_weight_i),.epsilon_i(32'h358637bd),.out_valid_o(rov),.out_ready_i(active_q&&out_ready_i),.y_o(out_y_o),.exception_flags_o,.accepted_o(accepted),.completed_o(completed),.reduction_cycles_o(rc),.rsqrt_cycles_o(qc),.output_cycles_o(oc));
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin active_q<=0;pending_q<=0;event_q<=0;status_q<=0;end else begin if(cmd_valid_i&&cmd_ready_o)begin event_q<=cmd_i[55:40];if(cmd_i[7:0]==8'h32)begin active_q<=1;status_q<=0;end else begin pending_q<=1;status_q<=8'd4;end end if(out_valid_o&&out_ready_i)begin active_q<=0;pending_q<=1;end if(pending_q&&completion_ready_i)pending_q<=0;end end
endmodule
