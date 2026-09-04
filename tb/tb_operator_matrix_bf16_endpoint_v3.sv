`timescale 1ns/1ps
module tb_operator_matrix_bf16_endpoint_v3;
 logic clk_i,rst_ni;initial begin clk_i=0;forever #1 clk_i=~clk_i;end
 logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i;logic[15:0]req_tag_i;
 logic[7:0]req_parent_phase_i,req_terminal_phase_i;logic[15:0]req_rows_i,req_columns_i,req_depth_i;
 logic step_valid_i,step_ready_o;logic[2:0]step_context_i;logic step_clear_i,step_last_i;
 logic[255:0]step_a_i;logic[511:0]step_b_i;logic out_valid_o,out_ready_i;logic[2:0]out_context_o;
 logic out_last_o;logic[16383:0]out_acc_o;logic[4:0]exception_flags_o;logic completion_valid_o,completion_ready_i;
 logic[15:0]completion_tag_o;logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;logic protocol_error_o;
 operator_matrix_bf16_endpoint_v3 dut(.*);
 task automatic run_op(input logic[7:0]op,input logic[15:0]tag);
  begin @(negedge clk_i);req_opcode_i=op;req_tag_i=tag;req_valid_i=1;do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;
   @(negedge clk_i);step_valid_i=1;do @(posedge clk_i);while(!step_ready_o);@(negedge clk_i);step_valid_i=0;
   wait(out_valid_o);if(!out_last_o||out_context_o!=0||(|out_acc_o))$fatal(1,"bad matrix output");
   @(posedge clk_i);wait(completion_valid_o);if(completion_status_o!=0||completion_tag_o!=tag)$fatal(1,"bad completion");
   @(negedge clk_i);completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;end
 endtask
 initial begin repeat(2000)@(posedge clk_i);$fatal(1,"watchdog");end
 initial begin rst_ni=0;req_valid_i=0;req_opcode_i=0;req_tag_i=0;req_parent_phase_i=8'h12;req_terminal_phase_i=8'h34;
  req_rows_i=16;req_columns_i=32;req_depth_i=1;step_valid_i=0;step_context_i=0;step_clear_i=1;step_last_i=1;
  step_a_i=0;step_b_i=0;out_ready_i=1;completion_ready_i=0;repeat(3)@(posedge clk_i);rst_ni=1;
  run_op(8'h20,16'h2000);run_op(8'h21,16'h2001);run_op(8'h22,16'h2002);
  run_op(8'h23,16'h2003);run_op(8'h24,16'h2004);run_op(8'h26,16'h2006);
  if(protocol_error_o)$fatal(1,"protocol error");
  $display("OPERATOR_MATRIX_BF16_ENDPOINT_V3_PASS opcodes=6 physical_array=16x32 contexts=5");$finish;end
endmodule
