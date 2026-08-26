`timescale 1ns/1ps
module tb_gemmini_scratchpad_gateway_integration;
  parameter integer TARGET = 100000;
  logic clk, rst_n;
  always #5 clk = ~clk;

  integer cycles, seed, completed, tx_seen;
  logic cfg_valid, cfg_ready, cfg_dir, cfg_route;
  logic [11:0] cfg_last;
  logic [15:0] cfg_tag;
  logic [11:0] cfg_tid;
  logic [3:0] cfg_fmt;

  logic [3:0] core_w_valid, core_w_ready;
  logic [47:0] core_w_addr;
  logic [511:0] core_w_data;
  logic [63:0] core_w_mask;
  logic [3:0] core_rreq_valid, core_rreq_ready, core_rreq_dma;
  logic [47:0] core_rreq_addr;
  logic [3:0] core_rresp_valid, core_rresp_ready, core_rresp_dma;
  logic [511:0] core_rresp_data;

  logic [3:0] ext_w_valid, ext_w_ready;
  logic [47:0] ext_w_addr;
  logic [511:0] ext_w_data;
  logic [63:0] ext_w_mask;
  logic [3:0] ext_rreq_valid, ext_rreq_ready;
  logic [47:0] ext_rreq_addr;
  logic [3:0] ext_rresp_valid, ext_rresp_ready;
  logic [511:0] ext_rresp_data;

  logic tx_valid, tx_ready, tx_route, tx_last;
  logic [511:0] tx_data;
  logic [63:0] tx_be;
  logic [15:0] tx_tag;
  logic [11:0] tx_tid;
  logic [3:0] tx_fmt;
  logic rx_valid, rx_ready, rx_route, rx_last;
  logic [511:0] rx_data;
  logic [63:0] rx_be;
  logic [15:0] rx_tag;
  logic [11:0] rx_tid;
  logic [3:0] rx_fmt;
  logic transfer_done;
  logic [31:0] protocol_errors;

  logic [3:0] stream_in_valid, stream_in_ready;
  logic [2047:0] stream_in_data;
  logic [255:0] stream_in_be;
  logic [63:0] stream_in_tag;
  logic [47:0] stream_in_tid;
  logic [3:0] stream_in_last;
  logic [15:0] stream_in_fmt;
  logic [3:0] stream_out_valid, stream_out_ready;
  logic [2047:0] stream_out_data;
  logic [255:0] stream_out_be;
  logic [63:0] stream_out_tag;
  logic [47:0] stream_out_tid;
  logic [3:0] stream_out_last;
  logic [15:0] stream_out_fmt;
  logic [3:0] source_valid, source_last;
  logic [2047:0] source_data;
  logic [255:0] source_be;
  logic [63:0] source_tag;
  logic [47:0] source_tid;
  logic [15:0] source_fmt;

  logic [511:0] expected_data;
  logic [63:0] expected_be;
  logic [15:0] expected_tag;
  logic [11:0] expected_tid;
  logic expected_route;

  generate
    for (genvar bank = 0; bank < 4; bank++) begin : g_bank
      HeteroScratchpadBankHarness u_bank (
        .clock(clk), .reset(~rst_n),
        .io_read_req_ready(core_rreq_ready[bank]),
        .io_read_req_valid(core_rreq_valid[bank]),
        .io_read_req_bits_addr(core_rreq_addr[bank*12 +: 12]),
        .io_read_req_bits_fromDMA(core_rreq_dma[bank]),
        .io_read_resp_ready(core_rresp_ready[bank]),
        .io_read_resp_valid(core_rresp_valid[bank]),
        .io_read_resp_bits_data(core_rresp_data[bank*128 +: 128]),
        .io_read_resp_bits_fromDMA(core_rresp_dma[bank]),
        .io_write_valid(core_w_valid[bank]),
        .io_write_ready(core_w_ready[bank]),
        .io_write_addr(core_w_addr[bank*12 +: 12]),
        .io_write_mask_0(core_w_mask[bank*16+0]),
        .io_write_mask_1(core_w_mask[bank*16+1]),
        .io_write_mask_2(core_w_mask[bank*16+2]),
        .io_write_mask_3(core_w_mask[bank*16+3]),
        .io_write_mask_4(core_w_mask[bank*16+4]),
        .io_write_mask_5(core_w_mask[bank*16+5]),
        .io_write_mask_6(core_w_mask[bank*16+6]),
        .io_write_mask_7(core_w_mask[bank*16+7]),
        .io_write_mask_8(core_w_mask[bank*16+8]),
        .io_write_mask_9(core_w_mask[bank*16+9]),
        .io_write_mask_10(core_w_mask[bank*16+10]),
        .io_write_mask_11(core_w_mask[bank*16+11]),
        .io_write_mask_12(core_w_mask[bank*16+12]),
        .io_write_mask_13(core_w_mask[bank*16+13]),
        .io_write_mask_14(core_w_mask[bank*16+14]),
        .io_write_mask_15(core_w_mask[bank*16+15]),
        .io_write_data(core_w_data[bank*128 +: 128]),
        .io_ext_mem_read_req_ready(ext_rreq_ready[bank]),
        .io_ext_mem_read_req_valid(ext_rreq_valid[bank]),
        .io_ext_mem_read_req_bits(ext_rreq_addr[bank*12 +: 12]),
        .io_ext_mem_read_resp_ready(ext_rresp_ready[bank]),
        .io_ext_mem_read_resp_valid(ext_rresp_valid[bank]),
        .io_ext_mem_read_resp_bits(ext_rresp_data[bank*128 +: 128]),
        .io_ext_mem_write_req_ready(ext_w_ready[bank]),
        .io_ext_mem_write_req_valid(ext_w_valid[bank]),
        .io_ext_mem_write_req_bits_addr(ext_w_addr[bank*12 +: 12]),
        .io_ext_mem_write_req_bits_data(ext_w_data[bank*128 +: 128]),
        .io_ext_mem_write_req_bits_mask(ext_w_mask[bank*16 +: 16])
      );
    end
  endgenerate

  gemmini_spad_tensor_gateway gateway (
    .clk_i(clk), .rst_ni(rst_n),
    .cfg_valid_i(cfg_valid), .cfg_ready_o(cfg_ready),
    .cfg_direction_i(cfg_dir), .cfg_route_i(cfg_route),
    .cfg_last_addr_i(cfg_last), .cfg_tag_i(cfg_tag),
    .cfg_tensor_id_i(cfg_tid), .cfg_format_i(cfg_fmt),
    .spad_write_valid_i(ext_w_valid), .spad_write_ready_o(ext_w_ready),
    .spad_write_addr_i(ext_w_addr), .spad_write_data_i(ext_w_data),
    .spad_write_mask_i(ext_w_mask),
    .spad_read_req_valid_i(ext_rreq_valid),
    .spad_read_req_ready_o(ext_rreq_ready),
    .spad_read_req_addr_i(ext_rreq_addr),
    .spad_read_resp_valid_o(ext_rresp_valid),
    .spad_read_resp_ready_i(ext_rresp_ready),
    .spad_read_resp_data_o(ext_rresp_data),
    .tx_valid_o(tx_valid), .tx_ready_i(tx_ready), .tx_route_o(tx_route),
    .tx_data_o(tx_data), .tx_be_o(tx_be), .tx_tag_o(tx_tag),
    .tx_tensor_id_o(tx_tid), .tx_last_o(tx_last), .tx_format_o(tx_fmt),
    .rx_valid_i(rx_valid), .rx_ready_o(rx_ready), .rx_route_i(rx_route),
    .rx_data_i(rx_data), .rx_be_i(rx_be), .rx_tag_i(rx_tag),
    .rx_tensor_id_i(rx_tid), .rx_last_i(rx_last), .rx_format_i(rx_fmt),
    .transfer_done_o(transfer_done),
    .protocol_error_count_o(protocol_errors)
  );

  matrix_direct_streams streams (
    .clk_i(clk), .rst_ni(rst_n),
    .in_valid_i(stream_in_valid), .in_ready_o(stream_in_ready),
    .in_data_i(stream_in_data), .in_be_i(stream_in_be),
    .in_tag_i(stream_in_tag), .in_tensor_id_i(stream_in_tid),
    .in_last_i(stream_in_last), .in_format_i(stream_in_fmt),
    .out_valid_o(stream_out_valid), .out_ready_i(stream_out_ready),
    .out_data_o(stream_out_data), .out_be_o(stream_out_be),
    .out_tag_o(stream_out_tag), .out_tensor_id_o(stream_out_tid),
    .out_last_o(stream_out_last), .out_format_o(stream_out_fmt)
  );

  always_comb begin
    stream_in_valid = source_valid;
    stream_in_data = source_data;
    stream_in_be = source_be;
    stream_in_tag = source_tag;
    stream_in_tid = source_tid;
    stream_in_last = source_last;
    stream_in_fmt = source_fmt;
    stream_out_ready = 0;

    stream_in_valid[tx_route ? 2 : 0] = tx_valid;
    stream_in_data[(tx_route ? 2 : 0)*512 +: 512] = tx_data;
    stream_in_be[(tx_route ? 2 : 0)*64 +: 64] = tx_be;
    stream_in_tag[(tx_route ? 2 : 0)*16 +: 16] = tx_tag;
    stream_in_tid[(tx_route ? 2 : 0)*12 +: 12] = tx_tid;
    stream_in_last[tx_route ? 2 : 0] = tx_last;
    stream_in_fmt[(tx_route ? 2 : 0)*4 +: 4] = tx_fmt;
    tx_ready = stream_in_ready[tx_route ? 2 : 0];

    rx_valid = stream_out_valid[cfg_route ? 3 : 1];
    rx_data = stream_out_data[(cfg_route ? 3 : 1)*512 +: 512];
    rx_be = stream_out_be[(cfg_route ? 3 : 1)*64 +: 64];
    rx_tag = stream_out_tag[(cfg_route ? 3 : 1)*16 +: 16];
    rx_tid = stream_out_tid[(cfg_route ? 3 : 1)*12 +: 12];
    rx_last = stream_out_last[cfg_route ? 3 : 1];
    rx_fmt = stream_out_fmt[(cfg_route ? 3 : 1)*4 +: 4];
    rx_route = cfg_route;
    stream_out_ready[cfg_route ? 3 : 1] = rx_ready;

    stream_out_ready[0] = (cycles % 4) != 1;
    stream_out_ready[2] = (cycles % 5) != 2;
  end

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      completed <= 0;
      tx_seen <= 0;
    end else begin
      cycles <= cycles + 1;
      if (transfer_done)
        completed <= completed + 1;
      if ((stream_out_valid[0] && stream_out_ready[0]) ||
          (stream_out_valid[2] && stream_out_ready[2])) begin
        int channel;
        channel = stream_out_valid[2] ? 2 : 0;
        if (channel != (expected_route ? 2 : 0) ||
            stream_out_data[channel*512 +: 512] !== expected_data ||
            stream_out_be[channel*64 +: 64] !== expected_be ||
            stream_out_tag[channel*16 +: 16] !== expected_tag ||
            stream_out_tid[channel*12 +: 12] !== expected_tid ||
            !stream_out_last[channel])
          $fatal(1, "upstream-bank TX stream mismatch");
        tx_seen <= tx_seen + 1;
      end
    end
  end

  task automatic configure(input logic direction, input logic route,
                           input logic [11:0] address,
                           input logic [15:0] id);
    begin
      @(negedge clk);
      cfg_dir = direction;
      cfg_route = route;
      cfg_last = address;
      cfg_tag = id;
      cfg_tid = id[11:0];
      cfg_fmt = 1;
      cfg_valid = 1;
      do @(posedge clk); while (!cfg_ready);
      @(negedge clk);
      cfg_valid = 0;
    end
  endtask

  task automatic write_group(input integer id);
    logic [11:0] address;
    logic [3:0] pending, offered, accepted;
    integer prior, tx_prior;
    begin
      address = 12'(id);
      prior = completed;
      tx_prior = tx_seen;
      configure(0, id[0], address, 16'(id));
      expected_tag = 16'(id);
      expected_tid = 12'(id);
      expected_route = id[0];
      expected_be = '1;
      for (int bank = 0; bank < 4; bank++) begin
        core_w_addr[bank*12 +: 12] = address;
        core_w_data[bank*128 +: 128] = {96'(id), 24'(bank), 8'h5a};
        core_w_mask[bank*16 +: 16] = '1;
      end
      expected_data = core_w_data;
      pending = 4'hf;
      while (pending != 0) begin
        @(negedge clk);
        offered = 4'($urandom) & pending;
        if (offered == 0)
          offered = pending & (~pending + 1'b1);
        core_w_valid = offered;
        #1 accepted = core_w_valid & core_w_ready;
        @(posedge clk);
        pending = pending & ~accepted;
      end
      @(negedge clk);
      core_w_valid = 0;
      wait(completed == prior + 1);
      wait(tx_seen == tx_prior + 1);
    end
  endtask

  task automatic read_group(input integer id);
    logic [11:0] address;
    logic [3:0] pending, offered, accepted, response_seen, response_fire;
    logic [3:0] expected_dma;
    integer prior, source_channel;
    begin
      address = 12'(id);
      prior = completed;
      configure(1, id[0], address, 16'(id));
      expected_tag = 16'(id);
      expected_tid = 12'(id);
      expected_be = '1;
      for (int bank = 0; bank < 4; bank++) begin
        core_rreq_addr[bank*12 +: 12] = address;
        core_rreq_dma[bank] = ((id + bank) & 1) != 0;
        expected_dma[bank] = ((id + bank) & 1) != 0;
        expected_data[bank*128 +: 128] = {96'(id), 24'(bank), 8'ha5};
      end
      pending = 4'hf;
      while (pending != 0) begin
        @(negedge clk);
        offered = 4'($urandom) & pending;
        if (offered == 0)
          offered = pending & (~pending + 1'b1);
        core_rreq_valid = offered;
        #1 accepted = core_rreq_valid & core_rreq_ready;
        @(posedge clk);
        pending = pending & ~accepted;
      end
      @(negedge clk);
      core_rreq_valid = 0;

      source_channel = id[0] ? 3 : 1;
      source_valid[source_channel] = 1;
      source_data[source_channel*512 +: 512] = expected_data;
      source_be[source_channel*64 +: 64] = '1;
      source_tag[source_channel*16 +: 16] = 16'(id);
      source_tid[source_channel*12 +: 12] = 12'(id);
      source_last[source_channel] = 1;
      source_fmt[source_channel*4 +: 4] = 1;
      do @(posedge clk); while (!stream_in_ready[source_channel]);
      @(negedge clk);
      source_valid[source_channel] = 0;

      response_seen = 0;
      while (response_seen != 4'hf) begin
        core_rresp_ready = 4'($urandom);
        #1 response_fire = core_rresp_valid & core_rresp_ready;
        for (int bank = 0; bank < 4; bank++) begin
          if (response_fire[bank]) begin
            if (core_rresp_data[bank*128 +: 128] !==
                  expected_data[bank*128 +: 128] ||
                core_rresp_dma[bank] !== expected_dma[bank])
              $fatal(1, "upstream-bank read response mismatch");
          end
        end
        @(posedge clk);
        response_seen = response_seen | response_fire;
        @(negedge clk);
      end
      core_rresp_ready = 0;
      wait(completed == prior + 1);
    end
  endtask

  initial begin
    clk = 0;
    rst_n = 0;
    cfg_valid = 0;
    cfg_dir = 0;
    cfg_route = 0;
    cfg_last = 0;
    cfg_tag = 0;
    cfg_tid = 0;
    cfg_fmt = 0;
    core_w_valid = 0;
    core_w_addr = 0;
    core_w_data = 0;
    core_w_mask = 0;
    core_rreq_valid = 0;
    core_rreq_addr = 0;
    core_rreq_dma = 0;
    core_rresp_ready = 0;
    source_valid = 0;
    source_data = 0;
    source_be = 0;
    source_tag = 0;
    source_tid = 0;
    source_last = 0;
    source_fmt = 0;
    seed = 32'h59a31c7d;
    void'($urandom(seed));
    repeat (3) @(posedge clk);
    rst_n = 1;
    for (int transaction = 0; transaction < TARGET/2; transaction++)
      write_group(transaction);
    for (int transaction = 0; transaction < TARGET/2; transaction++)
      read_group(transaction);
    if (completed != TARGET || tx_seen != TARGET/2 || protocol_errors != 0)
      $fatal(1, "pinned upstream integration accounting");
    $display("GEMMINI_PINNED_SPAD_GATEWAY_PASS transfers=%0d tx=%0d read_responses=%0d",
             completed, tx_seen, 4*(TARGET/2));
    $finish;
  end

  initial begin
    repeat (TARGET*100 + 10000) @(posedge clk);
    $display("TIMEOUT_DIAG completed=%0d tx_seen=%0d cfg_ready=%b active=%b dir=%b",
             completed, tx_seen, cfg_ready, gateway.active_q, gateway.direction_q);
    $display("TIMEOUT_DIAG core_w v=%b r=%b ext_w v=%b r=%b wall=%b",
             core_w_valid, core_w_ready, ext_w_valid, ext_w_ready, gateway.wall);
    $display("TIMEOUT_DIAG core_rr v=%b r=%b ext_rr v=%b r=%b rall=%b",
             core_rreq_valid, core_rreq_ready, ext_rreq_valid, ext_rreq_ready,
             gateway.rall);
    $display("TIMEOUT_DIAG source_v=%b stream_in_r=%b rx_vr=%b%b core_resp_vr=%b%b",
             source_valid, stream_in_ready, rx_valid, rx_ready,
             core_rresp_valid, core_rresp_ready);
    $fatal(1, "timeout");
  end
endmodule
