`timescale 1ns/1ps
module tb_independent_aperture #(parameter longint unsigned APERTURE_BEATS=24576);
 localparam logic [63:0] LIMIT=APERTURE_BEATS*64;
 logic clk_i=0, rst_ni=0, start_i=0; always #5 clk_i=~clk_i;
 logic [5:0] data_beats_i=8; logic [9:0] heads_i=1,head_dim_i=256,candidate_rotary_dim_i=64;
 logic [3:0] position_lane_i=0; logic [63:0] data_local_i=4096,position_local_i=0,out_local_i=12288,candidate_trig_local_i=8192;
 logic [7:0] candidate_policy_i=8'hb1; logic ready_o,l2_rd_valid_o,l2_rsp_ready_o,l2_wr_valid_o,done_o,unsupported_position_o;
 logic [14:0] l2_rd_addr_o,l2_wr_addr_o;logic [511:0] l2_wr_data_o;logic [63:0]l2_wr_be_o;
 logic [31:0]read_beats_o,write_beats_o,pairs_o,position_o,coefficient_steps_o;logic[4:0]exception_flags_o;
 integer rejected=0,admitted=0;
`define APERTURE_PORTS \
 \
  .clk_i,.rst_ni,.start_i,.data_beats_i,.heads_i,.head_dim_i,.position_lane_i,.data_local_i,.position_local_i,.out_local_i, \
  .candidate_trig_local_i,.candidate_rotary_dim_i,.candidate_policy_i,.ready_o,.l2_rd_valid_o,.l2_rd_ready_i(1'b0),.l2_rd_addr_o, \
  .l2_rsp_valid_i(1'b0),.l2_rsp_ready_o,.l2_rsp_data_i(512'd0),.l2_wr_valid_o,.l2_wr_ready_i(1'b0),.l2_wr_addr_o, \
  .l2_wr_data_o,.l2_wr_be_o,.done_o,.unsupported_position_o,.read_beats_o,.write_beats_o,.pairs_o,.position_o,.coefficient_steps_o,.exception_flags_o
 generate if (APERTURE_BEATS==24576) begin : default_capacity
  qwen2_shared_l2_rope_payload #(.ADDR_W(15),.EXPERIMENTAL_BF16_ROPE(1)) dut(`APERTURE_PORTS);
 end else begin : explicit_capacity
  qwen2_shared_l2_rope_payload #(.ADDR_W(15),.EXPERIMENTAL_BF16_ROPE(1),.CANDIDATE_L2_BEATS(APERTURE_BEATS)) dut(`APERTURE_PORTS);
 end endgenerate
`undef APERTURE_PORTS
 task automatic reset;begin @(negedge clk_i);rst_ni=0;start_i=0;repeat(4)@(negedge clk_i);rst_ni=1;repeat(2)@(negedge clk_i);
  if(!ready_o||done_o||l2_rd_valid_o||l2_rsp_ready_o||l2_wr_valid_o||read_beats_o||write_beats_o||pairs_o||exception_flags_o)$fatal(1,"reset residue");end endtask
 task automatic check(input logic[63:0]src,trig,dst,input integer heads,input bit legal);integer cycle;logic[14:0]held;begin
  while(!ready_o)@(negedge clk_i);
  data_local_i=src;candidate_trig_local_i=trig;out_local_i=dst;heads_i=10'(heads);data_beats_i=6'(heads*8);
  head_dim_i=256;candidate_rotary_dim_i=64;candidate_policy_i=8'hb1;start_i=1;
  @(negedge clk_i);start_i=0;
  // Once accepted, a changing caller must not change validation or request address.
  data_local_i=64'hffffffffffffffc0;candidate_trig_local_i=1;out_local_i=1;heads_i=0;data_beats_i=0;candidate_policy_i=0;
  cycle=0;
  if(legal)begin
   while(!l2_rd_valid_o&&!done_o&&cycle<8)begin @(negedge clk_i);cycle++;end
   if(done_o||!l2_rd_valid_o||l2_rd_addr_o!==15'(src>>6)||unsupported_position_o)$fatal(1,"legal boundary rejected src=%h trig=%h dst=%h",src,trig,dst);
   held=l2_rd_addr_o;start_i=1;
   repeat(9)begin @(negedge clk_i);if(!l2_rd_valid_o||l2_rd_addr_o!==held||done_o||l2_wr_valid_o||read_beats_o||write_beats_o||pairs_o)$fatal(1,"stalled request changed");end
   start_i=0;admitted++;reset();
  end else begin
   while(!done_o&&cycle<8)begin if(l2_rd_valid_o||l2_wr_valid_o||l2_rsp_ready_o)$fatal(1,"bad range touched bus src=%h trig=%h dst=%h",src,trig,dst);@(negedge clk_i);cycle++;end
   if(!done_o||!unsupported_position_o||read_beats_o||write_beats_o||pairs_o||exception_flags_o)$fatal(1,"invalid range accepted");
   @(negedge clk_i);if(done_o||!ready_o)$fatal(1,"bad completion duration");
   repeat(4)begin @(negedge clk_i);if(done_o||l2_rd_valid_o||l2_wr_valid_o)$fatal(1,"extra event after rejection");end
   rejected++;
  end
 end endtask
 initial begin
  reset();
  check(LIMIT,8192,12288,1,0);check(4096,LIMIT,12288,1,0);check(4096,8192,LIMIT,1,0);
  check(LIMIT-448,8192,12288,1,0);check(4096,LIMIT-64,12288,1,0);check(4096,8192,LIMIT-510,1,0);
  check(LIMIT-960,8192,12288,2,0);check(4096,8192,LIMIT-1022,2,0);
  check(64'hffffffffffffffc0,8192,12288,1,0);check(4096,64'hffffffffffffffc0,12288,1,0);check(4096,8192,64'hfffffffffffffffe,1,0);
  check(64'h200000,8192,12288,1,0);check(4097,8192,12288,1,0);check(4096,8193,12288,1,0);check(4096,8192,12289,1,0);
  check(LIMIT-512,8192,12288,1,1);check(4096,LIMIT-128,12288,1,1);check(4096,8192,LIMIT-512,1,1);
  check(LIMIT-1024,8192,LIMIT-1024,2,1);check(4096,8192,LIMIT-514,1,1);check(4096,8192,12288,1,1);
  $display("INDEPENDENT_APERTURE_PASS aperture_beats=%0d rejected=%0d admitted_preIO=%0d latched_config_and_stalled_request=1",APERTURE_BEATS,rejected,admitted);$finish;
 end
 initial begin repeat(4000)@(posedge clk_i);$fatal(1,"watchdog");end
endmodule
