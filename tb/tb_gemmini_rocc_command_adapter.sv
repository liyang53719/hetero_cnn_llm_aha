`timescale 1ns/1ps
module tb_gemmini_rocc_command_adapter;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;
  integer cycles;

  logic host_valid, host_ready;
  logic [127:0] host_data;
  logic rocc_valid, rocc_ready;
  logic [6:0] funct, opcode;
  logic [4:0] rs1_idx, rs2_idx, rd;
  logic xd, xs1, xs2;
  logic [63:0] rs1, rs2;
  logic resp_valid, resp_ready;
  logic [4:0] resp_rd;
  logic [63:0] resp_data;
  logic rocc_busy;
  logic event_valid, event_ready, illegal;
  logic [55:0] event_data;

  assign rocc_ready = (cycles % 3) != 0;
  assign event_ready = (cycles % 4) != 1;

  gemmini_rocc_command_adapter dut (
    .clk_i(clk), .rst_ni(rst_n),
    .host_cmd_valid_i(host_valid), .host_cmd_ready_o(host_ready),
    .host_cmd_data_i(host_data),
    .rocc_cmd_valid_o(rocc_valid), .rocc_cmd_ready_i(rocc_ready),
    .rocc_inst_funct_o(funct), .rocc_inst_rs2_o(rs2_idx),
    .rocc_inst_rs1_o(rs1_idx), .rocc_inst_xd_o(xd),
    .rocc_inst_xs1_o(xs1), .rocc_inst_xs2_o(xs2),
    .rocc_inst_rd_o(rd), .rocc_inst_opcode_o(opcode),
    .rocc_rs1_o(rs1), .rocc_rs2_o(rs2),
    .rocc_resp_valid_i(resp_valid), .rocc_resp_ready_o(resp_ready),
    .rocc_resp_rd_i(resp_rd), .rocc_resp_data_i(resp_data),
    .rocc_busy_i(rocc_busy),
    .event_valid_o(event_valid), .event_ready_i(event_ready),
    .event_data_o(event_data), .illegal_command_o(illegal)
  );

  always @(posedge clk) begin
    if (!rst_n) cycles <= 0;
    else cycles <= cycles + 1;
  end

  task automatic send_command(input logic [7:0] op, input logic [2:0] engine,
                              input logic [15:0] wait_id, input logic [15:0] signal_id,
                              input logic [23:0] src0, input logic [23:0] src1,
                              input logic [23:0] dst);
    begin
      @(negedge clk);
      host_data = '0;
      host_data[7:0] = op;
      host_data[10:8] = engine;
      host_data[39:24] = wait_id;
      host_data[55:40] = signal_id;
      host_data[79:56] = src0;
      host_data[103:80] = src1;
      host_data[127:104] = dst;
      host_valid = 1'b1;
      do @(posedge clk); while (!host_ready);
      @(negedge clk);
      host_valid = 1'b0;
    end
  endtask

  task automatic wait_event(input logic [15:0] signal_id, input logic bad);
    begin
      do @(posedge clk); while (!(event_valid && event_ready));
      if (event_data[55:40] !== signal_id)
        $fatal(1, "event signal got=%0d expected=%0d", event_data[55:40], signal_id);
      if (illegal !== bad)
        $fatal(1, "illegal flag got=%0d expected=%0d", illegal, bad);
    end
  endtask

  initial begin
    host_valid = 0;
    host_data = 0;
    resp_valid = 0;
    resp_rd = 0;
    resp_data = 0;
    rocc_busy = 0;
    cycles = 0;
    repeat (3) @(posedge clk);
    rst_n = 1;

    send_command(8'h20, 3'd2, 16'd0, 16'd7, 24'h123456, 24'h654321, 24'd3);
    do @(posedge clk); while (!rocc_valid);
    if (funct !== 7'h00 || opcode !== 7'b0001011)
      $fatal(1, "GEMM instruction decode mismatch");
    if (rs1 !== 64'h123456 || rs2 !== 64'h654321 || rd !== 5'd3)
      $fatal(1, "descriptor translation mismatch");
    if (!xd || !xs1 || !xs2 || rs1_idx != 0 || rs2_idx != 0)
      $fatal(1, "RoCC operand flags mismatch");
    if (!rocc_ready)
      do @(posedge clk); while (!(rocc_valid && rocc_ready));
    @(negedge clk);
    resp_rd = 5'd3;
    resp_data = 64'hdead_beef;
    resp_valid = 1'b1;
    do @(posedge clk); while (!resp_ready);
    @(negedge clk);
    resp_valid = 1'b0;
    wait_event(16'd7, 1'b0);

    send_command(8'h10, 3'd1, 16'd0, 16'd9, 24'd0, 24'd0, 24'd0);
    wait_event(16'd9, 1'b1);
    $display("GEMMINI_ROCC_ADAPTER_PASS cycles=%0d", cycles);
    $finish;
  end

  initial begin
    repeat (500) @(posedge clk);
    $fatal(1, "RoCC adapter timeout");
  end
endmodule
