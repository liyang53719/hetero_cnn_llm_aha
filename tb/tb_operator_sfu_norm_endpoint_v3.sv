`timescale 1ns/1ps
module tb_operator_sfu_norm_endpoint_v3;
 logic clk_i,rst_ni=0;initial clk_i=0;always #1 clk_i=~clk_i;
 logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i;logic[15:0]req_tag_i;
 logic[7:0]req_parent_phase_i,req_terminal_phase_i;logic payload_valid_i,payload_ready_o;
 logic[511:0]payload_x_i,payload_weight_i,payload_bias_i;logic[31:0]payload_epsilon_i;
 logic result_valid_o,result_ready_i;logic[511:0]result_y_o;logic[4:0]exception_flags_o;
 logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;
 logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;
 operator_sfu_norm_endpoint_v3 dut(.*);
 task run(input[7:0]op,input[31:0]lo,input[31:0]hi);begin
  @(negedge clk_i);req_opcode_i=op;req_valid_i=1;@(posedge clk_i);@(negedge clk_i);req_valid_i=0;payload_valid_i=1;
  do @(posedge clk_i);while(!payload_ready_o);@(negedge clk_i);payload_valid_i=0;wait(result_valid_o);
  for(int i=0;i<16;i++)if(result_y_o[i*32+:32]<lo||result_y_o[i*32+:32]>hi)$fatal(1,"norm %h",result_y_o[i*32+:32]);
  result_ready_i=1;@(posedge clk_i);@(negedge clk_i);result_ready_i=0;wait(completion_valid_o);if(completion_status_o)$fatal(1,"status");
  completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;
 end endtask
 initial begin repeat(5000)@(posedge clk_i);$fatal(1,"timeout");end
 initial begin
  req_valid_i=0;req_opcode_i=0;req_tag_i=1;req_parent_phase_i=2;req_terminal_phase_i=3;payload_valid_i=0;
  payload_x_i={16{32'h40000000}};payload_weight_i={16{32'h3f800000}};payload_bias_i=0;payload_epsilon_i=0;
  result_ready_i=0;completion_ready_i=0;repeat(3)@(posedge clk_i);rst_ni=1;
  run(8'h3d,32'h3f7ffff0,32'h3f800010);run(8'h3e,32'h3f7ffff0,32'h3f800010);run(8'h42,32'h3e7ffff0,32'h3e800010);
  for(int i=0;i<16;i++)payload_x_i[i*32+:32]=(i[0]?32'h40400000:32'h3f800000);
  payload_weight_i={16{32'h40000000}};payload_bias_i={16{32'h3f000000}};run(8'h4b,32'h00000000,32'hffffffff);
  for(int i=0;i<16;i++)if(result_y_o[i*32+:32]!=(i[0]?32'h40200000:32'hbfc00000))$fatal(1,"layer lane=%0d got=%h",i,result_y_o[i*32+:32]);
  $display("OPERATOR_SFU_NORM_ENDPOINT_V3_PASS rms=1 group_rms=1 l2=1 layer=1");$finish;
 end
endmodule
