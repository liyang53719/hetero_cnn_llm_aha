`timescale 1ns/1ps
module tb_engine_completion_rr_arbiter;
  parameter integer TARGET = 100000;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  always #5 clk = ~clk;
  logic [6:0] in_valid, in_ready;
  logic [7*56-1:0] in_data;
  logic out_valid, out_ready;
  logic [55:0] out_data;
  logic [31:0] grants;
  integer cycles, sent_total, received_total;
  integer sent [0:6];
  integer received [0:6];
  logic stalled_q;
  logic [55:0] stalled_data_q;

  engine_completion_rr_arbiter dut (
    .clk_i(clk), .rst_ni(rst_n), .in_valid_i(in_valid),
    .in_ready_o(in_ready), .in_data_i(in_data), .out_valid_o(out_valid),
    .out_ready_i(out_ready), .out_data_o(out_data), .grants_o(grants)
  );

  always_comb begin
    in_valid = {7{sent_total < TARGET}};
    out_ready = (cycles % 5) != 1 && (cycles % 11) != 4;
  end

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      sent_total <= 0;
      received_total <= 0;
      stalled_q <= 0;
      stalled_data_q <= 0;
      for (int source = 0; source < 7; source++) begin
        sent[source] <= 0;
        received[source] <= 0;
        in_data[source*56 +: 56] <= {3'(source), 21'd0, 32'd0};
      end
    end else begin
      int owner;
      cycles <= cycles + 1;
      for (int source = 0; source < 7; source++) begin
        if (in_valid[source] && in_ready[source]) begin
          sent[source] <= sent[source] + 1;
          sent_total <= sent_total + 1;
          in_data[source*56 +: 56] <=
            {3'(source), 21'd0, 32'(sent[source] + 1)};
        end
      end
      if (out_valid && out_ready) begin
        owner = 32'(out_data[55:53]);
        if (owner < 0 || owner >= 7 || out_data[31:0] != 32'(received[owner])) begin
          $display("RR_REORDER owner=%0d got=%0d expected=%0d sent=%0d data=%h",
                   owner, out_data[31:0], received[owner], sent[owner], out_data);
          $fatal(1, "completion arbiter reorder owner=%0d", owner);
        end
        received[owner] <= received[owner] + 1;
        received_total <= received_total + 1;
      end
      if (stalled_q && (!out_valid || out_data != stalled_data_q))
        $fatal(1, "completion arbiter stalled payload changed");
      stalled_q <= out_valid && !out_ready;
      if (out_valid && !out_ready)
        stalled_data_q <= out_data;
    end
  end

  initial begin
    clk = 0;
    rst_n = 0;
    repeat (3) @(posedge clk);
    rst_n = 1;
    wait(received_total == TARGET);
    @(negedge clk);
    if (grants != TARGET || sent_total != TARGET)
      $fatal(1, "completion arbiter accounting");
    for (int source = 0; source < 7; source++)
      if (received[source] < TARGET/7 - 1)
        $fatal(1, "completion source starved source=%0d count=%0d", source, received[source]);
    $display("ENGINE_COMPLETION_RR_100K_PASS grants=%0d min_source=%0d",
             grants, received[0]);
    $finish;
  end

  initial begin
    repeat (TARGET*5) @(posedge clk);
    $fatal(1, "completion arbiter timeout");
  end
endmodule
