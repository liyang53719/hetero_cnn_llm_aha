`timescale 1ns/1ps
module tb_gemmini_rocc_program_adapter;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  integer cycles, issued, events;
  logic op_valid, op_ready, op_first, op_last, op_legal;
  logic [15:0] event_id;
  logic [6:0] op_funct;
  logic [63:0] op_rs1, op_rs2;
  logic rocc_valid, rocc_ready, rocc_busy;
  logic [6:0] funct, opcode;
  logic [4:0] rs1_idx, rs2_idx, rd;
  logic xd, xs1, xs2;
  logic [63:0] rs1, rs2;
  logic event_valid, event_ready, illegal;
  logic [55:0] event_data;
  logic [6:0] seen_funct [0:31];
  logic [63:0] seen_rs1 [0:31], seen_rs2 [0:31];

  assign rocc_ready = (cycles % 4) != 1;
  assign event_ready = (cycles % 5) != 2;

  gemmini_rocc_program_adapter dut (
    .clk_i(clk), .rst_ni(rst_n), .op_valid_i(op_valid), .op_ready_o(op_ready),
    .op_first_i(op_first), .op_last_i(op_last), .op_legal_i(op_legal),
    .op_status_i(op_legal ? 8'd0 : 8'd1),
    .event_id_i(event_id), .op_funct_i(op_funct), .op_rs1_i(op_rs1), .op_rs2_i(op_rs2),
    .rocc_cmd_valid_o(rocc_valid), .rocc_cmd_ready_i(rocc_ready),
    .rocc_inst_funct_o(funct), .rocc_inst_rs2_o(rs2_idx), .rocc_inst_rs1_o(rs1_idx),
    .rocc_inst_xd_o(xd), .rocc_inst_xs1_o(xs1), .rocc_inst_xs2_o(xs2),
    .rocc_inst_rd_o(rd), .rocc_inst_opcode_o(opcode), .rocc_rs1_o(rs1), .rocc_rs2_o(rs2),
    .rocc_busy_i(rocc_busy), .event_valid_o(event_valid), .event_ready_i(event_ready),
    .event_data_o(event_data), .illegal_program_o(illegal)
  );

  always @(posedge clk) begin
    if (!rst_n) begin cycles <= 0; issued <= 0; events <= 0; end
    else begin
      cycles <= cycles + 1;
      if (rocc_valid && rocc_ready) begin
        seen_funct[issued] <= funct; seen_rs1[issued] <= rs1; seen_rs2[issued] <= rs2;
        issued <= issued + 1;
        if (opcode != 7'h7b || xd || !xs1 || !xs2 || rd != 0 || rs1_idx != 0 || rs2_idx != 0)
          $fatal(1, "CUSTOM_3 envelope mismatch");
      end
      if (event_valid && event_ready) events <= events + 1;
    end
  end

  task automatic send_op(input int index, input int count, input logic legal,
                         input logic [15:0] eid);
    begin
      @(negedge clk);
      op_first = index == 0; op_last = index == count-1; op_legal = legal;
      event_id = eid; op_funct = index + 8; op_rs1 = 64'h1000 + index;
      op_rs2 = 64'h2000 + index; op_valid = 1;
      do @(posedge clk); while (!op_ready);
      @(negedge clk); op_valid = 0;
    end
  endtask

  task automatic finish_busy;
    begin
      @(negedge clk); rocc_busy = 1;
      repeat (4) @(negedge clk);
      rocc_busy = 0;
    end
  endtask

  task automatic check_event(input logic [15:0] eid, input logic [7:0] status,
                             input integer count);
    begin
      do @(posedge clk); while (!(event_valid && event_ready));
      if (event_data[55:40] != eid || event_data[39:32] != status ||
          event_data[31:29] != 3'd2 || event_data[28:0] != count)
        $fatal(1, "event mismatch data=%h", event_data);
      if (illegal !== (status != 0)) $fatal(1, "illegal flag mismatch");
      @(negedge clk);
    end
  endtask

  initial begin
    op_valid=0; op_first=0; op_last=0; op_legal=0; event_id=0;
    op_funct=0; op_rs1=0; op_rs2=0; rocc_busy=0;
    repeat (3) @(posedge clk); rst_n=1;
    for (int i=0; i<12; i++) send_op(i, 12, 1, 16'h0123);
    finish_busy(); check_event(16'h0123, 0, 12);
    if (issued != 12 || events != 1) $fatal(1, "first program accounting mismatch");
    for (int i=0; i<12; i++)
      if (seen_funct[i] != i+8 || seen_rs1[i] != 64'h1000+i || seen_rs2[i] != 64'h2000+i)
        $fatal(1, "command order mismatch at %0d", i);

    send_op(0, 3, 1, 16'h0044); send_op(1, 3, 1, 16'h0044); send_op(2, 3, 1, 16'h0044);
    finish_busy(); check_event(16'h0044, 0, 3);
    if (issued != 15 || events != 2) $fatal(1, "second program accounting mismatch");

    send_op(0, 1, 0, 16'h0055);
    check_event(16'h0055, 1, 0);
    if (issued != 15 || events != 3) $fatal(1, "illegal program accounting mismatch");
    $display("GEMMINI_ROCC_PROGRAM_ADAPTER_PASS cycles=%0d issued=%0d events=%0d", cycles, issued, events);
    $finish;
  end
  initial begin repeat (2000) @(posedge clk); $fatal(1, "timeout"); end
endmodule
