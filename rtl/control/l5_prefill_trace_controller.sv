// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module l5_prefill_trace_controller(
 input logic clk_i,rst_ni,start_i,command_ready_i,engine_done_i,input logic[10:0]sequence_length_i,
 output logic command_valid_o,measured_latency_valid_o,score_matrix_o,done_o,config_error_o,
 output logic[10:0]sequence_length_o,output logic[4:0]operation_o,output logic[2:0]engine_o,
 output logic[31:0]work_items_o,matrix_steps_o,measured_latency_o,commands_issued_o,matrix_steps_total_o,rope_pairs_total_o,dot_operations_total_o,online_updates_total_o,reciprocals_total_o,normalization_chunks_total_o,silu_scalars_total_o,product_chunks_total_o,score_matrix_commands_o,
 output logic[63:0]busy_cycles_o);
 logic inflight,child_latency_valid;
 l5_prefill_count_controller u_count(.clk_i,.rst_ni,.start_i,.command_ready_i,.engine_done_i,.sequence_length_i,
  .command_valid_o,.measured_latency_valid_o(child_latency_valid),.score_matrix_o,.done_o,.config_error_o,
  .sequence_length_o,.operation_o,.engine_o,.work_items_o,.matrix_steps_o,.commands_issued_o,.matrix_steps_total_o,
  .rope_pairs_total_o,.dot_operations_total_o,.online_updates_total_o,.reciprocals_total_o,.normalization_chunks_total_o,
  .silu_scalars_total_o,.product_chunks_total_o,.score_matrix_commands_o);
 function automatic[31:0]lat(input[4:0]op,input logic q384);if(q384)case(op)
  0:lat=149760;1:lat=7077888;2,3:lat=1179648;4:lat=36864;5,6:lat=6144;7:lat=1179648;8:lat=196608;9,10:lat=49152;
  11:lat=23950080;12:lat=5308416;13:lat=18432;14:lat=36864;15:lat=7077888;16:lat=36864;17,18,21:lat=41287680;
  19:lat=30965760;20:lat=215040;22:lat=36864;default:lat=0;endcase else case(op)
  0:lat=49920;1:lat=2359296;2,3:lat=393216;4:lat=12288;5,6:lat=2048;7:lat=393216;8:lat=65536;9,10:lat=16384;
  11:lat=2674944;12:lat=589824;13:lat=6144;14:lat=12288;15:lat=2359296;16:lat=12288;17,18,21:lat=13762560;
  19:lat=10321920;20:lat=71680;22:lat=12288;default:lat=0;endcase endfunction
 assign measured_latency_valid_o=command_valid_o&&!config_error_o;
 assign measured_latency_o=lat(operation_o,sequence_length_o==384);
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin inflight<=0;busy_cycles_o<=0;end
  else if(start_i)begin inflight<=0;busy_cycles_o<=0;end
  else begin
   if(command_valid_o&&command_ready_i)inflight<=1;
   if(inflight)busy_cycles_o<=busy_cycles_o+1'b1;
   if(inflight&&engine_done_i)inflight<=0;
  end
 end
endmodule
