`timescale 1ns/1ps
/* verilator lint_off DECLFILENAME */
module tb_l4_matrix_l3_trace #(
  parameter integer CASE_ID=0,
  parameter logic[15:0] EVENT_ID=16'h0401,
  parameter logic[7:0] OPCODE=8'h10,
  parameter integer MACS=5814,
  parameter integer DESCRIPTOR_READS=4,
  parameter integer WEIGHT_READS=6,
  parameter integer ACTIVATION_BIAS_READS=26,
  parameter integer OUTPUT_WRITES=5,
  parameter integer SEMANTIC_DMA_BYTES=2195,
  parameter integer PHYSICAL_DMA_BYTES=2368,
  parameter integer DESCRIPTOR_BYTES=256,
  parameter bit REQUIRE_PROMOTION=1'b1
);
  logic clk_i;/* verilator lint_off SYNCASYNCNET */logic rst_ni;/* verilator lint_on SYNCASYNCNET */
  always #5 clk_i=~clk_i;integer cycles,start_cycle,end_cycle;
  logic host_cmd_valid_i,host_cmd_ready_o;logic[127:0]host_cmd_data_i;
  logic[5:0]engine_cmd_valid_o,engine_cmd_ready_i;
  logic[6*128-1:0]engine_cmd_data_o;logic[5:0]engine_completion_valid_i;
  logic[5:0]engine_completion_ready_o;logic[6*56-1:0]engine_completion_data_i;
  logic init_done_o;logic[4:0]command_level_o,completion_level_o;
  logic[31:0]event_macro_error_count_o;logic illegal_engine_o,watchdog_lock_o;
  logic[31:0]completion_grants_o,completion_protocol_error_count_o;
  logic[3:0]l2_rd_valid_i,l2_rd_ready_o,l2_rd_rsp_valid_o,l2_rd_rsp_ready_i;
  logic[59:0]l2_rd_addr_i;logic[2047:0]l2_rd_rsp_data_o;logic[3:0]l2_rd_rsp_error_o;
  logic[1:0]l2_wr_valid_i,l2_wr_ready_o;logic[29:0]l2_wr_addr_i;
  logic[1023:0]l2_wr_data_i;logic[127:0]l2_wr_be_i;
  logic[1:0]phy_rd_valid_o,phy_rd_ready_i;logic[29:0]phy_rd_addr_o;
  logic[1:0]phy_rsp_valid_i,phy_rsp_ready_o;logic[1023:0]phy_rsp_data_i;
  logic[1:0]phy_rsp_error_i;logic phy_wr_valid_o,phy_wr_ready_i;
  logic[14:0]phy_wr_addr_o;logic[511:0]phy_wr_data_o;logic[63:0]phy_wr_be_o;
  logic[31:0]descriptor_promotions_o,l2_read_grants_o,l2_write_grants_o;

  logic matrix_cfg_valid_i,matrix_cfg_ready_o,matrix_cfg_direction_i,matrix_cfg_route_i;
  logic[11:0]matrix_cfg_last_addr_i,matrix_cfg_tensor_id_i;logic[15:0]matrix_cfg_tag_i;
  logic[3:0]matrix_cfg_format_i,matrix_spad_write_valid_i,matrix_spad_write_ready_o;
  logic[47:0]matrix_spad_write_addr_i;logic[511:0]matrix_spad_write_data_i;
  logic[63:0]matrix_spad_write_mask_i;logic[3:0]matrix_spad_read_req_valid_i;
  logic[3:0]matrix_spad_read_req_ready_o;logic[47:0]matrix_spad_read_req_addr_i;
  logic[3:0]matrix_spad_read_resp_valid_o,matrix_spad_read_resp_ready_i;
  logic[511:0]matrix_spad_read_resp_data_o;logic matrix_transfer_done_o;
  logic[31:0]matrix_protocol_error_count_o;
  logic aha_cfg_valid_i,aha_cfg_ready_o;logic[17:0]aha_cfg_input_base_i,aha_cfg_output_base_i;
  logic[15:0]aha_cfg_input_beats_i,aha_cfg_output_beats_i,aha_cfg_output_tag_i;
  logic[11:0]aha_cfg_output_tensor_id_i;logic[3:0]aha_cfg_output_format_i;
  logic[63:0]aha_cfg_output_last_be_i;logic aha_run_done_i;
  logic aha_proc_packet_wr_en_o;logic[17:0]aha_proc_packet_wr_addr_o;
  logic[63:0]aha_proc_packet_wr_data_o;logic[7:0]aha_proc_packet_wr_strb_o;
  logic aha_proc_packet_rd_en_o;logic[17:0]aha_proc_packet_rd_addr_o;
  logic[63:0]aha_proc_packet_rd_data_i;logic aha_proc_packet_rd_data_valid_i;
  logic aha_native_eos_o,aha_transfer_done_o;logic[31:0]aha_protocol_error_count_o;
  logic kv_cfg_valid_i,kv_cfg_ready_o,kv_cfg_direction_i;logic[18:0]kv_cfg_base_addr_i;
  logic[15:0]kv_cfg_beats_i,kv_cfg_tag_i;logic[11:0]kv_cfg_tensor_id_i;
  logic[3:0]kv_cfg_format_i;logic[63:0]kv_cfg_last_be_i;
  logic kv_mem_write_valid_o,kv_mem_write_ready_i;logic[18:0]kv_mem_write_addr_o;
  logic[511:0]kv_mem_write_data_o;logic[63:0]kv_mem_write_be_o;
  logic kv_mem_read_req_valid_o,kv_mem_read_req_ready_i;logic[18:0]kv_mem_read_req_addr_o;
  logic kv_mem_read_rsp_valid_i,kv_mem_read_rsp_ready_o;logic[511:0]kv_mem_read_rsp_data_i;
  logic kv_mem_read_rsp_error_i,kv_transfer_done_o;logic[31:0]kv_protocol_error_count_o;
  hetero_l3_production_top #(.WATCHDOG_CYCLES(4096))dut(.*);

  logic[63:0]mem_cycle,mem_reads,mem_writes,mem_conflicts,mem_rstall,mem_wstall;
  shared_l2_fabric #(.ADDR_W(15),.ROWS_PER_BANK(6144))mem(
    .clk_i,.rst_ni,.rd_valid_i(phy_rd_valid_o),.rd_ready_o(phy_rd_ready_i),
    .rd_addr_i(phy_rd_addr_o),.rd_resp_valid_o(phy_rsp_valid_i),
    .rd_resp_ready_i(phy_rsp_ready_o),.rd_data_o(phy_rsp_data_i),
    .wr_valid_i(phy_wr_valid_o),.wr_ready_o(phy_wr_ready_i),.wr_addr_i(phy_wr_addr_o),
    .wr_data_i(phy_wr_data_o),.wr_be_i(phy_wr_be_o),.cycle_count_o(mem_cycle),
    .read_count_o(mem_reads),.write_count_o(mem_writes),.bank_conflict_count_o(mem_conflicts),
    .read_stall_count_o(mem_rstall),.write_stall_count_o(mem_wstall));
  assign phy_rsp_error_i=0;
  integer responses[0:2],writes_done;
  logic matrix_command_seen;
  always_comb begin engine_cmd_ready_i=0;engine_cmd_ready_i[2]=!matrix_command_seen;
    engine_completion_data_i=0;engine_completion_data_i[2*56 +:56]={EVENT_ID,8'd0,3'd2,29'(MACS)};end
  always @(posedge clk_i)begin
    if(!rst_ni)begin cycles<=0;matrix_command_seen<=0;end else begin cycles<=cycles+1;
      if(engine_cmd_valid_o[2]&&engine_cmd_ready_i[2])begin matrix_command_seen<=1;
        start_cycle<=cycles;end
      for(int c=0;c<3;c++)if(l2_rd_rsp_valid_o[c]&&l2_rd_rsp_ready_i[c])begin
        if(l2_rd_rsp_error_o[c]||l2_rd_rsp_data_o[c*512 +:512]!==0)$fatal(1,"trace read response");
        responses[c]<=responses[c]+1;end
    end
  end
  task automatic read_client(input integer client,input integer beats,input integer row_base);
    begin for(int beat=0;beat<beats;beat++)begin @(negedge clk_i);
      l2_rd_addr_i[client*15 +:15]=15'(((row_base+beat)<<2)|0);l2_rd_valid_i[client]=1;
      do @(posedge clk_i);while(!l2_rd_ready_o[client]);@(negedge clk_i);l2_rd_valid_i[client]=0;
      wait(responses[client]==beat+1);end end endtask
  task automatic write_client(input integer beats,input integer row_base);
    begin for(int beat=0;beat<beats;beat++)begin @(negedge clk_i);
      l2_wr_addr_i[0 +:15]=15'(((row_base+beat)<<2)|0);
      l2_wr_data_i[0 +:512]={8{({EVENT_ID,48'd0}|64'(beat))}};l2_wr_be_i[0 +:64]='1;
      l2_wr_valid_i[0]=1;do @(posedge clk_i);while(!l2_wr_ready_o[0]);
      @(negedge clk_i);l2_wr_valid_i[0]=0;writes_done=writes_done+1;end end endtask
  initial begin wait(matrix_command_seen);fork
      read_client(0,DESCRIPTOR_READS,0);read_client(1,WEIGHT_READS,0);
      read_client(2,ACTIVATION_BIAS_READS,0);write_client(OUTPUT_WRITES,1000);
    join
    @(negedge clk_i);engine_completion_valid_i[2]=1;
    do @(posedge clk_i);while(!engine_completion_ready_o[2]);end_cycle=cycles;
    @(negedge clk_i);engine_completion_valid_i[2]=0;
  end
  initial begin
    clk_i=0;rst_ni=0;start_cycle=0;end_cycle=0;host_cmd_valid_i=0;host_cmd_data_i=0;
    engine_completion_valid_i=0;l2_rd_valid_i=0;l2_rd_addr_i=0;l2_rd_rsp_ready_i='1;
    l2_wr_valid_i=0;l2_wr_addr_i=0;l2_wr_data_i=0;l2_wr_be_i=0;writes_done=0;
    for(int c=0;c<3;c++)responses[c]=0;
    matrix_cfg_valid_i=0;matrix_cfg_direction_i=0;matrix_cfg_route_i=0;matrix_cfg_last_addr_i=0;
    matrix_cfg_tag_i=0;matrix_cfg_tensor_id_i=0;matrix_cfg_format_i=0;
    matrix_spad_write_valid_i=0;matrix_spad_write_addr_i=0;matrix_spad_write_data_i=0;
    matrix_spad_write_mask_i=0;matrix_spad_read_req_valid_i=0;matrix_spad_read_req_addr_i=0;
    matrix_spad_read_resp_ready_i=0;aha_cfg_valid_i=0;aha_cfg_input_base_i=0;
    aha_cfg_output_base_i=0;aha_cfg_input_beats_i=0;aha_cfg_output_beats_i=0;
    aha_cfg_output_tag_i=0;aha_cfg_output_tensor_id_i=0;aha_cfg_output_format_i=0;
    aha_cfg_output_last_be_i=0;aha_run_done_i=0;aha_proc_packet_rd_data_i=0;
    aha_proc_packet_rd_data_valid_i=0;kv_cfg_valid_i=0;kv_cfg_direction_i=0;
    kv_cfg_base_addr_i=0;kv_cfg_beats_i=0;kv_cfg_tag_i=0;kv_cfg_tensor_id_i=0;
    kv_cfg_format_i=0;kv_cfg_last_be_i=0;kv_mem_write_ready_i=0;
    kv_mem_read_req_ready_i=0;kv_mem_read_rsp_valid_i=0;kv_mem_read_rsp_data_i=0;
    kv_mem_read_rsp_error_i=0;repeat(3)@(posedge clk_i);rst_ni=1;wait(init_done_o);
    @(negedge clk_i);host_cmd_data_i=0;host_cmd_data_i[7:0]=8'h10;
    host_cmd_data_i[7:0]=OPCODE;host_cmd_data_i[10:8]=3'd2;
    host_cmd_data_i[55:40]=EVENT_ID;host_cmd_valid_i=1;
    do @(posedge clk_i);while(!host_cmd_ready_o);@(negedge clk_i);host_cmd_valid_i=0;
    wait(completion_grants_o==1);wait(completion_level_o==0);repeat(3)@(posedge clk_i);
    if(responses[0]!=DESCRIPTOR_READS||responses[1]!=WEIGHT_READS||
       responses[2]!=ACTIVATION_BIAS_READS||writes_done!=OUTPUT_WRITES||
       l2_read_grants_o!=DESCRIPTOR_READS+WEIGHT_READS+ACTIVATION_BIAS_READS||
       l2_write_grants_o!=OUTPUT_WRITES||
       mem_reads!=64'(DESCRIPTOR_READS)+64'(WEIGHT_READS)+
         64'(ACTIVATION_BIAS_READS)||
       mem_writes!=64'(OUTPUT_WRITES)||(REQUIRE_PROMOTION&&descriptor_promotions_o==0)||
       event_macro_error_count_o!=0||
       completion_protocol_error_count_o!=0||watchdog_lock_o||illegal_engine_o||
       command_level_o!=0||l2_wr_ready_o[1]||mem_cycle==0||
       engine_cmd_valid_o!=0||engine_completion_ready_o!=0||
       matrix_protocol_error_count_o!=0||aha_protocol_error_count_o!=0||
       kv_protocol_error_count_o!=0||matrix_transfer_done_o||aha_transfer_done_o||
       kv_transfer_done_o||aha_native_eos_o||aha_proc_packet_wr_en_o||aha_proc_packet_rd_en_o||
       kv_mem_write_valid_o||kv_mem_read_req_valid_o||kv_mem_read_rsp_ready_o||
       !matrix_cfg_ready_o||matrix_spad_write_ready_o!=0||
       matrix_spad_read_req_ready_o!=0||matrix_spad_read_resp_valid_o!=0||
       !aha_cfg_ready_o||!kv_cfg_ready_o||
       $isunknown({engine_cmd_data_o,matrix_spad_read_resp_data_o,
         aha_proc_packet_wr_addr_o,aha_proc_packet_wr_data_o,
         aha_proc_packet_wr_strb_o,aha_proc_packet_rd_addr_o,
         kv_mem_write_addr_o,kv_mem_write_data_o,kv_mem_write_be_o,
         kv_mem_read_req_addr_o}))
      $fatal(1,"L4 trace accounting");
    $display("L4_MATRIX_L3_TRACE_PASS case_id=%0d cycles=%0d semantic_dma_bytes=%0d physical_dma_bytes=%0d descriptor_bytes=%0d reads=%0d writes=%0d conflicts=%0d rstall=%0d wstall=%0d promotions=%0d",
      CASE_ID,end_cycle-start_cycle,SEMANTIC_DMA_BYTES,PHYSICAL_DMA_BYTES,DESCRIPTOR_BYTES,
      l2_read_grants_o,l2_write_grants_o,mem_conflicts,mem_rstall,mem_wstall,
      descriptor_promotions_o);$finish;
  end
  initial begin repeat(200000)@(posedge clk_i);$fatal(1,"L4 trace timeout");end
endmodule

module tb_l4_int8_gemm_l3_trace;
  tb_l4_matrix_l3_trace u_trace();
endmodule

module tb_l4_conv1x1_l3_trace;
  tb_l4_matrix_l3_trace #(
    .CASE_ID(1),.EVENT_ID(16'h0402),.OPCODE(8'h22),.MACS(192),
    .DESCRIPTOR_READS(4),.WEIGHT_READS(1),.ACTIVATION_BIAS_READS(2),
    .OUTPUT_WRITES(1),.SEMANTIC_DMA_BYTES(140),.PHYSICAL_DMA_BYTES(256),
    .DESCRIPTOR_BYTES(256),.REQUIRE_PROMOTION(1'b0)
  )u_trace();
endmodule
/* verilator lint_on DECLFILENAME */
