`timescale 1ns/1ps
module tb_cgra_sfu_vector;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic [3:0] op;
  logic in_valid, in_ready, out_valid, out_ready;
  logic [4*16-1:0] in0, in1;
  logic [4*32-1:0] out;

  cgra_sfu_vector #(.LANES(4)) dut (
    .clk_i(clk), .rst_ni(rst_n), .op_i(op),
    .in_valid_i(in_valid), .in_ready_o(in_ready),
    .in0_data_i(in0), .in1_data_i(in1),
    .out_valid_o(out_valid), .out_ready_i(out_ready), .out_data_o(out)
  );

  task automatic issue(input logic [3:0] operation);
    begin
      @(negedge clk);
      op = operation;
      in_valid = 1;
      do @(posedge clk); while (!in_ready);
      @(negedge clk);
      in_valid = 0;
      do @(posedge clk); while (!out_valid);
    end
  endtask

  initial begin
    op = 0; in_valid = 0; out_ready = 1;
    in0 = {16'sd4, -16'sd3, 16'sd2, 16'sd1};
    in1 = {16'sd1, 16'sd7, -16'sd2, 16'sd5};
    repeat (3) @(posedge clk); rst_n = 1;

    issue(4'h0);
    if ($signed(out[0*32 +: 32]) != 6) $fatal(1, "add lane0");
    if ($signed(out[2*32 +: 32]) != 4) $fatal(1, "add lane2");

    issue(4'h3);
    if ($signed(out[2*32 +: 32]) != 0) $fatal(1, "relu lane2");

    issue(4'h5);
    if ($signed(out[0*32 +: 32]) != 4) $fatal(1, "reduce sum");
    if ($signed(out[1*32 +: 32]) != 0) $fatal(1, "reduce upper lane");

    $display("TB_SFU_PASS");
    $finish;
  end

  initial begin
    repeat (100) @(posedge clk);
    $fatal(1, "SFU test timeout");
  end
endmodule
