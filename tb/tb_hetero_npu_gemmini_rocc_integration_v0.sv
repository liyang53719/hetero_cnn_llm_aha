`timescale 1ns/1ps
module tb_hetero_npu_gemmini_rocc_integration_v0;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  integer cycles, event_count;
  logic host_valid, host_ready;
  logic [127:0] host_data;
  logic host_event_valid, host_event_ready;
  logic [55:0] host_event_data;
  logic illegal_engine, illegal_rocc;
  logic rocc_valid, rocc_ready;
  logic [6:0] funct, opcode;
  logic [4:0] rs1_idx, rs2_idx, rd;
  logic xd, xs1, xs2;
  logic [63:0] rs1, rs2;
  logic resp_valid, resp_ready, rocc_busy;
  logic [4:0] resp_rd;
  logic [63:0] resp_data;
  logic seen_matrix, seen_sfu;
  assign rocc_ready = (cycles % 3) != 0;
  assign host_event_ready = (cycles % 4) != 1;

  hetero_npu_gemmini_rocc_integration_v0 dut (
    .clk_i(clk), .rst_ni(rst_n), .host_cmd_valid_i(host_valid), .host_cmd_ready_o(host_ready),
    .host_cmd_data_i(host_data), .host_event_valid_o(host_event_valid), .host_event_ready_i(host_event_ready),
    .host_event_data_o(host_event_data), .illegal_engine_o(illegal_engine), .illegal_rocc_command_o(illegal_rocc),
    .rocc_cmd_valid_o(rocc_valid), .rocc_cmd_ready_i(rocc_ready), .rocc_inst_funct_o(funct),
    .rocc_inst_rs2_o(rs2_idx), .rocc_inst_rs1_o(rs1_idx), .rocc_inst_xd_o(xd), .rocc_inst_xs1_o(xs1),
    .rocc_inst_xs2_o(xs2), .rocc_inst_rd_o(rd), .rocc_inst_opcode_o(opcode), .rocc_rs1_o(rs1), .rocc_rs2_o(rs2),
    .rocc_resp_valid_i(resp_valid), .rocc_resp_ready_o(resp_ready), .rocc_resp_rd_i(resp_rd),
    .rocc_resp_data_i(resp_data), .rocc_busy_i(rocc_busy)
  );

  always @(posedge clk) begin
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;
    if (rst_n && host_event_valid && host_event_ready) begin
      event_count <= event_count + 1;
      if (host_event_data[55:40] == 16'd1) seen_matrix <= 1'b1;
      if (host_event_data[55:40] == 16'd2) seen_sfu <= 1'b1;
    end
  end

  task automatic send_command(input logic [7:0] op, input logic [2:0] engine,
                              input logic [15:0] signal_id);
    begin
      @(negedge clk);
      host_data = '0; host_data[7:0] = op; host_data[10:8] = engine;
      host_data[55:40] = signal_id; host_data[79:56] = 24'h123456; host_data[103:80] = 24'h654321;
      host_data[127:104] = 24'd3; host_valid = 1'b1;
      do @(posedge clk); while (!host_ready);
      @(negedge clk); host_valid = 1'b0;
    end
  endtask

  initial begin
    host_valid = 0; host_data = 0; resp_valid = 0; resp_rd = 0; resp_data = 0; rocc_busy = 0;
    cycles = 0; event_count = 0; seen_matrix = 0; seen_sfu = 0;
    repeat (3) @(posedge clk); rst_n = 1;
    send_command(8'h20, 3'd2, 16'd1);
    do @(posedge clk); while (!rocc_valid);
    if (funct !== 7'h00 || rs1 !== 64'h123456 || rs2 !== 64'h654321)
      $fatal(1, "integrated RoCC translation mismatch");
    if (!rocc_ready) do @(posedge clk); while (!(rocc_valid && rocc_ready));
    @(negedge clk); resp_rd = 5'd3; resp_data = 64'h55aa; resp_valid = 1'b1;
    do @(posedge clk); while (!resp_ready);
    @(negedge clk); resp_valid = 1'b0;
    wait (seen_matrix);
    send_command(8'h30, 3'd3, 16'd2);
    wait (seen_sfu);
    if (event_count != 2 || illegal_engine || illegal_rocc)
      $fatal(1, "integrated event/illegal result mismatch");
    $display("GEMMINI_ROCC_INTEGRATION_PASS cycles=%0d", cycles);
    $finish;
  end
  initial begin
    repeat (1000) @(posedge clk);
    $fatal(1, "integrated RoCC timeout");
  end
endmodule
