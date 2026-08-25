`timescale 1ns/1ps
module tb_matrix_engine_int8_tile;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic start, start_ready;
  logic [1:0] cfg_m, cfg_n;
  logic [15:0] cfg_k;
  logic a_valid, a_ready, b_valid, b_ready;
  logic [15:0] a_data, b_data;
  logic c_valid, c_ready, done, busy;
  logic [0:0] c_row, c_col;
  logic signed [31:0] c_data;
  int result_index = 0;
  integer expected [0:3];

  matrix_engine_int8_tile #(.MAX_M(2), .MAX_N(2)) dut (
    .clk_i(clk), .rst_ni(rst_n),
    .start_i(start), .start_ready_o(start_ready),
    .cfg_m_i(cfg_m), .cfg_n_i(cfg_n), .cfg_k_i(cfg_k),
    .a_valid_i(a_valid), .a_ready_o(a_ready), .a_data_i(a_data),
    .b_valid_i(b_valid), .b_ready_o(b_ready), .b_data_i(b_data),
    .c_valid_o(c_valid), .c_ready_i(c_ready),
    .c_row_o(c_row), .c_col_o(c_col), .c_data_o(c_data),
    .done_o(done), .busy_o(busy)
  );

  task automatic send_beat(input logic signed [7:0] a0, a1, b0, b1);
    begin
      @(negedge clk);
      a_data  = {a1, a0};
      b_data  = {b1, b0};
      a_valid = 1;
      b_valid = 1;
      do @(posedge clk); while (!(a_ready && b_ready));
      @(negedge clk);
      a_valid = 0;
      b_valid = 0;
    end
  endtask

  always @(posedge clk) begin
    if (rst_n && c_valid && c_ready) begin
      if ($signed(c_data) !== expected[result_index]) begin
        $fatal(1, "matrix mismatch idx=%0d got=%0d expected=%0d",
               result_index, $signed(c_data), expected[result_index]);
      end
      result_index <= result_index + 1;
    end
  end

  initial begin
    start = 0; a_valid = 0; b_valid = 0; a_data = 0; b_data = 0;
    c_ready = 1; cfg_m = 2; cfg_n = 2; cfg_k = 3;
    expected[0] = 12;
    expected[1] = 2;
    expected[2] = 2;
    expected[3] = 21;
    repeat (3) @(posedge clk);
    rst_n = 1;
    @(negedge clk);
    start = 1;
    @(posedge clk);
    @(negedge clk);
    start = 0;
    send_beat(1, 2, 4, 5);
    send_beat(3, -1, 2, 1);
    send_beat(-2, 4, -1, 3);
    wait (done);
    @(posedge clk);
    if (result_index != 4) $fatal(1, "expected four matrix outputs");
    $display("TB_MATRIX_PASS");
    $finish;
  end

  initial begin
    repeat (200) @(posedge clk);
    $fatal(1, "matrix test timeout");
  end
endmodule
