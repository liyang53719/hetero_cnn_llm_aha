`timescale 1ns/1ps
module tb_aha_garnet_axi_config_loader;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic cfg_valid, cfg_ready;
  logic [12:0] cfg_addr;
  logic [31:0] cfg_data;
  logic [12:0] awaddr;
  logic awvalid, awready;
  logic [31:0] wdata;
  logic wvalid, wready;
  logic bready, bvalid;
  logic [1:0] bresp;
  logic done, error_flag;
  int cycles;
  int phase;

  aha_garnet_axi_config_loader dut (
    .clk_i(clk), .rst_ni(rst_n),
    .cfg_valid_i(cfg_valid), .cfg_ready_o(cfg_ready), .cfg_addr_i(cfg_addr), .cfg_data_i(cfg_data),
    .axi_awaddr_o(awaddr), .axi_awvalid_o(awvalid), .axi_awready_i(awready),
    .axi_wdata_o(wdata), .axi_wvalid_o(wvalid), .axi_wready_i(wready),
    .axi_bready_o(bready), .axi_bvalid_i(bvalid), .axi_bresp_i(bresp),
    .write_done_o(done), .write_error_o(error_flag)
  );

  assign awready = (cycles % 3) != 0;
  assign wready = (cycles % 4) != 1;

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      phase <= 0;
    end else begin
      cycles <= cycles + 1;
      if (awvalid && awready) begin
        if (phase != 0) $fatal(1, "AW was not first");
        phase <= 1;
      end
      if (wvalid && wready) begin
        if (phase != 1) $fatal(1, "W did not follow AW");
        phase <= 2;
      end
      if (bvalid && bready) begin
        if (phase != 2) $fatal(1, "B did not follow W");
        phase <= 0;
      end
    end
  end

  task automatic send_config(input logic [12:0] addr, input logic [31:0] data,
                             input logic [1:0] response);
    begin
      @(negedge clk);
      cfg_addr = addr;
      cfg_data = data;
      cfg_valid = 1'b1;
      do @(posedge clk); while (!cfg_ready);
      @(negedge clk);
      cfg_valid = 1'b0;
      do @(posedge clk); while (!(wvalid && wready));
      @(negedge clk);
      bresp = response;
      bvalid = 1'b1;
      do @(posedge clk); while (!bready);
      @(negedge clk);
      bvalid = 1'b0;
      do @(posedge clk); while (!done);
      if (error_flag != (response != 0)) $fatal(1, "AXI response status mismatch");
    end
  endtask

  initial begin
    cfg_valid = 0;
    cfg_addr = 0;
    cfg_data = 0;
    bvalid = 0;
    bresp = 0;
    cycles = 0;
    phase = 0;
    repeat (3) @(posedge clk);
    rst_n = 1;
    send_config(13'h01c, 32'h0000_0001, 2'b00);
    send_config(13'h018, 32'h0003_0003, 2'b10);
    $display("AHA_GARNET_AXI_CONFIG_LOADER_PASS cycles=%0d", cycles);
    $finish;
  end

  initial begin
    repeat (300) @(posedge clk);
    $fatal(1, "AXI config-loader timeout");
  end
endmodule
