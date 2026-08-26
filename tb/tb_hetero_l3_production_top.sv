`timescale 1ns/1ps
module tb_hetero_l3_production_top;
  parameter integer CMD_TARGET = 100000;
  parameter integer L2_TARGET = 100000;
  parameter integer STREAM_TARGET = 10000;
  localparam integer ADDR_W = 15;
  localparam integer DATA_W = 512;
  logic clk_i;
  /* verilator lint_off SYNCASYNCNET */ logic rst_ni; /* verilator lint_on SYNCASYNCNET */
  always #5 clk_i = ~clk_i;
  integer cycles;

  logic host_cmd_valid_i,host_cmd_ready_o;logic[127:0]host_cmd_data_i;
  logic[5:0]engine_cmd_valid_o,engine_cmd_ready_i;
  logic[6*128-1:0]engine_cmd_data_o;
  logic[5:0]engine_completion_valid_i,engine_completion_ready_o;
  logic[6*56-1:0]engine_completion_data_i;
  logic init_done_o;logic[4:0]command_level_o,completion_level_o;
  logic[31:0]event_macro_error_count_o;logic illegal_engine_o,watchdog_lock_o;
  logic[31:0]completion_grants_o,completion_protocol_error_count_o;
  logic[3:0]l2_rd_valid_i,l2_rd_ready_o,l2_rd_rsp_valid_o,l2_rd_rsp_ready_i;
  logic[4*ADDR_W-1:0]l2_rd_addr_i;logic[4*DATA_W-1:0]l2_rd_rsp_data_o;
  logic[3:0]l2_rd_rsp_error_o;logic[1:0]l2_wr_valid_i,l2_wr_ready_o;
  logic[2*ADDR_W-1:0]l2_wr_addr_i;logic[2*DATA_W-1:0]l2_wr_data_i;
  logic[2*(DATA_W/8)-1:0]l2_wr_be_i;
  logic[1:0]phy_rd_valid_o,phy_rd_ready_i;logic[2*ADDR_W-1:0]phy_rd_addr_o;
  logic[1:0]phy_rsp_valid_i,phy_rsp_ready_o;logic[2*DATA_W-1:0]phy_rsp_data_i;
  logic[1:0]phy_rsp_error_i;logic phy_wr_valid_o,phy_wr_ready_i;
  logic[ADDR_W-1:0]phy_wr_addr_o;logic[DATA_W-1:0]phy_wr_data_o;
  logic[DATA_W/8-1:0]phy_wr_be_o;logic[31:0]descriptor_promotions_o;
  logic[31:0]l2_read_grants_o,l2_write_grants_o;

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
  logic sfu_select_dedicated_i,dedicated_cfg_valid_i,dedicated_cfg_ready_o,dedicated_cfg_op_i;
  logic[3:0]dedicated_cfg_h_i,dedicated_cfg_w_i;logic[4:0]dedicated_cfg_c_i;
  logic[6:0]dedicated_cfg_bytes_i;logic[15:0]dedicated_cfg_tag_i;
  logic[11:0]dedicated_cfg_tensor_id_i;logic[3:0]dedicated_cfg_format_i;
  logic dedicated_secondary_valid_i,dedicated_secondary_ready_o;
  logic[511:0]dedicated_secondary_data_i;logic[63:0]dedicated_secondary_be_i;
  logic dedicated_secondary_last_i;logic[3:0]dedicated_secondary_format_i;
  logic dedicated_transfer_done_o;logic[31:0]dedicated_protocol_error_count_o;
  logic[31:0]sfu_mux_protocol_error_count_o;
  logic kv_cfg_valid_i,kv_cfg_ready_o,kv_cfg_direction_i;logic[18:0]kv_cfg_base_addr_i;
  logic[15:0]kv_cfg_beats_i,kv_cfg_tag_i;logic[11:0]kv_cfg_tensor_id_i;
  logic[3:0]kv_cfg_format_i;logic[63:0]kv_cfg_last_be_i;
  logic kv_mem_write_valid_o,kv_mem_write_ready_i;logic[18:0]kv_mem_write_addr_o;
  logic[511:0]kv_mem_write_data_o;logic[63:0]kv_mem_write_be_o;
  logic kv_mem_read_req_valid_o,kv_mem_read_req_ready_i;logic[18:0]kv_mem_read_req_addr_o;
  logic kv_mem_read_rsp_valid_i,kv_mem_read_rsp_ready_o;logic[511:0]kv_mem_read_rsp_data_i;
  logic kv_mem_read_rsp_error_i,kv_transfer_done_o;logic[31:0]kv_protocol_error_count_o;

  hetero_l3_production_top #(.WATCHDOG_CYCLES(128))dut(.*);
  logic[63:0]mem_cycle,mem_reads,mem_writes,mem_conflicts,mem_rstall,mem_wstall;
  shared_l2_fabric #(.ADDR_W(ADDR_W),.ROWS_PER_BANK(6144))l2_mem(
    .clk_i,.rst_ni,.rd_valid_i(phy_rd_valid_o),.rd_ready_o(phy_rd_ready_i),
    .rd_addr_i(phy_rd_addr_o),.rd_resp_valid_o(phy_rsp_valid_i),
    .rd_resp_ready_i(phy_rsp_ready_o),.rd_data_o(phy_rsp_data_i),
    .wr_valid_i(phy_wr_valid_o),.wr_ready_o(phy_wr_ready_i),.wr_addr_i(phy_wr_addr_o),
    .wr_data_i(phy_wr_data_o),.wr_be_i(phy_wr_be_o),.cycle_count_o(mem_cycle),
    .read_count_o(mem_reads),.write_count_o(mem_writes),
    .bank_conflict_count_o(mem_conflicts),.read_stall_count_o(mem_rstall),
    .write_stall_count_o(mem_wstall));
  assign phy_rsp_error_i=0;

  integer host_accepted,engine_completed,illegal_seen;
  integer accepted_by_engine[0:5],completed_by_engine[0:5];
  logic[5:0]engine_busy;logic[7:0]engine_delay[0:5];
  logic[127:0]engine_command_q[0:5];logic stall_watchdog_engine;
  always_comb for(int e=0;e<6;e++)begin
    engine_cmd_ready_i[e]=!engine_busy[e]&&((cycles+e)%4!=1);
    engine_completion_data_i[e*56 +:56]={engine_command_q[e][55:40],8'd0,3'(e),29'(completed_by_engine[e])};
  end
  always @(posedge clk_i)begin
    if(!rst_ni)begin host_accepted<=0;engine_completed<=0;illegal_seen<=0;engine_busy<=0;
      engine_completion_valid_i<=0;for(int e=0;e<6;e++)begin engine_delay[e]<=0;
        engine_command_q[e]<=0;accepted_by_engine[e]<=0;completed_by_engine[e]<=0;end
    end else begin
      if(host_cmd_valid_i&&host_cmd_ready_o)host_accepted<=host_accepted+1;
      if(illegal_engine_o)illegal_seen<=illegal_seen+1;
      for(int e=0;e<6;e++)begin
        if(engine_cmd_valid_o[e]&&engine_cmd_ready_i[e])begin engine_busy[e]<=1;
          engine_command_q[e]<=engine_cmd_data_o[e*128 +:128];engine_delay[e]<=8'(2+(cycles+e)%7);
          accepted_by_engine[e]<=accepted_by_engine[e]+1;end
        else if(engine_busy[e]&&!engine_completion_valid_i[e]&&!(stall_watchdog_engine&&e==2))begin
          if(engine_delay[e]==0)engine_completion_valid_i[e]<=1;
          else engine_delay[e]<=engine_delay[e]-1'b1;end
        if(engine_completion_valid_i[e]&&engine_completion_ready_o[e])begin
          engine_completion_valid_i[e]<=0;engine_busy[e]<=0;engine_completed<=engine_completed+1;
          completed_by_engine[e]<=completed_by_engine[e]+1;end
      end
    end
  end
  task automatic send_command(input logic[2:0]engine,input logic[15:0]event_id);
    begin @(negedge clk_i);host_cmd_data_i=0;host_cmd_data_i[7:0]=8'h7f;
      host_cmd_data_i[10:8]=engine;host_cmd_data_i[55:40]=event_id;host_cmd_valid_i=1;
      do @(posedge clk_i);while(!host_cmd_ready_o);@(negedge clk_i);host_cmd_valid_i=0;end
  endtask

  logic[DATA_W-1:0]l2_model[0:24575],l2_expected[0:3],l2_merged;
  logic[3:0]l2_pending,l2_rfire;logic[1:0]l2_wfire;
  integer l2_accepted,l2_responses,l2_rng,l2_reads_by_client[0:3],l2_writes_by_client[0:1];
  function automatic[31:0]xorshift(input[31:0]value);reg[31:0]x;
    begin x=value;x=x^(x<<13);x=x^(x>>17);x=x^(x<<5);xorshift=x;end endfunction
  /* verilator lint_off BLKSEQ */
  always @(posedge clk_i)if(rst_ni)for(int c=0;c<4;c++)if(l2_rd_rsp_valid_o[c]&&l2_rd_rsp_ready_i[c])begin
    if(!l2_pending[c]||l2_rd_rsp_error_o[c]||l2_rd_rsp_data_o[c*DATA_W +:DATA_W]!==l2_expected[c])
      $fatal(1,"combined L2 read mismatch client=%0d",c);l2_pending[c]=0;l2_responses=l2_responses+1;end
  /* verilator lint_on BLKSEQ */

  logic[63:0]aha_mem[0:32767];logic[2:0]aha_rd_pipe_valid;
  logic[17:0]aha_rd_pipe_addr[0:2];logic[511:0]kv_mem[0:8191];
  logic kv_pending;logic[18:0]kv_pending_addr;
  integer stream_completed,matrix_done_count,aha_done_count,kv_done_count,stream_rng;
  assign kv_mem_write_ready_i=(cycles%4)!=1;
  assign kv_mem_read_req_ready_i=!kv_pending&&(cycles%5)!=2;
  assign kv_mem_read_rsp_valid_i=kv_pending;
  assign kv_mem_read_rsp_data_i=kv_mem[kv_pending_addr[18:6]];
  assign kv_mem_read_rsp_error_i=0;
  always @(posedge clk_i)begin
    if(!rst_ni)begin aha_run_done_i<=0;aha_rd_pipe_valid<=0;aha_proc_packet_rd_data_valid_i<=0;
      aha_proc_packet_rd_data_i<=0;kv_pending<=0;kv_pending_addr<=0;
      matrix_done_count<=0;aha_done_count<=0;kv_done_count<=0;end
    else begin
      if(matrix_transfer_done_o)matrix_done_count<=matrix_done_count+1;
      if(aha_transfer_done_o)aha_done_count<=aha_done_count+1;
      if(kv_transfer_done_o)kv_done_count<=kv_done_count+1;
      aha_run_done_i<=aha_native_eos_o;aha_proc_packet_rd_data_valid_i<=aha_rd_pipe_valid[2];
      if(aha_rd_pipe_valid[2])aha_proc_packet_rd_data_i<=aha_mem[aha_rd_pipe_addr[2][17:3]];
      aha_rd_pipe_valid[2]<=aha_rd_pipe_valid[1];aha_rd_pipe_valid[1]<=aha_rd_pipe_valid[0];
      aha_rd_pipe_valid[0]<=aha_proc_packet_rd_en_o;aha_rd_pipe_addr[2]<=aha_rd_pipe_addr[1];
      aha_rd_pipe_addr[1]<=aha_rd_pipe_addr[0];aha_rd_pipe_addr[0]<=aha_proc_packet_rd_addr_o;
      if(aha_proc_packet_wr_en_o)begin
        if(aha_proc_packet_wr_addr_o[2:0]!=0)$fatal(1,"combined AHA alignment");
        for(int b=0;b<8;b++)if(aha_proc_packet_wr_strb_o[b])
          aha_mem[aha_proc_packet_wr_addr_o[17:3]][b*8 +:8]<=aha_proc_packet_wr_data_o[b*8 +:8];
      end
      if(aha_native_eos_o)for(int w=0;w<8;w++)
        aha_mem[32'(aha_cfg_output_base_i[17:3])+w]<=aha_mem[32'(aha_cfg_input_base_i[17:3])+w];
      if(kv_mem_write_valid_o&&kv_mem_write_ready_i)begin
        if(kv_mem_write_addr_o[5:0]!=0)$fatal(1,"combined KV write alignment");
        for(int b=0;b<64;b++)if(kv_mem_write_be_o[b])
          kv_mem[kv_mem_write_addr_o[18:6]][b*8 +:8]<=kv_mem_write_data_o[b*8 +:8];
      end
      if(kv_mem_read_req_valid_o&&kv_mem_read_req_ready_i)begin kv_pending<=1;
        kv_pending_addr<=kv_mem_read_req_addr_o;end
      if(kv_mem_read_rsp_valid_i&&kv_mem_read_rsp_ready_o)begin
        if(kv_pending_addr[5:0]!=0)$fatal(1,"combined KV response alignment");
        kv_pending<=0;
      end
    end
  end
  task automatic cfg_matrix(input logic dir,input logic route,input logic[11:0]addr,
    input logic[15:0]tag,input logic[11:0]tid,input logic[3:0]fmt);
    begin @(negedge clk_i);matrix_cfg_direction_i=dir;matrix_cfg_route_i=route;
      matrix_cfg_last_addr_i=addr;matrix_cfg_tag_i=tag;matrix_cfg_tensor_id_i=tid;
      matrix_cfg_format_i=fmt;matrix_cfg_valid_i=1;do @(posedge clk_i);while(!matrix_cfg_ready_o);
      @(negedge clk_i);matrix_cfg_valid_i=0;end endtask
  task automatic matrix_write(input logic[11:0]addr,input logic[511:0]data,input logic[63:0]mask);
    begin for(int b=0;b<4;b++)begin matrix_spad_write_addr_i[b*12 +:12]=addr;
      matrix_spad_write_data_i[b*128 +:128]=data[b*128 +:128];
      matrix_spad_write_mask_i[b*16 +:16]=mask[b*16 +:16];end
      @(negedge clk_i);matrix_spad_write_valid_i='1;wait(&matrix_spad_write_ready_o);
      @(posedge clk_i);@(negedge clk_i);matrix_spad_write_valid_i=0;end endtask
  task automatic matrix_read(input logic[11:0]addr,input logic[511:0]expected);
    logic[3:0]seen,fire;begin for(int b=0;b<4;b++)matrix_spad_read_req_addr_i[b*12 +:12]=addr;
      @(negedge clk_i);matrix_spad_read_req_valid_i='1;wait(&matrix_spad_read_req_ready_o);
      @(posedge clk_i);@(negedge clk_i);matrix_spad_read_req_valid_i=0;seen=0;
      while(seen!=4'hf)begin stream_rng=xorshift(stream_rng);matrix_spad_read_resp_ready_i=stream_rng[3:0];
        #1;fire=matrix_spad_read_resp_valid_o&matrix_spad_read_resp_ready_i;
        for(int b=0;b<4;b++)if(fire[b]&&matrix_spad_read_resp_data_o[b*128 +:128]!==expected[b*128 +:128])
          $fatal(1,"combined stream read mismatch");@(posedge clk_i);seen=seen|fire;@(negedge clk_i);end
      matrix_spad_read_resp_ready_i=0;end endtask
  task automatic run_aha(input integer id);logic[511:0]data;logic[11:0]addr;integer mp,ap;
    begin data={8{64'(id)^64'h3c6e_f372_fe94_f82b}};addr=12'(id);mp=matrix_done_count;ap=aha_done_count;
      aha_cfg_input_base_i=18'((id%1024)*64);aha_cfg_output_base_i=18'h20000+18'((id%1024)*64);
      aha_cfg_input_beats_i=1;aha_cfg_output_beats_i=1;aha_cfg_output_tag_i=16'(id);
      aha_cfg_output_tensor_id_i=12'(id);aha_cfg_output_format_i=1;aha_cfg_output_last_be_i='1;
      @(negedge clk_i);aha_cfg_valid_i=1;do @(posedge clk_i);while(!aha_cfg_ready_o);
      @(negedge clk_i);aha_cfg_valid_i=0;cfg_matrix(0,0,addr,16'(id),12'(id),1);
      matrix_write(addr,data,'1);wait(matrix_done_count==mp+1);wait(aha_native_eos_o);
      cfg_matrix(1,0,addr,16'(id),12'(id),1);matrix_read(addr,data);
      wait(matrix_done_count==mp+2);wait(aha_done_count==ap+1);stream_completed=stream_completed+1;end endtask
  task automatic run_kv(input integer id);logic[511:0]data,expected;logic[63:0]mask;
    logic[11:0]addr;integer mp,kp;begin data={8{64'(id)^64'ha54f_f53a_5f1d_36f1}};
      mask=id[0]?64'hffff0000ffff0000:'1;addr=12'(id);mp=matrix_done_count;kp=kv_done_count;
      kv_cfg_direction_i=0;kv_cfg_base_addr_i=19'((id%8192)*64);kv_cfg_beats_i=1;
      kv_cfg_tag_i=16'(id);kv_cfg_tensor_id_i=12'(id);kv_cfg_format_i=2;kv_cfg_last_be_i=mask;
      @(negedge clk_i);kv_cfg_valid_i=1;do @(posedge clk_i);while(!kv_cfg_ready_o);
      @(negedge clk_i);kv_cfg_valid_i=0;cfg_matrix(0,1,addr,16'(id),12'(id),2);
      matrix_write(addr,data,mask);wait(matrix_done_count==mp+1);wait(kv_done_count==kp+1);
      expected=kv_mem[kv_cfg_base_addr_i[18:6]];kv_cfg_direction_i=1;kv_cfg_last_be_i='1;
      @(negedge clk_i);kv_cfg_valid_i=1;do @(posedge clk_i);while(!kv_cfg_ready_o);
      @(negedge clk_i);kv_cfg_valid_i=0;cfg_matrix(1,1,addr,16'(id),12'(id),2);
      matrix_read(addr,expected);wait(matrix_done_count==mp+2);wait(kv_done_count==kp+2);
      stream_completed=stream_completed+2;end endtask

  logic command_thread_done,l2_thread_done,stream_thread_done;
  initial begin wait(init_done_o);for(int c=0;c<CMD_TARGET;c++)send_command(3'(c%6),16'(c+1));
    send_command(3'd2,0);send_command(3'd7,16'hf001);wait(engine_completed==CMD_TARGET+1);
    wait(completion_grants_o==CMD_TARGET+2);wait(command_level_o==0&&completion_level_o==0);
    command_thread_done=1;end
  initial begin wait(init_done_o);while(l2_accepted<L2_TARGET||l2_rd_valid_i!=0||l2_wr_valid_i!=0||l2_pending!=0)begin
      @(negedge clk_i);for(int c=0;c<4;c++)if(l2_rfire[c])l2_rd_valid_i[c]=0;
      for(int c=0;c<2;c++)if(l2_wfire[c])l2_wr_valid_i[c]=0;
      for(int c=0;c<4;c++)begin l2_rng=xorshift(l2_rng);l2_rd_rsp_ready_i[c]=l2_rng[0];
        if(l2_accepted<L2_TARGET&&!l2_pending[c]&&!l2_rd_valid_i[c])begin l2_rng=xorshift(l2_rng);
          if(l2_rng[1])begin l2_rd_valid_i[c]=1;l2_rng=xorshift(l2_rng);
            l2_rd_addr_i[c*ADDR_W +:ADDR_W]=ADDR_W'(l2_rng%24576);end end end
      for(int c=0;c<2;c++)if(l2_accepted<L2_TARGET&&!l2_wr_valid_i[c])begin l2_rng=xorshift(l2_rng);
        if(l2_rng[1])begin l2_wr_valid_i[c]=1;l2_rng=xorshift(l2_rng);
          l2_wr_addr_i[c*ADDR_W +:ADDR_W]=ADDR_W'(l2_rng%24576);
          for(int w=0;w<16;w++)begin l2_rng=xorshift(l2_rng);l2_wr_data_i[c*DATA_W+w*32 +:32]=l2_rng;end
          for(int b=0;b<64;b++)begin l2_rng=xorshift(l2_rng);l2_wr_be_i[c*64+b]=l2_rng[0];end end end
      #1;l2_rfire=l2_rd_valid_i&l2_rd_ready_o;l2_wfire=l2_wr_valid_i&l2_wr_ready_o;
      for(int c=0;c<4;c++)if(l2_rfire[c])begin l2_expected[c]=l2_model[l2_rd_addr_i[c*ADDR_W +:ADDR_W]];
        l2_pending[c]=1;l2_accepted=l2_accepted+1;l2_reads_by_client[c]++;end
      for(int c=0;c<2;c++)if(l2_wfire[c])begin l2_merged=l2_model[l2_wr_addr_i[c*ADDR_W +:ADDR_W]];
        for(int b=0;b<64;b++)if(l2_wr_be_i[c*64+b])l2_merged[b*8 +:8]=l2_wr_data_i[c*DATA_W+b*8 +:8];
        l2_model[l2_wr_addr_i[c*ADDR_W +:ADDR_W]]=l2_merged;l2_accepted++;
        l2_writes_by_client[c]++;end @(posedge clk_i);end l2_thread_done=1;end
  initial begin wait(init_done_o);for(int s=0;s<STREAM_TARGET/2;s++)run_aha(s);
    for(int s=0;s<STREAM_TARGET/4;s++)run_kv(s);stream_thread_done=1;end

  initial begin
    clk_i=0;rst_ni=0;cycles=0;host_cmd_valid_i=0;host_cmd_data_i=0;stall_watchdog_engine=0;
    command_thread_done=0;l2_thread_done=0;stream_thread_done=0;l2_rd_valid_i=0;l2_rd_addr_i=0;
    l2_rd_rsp_ready_i='1;l2_wr_valid_i=0;l2_wr_addr_i=0;l2_wr_data_i=0;l2_wr_be_i=0;
    l2_pending=0;l2_rfire=0;l2_wfire=0;l2_accepted=0;l2_responses=0;l2_rng=32'h51ac73d9;
    for(int i=0;i<24576;i++)l2_model[i]=0;for(int c=0;c<4;c++)l2_reads_by_client[c]=0;
    for(int c=0;c<2;c++)l2_writes_by_client[c]=0;stream_completed=0;stream_rng=32'h7f4a2c19;
    matrix_cfg_valid_i=0;matrix_cfg_direction_i=0;matrix_cfg_route_i=0;matrix_cfg_last_addr_i=0;
    matrix_cfg_tag_i=0;matrix_cfg_tensor_id_i=0;matrix_cfg_format_i=0;matrix_spad_write_valid_i=0;
    matrix_spad_write_addr_i=0;matrix_spad_write_data_i=0;matrix_spad_write_mask_i=0;
    matrix_spad_read_req_valid_i=0;matrix_spad_read_req_addr_i=0;matrix_spad_read_resp_ready_i=0;
    aha_cfg_valid_i=0;aha_cfg_input_base_i=0;aha_cfg_output_base_i=0;aha_cfg_input_beats_i=0;
    aha_cfg_output_beats_i=0;aha_cfg_output_tag_i=0;aha_cfg_output_tensor_id_i=0;
    aha_cfg_output_format_i=0;aha_cfg_output_last_be_i=0;sfu_select_dedicated_i=0;
    dedicated_cfg_valid_i=0;dedicated_cfg_op_i=0;dedicated_cfg_h_i=0;dedicated_cfg_w_i=0;
    dedicated_cfg_c_i=0;dedicated_cfg_bytes_i=0;dedicated_cfg_tag_i=0;
    dedicated_cfg_tensor_id_i=0;dedicated_cfg_format_i=0;dedicated_secondary_valid_i=0;
    dedicated_secondary_data_i=0;dedicated_secondary_be_i=0;dedicated_secondary_last_i=1;
    dedicated_secondary_format_i=1;kv_cfg_valid_i=0;kv_cfg_direction_i=0;
    kv_cfg_base_addr_i=0;kv_cfg_beats_i=0;kv_cfg_tag_i=0;kv_cfg_tensor_id_i=0;
    kv_cfg_format_i=0;kv_cfg_last_be_i=0;kv_pending=0;
    for(int i=0;i<32768;i++)aha_mem[i]=0;for(int i=0;i<8192;i++)kv_mem[i]=0;
    repeat(3)@(posedge clk_i);rst_ni=1;wait(command_thread_done&&l2_thread_done&&stream_thread_done);
    wait(l2_responses==l2_read_grants_o);repeat(5)@(posedge clk_i);
    if(host_accepted!=CMD_TARGET+2||illegal_seen!=1||event_macro_error_count_o!=0||
       completion_protocol_error_count_o!=0||l2_accepted<L2_TARGET||
       l2_accepted!=l2_read_grants_o+l2_write_grants_o||mem_reads!=64'(l2_read_grants_o)||
       mem_writes!=64'(l2_write_grants_o)||stream_completed!=STREAM_TARGET||
       matrix_protocol_error_count_o!=0||aha_protocol_error_count_o!=0||
       kv_protocol_error_count_o!=0||dedicated_protocol_error_count_o!=0||
       sfu_mux_protocol_error_count_o!=0||dedicated_transfer_done_o||
       dedicated_cfg_ready_o||dedicated_secondary_ready_o||
       descriptor_promotions_o==0||mem_cycle==0)
      begin
        $display("COMBINED_DIAG host=%0d exp=%0d illegal=%0d macro=%0d cperr=%0d",
          host_accepted,CMD_TARGET+2,illegal_seen,event_macro_error_count_o,
          completion_protocol_error_count_o);
        $display("COMBINED_DIAG l2=%0d exp=%0d rg=%0d wg=%0d memr=%0d memw=%0d resp=%0d prom=%0d",
          l2_accepted,L2_TARGET,l2_read_grants_o,l2_write_grants_o,mem_reads,mem_writes,
          l2_responses,descriptor_promotions_o);
        $display("COMBINED_DIAG stream=%0d exp=%0d matrixerr=%0d ahaerr=%0d kverr=%0d cycle=%0d",
          stream_completed,STREAM_TARGET,matrix_protocol_error_count_o,
          aha_protocol_error_count_o,kv_protocol_error_count_o,mem_cycle);
        $fatal(1,"combined accounting");
      end
    for(int c=0;c<4;c++)if(l2_reads_by_client[c]==0)$fatal(1,"L2 read starvation");
    for(int c=0;c<2;c++)if(l2_writes_by_client[c]==0)$fatal(1,"L2 write starvation");
    for(int e=0;e<6;e++)if(accepted_by_engine[e]==0||
      accepted_by_engine[e]!=completed_by_engine[e])
      $fatal(1,"combined engine progress mismatch engine=%0d accepted=%0d completed=%0d",
        e,accepted_by_engine[e],completed_by_engine[e]);
    stall_watchdog_engine=1;send_command(3'd2,16'hf100);wait(watchdog_lock_o);
    repeat(4)@(posedge clk_i);if(host_cmd_ready_o||completion_grants_o!=CMD_TARGET+3)
      $fatal(1,"combined watchdog");
    $display("HETERO_L3_PRODUCTION_TOP_COMBINED_PASS commands=%0d l2=%0d reads=%0d writes=%0d responses=%0d streams=%0d matrix=%0d aha=%0d kv=%0d promotions=%0d conflicts=%0d rstall=%0d wstall=%0d",
      host_accepted,l2_accepted,l2_read_grants_o,l2_write_grants_o,l2_responses,
      stream_completed,matrix_done_count,aha_done_count,kv_done_count,
      descriptor_promotions_o,mem_conflicts,mem_rstall,mem_wstall);$finish;
  end
  always @(posedge clk_i)if(rst_ni)cycles<=cycles+1;
  initial begin repeat(CMD_TARGET*200+1000000)@(posedge clk_i);$fatal(1,"combined timeout");end
endmodule
