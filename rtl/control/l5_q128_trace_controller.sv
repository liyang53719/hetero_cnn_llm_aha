// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module l5_q128_trace_controller(
 input logic clk_i,rst_ni,start_i,command_ready_i,engine_done_i,
 output logic command_valid_o,measured_latency_valid_o,score_matrix_o,done_o,
 output logic[4:0]operation_o,output logic[2:0]engine_o,
 output logic[31:0]work_items_o,matrix_steps_o,measured_latency_o,
 output logic[31:0]commands_issued_o,matrix_steps_total_o,rope_pairs_total_o,dot_operations_total_o,online_updates_total_o,reciprocals_total_o,normalization_chunks_total_o,silu_scalars_total_o,product_chunks_total_o,score_matrix_commands_o,
 output logic[63:0]busy_cycles_o);
 logic inflight,child_latency_valid;
 l5_q128_count_controller u(.clk_i,.rst_ni,.start_i,.command_valid_o,.command_ready_i,.operation_o,.engine_o,.work_items_o,.matrix_steps_o,.measured_latency_valid_o(child_latency_valid),.score_matrix_o,.engine_done_i,.done_o,.commands_issued_o,.matrix_steps_total_o,.rope_pairs_total_o,.dot_operations_total_o,.online_updates_total_o,.reciprocals_total_o,.normalization_chunks_total_o,.silu_scalars_total_o,.product_chunks_total_o,.score_matrix_commands_o);
 function automatic[31:0]lat(input[4:0]op);case(op)0:lat=49920;1:lat=2359296;2,3:lat=393216;4:lat=12288;5,6:lat=2048;7:lat=393216;8:lat=65536;9,10:lat=16384;11:lat=2674944;12:lat=589824;13:lat=6144;14:lat=12288;15:lat=2359296;16:lat=12288;17,18,21:lat=13762560;19:lat=10321920;20:lat=71680;22:lat=12288;default:lat=0;endcase endfunction
 assign measured_latency_valid_o=command_valid_o;assign measured_latency_o=lat(operation_o);
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin inflight<=0;busy_cycles_o<=0;end else begin if(start_i)begin inflight<=0;busy_cycles_o<=0;end else begin if(command_valid_o&&command_ready_i)inflight<=1;if(inflight)busy_cycles_o<=busy_cycles_o+1'b1;if(inflight&&engine_done_i)inflight<=0;end end end
endmodule
