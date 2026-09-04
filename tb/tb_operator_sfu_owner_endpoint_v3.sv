`timescale 1ns/1ps
module tb_operator_sfu_owner_endpoint_v3;
 logic clk_i,rst_ni;initial begin clk_i=0;rst_ni=0;end always #1 clk_i=~clk_i;
 logic req_valid_i,req_ready_o;logic[7:0]req_opcode_i,req_variant_i;logic[15:0]req_tag_i;logic[7:0]req_parent_phase_i,req_terminal_phase_i;
 logic req_scratch_valid_i,req_first_i,req_last_i;logic[3:0]req_scratch_src0_i,req_scratch_src1_i,req_scratch_dst_i;
 logic payload_valid_i,payload_ready_o;logic[511:0]payload_a_i,payload_b_i,payload_c_i;logic[15:0]payload_mask_i;logic[31:0]payload_epsilon_i;logic payload_last_i;
 logic result_valid_o,result_ready_i;logic[511:0]result_data_o;logic result_last_o;logic[12:0]exception_flags_o;logic domain_error_o;
 logic soft_score_valid_i,soft_score_ready_o;logic[31:0]soft_score_i;logic soft_score_mask_i;logic soft_merge_header_valid_i,soft_merge_header_ready_o;logic[31:0]soft_ma_i,soft_la_i,soft_mb_i,soft_lb_i;logic soft_merge_beat_valid_i,soft_merge_beat_ready_o;logic[127:0]soft_oa_i,soft_ob_i;logic soft_merge_beat_last_i;logic soft_header_valid_o,soft_header_ready_i;logic[31:0]soft_m_o,soft_l_o;logic soft_weight_valid_o,soft_weight_ready_i;logic[31:0]soft_weight_o;logic soft_weight_last_o;logic soft_beat_valid_o,soft_beat_ready_i;logic[127:0]soft_o_o;logic soft_beat_last_o;
 logic completion_valid_o,completion_ready_i;logic[15:0]completion_tag_o;logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o;logic[7:0]ops[0:21];integer completed;
 operator_sfu_owner_endpoint_v3 dut(.*);
 task accept_completion(input[7:0]status);begin wait(completion_valid_o);if(completion_status_o!=status||completion_tag_o!=16'h1234||completion_parent_phase_o!=8'h56||completion_terminal_phase_o!=8'h78)$fatal(1,"completion op=%h status=%h",req_opcode_i,completion_status_o);completion_ready_i=1;@(posedge clk_i);@(negedge clk_i);completion_ready_i=0;completed=completed+1;end endtask
 task run_common(input[7:0]op,input[7:0]variant);begin @(negedge clk_i);req_opcode_i=op;req_variant_i=variant;req_valid_i=1;do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;payload_valid_i=1;do @(posedge clk_i);while(!payload_ready_o);@(negedge clk_i);payload_valid_i=0;wait(result_valid_o);repeat(2)@(posedge clk_i);if(!result_valid_o)$fatal(1,"result unstable op=%h",op);result_ready_i=1;@(posedge clk_i);@(negedge clk_i);result_ready_i=0;accept_completion(0);end endtask
 initial begin repeat(500000)@(posedge clk_i);$fatal(1,"timeout");end
 initial begin
  ops='{8'h30,8'h31,8'h32,8'h33,8'h34,8'h35,8'h43,8'h44,8'h45,8'h46,8'h49,8'h4a,8'h36,8'h37,8'h48,8'h3d,8'h3e,8'h42,8'h4b,8'h3f,8'h41,8'h47};
  req_valid_i=0;req_opcode_i=0;req_variant_i=0;req_tag_i=16'h1234;req_parent_phase_i=8'h56;req_terminal_phase_i=8'h78;req_scratch_valid_i=0;req_scratch_src0_i=0;req_scratch_src1_i=0;req_scratch_dst_i=0;req_first_i=1;req_last_i=1;payload_valid_i=0;payload_a_i=0;payload_b_i={16{32'h3f800000}};payload_c_i=0;payload_mask_i=16'hffff;payload_epsilon_i=32'h3727c5ac;payload_last_i=1;result_ready_i=0;
  soft_score_valid_i=0;soft_score_i=0;soft_score_mask_i=0;soft_merge_header_valid_i=0;soft_ma_i=0;soft_la_i=0;soft_mb_i=0;soft_lb_i=0;soft_merge_beat_valid_i=0;soft_oa_i=0;soft_ob_i=0;soft_merge_beat_last_i=0;soft_header_ready_i=0;soft_weight_ready_i=0;soft_beat_ready_i=0;completion_ready_i=0;completed=0;
  for(int i=0;i<16;i++)payload_a_i[i*32+:32]=i[0]?32'h40400000:32'h3f800000;
  repeat(5)@(posedge clk_i);rst_ni=1;
  for(int i=0;i<22;i++)begin if(ops[i]==8'h3f)for(int j=0;j<16;j++)payload_b_i[j*32+:32]=j[0]?0:32'h3f800000;else payload_b_i={16{32'h3f800000}};run_common(ops[i],(ops[i]==8'h47)?8'd1:8'd0);end
  @(negedge clk_i);req_opcode_i=8'h40;req_variant_i=0;req_valid_i=1;do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;
  for(int i=0;i<32;i++)begin @(negedge clk_i);soft_score_valid_i=1;do @(posedge clk_i);while(!soft_score_ready_o);end @(negedge clk_i);soft_score_valid_i=0;wait(soft_header_valid_o);if(soft_m_o!=0||soft_l_o!=32'h42000000)$fatal(1,"soft header");soft_header_ready_i=1;@(posedge clk_i);@(negedge clk_i);soft_header_ready_i=0;
  for(int i=0;i<32;i++)begin wait(soft_weight_valid_o);if(soft_weight_o!=32'h3f800000||soft_weight_last_o!=(i==31))$fatal(1,"soft weight");soft_weight_ready_i=1;@(posedge clk_i);@(negedge clk_i);soft_weight_ready_i=0;end accept_completion(0);
  @(negedge clk_i);req_opcode_i=8'hff;req_variant_i=0;req_valid_i=1;do @(posedge clk_i);while(!req_ready_o);@(negedge clk_i);req_valid_i=0;accept_completion(4);
  if(completed!=24)$fatal(1,"completed=%0d",completed);$display("OPERATOR_SFU_OWNER_ENDPOINT_V3_PASS opcodes=23 invalid=1 checked_completions=24");$finish;
 end
endmodule
