`timescale 1ns/1ps
module tb_shared_l2_fabric;
  localparam integer ADDR_W=10, DATA_W=512, ROWS=256, TARGET=100000;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  logic [1:0] rd_valid,rd_ready,resp_valid,resp_ready;
  logic [2*ADDR_W-1:0] rd_addr;
  logic [2*DATA_W-1:0] resp_data;
  logic wr_valid,wr_ready;
  logic [ADDR_W-1:0] wr_addr;
  logic [DATA_W-1:0] wr_data;
  logic [DATA_W/8-1:0] wr_be;
  logic [63:0] cycles,reads,writes,conflicts,rd_stalls,wr_stalls;
  logic [DATA_W-1:0] model [0:(1<<ADDR_W)-1];
  logic pending0,pending1,fire0_d,fire1_d,firew_d;
  logic [DATA_W-1:0] expect0,expect1,merged;
  integer i,b,seed,accepted,responses;

  shared_l2_fabric #(.ADDR_W(ADDR_W),.ROWS_PER_BANK(ROWS)) dut (
    .clk_i(clk),.rst_ni(rst_n),.rd_valid_i(rd_valid),.rd_ready_o(rd_ready),
    .rd_addr_i(rd_addr),.rd_resp_valid_o(resp_valid),.rd_resp_ready_i(resp_ready),
    .rd_data_o(resp_data),.wr_valid_i(wr_valid),.wr_ready_o(wr_ready),
    .wr_addr_i(wr_addr),.wr_data_i(wr_data),.wr_be_i(wr_be),
    .cycle_count_o(cycles),.read_count_o(reads),.write_count_o(writes),
    .bank_conflict_count_o(conflicts),.read_stall_count_o(rd_stalls),
    .write_stall_count_o(wr_stalls));

  always @(posedge clk) if(rst_n) begin
    if(resp_valid[0]&&resp_ready[0]) begin
      if(!pending0||resp_data[0 +: DATA_W]!==expect0) $fatal(1,"read0 mismatch");
      pending0=0; responses=responses+1;
    end
    if(resp_valid[1]&&resp_ready[1]) begin
      if(!pending1||resp_data[DATA_W +: DATA_W]!==expect1) $fatal(1,"read1 mismatch");
      pending1=0; responses=responses+1;
    end
  end

  initial begin
    rd_valid=0;rd_addr=0;resp_ready=0;wr_valid=0;wr_addr=0;wr_data=0;wr_be=0;
    pending0=0;pending1=0;fire0_d=0;fire1_d=0;firew_d=0;
    accepted=0;responses=0;seed=32'h12345678;
    for(i=0;i<(1<<ADDR_W);i++) model[i]='0;
    repeat(3) @(posedge clk);rst_n=1;
    // Address 6 maps to bank group 2 and row 1: lanes must land in banks 8..11.
    @(negedge clk);wr_valid=1;wr_addr=10'd6;wr_be='1;
    wr_data={128'h4444,128'h3333,128'h2222,128'h1111};
    #1;if(!wr_ready) $fatal(1,"directed mapping write was not accepted");
    firew_d=1;model[6]=wr_data;accepted=accepted+1;
    @(posedge clk);@(negedge clk);
    if(dut.mem_q[8][1]!==128'h1111||dut.mem_q[9][1]!==128'h2222||
       dut.mem_q[10][1]!==128'h3333||dut.mem_q[11][1]!==128'h4444)
      $fatal(1,"512-bit beat did not span four consecutive 128-bit banks");
    wr_valid=0;firew_d=0;
    while(accepted<TARGET||rd_valid!=0||wr_valid||pending0||pending1) begin
      @(negedge clk);
      if(fire0_d) rd_valid[0]=0;
      if(fire1_d) rd_valid[1]=0;
      if(firew_d) wr_valid=0;
      resp_ready[0]=($urandom(seed)%4)!=0;
      resp_ready[1]=($urandom(seed)%5)!=0;
      if(accepted<TARGET&&!pending0&&!rd_valid[0]&&($urandom(seed)%3)!=0) begin
        rd_valid[0]=1;rd_addr[0 +: ADDR_W]=$urandom(seed)&((1<<ADDR_W)-1);
      end
      if(accepted<TARGET&&!pending1&&!rd_valid[1]&&($urandom(seed)%3)!=0) begin
        rd_valid[1]=1;
        if(($urandom(seed)%3)==0) rd_addr[ADDR_W +: ADDR_W]=rd_addr[0 +: ADDR_W];
        else rd_addr[ADDR_W +: ADDR_W]=$urandom(seed)&((1<<ADDR_W)-1);
      end
      if(accepted<TARGET&&!wr_valid&&($urandom(seed)%3)!=0) begin
        wr_valid=1;wr_addr=$urandom(seed)&((1<<ADDR_W)-1);
        for(i=0;i<16;i++) wr_data[i*32 +: 32]=$urandom(seed);
        for(i=0;i<64;i++) wr_be[i]=($urandom(seed)%4)!=0;
      end
      #1;
      fire0_d=rd_valid[0]&&rd_ready[0];
      fire1_d=rd_valid[1]&&rd_ready[1];
      firew_d=wr_valid&&wr_ready;
      if(fire0_d) begin expect0=model[rd_addr[0 +: ADDR_W]];pending0=1;accepted=accepted+1;end
      if(fire1_d) begin expect1=model[rd_addr[ADDR_W +: ADDR_W]];pending1=1;accepted=accepted+1;end
      if(firew_d) begin
        merged=model[wr_addr];
        for(b=0;b<64;b++) if(wr_be[b]) merged[b*8 +: 8]=wr_data[b*8 +: 8];
        model[wr_addr]=merged;accepted=accepted+1;
      end
      @(posedge clk);
    end
    repeat(2) @(posedge clk);
    if(reads+writes!=accepted) $fatal(1,"counter mismatch");
    if(conflicts==0||rd_stalls==0||wr_stalls==0) $fatal(1,"stall coverage missing");
    if(responses!=reads) $fatal(1,"response mismatch responses=%0d reads=%0d",responses,reads);
    $display("TB_SHARED_L2_100K_PASS transactions=%0d reads=%0d writes=%0d conflicts=%0d rd_stalls=%0d wr_stalls=%0d cycles=%0d",
             accepted,reads,writes,conflicts,rd_stalls,wr_stalls,cycles);
    $finish;
  end
  initial begin repeat(1000000) @(posedge clk);$fatal(1,"shared L2 timeout");end
endmodule
