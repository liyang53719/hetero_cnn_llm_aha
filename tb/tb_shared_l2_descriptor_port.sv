`timescale 1ns/1ps
module tb_shared_l2_descriptor_port;
  localparam integer ADDR_W=8;
  logic clk=0,rst_n=0;always #5 clk=~clk;
  integer cycles,accepted,responses,seed;
  logic[63:0] base;
  logic req_valid,req_ready;logic[23:0] req_index;
  logic rsp_valid,rsp_ready,rsp_error;logic[127:0] rsp_data;
  logic f_req_valid,f_req_ready;logic[ADDR_W-1:0] f_req_addr;
  logic f_rsp_valid,f_rsp_ready,f_rsp_error;logic[511:0] f_rsp_data;
  logic f_pending;logic[ADDR_W-1:0] f_addr_q;
  logic[127:0] expected_q;

  shared_l2_descriptor_port #(.ADDR_W(ADDR_W),.SRAM_BYTES(64'd16384))dut(
    .clk_i(clk),.rst_ni(rst_n),.descriptor_base_i(base),
    .descriptor_req_valid_i(req_valid),.descriptor_req_ready_o(req_ready),
    .descriptor_req_index_i(req_index),.descriptor_rsp_valid_o(rsp_valid),
    .descriptor_rsp_ready_i(rsp_ready),.descriptor_rsp_data_o(rsp_data),
    .descriptor_rsp_error_o(rsp_error),.fabric_req_valid_o(f_req_valid),
    .fabric_req_ready_i(f_req_ready),.fabric_req_addr_o(f_req_addr),
    .fabric_rsp_valid_i(f_rsp_valid),.fabric_rsp_ready_o(f_rsp_ready),
    .fabric_rsp_data_i(f_rsp_data),.fabric_rsp_error_i(f_rsp_error));

  function automatic logic[127:0] lane_value(input logic[ADDR_W-1:0] beat,input logic[1:0] lane);
    lane_value={94'd0,beat,lane,24'h5a1234};
  endfunction
  always_comb begin
    for(int lane=0;lane<4;lane++)f_rsp_data[lane*128 +: 128]=lane_value(f_addr_q,lane[1:0]);
  end
  assign f_req_ready=(cycles%4)!=1&&!f_pending;
  assign f_rsp_valid=f_pending;
  assign f_rsp_error=0;
  assign rsp_ready=(cycles%5)!=2;

  always @(posedge clk)begin
    if(!rst_n)begin cycles<=0;f_pending<=0;f_addr_q<=0;accepted<=0;responses<=0;end
    else begin
      cycles<=cycles+1;
      if(f_req_valid&&f_req_ready)begin f_pending<=1;f_addr_q<=f_req_addr;end
      if(f_rsp_valid&&f_rsp_ready)f_pending<=0;
      if(req_valid&&req_ready)begin
        accepted<=accepted+1;
        if(base[3:0]==0&&base+({40'd0,req_index}<<4)<16384)
          expected_q<=lane_value((base+({40'd0,req_index}<<4))>>6,
                                 (base+({40'd0,req_index}<<4))>>4);
        else expected_q<='0;
      end
      if(rsp_valid&&rsp_ready)begin
        responses<=responses+1;
        if(!rsp_error&&rsp_data!==expected_q)$fatal(1,"lane extraction mismatch got=%h expected=%h",rsp_data,expected_q);
      end
    end
  end
  task automatic send(input logic[63:0] b,input logic[23:0] index,input logic expect_error);
    begin
      @(negedge clk);base=b;req_index=index;req_valid=1;
      do @(posedge clk);while(!req_ready);@(negedge clk);req_valid=0;
      do @(posedge clk);while(!(rsp_valid&&rsp_ready));
      if(rsp_error!==expect_error)$fatal(1,"error mismatch base=%h index=%h",b,index);
      @(negedge clk);
    end
  endtask
  initial begin
    req_valid=0;req_index=0;base=0;seed=32'h31415926;
    repeat(3)@(posedge clk);rst_n=1;
    for(int i=0;i<1000;i++)send(64'h40,($urandom(seed)%1019),0);
    send(64'h41,0,1);send(64'h40,24'hffffff,1);
    if(accepted!=1002||responses!=1002)$fatal(1,"account mismatch");
    $display("SHARED_L2_DESCRIPTOR_PORT_PASS cycles=%0d requests=%0d",cycles,accepted);$finish;
  end
  initial begin repeat(50000)@(posedge clk);$fatal(1,"timeout");end
endmodule
