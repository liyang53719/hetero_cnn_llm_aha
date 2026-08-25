`timescale 1ns/1ps
module tb_shared_l2_macro_descriptor_fabric;
  parameter integer TARGET=100000;
  localparam integer ADDR_W=10;
  logic clk=0,rst_n=0;always #5 clk=~clk;
  logic[63:0] descriptor_base;
  logic d_req_valid,d_req_ready;logic[23:0] d_req_index;
  logic d_rsp_valid,d_rsp_ready,d_rsp_error;logic[127:0] d_rsp_data;
  logic rd_valid,rd_ready;logic[ADDR_W-1:0] rd_addr;
  logic rd_rsp_valid,rd_rsp_ready;logic[511:0] rd_data;
  logic wr_valid,wr_ready;logic[ADDR_W-1:0] wr_addr;logic[511:0] wr_data;logic[63:0] wr_be;
  logic[63:0] cycles,reads,writes,conflicts,rd_stalls,wr_stalls,macro_errors;
  logic[511:0] model[0:(1<<ADDR_W)-1];
  logic d_pending,rd_pending,d_fire_q,rd_fire_q,wr_fire_q;
  logic d_expect_error;
  logic[127:0] d_expected;logic[511:0] rd_expected,merged;
  integer accepted,responses,seed,i,b;

  shared_l2_macro_descriptor_fabric #(.ADDR_W(ADDR_W),.SRAM_BYTES(64'd65536))dut(
    .clk_i(clk),.rst_ni(rst_n),.descriptor_base_i(descriptor_base),
    .descriptor_req_valid_i(d_req_valid),.descriptor_req_ready_o(d_req_ready),
    .descriptor_req_index_i(d_req_index),.descriptor_rsp_valid_o(d_rsp_valid),
    .descriptor_rsp_ready_i(d_rsp_ready),.descriptor_rsp_data_o(d_rsp_data),
    .descriptor_rsp_error_o(d_rsp_error),.rd_valid_i(rd_valid),.rd_ready_o(rd_ready),
    .rd_addr_i(rd_addr),.rd_resp_valid_o(rd_rsp_valid),.rd_resp_ready_i(rd_rsp_ready),
    .rd_data_o(rd_data),.wr_valid_i(wr_valid),.wr_ready_o(wr_ready),.wr_addr_i(wr_addr),
    .wr_data_i(wr_data),.wr_be_i(wr_be),.cycle_count_o(cycles),.read_count_o(reads),
    .write_count_o(writes),.bank_conflict_count_o(conflicts),.read_stall_count_o(rd_stalls),
    .write_stall_count_o(wr_stalls),.macro_error_count_o(macro_errors));

  always @(posedge clk)if(rst_n)begin
    if(d_rsp_valid&&d_rsp_ready)begin
      if(!d_pending||d_rsp_error!==d_expect_error||(!d_rsp_error&&d_rsp_data!==d_expected))
        $fatal(1,"descriptor mismatch");
      d_pending=0;responses=responses+1;
    end
    if(rd_rsp_valid&&rd_rsp_ready)begin
      if(!rd_pending||rd_data!==rd_expected)$fatal(1,"normal read mismatch");
      rd_pending=0;responses=responses+1;
    end
  end

  initial begin
    descriptor_base=0;d_req_valid=0;d_req_index=0;d_rsp_ready=0;
    rd_valid=0;rd_addr=0;rd_rsp_ready=0;wr_valid=0;wr_addr=0;wr_data=0;wr_be=0;
    d_pending=0;d_expect_error=0;rd_pending=0;d_fire_q=0;rd_fire_q=0;wr_fire_q=0;
    accepted=0;responses=0;seed=32'h5eed1234;
    for(i=0;i<(1<<ADDR_W);i++)model[i]='0;
    repeat(3)@(posedge clk);rst_n=1;
    // Physical macro contents are undefined until initialized through the port.
    for(i=0;i<(1<<ADDR_W);i++)begin
      @(negedge clk);wr_valid=1;wr_addr=i;wr_data='0;wr_be='1;#1;
      while(!wr_ready)begin @(posedge clk);@(negedge clk);#1;end
      accepted=accepted+1;@(posedge clk);@(negedge clk);wr_valid=0;
    end
    wait(dut.u_fabric.group_req_ready===4'b1111);repeat(2)@(posedge clk);
    while(accepted<TARGET||d_req_valid||rd_valid||wr_valid||d_pending||rd_pending)begin
      @(negedge clk);
      if(d_fire_q)d_req_valid=0;if(rd_fire_q)rd_valid=0;if(wr_fire_q)wr_valid=0;
      d_rsp_ready=($urandom(seed)%4)!=0;rd_rsp_ready=($urandom(seed)%5)!=0;
      if(accepted<TARGET&&!d_pending&&!d_req_valid&&($urandom(seed)%3)!=0)begin
        d_req_valid=1;d_req_index=$urandom(seed)&12'hfff;
      end
      if(accepted<TARGET&&!rd_pending&&!rd_valid&&($urandom(seed)%3)!=0)begin
        rd_valid=1;rd_addr=$urandom(seed)&10'h3ff;
      end
      if(accepted<TARGET&&!wr_valid&&($urandom(seed)%3)!=0)begin
        wr_valid=1;wr_addr=$urandom(seed)&10'h3ff;
        for(i=0;i<16;i++)wr_data[i*32 +: 32]=$urandom(seed);
        for(i=0;i<64;i++)wr_be[i]=($urandom(seed)%4)!=0;
      end
      #1;d_fire_q=d_req_valid&&d_req_ready;rd_fire_q=rd_valid&&rd_ready;wr_fire_q=wr_valid&&wr_ready;
      if(d_fire_q)begin
        d_expected=model[d_req_index[11:2]][d_req_index[1:0]*128 +: 128];
        d_pending=1;d_expect_error=0;accepted=accepted+1;
      end
      if(rd_fire_q)begin rd_expected=model[rd_addr];rd_pending=1;accepted=accepted+1;end
      if(wr_fire_q)begin
        merged=model[wr_addr];for(b=0;b<64;b++)if(wr_be[b])merged[b*8 +: 8]=wr_data[b*8 +: 8];
        model[wr_addr]=merged;accepted=accepted+1;
      end
      @(posedge clk);
    end
    repeat(3)@(posedge clk);
    if(reads+writes!=accepted)$fatal(1,"counter mismatch read=%0d write=%0d accepted=%0d",reads,writes,accepted);
    if(responses!=reads||conflicts==0||rd_stalls==0||wr_stalls==0||macro_errors!=0)
      $fatal(1,"coverage/counter mismatch");
    // Misaligned base is rejected locally and must not touch the macro fabric.
    @(negedge clk);descriptor_base=1;d_req_index=0;d_req_valid=1;d_rsp_ready=1;
    do @(posedge clk);while(!d_req_ready);@(negedge clk);d_req_valid=0;d_pending=1;d_expect_error=1;
    do @(posedge clk);while(!(d_rsp_valid&&d_rsp_ready));
    if(!d_rsp_error)$fatal(1,"misaligned descriptor base was accepted");
    $display("L3_DESCRIPTOR_MACRO_FABRIC_100K_PASS transactions=%0d descriptor_and_normal_responses=%0d conflicts=%0d cycles=%0d",
             accepted,responses,conflicts,cycles);$finish;
  end
  initial begin repeat(1500000)@(posedge clk);$fatal(1,"timeout");end
endmodule
