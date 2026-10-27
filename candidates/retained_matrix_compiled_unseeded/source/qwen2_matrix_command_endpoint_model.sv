// SPDX-License-Identifier: Apache-2.0
// SIMULATION ONLY: exact unseeded ExtModule ABI. This is NOT provider RTL.
module qwen2_matrix_command_endpoint(
  input wire clk_i,input wire rst_ni,input wire cmd_valid_i,input wire [127:0] cmd_i,
  output bit cmd_ready_o,input wire step_valid_i,input wire [2:0] step_context_i,
  input wire step_clear_i,input wire step_last_i,input wire command_last_tile_i,
  input wire [255:0] step_a_i,input wire [511:0] step_b_i,output bit step_ready_o,
  output bit out_valid_o,output wire [2:0] out_context_o,output bit out_last_o,
  output bit [16383:0] out_acc_o,input wire out_ready_i,output bit completion_valid_o,
  output wire [55:0] completion_data_o,input wire completion_ready_i,output bit protocol_error_o
);
  import "DPI-C" function chandle retained_endpoint_create_unseeded();
  import "DPI-C" function void retained_endpoint_reset(input chandle handle);
  import "DPI-C" function void retained_endpoint_edge(input chandle handle,input bit rst,
    input bit cv,input bit [127:0] cmd,input bit sv,input int unsigned ctx,input bit clear,
    input bit last,input bit command_last,input bit [255:0] a,input bit [511:0] b,
    input bit out_ready,input bit completion_ready);
  import "DPI-C" function void retained_endpoint_state_outputs(input chandle handle,input longint unsigned revision,
    output bit cmd_ready,output bit out_valid,output int unsigned out_context,output bit out_last,
    output bit [16383:0] out_acc,output bit completion_valid,output longint unsigned completion_data,output bit protocol_error);
  import "DPI-C" function bit retained_endpoint_step_ready(input chandle handle,input longint unsigned revision,
    input int unsigned ctx,input bit out_ready);
  chandle model_handle;
  bit initialized=0;
  longint unsigned state_revision=0;
  int unsigned context_word;
  longint unsigned completion_word;
  assign out_context_o=context_word[2:0];
  assign completion_data_o=completion_word[55:0];
  initial begin
    model_handle=retained_endpoint_create_unseeded();
    initialized=1;
  end
  // Capture actual inputs on the physical gated edge. Never infer an edge
  // inside a combinational callback: parent next-state inputs are not pre-edge.
  // Initialization joins this same process so explicit low reset is observed,
  // including a clock-gated endpoint whose first clock has not arrived yet.
  always @(posedge clk_i or negedge rst_ni or posedge initialized) begin
    if(initialized) begin
      if(!rst_ni) retained_endpoint_reset(model_handle);
      else if(clk_i) retained_endpoint_edge(model_handle,rst_ni,cmd_valid_i,cmd_i,
        step_valid_i,{29'b0,step_context_i},step_clear_i,step_last_i,command_last_tile_i,
        step_a_i,step_b_i,out_ready_i,completion_ready_i);
      if(state_revision==64'hffffffffffffffff) $fatal(1,"endpoint revision exhausted");
      state_revision<=state_revision+1;
    end
  end
  // State-only outputs have no live input dependency in the original unseeded
  // model. Keep a distinct process so the opaque DPI call does not create false
  // ready/valid dependency edges across the full original service handshake.
  always_comb begin
    if(initialized) retained_endpoint_state_outputs(model_handle,state_revision,
      cmd_ready_o,out_valid_o,context_word,out_last_o,out_acc_o,completion_valid_o,completion_word,protocol_error_o);
    else begin
      cmd_ready_o=0;out_valid_o=0;context_word=0;out_last_o=0;out_acc_o=0;
      completion_valid_o=0;completion_word=0;protocol_error_o=0;
    end
  end
  // This ready is NOT state-only: preserve step context and out_ready because
  // the original hardware permits a same-context pop/refill in the same cycle.
  always_comb begin
    if(initialized) step_ready_o=retained_endpoint_step_ready(model_handle,state_revision,
      {29'b0,step_context_i},out_ready_i);
    else step_ready_o=0;
  end
endmodule
