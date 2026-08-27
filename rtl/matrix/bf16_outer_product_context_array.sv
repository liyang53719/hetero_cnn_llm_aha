// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Context-interleaved wrapper for the proven BF16 outer-product array.
module bf16_outer_product_context_array #(
 parameter integer ROWS=16,COLS=32,CONTEXTS=4,FIFO_DEPTH=8,
 localparam integer LANES=ROWS*COLS,
 localparam integer CONTEXT_BITS=(CONTEXTS<=1)?1:$clog2(CONTEXTS),
 localparam integer FIFO_BITS=(FIFO_DEPTH<=1)?1:$clog2(FIFO_DEPTH)
)(input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic [CONTEXT_BITS-1:0] context_i,input logic clear_i,last_i,input logic [ROWS*16-1:0] a_i,input logic [COLS*16-1:0] b_i,output logic out_valid_o,input logic out_ready_i,output logic [CONTEXT_BITS-1:0] context_o,output logic last_o,output logic [LANES*32-1:0] acc_o,output logic [4:0] exception_flags_o,output logic [CONTEXTS-1:0] busy_o,accumulator_valid_o,output logic [31:0] accepted_steps_o,completed_steps_o,output logic protocol_error_o);
 logic [LANES*32-1:0] accumulator_bank[0:CONTEXTS-1];logic [CONTEXTS-1:0] accumulator_valid_q,busy_q;logic [CONTEXT_BITS-1:0] context_fifo[0:FIFO_DEPTH-1];logic last_fifo[0:FIFO_DEPTH-1];logic [FIFO_BITS-1:0] write_pointer_q,read_pointer_q;logic [FIFO_BITS:0] fifo_count_q;
 logic context_legal;logic [CONTEXT_BITS-1:0] safe_context;logic fifo_not_full,fifo_not_empty;logic array_in_valid,array_in_ready,issue_fire,array_out_valid,array_out_ready,completion_fire;logic [LANES*32-1:0] array_accumulator,issue_accumulator;logic [4:0] array_flags;logic [31:0] array_accepted,array_completed;logic [CONTEXT_BITS-1:0] completion_context;logic completion_last,completion_same_context,context_available;
 assign context_legal=context_i<CONTEXTS;assign safe_context=context_legal?context_i:'0;assign fifo_not_full=fifo_count_q<FIFO_DEPTH;assign fifo_not_empty=fifo_count_q!=0;assign completion_context=fifo_not_empty?context_fifo[read_pointer_q]:'0;assign completion_last=fifo_not_empty?last_fifo[read_pointer_q]:1'b0;
 assign out_valid_o=array_out_valid&&fifo_not_empty;assign array_out_ready=out_ready_i&&fifo_not_empty;assign completion_fire=array_out_valid&&array_out_ready;assign completion_same_context=completion_fire&&completion_context==safe_context;assign context_available=!busy_q[safe_context]||completion_same_context;assign issue_accumulator=clear_i?'0:completion_same_context?array_accumulator:accumulator_valid_q[safe_context]?accumulator_bank[safe_context]:'0;
 assign array_in_valid=in_valid_i&&context_legal&&context_available&&fifo_not_full;assign in_ready_o=context_legal&&context_available&&fifo_not_full&&array_in_ready;assign issue_fire=array_in_valid&&array_in_ready;assign context_o=completion_context;assign last_o=completion_last;assign acc_o=array_accumulator;assign exception_flags_o=array_flags;assign busy_o=busy_q;assign accumulator_valid_o=accumulator_valid_q;
 bf16_outer_product_array #(.ROWS(ROWS),.COLS(COLS)) array(.clk_i,.rst_ni,.in_valid_i(array_in_valid),.in_ready_o(array_in_ready),.a_i,.b_i,.acc_i(issue_accumulator),.out_valid_o(array_out_valid),.out_ready_i(array_out_ready),.acc_o(array_accumulator),.exception_flags_o(array_flags),.accepted_steps_o(array_accepted),.completed_steps_o(array_completed));
 always_ff @(posedge clk_i or negedge rst_ni) begin
  if(!rst_ni)begin accumulator_valid_q<='0;busy_q<='0;write_pointer_q<='0;read_pointer_q<='0;fifo_count_q<='0;accepted_steps_o<='0;completed_steps_o<='0;protocol_error_o<=1'b0;end
  else begin
   if(in_valid_i&&!context_legal)protocol_error_o<=1'b1;if(array_out_valid&&!fifo_not_empty)protocol_error_o<=1'b1;
   if(completion_fire)begin accumulator_bank[completion_context]<=array_accumulator;accumulator_valid_q[completion_context]<=1'b1;busy_q[completion_context]<=1'b0;read_pointer_q<=(read_pointer_q==FIFO_DEPTH-1)?'0:read_pointer_q+1'b1;completed_steps_o<=completed_steps_o+1'b1;end
   if(issue_fire)begin context_fifo[write_pointer_q]<=safe_context;last_fifo[write_pointer_q]<=last_i;write_pointer_q<=(write_pointer_q==FIFO_DEPTH-1)?'0:write_pointer_q+1'b1;busy_q[safe_context]<=1'b1;accepted_steps_o<=accepted_steps_o+1'b1;end
   case({issue_fire,completion_fire})2'b10:fifo_count_q<=fifo_count_q+1'b1;2'b01:fifo_count_q<=fifo_count_q-1'b1;default:fifo_count_q<=fifo_count_q;endcase
  end
 end
`ifndef SYNTHESIS
 initial begin if(CONTEXTS<1)$fatal(1,"CONTEXTS");if(FIFO_DEPTH<2||(FIFO_DEPTH&(FIFO_DEPTH-1))!=0)$fatal(1,"FIFO_DEPTH");end
`endif
endmodule
