`timescale 1ns/1ps
module tb_aha_garnet_microsequencer;
  localparam logic [1:0] OP_PACKET = 2'd0;
  localparam logic [1:0] OP_AXI = 2'd1;
  localparam logic [1:0] OP_WAIT_INTERRUPT = 2'd2;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;
  logic op_valid, op_ready;
  logic [1:0] op_kind;
  logic [12:0] op_axi_addr;
  logic [31:0] op_axi_data;
  logic [17:0] op_packet_addr;
  logic [511:0] op_packet_data;
  logic [63:0] op_packet_strb;
  logic interrupt;
  logic [12:0] awaddr;
  logic awvalid, awready;
  logic [31:0] wdata;
  logic wvalid, wready;
  logic bready, bvalid;
  logic [1:0] bresp;
  logic wr_en;
  logic [17:0] wr_addr;
  logic [63:0] wr_data;
  logic [7:0] wr_strb;
  logic done, error_flag;
  int packet_writes;

  aha_garnet_microsequencer dut (
    .clk_i(clk), .rst_ni(rst_n),
    .op_valid_i(op_valid), .op_ready_o(op_ready), .op_kind_i(op_kind),
    .op_axi_addr_i(op_axi_addr), .op_axi_data_i(op_axi_data),
    .op_packet_addr_i(op_packet_addr), .op_packet_data_i(op_packet_data), .op_packet_strb_i(op_packet_strb),
    .garnet_interrupt_i(interrupt),
    .axi_awaddr_o(awaddr), .axi_awvalid_o(awvalid), .axi_awready_i(awready),
    .axi_wdata_o(wdata), .axi_wvalid_o(wvalid), .axi_wready_i(wready),
    .axi_bready_o(bready), .axi_bvalid_i(bvalid), .axi_bresp_i(bresp),
    .proc_packet_wr_en_o(wr_en), .proc_packet_wr_addr_o(wr_addr),
    .proc_packet_wr_data_o(wr_data), .proc_packet_wr_strb_o(wr_strb),
    .op_done_o(done), .op_error_o(error_flag)
  );
  assign awready = 1'b1;
  assign wready = 1'b1;

  always @(posedge clk) if (rst_n && wr_en) begin
    if (wr_addr != 18'h200 + packet_writes * 8) $fatal(1, "packet address order");
    if (wr_data != packet_writes) $fatal(1, "packet word order");
    if (wr_strb != 8'hff) $fatal(1, "packet strb");
    packet_writes <= packet_writes + 1;
  end

  task automatic issue(input logic [1:0] kind);
    begin
      @(negedge clk);
      op_kind = kind;
      op_valid = 1'b1;
      do @(posedge clk); while (!op_ready);
      @(negedge clk);
      op_valid = 1'b0;
    end
  endtask

  initial begin
    op_valid=0; op_kind=0; op_axi_addr=13'h1c; op_axi_data=32'h1;
    op_packet_addr=18'h200; op_packet_strb='1; interrupt=0; bvalid=0; bresp=0; packet_writes=0;
    for (int i=0; i<8; i++) op_packet_data[i*64 +: 64] = i;
    repeat (3) @(posedge clk);
    rst_n=1;
    issue(OP_PACKET);
    do @(posedge clk); while (!done);
    if (packet_writes != 8 || error_flag) $fatal(1, "packet op result");
    issue(OP_AXI);
    do @(posedge clk); while (wvalid != 1'b1);
    @(negedge clk); bvalid=1; bresp=0;
    do @(posedge clk); while (!bready);
    @(negedge clk); bvalid=0;
    do @(posedge clk); while (!done);
    if (awaddr != 13'h1c || wdata != 32'h1 || error_flag) $fatal(1, "AXI op result");
    issue(OP_WAIT_INTERRUPT);
    repeat (3) @(posedge clk);
    if (done) $fatal(1, "interrupt wait ended too early");
    @(negedge clk); interrupt=1;
    do @(posedge clk); while (!done);
    interrupt=0;
    if (error_flag) $fatal(1, "interrupt wait result");
    $display("AHA_GARNET_MICROSEQUENCER_PASS packet_writes=%0d", packet_writes);
    $finish;
  end
  initial begin
    repeat (250) @(posedge clk);
    $fatal(1, "microsequencer timeout");
  end
endmodule
