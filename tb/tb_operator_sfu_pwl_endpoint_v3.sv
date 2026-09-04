`timescale 1ns/1ps
module tb_operator_sfu_pwl_endpoint_v3;
 logic clk_i,rst_ni;initial begin clk_i=0;rst_ni=0;end always #1 clk_i=~clk_i;logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i,req_variant_i;logic[15:0]req_tag_i;logic[7:0]req_parent_phase_i,req_terminal_phase_i;logic payload_valid_i,payload_ready_o;logic[511:0]payload_x_i;logic result_valid_o,result_ready_i;logic[511:0]result_y_o;logic[4:0]exception_flags_o;logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;
 operator_sfu_pwl_endpoint_v3 dut(.*);
 task finish_request(input[7:0]status);begin wait(completion_valid_o);if(completion_status_o!=status||completion_tag_o!=16'h1234||completion_parent_phase_o!=8'h56||completion_terminal_phase_o!=8'h78)$fatal(1,"completion");completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;end endtask
 initial begin repeat(100000)@(posedge clk_i);$fatal(1,"timeout");end
 initial begin req_valid_i=0;req_opcode_i=8'h47;req_variant_i=0;req_tag_i=16'h1234;req_parent_phase_i=8'h56;req_terminal_phase_i=8'h78;payload_valid_i=0;payload_x_i=0;result_ready_i=0;completion_ready_i=0;repeat(5)@(posedge clk_i);rst_ni=1;
  for(int tx=0;tx<100;tx++)begin @(negedge clk_i);req_variant_i=tx[0]?2:1;req_valid_i=1;do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;payload_valid_i=1;do @(posedge clk_i);while(!payload_ready_o);@(negedge clk_i);payload_valid_i=0;wait(result_valid_o);if(result_y_o!={16{tx[0]?32'h00000000:32'h3f317218}})$fatal(1,"result tx=%0d data=%h",tx,result_y_o);repeat(tx%4)@(posedge clk_i);if(!result_valid_o)$fatal(1,"stall");result_ready_i=1;@(posedge clk_i);@(negedge clk_i);result_ready_i=0;finish_request(0);end
  @(negedge clk_i);req_variant_i=0;req_valid_i=1;do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;finish_request(4);
  $display("OPERATOR_SFU_PWL_ENDPOINT_V3_PASS transactions=100 invalid=1 variants=2");$finish;end
endmodule
