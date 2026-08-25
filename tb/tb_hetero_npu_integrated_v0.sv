`timescale 1ns/1ps
module tb_hetero_npu_integrated_v0;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;
  logic cmd_valid, cmd_ready;
  logic [127:0] cmd_data;
  logic event_valid, event_ready;
  logic [55:0] event_data;
  logic illegal_engine;
  integer event_count;
  logic seen1, seen2, seen3, seen4;

  hetero_npu_integrated_v0 dut (
    .clk_i(clk), .rst_ni(rst_n),
    .host_cmd_valid_i(cmd_valid), .host_cmd_ready_o(cmd_ready),
    .host_cmd_data_i(cmd_data),
    .host_event_valid_o(event_valid), .host_event_ready_i(event_ready),
    .host_event_data_o(event_data), .illegal_engine_o(illegal_engine)
  );

  task automatic send_command(input logic [2:0] engine, input logic [15:0] wait_id,
                              input logic [15:0] signal_id);
    begin
      @(negedge clk);
      cmd_data = '0;
      cmd_data[10:8] = engine;
      cmd_data[39:24] = wait_id;
      cmd_data[55:40] = signal_id;
      cmd_valid = 1'b1;
      do @(posedge clk); while (!cmd_ready);
      @(negedge clk);
      cmd_valid = 1'b0;
    end
  endtask

  always @(posedge clk) begin
    if (rst_n && event_valid && event_ready) begin
      event_count <= event_count + 1;
      case (event_data[55:40])
        16'd1: seen1 <= 1'b1;
        16'd2: seen2 <= 1'b1;
        16'd3: begin
          if (!seen1 || !seen2) $fatal(1, "barrier released before dependencies");
          seen3 <= 1'b1;
        end
        16'd4: begin
          if (!seen3) $fatal(1, "wait-gated matrix released before barrier");
          seen4 <= 1'b1;
        end
        default: $fatal(1, "unexpected event id=%0d", event_data[55:40]);
      endcase
    end
  end

  initial begin
    cmd_valid = 1'b0;
    cmd_data = '0;
    event_ready = 1'b1;
    event_count = 0;
    seen1 = 1'b0;
    seen2 = 1'b0;
    seen3 = 1'b0;
    seen4 = 1'b0;
    repeat (3) @(posedge clk);
    rst_n = 1'b1;

    // Two independent commands, then a barrier, then a wait-gated matrix op.
    send_command(3'd3, 16'd0, 16'd1);
    send_command(3'd1, 16'd0, 16'd2);
    send_command(3'd0, 16'd0, 16'd3);
    send_command(3'd2, 16'd3, 16'd4);
    wait (event_count == 4);
    if (!seen1 || !seen2 || !seen3 || !seen4) $fatal(1, "missing completion event");
    if (illegal_engine) $fatal(1, "unexpected illegal engine indication");
    $display("TB_INTEGRATED_V0_PASS");
    $finish;
  end

  initial begin
    repeat (500) @(posedge clk);
    $fatal(1, "integrated v0 timeout");
  end
endmodule
