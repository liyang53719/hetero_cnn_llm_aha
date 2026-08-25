`timescale 1ns/1ps
module tb_aha_garnet_proc_packet_writer;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic valid, ready;
  logic [17:0] addr;
  logic [511:0] data;
  logic [63:0] strb;
  logic wr_en;
  logic [17:0] wr_addr;
  logic [63:0] wr_data;
  logic [7:0] wr_strb;
  logic done;
  int writes;

  aha_garnet_proc_packet_writer dut (
    .clk_i(clk), .rst_ni(rst_n),
    .packet_valid_i(valid), .packet_ready_o(ready), .packet_addr_i(addr),
    .packet_data_i(data), .packet_strb_i(strb),
    .proc_packet_wr_en_o(wr_en), .proc_packet_wr_addr_o(wr_addr),
    .proc_packet_wr_data_o(wr_data), .proc_packet_wr_strb_o(wr_strb),
    .packet_done_o(done)
  );

  always @(posedge clk) begin
    if (!rst_n) writes <= 0;
    else if (wr_en) begin
      if (wr_addr !== 18'h120 + writes * 8)
        $fatal(1, "address mismatch got=%h expected=%h", wr_addr, 18'h120 + writes * 8);
      if (wr_data !== 64'h0100_0000_0000_0000 + writes)
        $fatal(1, "data order mismatch got=%h", wr_data);
      if (wr_strb !== (8'h80 >> writes))
        $fatal(1, "byte-enable mismatch got=%h", wr_strb);
      writes <= writes + 1;
    end
  end

  initial begin
    valid = 0;
    addr = 18'h120;
    strb = 64'h0102_0408_1020_4080;
    for (int i = 0; i < 8; i++) data[i*64 +: 64] = 64'h0100_0000_0000_0000 + i;
    writes = 0;
    repeat (3) @(posedge clk);
    rst_n = 1;
    @(negedge clk);
    valid = 1;
    do @(posedge clk); while (!ready);
    @(negedge clk);
    valid = 0;
    do @(posedge clk); while (!done);
    if (writes != 8) $fatal(1, "expected eight 64-bit writes, got %0d", writes);
    if (!ready) $fatal(1, "writer did not return ready after completion");
    $display("AHA_GARNET_PROC_PACKET_WRITER_PASS writes=%0d", writes);
    $finish;
  end

  initial begin
    repeat (100) @(posedge clk);
    $fatal(1, "proc-packet writer timeout");
  end
endmodule
