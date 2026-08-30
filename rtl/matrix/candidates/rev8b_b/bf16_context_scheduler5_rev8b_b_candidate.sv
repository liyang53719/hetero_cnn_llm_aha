// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_context_scheduler5_rev8b_b_candidate (
  input logic clk_i,rst_ni,in_valid_i,
  output logic in_ready_o,
  input logic [2:0] context_i,
  input logic clear_i,last_i,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic [2:0] context_o,
  output logic last_o,array_in_valid_o,
  input logic array_in_ready_i,array_out_valid_i,
  output logic array_out_ready_o,
  output logic [2:0] issue_context_o,
  output logic issue_clear_o,completion_fire_o,
  output logic [2:0] completion_context_o,
  output logic [4:0] busy_o,accumulator_valid_o,
  output logic [31:0] accepted_steps_o,completed_steps_o,
  output logic protocol_error_o
);
  logic [4:0] busy_q,accumulator_valid_q;
  logic [2:0] context_fifo[0:7];
  logic last_fifo[0:7];
  logic [2:0] write_pointer_q,read_pointer_q;
  logic [3:0] fifo_count_q;
  logic fifo_not_full,fifo_not_empty,context_legal,context_available,issue_fire,completion_same_context;
  assign fifo_not_full=fifo_count_q<8;
  assign fifo_not_empty=fifo_count_q!=0;
  assign context_legal=context_i<3'd5;
  assign completion_context_o=fifo_not_empty?context_fifo[read_pointer_q]:'0;
  assign last_o=fifo_not_empty?last_fifo[read_pointer_q]:1'b0;
  assign out_valid_o=array_out_valid_i&&fifo_not_empty;
  assign array_out_ready_o=out_ready_i&&fifo_not_empty;
  assign completion_fire_o=array_out_valid_i&&array_out_ready_o;
  assign completion_same_context=completion_fire_o&&completion_context_o==context_i;
  assign context_available=context_legal&&(!busy_q[context_i]||completion_same_context);
  assign array_in_valid_o=in_valid_i&&context_available&&fifo_not_full;
  assign in_ready_o=context_available&&fifo_not_full&&array_in_ready_i;
  assign issue_fire=array_in_valid_o&&array_in_ready_i;
  assign issue_context_o=context_i;
  assign issue_clear_o=clear_i;
  assign context_o=completion_context_o;
  assign busy_o=busy_q;
  assign accumulator_valid_o=accumulator_valid_q;
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin
      busy_q<='0;accumulator_valid_q<='0;write_pointer_q<='0;read_pointer_q<='0;fifo_count_q<='0;
      accepted_steps_o<='0;completed_steps_o<='0;protocol_error_o<=0;
    end else begin
      if(in_valid_i&&!context_legal)protocol_error_o<=1'b1;
      if(array_out_valid_i&&!fifo_not_empty)protocol_error_o<=1'b1;
      if(completion_fire_o)begin
        accumulator_valid_q[completion_context_o]<=1'b1;
        busy_q[completion_context_o]<=1'b0;
        read_pointer_q<=read_pointer_q+1'b1;
        completed_steps_o<=completed_steps_o+1'b1;
      end
      if(issue_fire)begin
        context_fifo[write_pointer_q]<=context_i;last_fifo[write_pointer_q]<=last_i;
        write_pointer_q<=write_pointer_q+1'b1;busy_q[context_i]<=1'b1;
        accepted_steps_o<=accepted_steps_o+1'b1;
      end
      case({issue_fire,completion_fire_o})
        2'b10:fifo_count_q<=fifo_count_q+1'b1;
        2'b01:fifo_count_q<=fifo_count_q-1'b1;
        default:fifo_count_q<=fifo_count_q;
      endcase
    end
  end
endmodule
