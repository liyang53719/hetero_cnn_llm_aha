`timescale 1ns/1ps
module tb_operator_sfu_rope_endpoint_v3;
 logic clk_i,rst_ni;initial begin clk_i=0;rst_ni=0;end always #1 clk_i=~clk_i;
 logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i;logic[15:0]req_tag_i;logic[7:0]req_parent_phase_i,req_terminal_phase_i;
 logic payload_valid_i,payload_ready_o;logic[511:0]payload_data_i,payload_trig_i;logic result_valid_o,result_ready_i;logic[511:0]result_data_o;logic[4:0]exception_flags_o;
 logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;
 integer tx,cycles;logic[511:0]held;
 operator_sfu_rope_endpoint_v3 dut(.*);
 initial begin repeat(30000)@(posedge clk_i);$fatal(1,"timeout");end
 initial begin req_valid_i=0;req_opcode_i=8'h3f;req_tag_i=16'h1234;req_parent_phase_i=8'h56;req_terminal_phase_i=8'h78;payload_valid_i=0;payload_data_i=0;payload_trig_i=0;result_ready_i=0;completion_ready_i=0;tx=0;cycles=0;repeat(4)@(posedge clk_i);rst_ni=1;
  for(tx=0;tx<100;tx++)begin
   for(int i=0;i<16;i++)begin payload_data_i[i*32+:32]=32'h3f000000+(tx*16+i)*32'h00001000;payload_trig_i[i*32+:32]=i[0]?32'h00000000:32'h3f800000;end held=payload_data_i;
   @(negedge clk_i);req_valid_i=1;do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;payload_valid_i=1;do @(posedge clk_i);while(!payload_ready_o);@(negedge clk_i);payload_valid_i=0;
   while(!result_valid_o)begin @(negedge clk_i);result_ready_i=(cycles%5)!=1;cycles=cycles+1;end
   if(result_data_o!==held)$fatal(1,"identity mismatch tx=%0d",tx);if(exception_flags_o[4:1])$fatal(1,"flags");
   result_ready_i=1;@(posedge clk_i);@(negedge clk_i);result_ready_i=0;wait(completion_valid_o);if(completion_status_o||completion_tag_o!=16'h1234||completion_parent_phase_o!=8'h56||completion_terminal_phase_o!=8'h78)$fatal(1,"completion");completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;
  end
  $display("OPERATOR_SFU_ROPE_ENDPOINT_V3_PASS transactions=100 pairs=800");$finish;
 end
endmodule
