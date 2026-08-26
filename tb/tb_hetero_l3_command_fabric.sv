`timescale 1ns/1ps
module tb_hetero_l3_command_fabric;
  parameter integer TARGET = 600;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  always #5 clk = ~clk;
  integer cycles, host_accepted, engine_completed, illegal_seen;
  integer observed_commands, observed_completions, observed_illegal;
  integer accepted_by_engine [0:5];
  integer completed_by_engine [0:5];

  logic host_valid, host_ready;
  logic [127:0] host_data;
  logic [5:0] engine_cmd_valid, engine_cmd_ready;
  logic [6*128-1:0] engine_cmd_data;
  logic [5:0] engine_completion_valid, engine_completion_ready;
  logic [6*56-1:0] engine_completion_data;
  logic init_done, illegal_engine, watchdog_lock;
  logic [4:0] command_level, completion_level;
  logic [31:0] macro_errors, completion_grants, completion_protocol_errors;
  logic [5:0] engine_busy;
  logic [7:0] engine_delay [0:5];
  logic [127:0] engine_command_q [0:5];
  logic stall_engine2;

  logic [3:0] l2_rd_valid, l2_rd_ready, l2_rd_rsp_valid, l2_rd_rsp_ready;
  logic [59:0] l2_rd_addr;
  logic [2047:0] l2_rd_rsp_data;
  logic [3:0] l2_rd_rsp_error;
  logic [1:0] l2_wr_valid, l2_wr_ready;
  logic [29:0] l2_wr_addr;
  logic [1023:0] l2_wr_data;
  logic [127:0] l2_wr_be;
  logic [1:0] phy_rd_valid, phy_rd_ready, phy_rsp_valid, phy_rsp_ready;
  logic [29:0] phy_rd_addr;
  logic [1023:0] phy_rsp_data;
  logic [1:0] phy_rsp_error;
  logic phy_wr_valid, phy_wr_ready;
  logic [14:0] phy_wr_addr;
  logic [511:0] phy_wr_data;
  logic [63:0] phy_wr_be;
  logic [31:0] promotions, read_grants, write_grants;

  hetero_l3_command_fabric #(.WATCHDOG_ENABLE(1), .WATCHDOG_CYCLES(64)) dut (
    .clk_i(clk), .rst_ni(rst_n),
    .host_cmd_valid_i(host_valid), .host_cmd_ready_o(host_ready),
    .host_cmd_data_i(host_data), .engine_cmd_valid_o(engine_cmd_valid),
    .engine_cmd_ready_i(engine_cmd_ready), .engine_cmd_data_o(engine_cmd_data),
    .engine_completion_valid_i(engine_completion_valid),
    .engine_completion_ready_o(engine_completion_ready),
    .engine_completion_data_i(engine_completion_data),
    .init_done_o(init_done), .command_level_o(command_level),
    .completion_level_o(completion_level),
    .event_macro_error_count_o(macro_errors), .illegal_engine_o(illegal_engine),
    .watchdog_lock_o(watchdog_lock), .completion_grants_o(completion_grants),
    .completion_protocol_error_count_o(completion_protocol_errors),
    .l2_rd_valid_i(l2_rd_valid), .l2_rd_ready_o(l2_rd_ready),
    .l2_rd_addr_i(l2_rd_addr), .l2_rd_rsp_valid_o(l2_rd_rsp_valid),
    .l2_rd_rsp_ready_i(l2_rd_rsp_ready), .l2_rd_rsp_data_o(l2_rd_rsp_data),
    .l2_rd_rsp_error_o(l2_rd_rsp_error), .l2_wr_valid_i(l2_wr_valid),
    .l2_wr_ready_o(l2_wr_ready), .l2_wr_addr_i(l2_wr_addr),
    .l2_wr_data_i(l2_wr_data), .l2_wr_be_i(l2_wr_be),
    .phy_rd_valid_o(phy_rd_valid), .phy_rd_ready_i(phy_rd_ready),
    .phy_rd_addr_o(phy_rd_addr), .phy_rsp_valid_i(phy_rsp_valid),
    .phy_rsp_ready_o(phy_rsp_ready), .phy_rsp_data_i(phy_rsp_data),
    .phy_rsp_error_i(phy_rsp_error), .phy_wr_valid_o(phy_wr_valid),
    .phy_wr_ready_i(phy_wr_ready), .phy_wr_addr_o(phy_wr_addr),
    .phy_wr_data_o(phy_wr_data), .phy_wr_be_o(phy_wr_be),
    .descriptor_promotions_o(promotions), .l2_read_grants_o(read_grants),
    .l2_write_grants_o(write_grants)
  );

  always_comb begin
    for (int engine = 0; engine < 6; engine++) begin
      engine_cmd_ready[engine] = !engine_busy[engine] &&
                                 ((cycles + engine) % 4 != 1);
      engine_completion_data[engine*56 +: 56] = {
        engine_command_q[engine][55:40], 8'd0, 3'(engine),
        29'(completed_by_engine[engine])
      };
    end
  end

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      host_accepted <= 0;
      engine_completed <= 0;
      illegal_seen <= 0;
      engine_busy <= 0;
      engine_completion_valid <= 0;
      for (int engine = 0; engine < 6; engine++) begin
        engine_delay[engine] <= 0;
        engine_command_q[engine] <= 0;
        accepted_by_engine[engine] <= 0;
        completed_by_engine[engine] <= 0;
      end
    end else begin
      cycles <= cycles + 1;
      if (host_valid && host_ready)
        host_accepted <= host_accepted + 1;
      if (illegal_engine)
        illegal_seen <= illegal_seen + 1;
      for (int engine = 0; engine < 6; engine++) begin
        if (engine_cmd_valid[engine] && engine_cmd_ready[engine]) begin
          engine_busy[engine] <= 1;
          engine_command_q[engine] <= engine_cmd_data[engine*128 +: 128];
          engine_delay[engine] <= 8'(2 + ((cycles + engine) % 7));
          accepted_by_engine[engine] <= accepted_by_engine[engine] + 1;
        end else if (engine_busy[engine] && !engine_completion_valid[engine] &&
                     !(stall_engine2 && engine == 2)) begin
          if (engine_delay[engine] == 0)
            engine_completion_valid[engine] <= 1;
          else
            engine_delay[engine] <= engine_delay[engine] - 1'b1;
        end
        if (engine_completion_valid[engine] && engine_completion_ready[engine]) begin
          engine_completion_valid[engine] <= 0;
          engine_busy[engine] <= 0;
          engine_completed <= engine_completed + 1;
          completed_by_engine[engine] <= completed_by_engine[engine] + 1;
        end
      end
    end
  end

  task automatic send_command(input logic [2:0] engine,
                              input logic [15:0] event_id,
                              input logic [15:0] wait_id);
    begin
      @(negedge clk);
      host_data = 0;
      host_data[7:0] = 8'h7f;
      host_data[10:8] = engine;
      host_data[39:24] = wait_id;
      host_data[55:40] = event_id;
      host_valid = 1;
      do @(posedge clk); while (!host_ready);
      @(negedge clk);
      host_valid = 0;
    end
  endtask

  initial begin
    clk = 0;
    rst_n = 0;
    host_valid = 0;
    host_data = 0;
    stall_engine2 = 0;
    l2_rd_valid = 0;
    l2_rd_addr = 0;
    l2_rd_rsp_ready = 0;
    l2_wr_valid = 0;
    l2_wr_addr = 0;
    l2_wr_data = 0;
    l2_wr_be = 0;
    phy_rd_ready = 0;
    phy_rsp_valid = 0;
    phy_rsp_data = 0;
    phy_rsp_error = 0;
    phy_wr_ready = 0;
    repeat (3) @(posedge clk);
    rst_n = 1;
    wait(init_done);
    #1;
    if (host_ready !== 1)
      $fatal(1, "host did not open after event SRAM init");

    for (int command = 0; command < TARGET; command++)
      send_command(3'(command % 6), 16'(command + 1), 16'd0);
    send_command(3'd2, 16'd0, 16'd0);
    send_command(3'd7, 16'hf001, 16'd0);
    wait(engine_completed == TARGET + 1);
    wait(completion_grants == TARGET + 2);
    wait(command_level == 0 && completion_level == 0);
    if (illegal_seen != 1 || macro_errors != 0 ||
        completion_protocol_errors != 0 || watchdog_lock)
      $fatal(1, "normal command fabric accounting");
    for (int engine = 0; engine < 6; engine++)
      if (accepted_by_engine[engine] == 0 ||
          accepted_by_engine[engine] != completed_by_engine[engine])
        $fatal(1, "engine progress mismatch engine=%0d", engine);

    stall_engine2 = 1;
    send_command(3'd2, 16'hf100, 16'd0);
    wait(watchdog_lock);
    repeat (4) @(posedge clk);
    if (host_ready || completion_grants != TARGET + 3)
      $fatal(1, "watchdog lock/status completion failure");
    observed_commands = host_accepted;
    observed_completions = completion_grants;
    observed_illegal = illegal_seen;

    @(negedge clk);
    rst_n = 0;
    repeat (3) @(posedge clk);
    stall_engine2 = 0;
    rst_n = 1;
    wait(init_done);
    #1;
    if (watchdog_lock || !host_ready || macro_errors != 0)
      $fatal(1, "watchdog reset recovery failure");
    if (observed_commands != TARGET + 3 || observed_completions != TARGET + 3 ||
        observed_illegal != 1)
      $fatal(1, "pre-reset snapshot mismatch");
    if (l2_rd_ready != 0 || l2_rd_rsp_valid != 0 || l2_rd_rsp_data != 0 ||
        l2_rd_rsp_error != 0 || l2_wr_ready != 0 || phy_rd_valid != 0 ||
        phy_rsp_ready != 0 || phy_rd_addr != 0 || phy_wr_valid ||
        phy_wr_addr != 0 || phy_wr_data != 0 || phy_wr_be != 0 ||
        promotions != 0 || read_grants != 0 || write_grants != 0)
      $fatal(1, "idle L2 interface changed during command-only test");
    $display("HETERO_L3_COMMAND_FABRIC_PASS commands=%0d completions=%0d illegal=%0d",
             observed_commands, observed_completions, observed_illegal);
    $finish;
  end

  initial begin
    repeat (TARGET*200 + 100000) @(posedge clk);
    $fatal(1, "command fabric timeout accepted=%0d completed=%0d grants=%0d",
           host_accepted, engine_completed, completion_grants);
  end
endmodule
