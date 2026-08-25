`timescale 1ns/1ps
module tb_l2_512b_macro_bank_group;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  logic req_valid,req_ready,req_write,rsp_valid,rsp_ready,rsp_error;
  logic [12:0] req_row;
  logic [511:0] req_wdata,rsp_rdata;
  logic [63:0] req_wstrb;
  integer cycles;
  l2_512b_macro_bank_group dut(.clk_i(clk),.rst_ni(rst_n),
    .req_valid_i(req_valid),.req_ready_o(req_ready),.req_write_i(req_write),
    .req_row_i(req_row),.req_wdata_i(req_wdata),.req_wstrb_i(req_wstrb),
    .rsp_valid_o(rsp_valid),.rsp_ready_i(rsp_ready),.rsp_error_o(rsp_error),
    .rsp_rdata_o(rsp_rdata));
  always @(posedge clk)if(!rst_n)cycles<=0;else cycles<=cycles+1;

  task automatic transact(input logic wr,input logic[12:0] row,
    input logic[511:0] data,input logic[63:0] strb,input logic err,
    input logic[511:0] expected);
    begin
      @(negedge clk);req_write=wr;req_row=row;req_wdata=data;req_wstrb=strb;req_valid=1;
      do @(posedge clk);while(!req_ready);
      @(negedge clk);req_valid=0;
      do @(posedge clk);while(!rsp_valid);
      if(rsp_error!==err)$fatal(1,"error mismatch");
      if(!wr&&!err&&rsp_rdata!==expected)$fatal(1,"read mismatch");
      @(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;
    end
  endtask

  initial begin
    logic[511:0] a,b,m,held;logic[63:0] mask;
    req_valid=0;req_write=0;req_row=0;req_wdata=0;req_wstrb=0;rsp_ready=0;cycles=0;
    a={128'h4444,128'h3333,128'h2222,128'h1111};
    b={8{64'hffeeddccbbaa9988}};mask=64'h8001008040201009;
    repeat(4)@(posedge clk);rst_n=1;
    transact(1,13'd23,a,{64{1'b1}},0,0);transact(0,13'd23,0,0,0,a);
    m=a;for(integer i=0;i<64;i++)if(mask[i])m[i*8 +: 8]=b[i*8 +: 8];
    transact(1,13'd23,b,mask,0,0);transact(0,13'd23,0,0,0,m);
    @(negedge clk);req_row=13'd23;req_write=0;req_valid=1;
    do @(posedge clk);while(!req_ready);@(negedge clk);req_valid=0;
    do @(posedge clk);while(!rsp_valid);held=rsp_rdata;
    repeat(5)begin @(posedge clk);if(!rsp_valid||rsp_rdata!==held)$fatal(1,"stall instability");end
    @(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;
    transact(0,13'd6144,0,0,1,0);
    $display("L2_512B_MACRO_BANK_GROUP_PASS cycles=%0d",cycles);$finish;
  end
  initial begin repeat(1000)@(posedge clk);$fatal(1,"timeout");end
endmodule
