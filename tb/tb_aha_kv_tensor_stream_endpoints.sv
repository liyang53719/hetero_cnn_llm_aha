`timescale 1ns/1ps
module tb_aha_kv_tensor_stream_endpoints;
  parameter integer TARGET = 100000;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  always #5 clk = ~clk;
  integer cycles, completed, aha_seen, kv_seen;
  integer aha_source_accepts, kv_source_accepts;
  integer aha_completions, kv_read_completions;

  logic [3:0] source_valid, source_last;
  logic [2047:0] source_data;
  logic [255:0] source_be;
  logic [63:0] source_tag;
  logic [47:0] source_tid;
  logic [15:0] source_fmt;
  logic [3:0] stream_in_valid, stream_in_ready, stream_in_last;
  logic [2047:0] stream_in_data;
  logic [255:0] stream_in_be;
  logic [63:0] stream_in_tag;
  logic [47:0] stream_in_tid;
  logic [15:0] stream_in_fmt;
  logic [3:0] stream_out_valid, stream_out_ready, stream_out_last;
  logic [2047:0] stream_out_data;
  logic [255:0] stream_out_be;
  logic [63:0] stream_out_tag;
  logic [47:0] stream_out_tid;
  logic [15:0] stream_out_fmt;

  logic aha_cfg_valid, aha_cfg_ready, aha_run_done;
  logic [17:0] aha_input_base, aha_output_base;
  logic [15:0] aha_input_beats, aha_output_beats, aha_output_tag;
  logic [11:0] aha_output_tid;
  logic [3:0] aha_output_fmt;
  logic [63:0] aha_output_last_be;
  logic aha_in_ready, aha_out_valid, aha_out_ready, aha_out_last;
  logic [511:0] aha_out_data;
  logic [63:0] aha_out_be;
  logic [15:0] aha_out_tag;
  logic [11:0] aha_out_tid;
  logic [3:0] aha_out_fmt;
  logic proc_wr_en, proc_rd_en, proc_rd_valid;
  logic [17:0] proc_wr_addr, proc_rd_addr;
  logic [63:0] proc_wr_data, proc_rd_data;
  logic [7:0] proc_wr_strb;
  logic aha_eos, aha_done;
  logic [31:0] aha_errors;

  logic kv_cfg_valid, kv_cfg_ready, kv_cfg_dir;
  logic [18:0] kv_cfg_base;
  logic [15:0] kv_cfg_beats, kv_cfg_tag;
  logic [11:0] kv_cfg_tid;
  logic [3:0] kv_cfg_fmt;
  logic [63:0] kv_cfg_last_be;
  logic kv_in_ready, kv_out_valid, kv_out_ready, kv_out_last;
  logic [511:0] kv_out_data;
  logic [63:0] kv_out_be;
  logic [15:0] kv_out_tag;
  logic [11:0] kv_out_tid;
  logic [3:0] kv_out_fmt;
  logic kv_mem_wvalid, kv_mem_wready, kv_mem_rvalid, kv_mem_rready;
  logic [18:0] kv_mem_waddr, kv_mem_raddr;
  logic [511:0] kv_mem_wdata;
  logic [63:0] kv_mem_wbe;
  logic kv_mem_rsp_valid, kv_mem_rsp_ready, kv_mem_rsp_error;
  logic [511:0] kv_mem_rsp_data;
  logic kv_done;
  logic [31:0] kv_errors;

  logic [63:0] aha_mem [0:32767];
  logic [2:0] aha_rd_pipe_valid;
  logic [17:0] aha_rd_pipe_addr [0:2];
  logic [511:0] kv_mem [0:8191];
  logic kv_model_pending;
  logic [18:0] kv_model_addr;

  logic expect_aha, expect_kv;
  logic [511:0] expected_aha_data, expected_kv_data;
  logic [63:0] expected_aha_be, expected_kv_be;
  logic [15:0] expected_aha_tag, expected_kv_tag;
  logic [11:0] expected_aha_tid, expected_kv_tid;
  logic [3:0] expected_aha_fmt, expected_kv_fmt;

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

  aha_tensor_stream_endpoint aha (
    .clk_i(clk), .rst_ni(rst_n),
    .cfg_valid_i(aha_cfg_valid), .cfg_ready_o(aha_cfg_ready),
    .cfg_input_base_i(aha_input_base), .cfg_output_base_i(aha_output_base),
    .cfg_input_beats_i(aha_input_beats), .cfg_output_beats_i(aha_output_beats),
    .cfg_output_tag_i(aha_output_tag), .cfg_output_tensor_id_i(aha_output_tid),
    .cfg_output_format_i(aha_output_fmt), .cfg_output_last_be_i(aha_output_last_be),
    .run_done_i(aha_run_done),
    .stream_in_valid_i(stream_out_valid[0]), .stream_in_ready_o(aha_in_ready),
    .stream_in_data_i(stream_out_data[0*512 +: 512]),
    .stream_in_be_i(stream_out_be[0*64 +: 64]),
    .stream_in_tag_i(stream_out_tag[0*16 +: 16]),
    .stream_in_tensor_id_i(stream_out_tid[0*12 +: 12]),
    .stream_in_last_i(stream_out_last[0]), .stream_in_format_i(stream_out_fmt[0*4 +: 4]),
    .stream_out_valid_o(aha_out_valid), .stream_out_ready_i(aha_out_ready),
    .stream_out_data_o(aha_out_data), .stream_out_be_o(aha_out_be),
    .stream_out_tag_o(aha_out_tag), .stream_out_tensor_id_o(aha_out_tid),
    .stream_out_last_o(aha_out_last), .stream_out_format_o(aha_out_fmt),
    .proc_packet_wr_en_o(proc_wr_en), .proc_packet_wr_addr_o(proc_wr_addr),
    .proc_packet_wr_data_o(proc_wr_data), .proc_packet_wr_strb_o(proc_wr_strb),
    .proc_packet_rd_en_o(proc_rd_en), .proc_packet_rd_addr_o(proc_rd_addr),
    .proc_packet_rd_data_i(proc_rd_data), .proc_packet_rd_data_valid_i(proc_rd_valid),
    .native_eos_o(aha_eos), .transfer_done_o(aha_done),
    .protocol_error_count_o(aha_errors)
  );

  kv_tensor_stream_endpoint kv (
    .clk_i(clk), .rst_ni(rst_n),
    .cfg_valid_i(kv_cfg_valid), .cfg_ready_o(kv_cfg_ready),
    .cfg_direction_i(kv_cfg_dir), .cfg_base_addr_i(kv_cfg_base),
    .cfg_beats_i(kv_cfg_beats), .cfg_tag_i(kv_cfg_tag),
    .cfg_tensor_id_i(kv_cfg_tid), .cfg_format_i(kv_cfg_fmt),
    .cfg_last_be_i(kv_cfg_last_be),
    .stream_in_valid_i(stream_out_valid[2]), .stream_in_ready_o(kv_in_ready),
    .stream_in_data_i(stream_out_data[2*512 +: 512]),
    .stream_in_be_i(stream_out_be[2*64 +: 64]),
    .stream_in_tag_i(stream_out_tag[2*16 +: 16]),
    .stream_in_tensor_id_i(stream_out_tid[2*12 +: 12]),
    .stream_in_last_i(stream_out_last[2]),
    .stream_in_format_i(stream_out_fmt[2*4 +: 4]),
    .stream_out_valid_o(kv_out_valid), .stream_out_ready_i(kv_out_ready),
    .stream_out_data_o(kv_out_data), .stream_out_be_o(kv_out_be),
    .stream_out_tag_o(kv_out_tag), .stream_out_tensor_id_o(kv_out_tid),
    .stream_out_last_o(kv_out_last), .stream_out_format_o(kv_out_fmt),
    .mem_write_valid_o(kv_mem_wvalid), .mem_write_ready_i(kv_mem_wready),
    .mem_write_addr_o(kv_mem_waddr), .mem_write_data_o(kv_mem_wdata),
    .mem_write_be_o(kv_mem_wbe), .mem_read_req_valid_o(kv_mem_rvalid),
    .mem_read_req_ready_i(kv_mem_rready), .mem_read_req_addr_o(kv_mem_raddr),
    .mem_read_rsp_valid_i(kv_mem_rsp_valid), .mem_read_rsp_ready_o(kv_mem_rsp_ready),
    .mem_read_rsp_data_i(kv_mem_rsp_data), .mem_read_rsp_error_i(kv_mem_rsp_error),
    .transfer_done_o(kv_done), .protocol_error_count_o(kv_errors)
  );

  always_comb begin
    stream_in_valid = source_valid;
    stream_in_data = source_data;
    stream_in_be = source_be;
    stream_in_tag = source_tag;
    stream_in_tid = source_tid;
    stream_in_last = source_last;
    stream_in_fmt = source_fmt;
    stream_in_valid[1] = aha_out_valid;
    stream_in_data[1*512 +: 512] = aha_out_data;
    stream_in_be[1*64 +: 64] = aha_out_be;
    stream_in_tag[1*16 +: 16] = aha_out_tag;
    stream_in_tid[1*12 +: 12] = aha_out_tid;
    stream_in_last[1] = aha_out_last;
    stream_in_fmt[1*4 +: 4] = aha_out_fmt;
    aha_out_ready = stream_in_ready[1];
    stream_in_valid[3] = kv_out_valid;
    stream_in_data[3*512 +: 512] = kv_out_data;
    stream_in_be[3*64 +: 64] = kv_out_be;
    stream_in_tag[3*16 +: 16] = kv_out_tag;
    stream_in_tid[3*12 +: 12] = kv_out_tid;
    stream_in_last[3] = kv_out_last;
    stream_in_fmt[3*4 +: 4] = kv_out_fmt;
    kv_out_ready = stream_in_ready[3];

    stream_out_ready = 0;
    stream_out_ready[0] = aha_in_ready;
    stream_out_ready[2] = kv_in_ready;
    stream_out_ready[1] = (cycles % 5) != 1;
    stream_out_ready[3] = (cycles % 7) != 2;
  end

  assign kv_mem_wready = (cycles % 4) != 1;
  assign kv_mem_rready = !kv_model_pending && (cycles % 3) != 1;
  assign kv_mem_rsp_valid = kv_model_pending;
  assign kv_mem_rsp_data = kv_mem[kv_model_addr[18:6]];
  assign kv_mem_rsp_error = 0;

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      completed <= 0;
      aha_seen <= 0;
      kv_seen <= 0;
      aha_source_accepts <= 0;
      kv_source_accepts <= 0;
      aha_completions <= 0;
      kv_read_completions <= 0;
      aha_run_done <= 0;
      aha_rd_pipe_valid <= 0;
      proc_rd_valid <= 0;
      proc_rd_data <= 0;
      kv_model_pending <= 0;
      kv_model_addr <= 0;
    end else begin
      cycles <= cycles + 1;
      aha_run_done <= aha_eos;
      proc_rd_valid <= aha_rd_pipe_valid[2];
      if (aha_rd_pipe_valid[2])
        proc_rd_data <= aha_mem[aha_rd_pipe_addr[2][17:3]];
      aha_rd_pipe_valid[2] <= aha_rd_pipe_valid[1];
      aha_rd_pipe_valid[1] <= aha_rd_pipe_valid[0];
      aha_rd_pipe_valid[0] <= proc_rd_en;
      aha_rd_pipe_addr[2] <= aha_rd_pipe_addr[1];
      aha_rd_pipe_addr[1] <= aha_rd_pipe_addr[0];
      aha_rd_pipe_addr[0] <= proc_rd_addr;

      if (proc_wr_en) begin
        if (proc_wr_addr[2:0] != 0)
          $fatal(1, "unaligned AHA proc write");
        for (int byte_index = 0; byte_index < 8; byte_index++)
          if (proc_wr_strb[byte_index])
            aha_mem[proc_wr_addr[17:3]][byte_index*8 +: 8] <=
              proc_wr_data[byte_index*8 +: 8];
      end
      if (aha_eos) begin
        for (int word = 0; word < 8; word++)
          aha_mem[32'(aha_output_base[17:3]) + word] <=
            aha_mem[32'(aha_input_base[17:3]) + word];
      end

      if (kv_mem_wvalid && kv_mem_wready) begin
        if (kv_mem_waddr[5:0] != 0)
          $fatal(1, "unaligned KV staging write");
        for (int byte_index = 0; byte_index < 64; byte_index++)
          if (kv_mem_wbe[byte_index])
            kv_mem[kv_mem_waddr[18:6]][byte_index*8 +: 8] <=
              kv_mem_wdata[byte_index*8 +: 8];
      end
      if (kv_mem_rvalid && kv_mem_rready) begin
        if (kv_mem_raddr[5:0] != 0)
          $fatal(1, "unaligned KV staging read");
        kv_model_pending <= 1;
        kv_model_addr <= kv_mem_raddr;
      end
      if (kv_mem_rsp_valid && kv_mem_rsp_ready)
        begin
          if (kv_model_addr[5:0] != 0)
            $fatal(1, "unaligned KV staging response");
          kv_model_pending <= 0;
        end

      if (aha_out_valid && aha_out_ready)
        aha_source_accepts <= aha_source_accepts + 1;
      if (kv_out_valid && kv_out_ready)
        kv_source_accepts <= kv_source_accepts + 1;

      if (aha_done) begin
        completed <= completed + 1;
        if (!expect_aha || aha_source_accepts <= aha_completions)
          $fatal(1, "AHA completion ordering");
        aha_completions <= aha_completions + 1;
      end
      if (kv_done) begin
        completed <= completed + 1;
        if (kv_cfg_dir) begin
          if (!expect_kv || kv_source_accepts <= kv_read_completions)
            $fatal(1, "KV completion ordering");
          kv_read_completions <= kv_read_completions + 1;
        end
      end

      if (stream_out_valid[1] && stream_out_ready[1]) begin
        if (!expect_aha || stream_out_data[1*512 +: 512] !== expected_aha_data ||
            stream_out_be[1*64 +: 64] !== expected_aha_be ||
            stream_out_tag[1*16 +: 16] !== expected_aha_tag ||
            stream_out_tid[1*12 +: 12] !== expected_aha_tid ||
            stream_out_fmt[1*4 +: 4] !== expected_aha_fmt || !stream_out_last[1])
          $fatal(1, "AHA endpoint output mismatch");
        aha_seen <= aha_seen + 1;
        expect_aha <= 0;
      end
      if (stream_out_valid[3] && stream_out_ready[3]) begin
        if (!expect_kv || stream_out_data[3*512 +: 512] !== expected_kv_data ||
            stream_out_be[3*64 +: 64] !== expected_kv_be ||
            stream_out_tag[3*16 +: 16] !== expected_kv_tag ||
            stream_out_tid[3*12 +: 12] !== expected_kv_tid ||
            stream_out_fmt[3*4 +: 4] !== expected_kv_fmt || !stream_out_last[3]) begin
          $display("KV_MISMATCH data_exp=%h data_got=%h", expected_kv_data,
                   stream_out_data[3*512 +: 512]);
          $display("KV_MISMATCH be=%h/%h tag=%h/%h tid=%h/%h fmt=%h/%h last=%b expect=%b",
                   expected_kv_be, stream_out_be[3*64 +: 64],
                   expected_kv_tag, stream_out_tag[3*16 +: 16],
                   expected_kv_tid, stream_out_tid[3*12 +: 12],
                   expected_kv_fmt, stream_out_fmt[3*4 +: 4],
                   stream_out_last[3], expect_kv);
          $fatal(1, "KV endpoint output mismatch");
        end
        kv_seen <= kv_seen + 1;
        expect_kv <= 0;
      end
    end
  end

  task automatic send_source(input integer channel, input logic [511:0] data,
                             input logic [63:0] be, input logic [15:0] tag,
                             input logic [11:0] tid, input logic [3:0] format);
    begin
      @(negedge clk);
      source_valid[channel] = 1;
      source_data[channel*512 +: 512] = data;
      source_be[channel*64 +: 64] = be;
      source_tag[channel*16 +: 16] = tag;
      source_tid[channel*12 +: 12] = tid;
      source_last[channel] = 1;
      source_fmt[channel*4 +: 4] = format;
      do @(posedge clk); while (!stream_in_ready[channel]);
      @(negedge clk);
      source_valid[channel] = 0;
    end
  endtask

  task automatic run_aha(input integer id);
    logic [511:0] data;
    integer prior, seen_prior;
    begin
      prior = completed;
      seen_prior = aha_seen;
      aha_input_base = 18'((id % 1024) * 64);
      aha_output_base = 18'h20000 + 18'((id % 1024) * 64);
      data = {8{64'(id) ^ 64'h91e1_0da5_c79b_3f27}};
      expected_aha_data = data;
      expected_aha_be = '1;
      expected_aha_tag = 16'(id);
      expected_aha_tid = 12'(id);
      expected_aha_fmt = 1;
      expect_aha = 1;
      aha_input_beats = 1;
      aha_output_beats = 1;
      aha_output_tag = 16'(id);
      aha_output_tid = 12'(id);
      aha_output_fmt = 1;
      aha_output_last_be = '1;
      @(negedge clk);
      aha_cfg_valid = 1;
      do @(posedge clk); while (!aha_cfg_ready);
      @(negedge clk);
      aha_cfg_valid = 0;
      send_source(0, data, 64'hffff_ffff_ffff_ffff, 16'(id), 12'(id), 1);
      wait(completed == prior + 1);
      wait(aha_seen == seen_prior + 1);
    end
  endtask

  task automatic run_kv_write(input integer id);
    logic [511:0] data;
    logic [63:0] be;
    integer prior;
    begin
      prior = completed;
      kv_cfg_base = 19'((id % 8192) * 64);
      data = {8{64'(id) ^ 64'h4b56_7374_6167_696e}};
      be = id[0] ? 64'hffff_0000_ffff_0000 : 64'hffff_ffff_ffff_ffff;
      kv_cfg_dir = 0;
      kv_cfg_beats = 1;
      kv_cfg_tag = 16'(id);
      kv_cfg_tid = 12'(id);
      kv_cfg_fmt = 2;
      kv_cfg_last_be = be;
      expect_kv = 0;
      @(negedge clk);
      kv_cfg_valid = 1;
      do @(posedge clk); while (!kv_cfg_ready);
      @(negedge clk);
      kv_cfg_valid = 0;
      send_source(2, data, be, 16'(id), 12'(id), 2);
      wait(completed == prior + 1);
    end
  endtask

  task automatic run_kv_read(input integer id);
    integer prior, seen_prior;
    begin
      prior = completed;
      seen_prior = kv_seen;
      kv_cfg_base = 19'((id % 8192) * 64);
      expected_kv_data = kv_mem[kv_cfg_base[18:6]];
      expected_kv_be = id[0] ? 64'hffff_0000_ffff_0000 : 64'hffff_ffff_ffff_ffff;
      expected_kv_tag = 16'(id);
      expected_kv_tid = 12'(id);
      expected_kv_fmt = 2;
      expect_kv = 1;
      kv_cfg_dir = 1;
      kv_cfg_beats = 1;
      kv_cfg_tag = 16'(id);
      kv_cfg_tid = 12'(id);
      kv_cfg_fmt = 2;
      kv_cfg_last_be = expected_kv_be;
      @(negedge clk);
      kv_cfg_valid = 1;
      do @(posedge clk); while (!kv_cfg_ready);
      @(negedge clk);
      kv_cfg_valid = 0;
      wait(completed == prior + 1);
      wait(kv_seen == seen_prior + 1);
    end
  endtask

  initial begin
    clk = 0;
    rst_n = 0;
    aha_cfg_valid = 0;
    aha_input_base = 0;
    aha_output_base = 0;
    aha_input_beats = 0;
    aha_output_beats = 0;
    aha_output_tag = 0;
    aha_output_tid = 0;
    aha_output_fmt = 0;
    aha_output_last_be = 0;
    kv_cfg_valid = 0;
    kv_cfg_dir = 0;
    kv_cfg_base = 0;
    kv_cfg_beats = 0;
    kv_cfg_tag = 0;
    kv_cfg_tid = 0;
    kv_cfg_fmt = 0;
    kv_cfg_last_be = 0;
    source_valid = 0;
    source_data = 0;
    source_be = 0;
    source_tag = 0;
    source_tid = 0;
    source_last = 0;
    source_fmt = 0;
    expect_aha = 0;
    expect_kv = 0;
    for (int index = 0; index < 32768; index++) aha_mem[index] = 0;
    for (int index = 0; index < 8192; index++) kv_mem[index] = 0;
    repeat (3) @(posedge clk);
    rst_n = 1;
    for (int transaction = 0; transaction < TARGET/2; transaction++)
      run_aha(transaction);
    for (int transaction = 0; transaction < TARGET/4; transaction++) begin
      run_kv_write(transaction);
      run_kv_read(transaction);
    end
    if (completed != TARGET || aha_errors != 0 || kv_errors != 0 ||
        aha_seen != TARGET/2 || kv_seen != TARGET/4)
      $fatal(1, "endpoint accounting");
    $display("AHA_KV_TENSOR_ENDPOINTS_100K_PASS transfers=%0d aha=%0d kv_reads=%0d",
             completed, aha_seen, kv_seen);
    $finish;
  end

  initial begin
    repeat (TARGET*80 + 10000) @(posedge clk);
    $fatal(1, "endpoint timeout completed=%0d aha=%0d kv=%0d", completed, aha_seen, kv_seen);
  end
endmodule
