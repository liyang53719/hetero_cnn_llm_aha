`timescale 1ns/1ps
module tb_operator_sfu_online_softmax_endpoint_v3;
 logic clk_i,rst_ni;initial begin clk_i=0;rst_ni=0;end always #1 clk_i=~clk_i;
 logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i,req_variant_i;logic[15:0]req_tag_i;logic[7:0]req_parent_phase_i,req_terminal_phase_i;
 logic score_valid_i,score_ready_o;logic[31:0]score_i;logic score_mask_i;
 logic merge_header_valid_i,merge_header_ready_o;logic[31:0]ma_i,la_i,mb_i,lb_i;
 logic merge_beat_valid_i,merge_beat_ready_o;logic[127:0]oa_i,ob_i;logic merge_beat_last_i;
 logic header_valid_o,header_ready_i;logic[31:0]m_o,l_o;logic weight_valid_o,weight_ready_i;logic[31:0]weight_o;logic weight_last_o;
 logic beat_valid_o,beat_ready_i;logic[127:0]o_o;logic beat_last_o;logic[4:0]exception_flags_o;
 logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;
 integer outputs,cycles;
 operator_sfu_online_softmax_endpoint_v3 dut(.*);
 task request(input[7:0]variant);begin @(negedge clk_i);req_variant_i=variant;req_valid_i=1;do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;end endtask
 task finish_request;begin wait(completion_valid_o);if(completion_status_o||completion_tag_o!=16'h1234||completion_parent_phase_o!=8'h56||completion_terminal_phase_o!=8'h78)$fatal(1,"completion");completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;end endtask
 initial begin repeat(100000)@(posedge clk_i);$fatal(1,"timeout");end
 initial begin
  req_valid_i=0;req_opcode_i=8'h40;req_variant_i=0;req_tag_i=16'h1234;req_parent_phase_i=8'h56;req_terminal_phase_i=8'h78;
  score_valid_i=0;score_i=0;score_mask_i=0;merge_header_valid_i=0;ma_i=0;la_i=0;mb_i=0;lb_i=0;merge_beat_valid_i=0;oa_i=0;ob_i=0;merge_beat_last_i=0;
  header_ready_i=0;weight_ready_i=0;beat_ready_i=0;completion_ready_i=0;repeat(5)@(posedge clk_i);rst_ni=1;
  request(0);for(int i=0;i<32;i++)begin @(negedge clk_i);score_valid_i=1;do @(posedge clk_i);while(!score_ready_o);end @(negedge clk_i);score_valid_i=0;
  wait(header_valid_o);if(m_o!=0||l_o!=32'h42000000)$fatal(1,"block header m=%h l=%h",m_o,l_o);repeat(3)@(posedge clk_i);if(!header_valid_o)$fatal(1,"block header stall");header_ready_i=1;@(posedge clk_i);@(negedge clk_i);header_ready_i=0;
  outputs=0;cycles=0;while(outputs<32)begin @(negedge clk_i);weight_ready_i=(cycles%3)!=1;@(posedge clk_i);if(weight_valid_o&&weight_ready_i)begin if(weight_o!=32'h3f800000||weight_last_o!=(outputs==31))$fatal(1,"weight i=%0d w=%h last=%0d",outputs,weight_o,weight_last_o);outputs=outputs+1;end cycles=cycles+1;end @(negedge clk_i);weight_ready_i=0;finish_request();
  request(1);@(negedge clk_i);ma_i=0;la_i=32'h42000000;mb_i=0;lb_i=32'h42000000;merge_header_valid_i=1;do @(posedge clk_i);while(!merge_header_ready_o);@(negedge clk_i);merge_header_valid_i=0;
  wait(header_valid_o);if(m_o!=0||l_o!=32'h42800000)$fatal(1,"merge header m=%h l=%h",m_o,l_o);repeat(2)@(posedge clk_i);header_ready_i=1;@(posedge clk_i);@(negedge clk_i);header_ready_i=0;
  for(int i=0;i<32;i++)begin @(negedge clk_i);oa_i={4{32'h3f800000}};ob_i={4{32'h40400000}};merge_beat_last_i=i==31;merge_beat_valid_i=1;do @(posedge clk_i);while(!merge_beat_ready_o);@(negedge clk_i);merge_beat_valid_i=0;cycles=0;while(1)begin beat_ready_i=(cycles%4)!=1;@(posedge clk_i);if(beat_valid_o&&beat_ready_i)begin if(o_o!={4{32'h40800000}}||beat_last_o!=(i==31))$fatal(1,"merge beat i=%0d o=%h last=%0d",i,o_o,beat_last_o);break;end @(negedge clk_i);cycles=cycles+1;end @(negedge clk_i);beat_ready_i=0;end finish_request();
  $display("OPERATOR_SFU_ONLINE_SOFTMAX_ENDPOINT_V3_PASS block32=1 merge128_beats=32 legacy=0");$finish;
 end
endmodule
