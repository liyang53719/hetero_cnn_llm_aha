`timescale 1ns/1ps
module tb_l2_sp6144x128_macro_wrapper;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  logic req_valid,req_ready,req_write;
  logic [12:0] req_addr;
  logic [127:0] req_wdata;
  logic [15:0] req_wstrb;
  logic rsp_valid,rsp_ready,rsp_error;
  logic [127:0] rsp_rdata;
  integer cycles;

  l2_sp6144x128_macro_wrapper dut (
    .clk_i(clk),.rst_ni(rst_n),.req_valid_i(req_valid),.req_ready_o(req_ready),
    .req_write_i(req_write),.req_addr_i(req_addr),.req_wdata_i(req_wdata),
    .req_wstrb_i(req_wstrb),.rsp_valid_o(rsp_valid),.rsp_ready_i(rsp_ready),
    .rsp_error_o(rsp_error),.rsp_rdata_o(rsp_rdata));

  always @(posedge clk) if(!rst_n) cycles<=0; else cycles<=cycles+1;

  task automatic transact(input logic write, input logic [12:0] addr,
                           input logic [127:0] data, input logic [15:0] strb,
                           input logic error, input logic [127:0] expected);
    begin
      @(negedge clk); req_write=write;req_addr=addr;req_wdata=data;req_wstrb=strb;req_valid=1;
      do @(posedge clk); while(!req_ready);
      @(negedge clk);req_valid=0;
      do @(posedge clk); while(!rsp_valid);
      if(rsp_error!==error) $fatal(1,"error mismatch addr=%0d",addr);
      if(!write&&!error&&rsp_rdata!==expected)
        $fatal(1,"read mismatch addr=%0d got=%h expected=%h",addr,rsp_rdata,expected);
      @(negedge clk);rsp_ready=1;
      @(posedge clk);@(negedge clk);rsp_ready=0;
    end
  endtask

  initial begin
    logic [127:0] first,second,merged,held;
    logic [15:0] mask;
    req_valid=0;req_write=0;req_addr=0;req_wdata=0;req_wstrb=0;rsp_ready=0;cycles=0;
    first=128'h00112233445566778899aabbccddeeff;
    second=128'hffeeddccbbaa99887766554433221100;
    mask=16'h50a5;
    repeat(4) @(posedge clk);rst_n=1;
    transact(1,13'd5,first,16'hffff,0,0);
    transact(0,13'd5,0,0,0,first);
    merged=first;
    for(integer b=0;b<16;b++) if(mask[b]) merged[b*8 +: 8]=second[b*8 +: 8];
    transact(1,13'd5,second,mask,0,0);
    transact(0,13'd5,0,0,0,merged);

    // Response must remain stable under host backpressure.
    @(negedge clk);req_write=0;req_addr=13'd5;req_valid=1;
    do @(posedge clk);while(!req_ready);
    @(negedge clk);req_valid=0;
    do @(posedge clk);while(!rsp_valid);
    held=rsp_rdata;
    repeat(4) begin @(posedge clk);if(!rsp_valid||rsp_rdata!==held)$fatal(1,"response changed under stall");end
    @(negedge clk);rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;

    transact(0,13'd6144,0,0,1,0);
    transact(1,13'd8191,second,16'hffff,1,0);
    $display("L2_SP6144X128_MACRO_WRAPPER_PASS cycles=%0d",cycles);
    $finish;
  end
  initial begin repeat(1000) @(posedge clk);$fatal(1,"timeout");end
endmodule
