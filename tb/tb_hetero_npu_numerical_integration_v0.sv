`timescale 1ns/1ps
// Concurrent numerical/cycle regression for the clean-room integrated kernel.
module tb_hetero_npu_numerical_integration_v0;
  logic clk = 1'b0;
  logic rst_n = 1'b0;
  always #5 clk = ~clk;

  integer cycle_count;
  always @(posedge clk) begin
    if (!rst_n) cycle_count <= 0;
    else cycle_count <= cycle_count + 1;
  end

  logic matrix_start, matrix_start_ready;
  logic [1:0] matrix_cfg_m, matrix_cfg_n;
  logic [15:0] matrix_cfg_k;
  logic matrix_a_valid, matrix_a_ready, matrix_b_valid, matrix_b_ready;
  logic [15:0] matrix_a_data, matrix_b_data;
  logic matrix_c_valid, matrix_c_ready, matrix_done, matrix_busy;
  logic [0:0] matrix_c_row, matrix_c_col;
  logic signed [31:0] matrix_c_data;

  logic [3:0] sfu_op;
  logic sfu_in_valid, sfu_in_ready, sfu_out_valid, sfu_out_ready;
  logic [4*16-1:0] sfu_in0, sfu_in1;
  logic [4*32-1:0] sfu_out;

  logic [1:0] kv_cmd_op, kv_cmd_sequence, kv_cmd_layer;
  logic kv_cmd_valid, kv_cmd_ready;
  logic [15:0] kv_cmd_token;
  logic [63:0] kv_cmd_k, kv_cmd_v;
  logic kv_rsp_valid, kv_rsp_ready;
  logic [2:0] kv_rsp_status;
  logic [15:0] kv_rsp_length;
  logic [63:0] kv_rsp_k, kv_rsp_v;

  hetero_npu_numerical_integration_v0 dut (
    .clk_i(clk), .rst_ni(rst_n),
    .matrix_start_i(matrix_start), .matrix_start_ready_o(matrix_start_ready),
    .matrix_cfg_m_i(matrix_cfg_m), .matrix_cfg_n_i(matrix_cfg_n),
    .matrix_cfg_k_i(matrix_cfg_k),
    .matrix_a_valid_i(matrix_a_valid), .matrix_a_ready_o(matrix_a_ready),
    .matrix_a_data_i(matrix_a_data),
    .matrix_b_valid_i(matrix_b_valid), .matrix_b_ready_o(matrix_b_ready),
    .matrix_b_data_i(matrix_b_data),
    .matrix_c_valid_o(matrix_c_valid), .matrix_c_ready_i(matrix_c_ready),
    .matrix_c_row_o(matrix_c_row), .matrix_c_col_o(matrix_c_col),
    .matrix_c_data_o(matrix_c_data), .matrix_done_o(matrix_done),
    .matrix_busy_o(matrix_busy),
    .sfu_op_i(sfu_op), .sfu_in_valid_i(sfu_in_valid),
    .sfu_in_ready_o(sfu_in_ready), .sfu_in0_data_i(sfu_in0),
    .sfu_in1_data_i(sfu_in1), .sfu_out_valid_o(sfu_out_valid),
    .sfu_out_ready_i(sfu_out_ready), .sfu_out_data_o(sfu_out),
    .kv_cmd_op_i(kv_cmd_op), .kv_cmd_valid_i(kv_cmd_valid),
    .kv_cmd_ready_o(kv_cmd_ready), .kv_cmd_sequence_i(kv_cmd_sequence),
    .kv_cmd_layer_i(kv_cmd_layer), .kv_cmd_token_i(kv_cmd_token),
    .kv_cmd_k_i(kv_cmd_k), .kv_cmd_v_i(kv_cmd_v),
    .kv_rsp_valid_o(kv_rsp_valid), .kv_rsp_ready_i(kv_rsp_ready),
    .kv_rsp_status_o(kv_rsp_status), .kv_rsp_length_o(kv_rsp_length),
    .kv_rsp_k_o(kv_rsp_k), .kv_rsp_v_o(kv_rsp_v)
  );

  // Deterministic backpressure makes the cycle result reproducible while
  // exercising hold-until-ready behavior in all three integrated engines.
  assign matrix_c_ready = (cycle_count % 3) != 0;
  assign sfu_out_ready  = (cycle_count % 4) != 1;
  assign kv_rsp_ready   = (cycle_count % 5) != 2;

  integer matrix_count;
  integer matrix_values [0:3];
  logic matrix_done_seen;
  integer sfu_count;
  integer sfu_ops [0:2];
  integer sfu_values [0:2][0:3];
  integer kv_count;
  integer kv_ops [0:7];
  integer kv_statuses [0:7];
  integer kv_lengths [0:7];
  logic [63:0] kv_keys [0:7];
  logic [63:0] kv_values [0:7];

  always @(posedge clk) begin
    if (rst_n && matrix_c_valid && matrix_c_ready) begin
      if (matrix_count < 4) matrix_values[matrix_count] = $signed(matrix_c_data);
      matrix_count = matrix_count + 1;
    end
    if (rst_n && matrix_done) matrix_done_seen = 1'b1;
    if (rst_n && sfu_out_valid && sfu_out_ready) begin
      if (sfu_count < 3) begin
        sfu_ops[sfu_count] = sfu_op;
        sfu_values[sfu_count][0] = $signed(sfu_out[0*32 +: 32]);
        sfu_values[sfu_count][1] = $signed(sfu_out[1*32 +: 32]);
        sfu_values[sfu_count][2] = $signed(sfu_out[2*32 +: 32]);
        sfu_values[sfu_count][3] = $signed(sfu_out[3*32 +: 32]);
      end
      sfu_count = sfu_count + 1;
    end
    if (rst_n && kv_rsp_valid && kv_rsp_ready) begin
      if (kv_count < 8) begin
        kv_ops[kv_count] = kv_cmd_op;
        kv_statuses[kv_count] = kv_rsp_status;
        kv_lengths[kv_count] = kv_rsp_length;
        kv_keys[kv_count] = kv_rsp_k;
        kv_values[kv_count] = kv_rsp_v;
      end
      kv_count = kv_count + 1;
    end
  end

  task automatic matrix_send_beat(input integer a0, input integer a1,
                                  input integer b0, input integer b1);
    begin
      @(negedge clk);
      matrix_a_data = {a1[7:0], a0[7:0]};
      matrix_b_data = {b1[7:0], b0[7:0]};
      matrix_a_valid = 1'b1;
      matrix_b_valid = 1'b1;
      do @(posedge clk); while (!(matrix_a_ready && matrix_b_ready));
      @(negedge clk);
      matrix_a_valid = 1'b0;
      matrix_b_valid = 1'b0;
    end
  endtask

  task automatic matrix_driver;
    begin
      @(negedge clk);
      matrix_cfg_m = 2;
      matrix_cfg_n = 2;
      matrix_cfg_k = 3;
      matrix_start = 1'b1;
      do @(posedge clk); while (!matrix_start_ready);
      @(negedge clk);
      matrix_start = 1'b0;
      matrix_send_beat(1, 2, 4, 5);
      matrix_send_beat(3, -1, 2, 1);
      matrix_send_beat(-2, 4, -1, 3);
      wait (matrix_done_seen);
    end
  endtask

  task automatic sfu_issue(input logic [3:0] operation);
    integer before_count;
    begin
      before_count = sfu_count;
      @(negedge clk);
      sfu_op = operation;
      sfu_in_valid = 1'b1;
      do @(posedge clk); while (!sfu_in_ready);
      @(negedge clk);
      sfu_in_valid = 1'b0;
      wait (sfu_count > before_count);
    end
  endtask

  task automatic sfu_driver;
    begin
      @(negedge clk);
      sfu_in0 = {16'sd4, -16'sd3, 16'sd2, 16'sd1};
      sfu_in1 = {16'sd1, 16'sd7, -16'sd2, 16'sd5};
      sfu_issue(4'h0);
      sfu_issue(4'h3);
      sfu_issue(4'h5);
    end
  endtask

  task automatic kv_issue(input logic [1:0] operation,
                          input logic [15:0] token_arg,
                          input logic [63:0] key_arg,
                          input logic [63:0] value_arg);
    integer before_count;
    begin
      before_count = kv_count;
      @(negedge clk);
      kv_cmd_op = operation;
      kv_cmd_token = token_arg;
      kv_cmd_k = key_arg;
      kv_cmd_v = value_arg;
      kv_cmd_valid = 1'b1;
      do @(posedge clk); while (!kv_cmd_ready);
      @(negedge clk);
      kv_cmd_valid = 1'b0;
      wait (kv_count > before_count);
      if (kv_statuses[before_count] != 0)
        $fatal(1, "KV status=%0d op=%0d", kv_statuses[before_count], operation);
    end
  endtask

  task automatic kv_driver;
    integer index;
    begin
      for (index = 0; index < 5; index = index + 1)
        kv_issue(2'd0, 0, 64'h100 + index, 64'h200 + index);
      kv_issue(2'd1, 16'd4, 0, 0);
      kv_issue(2'd2, 0, 0, 0);
      kv_issue(2'd3, 0, 0, 0);
    end
  endtask

  initial begin
    matrix_start = 0;
    matrix_cfg_m = 0;
    matrix_cfg_n = 0;
    matrix_cfg_k = 0;
    matrix_a_valid = 0;
    matrix_b_valid = 0;
    matrix_a_data = 0;
    matrix_b_data = 0;
    sfu_op = 0;
    sfu_in_valid = 0;
    sfu_in0 = 0;
    sfu_in1 = 0;
    kv_cmd_op = 0;
    kv_cmd_valid = 0;
    kv_cmd_sequence = 0;
    kv_cmd_layer = 0;
    kv_cmd_token = 0;
    kv_cmd_k = 0;
    kv_cmd_v = 0;
    cycle_count = 0;
    matrix_count = 0;
    matrix_done_seen = 1'b0;
    sfu_count = 0;
    kv_count = 0;
    repeat (3) @(posedge clk);
    rst_n = 1'b1;
    fork
      matrix_driver();
      sfu_driver();
      kv_driver();
    join
    if (matrix_count != 4) $fatal(1, "matrix count=%0d", matrix_count);
    if (sfu_count != 3) $fatal(1, "SFU count=%0d", sfu_count);
    if (kv_count != 8) $fatal(1, "KV count=%0d", kv_count);
    $display("RTL_MATRIX_RESULT count=%0d v0=%0d v1=%0d v2=%0d v3=%0d",
             matrix_count, matrix_values[0], matrix_values[1],
             matrix_values[2], matrix_values[3]);
    $display("RTL_SFU_RESULT op=%0d l0=%0d l1=%0d l2=%0d l3=%0d",
             sfu_ops[0], sfu_values[0][0], sfu_values[0][1],
             sfu_values[0][2], sfu_values[0][3]);
    $display("RTL_SFU_RESULT op=%0d l0=%0d l1=%0d l2=%0d l3=%0d",
             sfu_ops[1], sfu_values[1][0], sfu_values[1][1],
             sfu_values[1][2], sfu_values[1][3]);
    $display("RTL_SFU_RESULT op=%0d l0=%0d l1=%0d l2=%0d l3=%0d",
             sfu_ops[2], sfu_values[2][0], sfu_values[2][1],
             sfu_values[2][2], sfu_values[2][3]);
    $display("RTL_KV_RESULT op=%0d status=%0d length=%0d k=%h v=%h",
             kv_ops[5], kv_statuses[5], kv_lengths[5], kv_keys[5], kv_values[5]);
    $display("RTL_KV_RESULT op=%0d status=%0d length=%0d k=%h v=%h",
             kv_ops[7], kv_statuses[7], kv_lengths[7], kv_keys[7], kv_values[7]);
    $display("RTL_NUMERICAL_INTEGRATION_PASS cycles=%0d", cycle_count);
    $finish;
  end

  initial begin
    repeat (5000) @(posedge clk);
    $fatal(1, "numerical integration timeout");
  end
endmodule
