`timescale 1ns/1ps
module tb_operator_sfu_vector_endpoint_v3;
 logic clk_i,rst_ni;initial begin clk_i=0;forever #1 clk_i=~clk_i;end
 logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i,req_parent_phase_i,req_terminal_phase_i,req_variant_i;logic[15:0]req_tag_i;
 logic payload_valid_i,payload_ready_o;logic[511:0]payload_a_i,payload_b_i;logic[15:0]payload_mask_i;
 logic result_valid_o,result_ready_i;logic[511:0]result_data_o;logic[4:0]exception_flags_o;
 logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;
 operator_sfu_vector_endpoint_v3 dut(.*);integer lane;
 task automatic run_op(input logic[7:0]op,input logic[7:0]variant,input logic mask,input logic[31:0]expected,input logic[15:0]tag);
  begin @(negedge clk_i);req_opcode_i=op;req_variant_i=variant;req_tag_i=tag;req_valid_i=1;@(posedge clk_i);@(negedge clk_i);req_valid_i=0;
   payload_mask_i={16{mask}};payload_valid_i=1;do @(posedge clk_i);while(!payload_ready_o);@(negedge clk_i);payload_valid_i=0;
   wait(result_valid_o);for(lane=0;lane<16;lane++)if(result_data_o[lane*32+:32]!==expected)$fatal(1,"op %h lane %0d got %h",op,lane,result_data_o[lane*32+:32]);
   repeat(2)begin @(posedge clk_i);if(!result_valid_o||result_data_o[31:0]!==expected)$fatal(1,"unstable result");end
   @(negedge clk_i);result_ready_i=1;@(posedge clk_i);@(negedge clk_i);result_ready_i=0;
   wait(completion_valid_o);if(completion_status_o!=0||completion_tag_o!=tag)$fatal(1,"bad completion");
   completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;end
 endtask
 task automatic run_reduce(input logic[7:0]op,input logic[31:0]expected,input logic[3:0]expected_index,input logic[15:0]tag);
  begin @(negedge clk_i);req_opcode_i=op;req_variant_i=0;req_tag_i=tag;req_valid_i=1;@(posedge clk_i);@(negedge clk_i);req_valid_i=0;
   payload_valid_i=1;do @(posedge clk_i);while(!payload_ready_o);@(negedge clk_i);payload_valid_i=0;
   wait(result_valid_o);if(result_data_o[31:0]!==expected||result_data_o[35:32]!==expected_index)$fatal(1,"bad reduce result");
   result_ready_i=1;@(posedge clk_i);@(negedge clk_i);result_ready_i=0;wait(completion_valid_o);
   if(completion_status_o!=0||completion_tag_o!=tag)$fatal(1,"bad reduce completion");completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;end
 endtask
 initial begin repeat(1000)@(posedge clk_i);$fatal(1,"watchdog");end
 initial begin rst_ni=0;req_valid_i=0;req_opcode_i=0;req_tag_i=0;req_parent_phase_i=8'h12;req_terminal_phase_i=8'h34;req_variant_i=0;
  payload_valid_i=0;payload_a_i={16{32'h3fc00000}};payload_b_i={16{32'h40000000}};payload_mask_i=0;result_ready_i=0;completion_ready_i=0;
  repeat(3)@(posedge clk_i);rst_ni=1;
  run_op(8'h30,0,0,32'h40600000,16'h3000);run_op(8'h31,0,0,32'hbf000000,16'h3001);
  run_op(8'h32,0,0,32'h40400000,16'h3002);run_op(8'h33,0,0,32'h40400000,16'h3003);
  run_op(8'h43,0,0,32'h3fc00000,16'h3004);run_op(8'h44,0,0,32'h40000000,16'h3005);
  run_op(8'h45,0,0,32'h00000000,16'h3006);run_op(8'h45,1,1,32'h3fc00000,16'h3007);
  run_op(8'h46,0,0,32'hbfc00000,16'h3008);run_op(8'h49,0,0,32'h3fc00000,16'h3009);
  run_op(8'h4a,0,0,32'hff800000,16'h300a);
  payload_a_i={16{32'h3fc00000}};run_reduce(8'h34,32'h41c00000,0,16'h300b);
  run_reduce(8'h35,32'h3fc00000,0,16'h300c);
  if(exception_flags_o!=0)$fatal(1,"unexpected fp flags");
  $display("OPERATOR_SFU_VECTOR_ENDPOINT_V3_PASS opcodes=12 cases=13 lanes=16");$finish;end
endmodule
