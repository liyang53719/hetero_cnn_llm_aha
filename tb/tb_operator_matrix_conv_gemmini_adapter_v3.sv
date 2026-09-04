`timescale 1ns/1ps
module tb_operator_matrix_conv_gemmini_adapter_v3;
 logic clk_i=0,rst_ni=0;always #1 clk_i=~clk_i;logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i;
 logic[15:0]req_tag_i,req_flags_i;logic[7:0]req_parent_phase_i,req_terminal_phase_i;logic[23:0]req_src0_i,req_src1_i,req_dst_i;
 logic command_valid_o,command_ready_i;logic[127:0]command_data_o;logic event_valid_i,event_ready_o;logic[55:0]event_data_i;
 logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;
 operator_matrix_conv_gemmini_adapter_v3 dut(.*);
 initial begin repeat(100)@(posedge clk_i);$fatal(1,"watchdog");end
 initial begin req_valid_i=0;req_opcode_i=8'h25;req_tag_i=16'h55aa;req_flags_i=16'h1234;req_parent_phase_i=8'h12;req_terminal_phase_i=8'h34;
  req_src0_i=24'h10203;req_src1_i=24'h40506;req_dst_i=24'h70809;command_ready_i=0;event_valid_i=0;event_data_i=0;completion_ready_i=0;
  repeat(3)@(posedge clk_i);rst_ni=1;@(negedge clk_i);req_valid_i=1;@(posedge clk_i);@(negedge clk_i);req_valid_i=0;
  wait(command_valid_o);repeat(3)begin @(posedge clk_i);if(!command_valid_o)$fatal(1,"unstable command");end
  if(command_data_o[7:0]!=8'h22||command_data_o[10:8]!=3'd2||command_data_o[55:40]!=16'h55aa||command_data_o[79:56]!=req_src0_i||command_data_o[103:80]!=req_src1_i||command_data_o[127:104]!=req_dst_i)$fatal(1,"bad command encoding");
  @(negedge clk_i);command_ready_i=1;@(posedge clk_i);@(negedge clk_i);command_ready_i=0;
  repeat(4)begin @(posedge clk_i);if(completion_valid_o)$fatal(1,"early completion");end
  @(negedge clk_i);event_data_i={16'h55aa,8'd0,3'd2,29'd17};event_valid_i=1;@(posedge clk_i);@(negedge clk_i);event_valid_i=0;
  wait(completion_valid_o);if(completion_status_o!=0||completion_tag_o!=16'h55aa)$fatal(1,"bad completion");
  $display("OPERATOR_MATRIX_CONV_GEMMINI_ADAPTER_V3_PASS command128=1 early_completion=0");$finish;end
endmodule
