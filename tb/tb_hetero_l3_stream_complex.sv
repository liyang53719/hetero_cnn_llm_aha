`timescale 1ns/1ps
module tb_hetero_l3_stream_complex;
  parameter integer TARGET = 100000;
  logic clk;
  /* verilator lint_off SYNCASYNCNET */
  logic rst_n;
  /* verilator lint_on SYNCASYNCNET */
  always #5 clk = ~clk;
  integer cycles, completed, matrix_done_count, aha_done_count, kv_done_count;
  integer seed;

  logic m_cfg_valid, m_cfg_ready, m_cfg_dir, m_cfg_route;
  logic [11:0] m_cfg_last, m_cfg_tid;
  logic [15:0] m_cfg_tag;
  logic [3:0] m_cfg_fmt;
  logic [3:0] m_wvalid, m_wready, m_rrvalid, m_rrready, m_rvalid, m_rready;
  logic [47:0] m_waddr, m_raddr;
  logic [511:0] m_wdata, m_resp_data;
  logic [63:0] m_wmask;
  logic m_done;
  logic [31:0] m_errors;

  logic aha_cfg_valid, aha_cfg_ready, aha_run_done;
  logic [17:0] aha_in_base, aha_out_base;
  logic [15:0] aha_in_beats, aha_out_beats, aha_out_tag;
  logic [11:0] aha_out_tid;
  logic [3:0] aha_out_fmt;
  logic [63:0] aha_last_be;
  logic proc_wr_en, proc_rd_en, proc_rd_valid, aha_eos, aha_done;
  logic [17:0] proc_wr_addr, proc_rd_addr;
  logic [63:0] proc_wr_data, proc_rd_data;
  logic [7:0] proc_wr_strb;
  logic [31:0] aha_errors;

  logic kv_cfg_valid, kv_cfg_ready, kv_cfg_dir;
  logic [18:0] kv_cfg_base;
  logic [15:0] kv_cfg_beats, kv_cfg_tag;
  logic [11:0] kv_cfg_tid;
  logic [3:0] kv_cfg_fmt;
  logic [63:0] kv_last_be;
  logic kv_wvalid, kv_wready, kv_rvalid, kv_rready;
  logic [18:0] kv_waddr, kv_raddr;
  logic [511:0] kv_wdata;
  logic [63:0] kv_wbe;
  logic kv_rsp_valid, kv_rsp_ready, kv_rsp_error, kv_done;
  logic [511:0] kv_rsp_data;
  logic [31:0] kv_errors;

  logic [63:0] aha_mem [0:32767];
  logic [2:0] aha_rd_valid_pipe;
  logic [17:0] aha_rd_addr_pipe [0:2];
  logic [511:0] kv_mem [0:8191];
  logic kv_pending;
  logic [18:0] kv_pending_addr;

  hetero_l3_stream_complex dut (
    .clk_i(clk), .rst_ni(rst_n),
    .matrix_cfg_valid_i(m_cfg_valid), .matrix_cfg_ready_o(m_cfg_ready),
    .matrix_cfg_direction_i(m_cfg_dir), .matrix_cfg_route_i(m_cfg_route),
    .matrix_cfg_last_addr_i(m_cfg_last), .matrix_cfg_tag_i(m_cfg_tag),
    .matrix_cfg_tensor_id_i(m_cfg_tid), .matrix_cfg_format_i(m_cfg_fmt),
    .matrix_spad_write_valid_i(m_wvalid), .matrix_spad_write_ready_o(m_wready),
    .matrix_spad_write_addr_i(m_waddr), .matrix_spad_write_data_i(m_wdata),
    .matrix_spad_write_mask_i(m_wmask),
    .matrix_spad_read_req_valid_i(m_rrvalid),
    .matrix_spad_read_req_ready_o(m_rrready),
    .matrix_spad_read_req_addr_i(m_raddr),
    .matrix_spad_read_resp_valid_o(m_rvalid),
    .matrix_spad_read_resp_ready_i(m_rready),
    .matrix_spad_read_resp_data_o(m_resp_data),
    .matrix_transfer_done_o(m_done),
    .matrix_protocol_error_count_o(m_errors),
    .aha_cfg_valid_i(aha_cfg_valid), .aha_cfg_ready_o(aha_cfg_ready),
    .aha_cfg_input_base_i(aha_in_base), .aha_cfg_output_base_i(aha_out_base),
    .aha_cfg_input_beats_i(aha_in_beats), .aha_cfg_output_beats_i(aha_out_beats),
    .aha_cfg_output_tag_i(aha_out_tag), .aha_cfg_output_tensor_id_i(aha_out_tid),
    .aha_cfg_output_format_i(aha_out_fmt), .aha_cfg_output_last_be_i(aha_last_be),
    .aha_run_done_i(aha_run_done), .aha_proc_packet_wr_en_o(proc_wr_en),
    .aha_proc_packet_wr_addr_o(proc_wr_addr), .aha_proc_packet_wr_data_o(proc_wr_data),
    .aha_proc_packet_wr_strb_o(proc_wr_strb), .aha_proc_packet_rd_en_o(proc_rd_en),
    .aha_proc_packet_rd_addr_o(proc_rd_addr), .aha_proc_packet_rd_data_i(proc_rd_data),
    .aha_proc_packet_rd_data_valid_i(proc_rd_valid), .aha_native_eos_o(aha_eos),
    .aha_transfer_done_o(aha_done), .aha_protocol_error_count_o(aha_errors),
    .kv_cfg_valid_i(kv_cfg_valid), .kv_cfg_ready_o(kv_cfg_ready),
    .kv_cfg_direction_i(kv_cfg_dir), .kv_cfg_base_addr_i(kv_cfg_base),
    .kv_cfg_beats_i(kv_cfg_beats), .kv_cfg_tag_i(kv_cfg_tag),
    .kv_cfg_tensor_id_i(kv_cfg_tid), .kv_cfg_format_i(kv_cfg_fmt),
    .kv_cfg_last_be_i(kv_last_be), .kv_mem_write_valid_o(kv_wvalid),
    .kv_mem_write_ready_i(kv_wready), .kv_mem_write_addr_o(kv_waddr),
    .kv_mem_write_data_o(kv_wdata), .kv_mem_write_be_o(kv_wbe),
    .kv_mem_read_req_valid_o(kv_rvalid), .kv_mem_read_req_ready_i(kv_rready),
    .kv_mem_read_req_addr_o(kv_raddr), .kv_mem_read_rsp_valid_i(kv_rsp_valid),
    .kv_mem_read_rsp_ready_o(kv_rsp_ready), .kv_mem_read_rsp_data_i(kv_rsp_data),
    .kv_mem_read_rsp_error_i(kv_rsp_error), .kv_transfer_done_o(kv_done),
    .kv_protocol_error_count_o(kv_errors)
  );

  assign kv_wready = (cycles % 4) != 1;
  assign kv_rready = !kv_pending && (cycles % 5) != 2;
  assign kv_rsp_valid = kv_pending;
  assign kv_rsp_data = kv_mem[kv_pending_addr[18:6]];
  assign kv_rsp_error = 0;

  always @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0;
      completed <= 0;
      matrix_done_count <= 0;
      aha_done_count <= 0;
      kv_done_count <= 0;
      aha_run_done <= 0;
      aha_rd_valid_pipe <= 0;
      proc_rd_valid <= 0;
      proc_rd_data <= 0;
      kv_pending <= 0;
      kv_pending_addr <= 0;
    end else begin
      cycles <= cycles + 1;
      if (m_done) matrix_done_count <= matrix_done_count + 1;
      if (aha_done) aha_done_count <= aha_done_count + 1;
      if (kv_done) kv_done_count <= kv_done_count + 1;
      aha_run_done <= aha_eos;
      proc_rd_valid <= aha_rd_valid_pipe[2];
      if (aha_rd_valid_pipe[2])
        proc_rd_data <= aha_mem[aha_rd_addr_pipe[2][17:3]];
      aha_rd_valid_pipe[2] <= aha_rd_valid_pipe[1];
      aha_rd_valid_pipe[1] <= aha_rd_valid_pipe[0];
      aha_rd_valid_pipe[0] <= proc_rd_en;
      aha_rd_addr_pipe[2] <= aha_rd_addr_pipe[1];
      aha_rd_addr_pipe[1] <= aha_rd_addr_pipe[0];
      aha_rd_addr_pipe[0] <= proc_rd_addr;
      if (proc_wr_en) begin
        if (proc_wr_addr[2:0] != 0) $fatal(1, "AHA proc address alignment");
        for (int byte_index = 0; byte_index < 8; byte_index++)
          if (proc_wr_strb[byte_index])
            aha_mem[proc_wr_addr[17:3]][byte_index*8 +: 8] <=
              proc_wr_data[byte_index*8 +: 8];
      end
      if (aha_eos)
        for (int word = 0; word < 8; word++)
          aha_mem[32'(aha_out_base[17:3]) + word] <=
            aha_mem[32'(aha_in_base[17:3]) + word];

      if (kv_wvalid && kv_wready) begin
        if (kv_waddr[5:0] != 0) $fatal(1, "KV write alignment");
        for (int byte_index = 0; byte_index < 64; byte_index++)
          if (kv_wbe[byte_index])
            kv_mem[kv_waddr[18:6]][byte_index*8 +: 8] <=
              kv_wdata[byte_index*8 +: 8];
      end
      if (kv_rvalid && kv_rready) begin
        if (kv_raddr[5:0] != 0) $fatal(1, "KV read alignment");
        kv_pending <= 1;
        kv_pending_addr <= kv_raddr;
      end
      if (kv_rsp_valid && kv_rsp_ready) begin
        if (kv_pending_addr[5:0] != 0) $fatal(1, "KV response alignment");
        kv_pending <= 0;
      end
    end
  end

  task automatic configure_matrix(input logic direction, input logic route,
                                  input logic [11:0] address,
                                  input logic [15:0] tag,
                                  input logic [11:0] tensor,
                                  input logic [3:0] format);
    begin
      @(negedge clk);
      m_cfg_dir = direction; m_cfg_route = route; m_cfg_last = address;
      m_cfg_tag = tag; m_cfg_tid = tensor; m_cfg_fmt = format; m_cfg_valid = 1;
      do @(posedge clk); while (!m_cfg_ready);
      @(negedge clk); m_cfg_valid = 0;
    end
  endtask

  task automatic write_matrix_beat(input logic [11:0] address,
                                   input logic [511:0] data,
                                   input logic [63:0] mask);
    begin
      for (int bank = 0; bank < 4; bank++) begin
        m_waddr[bank*12 +: 12] = address;
        m_wdata[bank*128 +: 128] = data[bank*128 +: 128];
        m_wmask[bank*16 +: 16] = mask[bank*16 +: 16];
      end
      @(negedge clk); m_wvalid = '1;
      wait(&m_wready); @(posedge clk); @(negedge clk); m_wvalid = 0;
    end
  endtask

  task automatic read_matrix_beat(input logic [11:0] address,
                                  input logic [511:0] expected);
    logic [3:0] seen, fire;
    begin
      for (int bank = 0; bank < 4; bank++) m_raddr[bank*12 +: 12] = address;
      @(negedge clk); m_rrvalid = '1;
      wait(&m_rrready); @(posedge clk); @(negedge clk); m_rrvalid = 0;
      seen = 0;
      while (seen != 4'hf) begin
        m_rready = 4'($urandom);
        #1 fire = m_rvalid & m_rready;
        for (int bank = 0; bank < 4; bank++)
          if (fire[bank] && m_resp_data[bank*128 +: 128] !== expected[bank*128 +: 128])
            $fatal(1, "Matrix return mismatch bank=%0d", bank);
        @(posedge clk); seen = seen | fire; @(negedge clk);
      end
      m_rready = 0;
    end
  endtask

  task automatic run_aha(input integer id);
    logic [511:0] data;
    logic [11:0] address;
    integer matrix_prior, aha_prior;
    begin
      data = {8{64'(id) ^ 64'h6a09_e667_f3bc_c909}};
      address = 12'(id);
      matrix_prior = matrix_done_count; aha_prior = aha_done_count;
      aha_in_base = 18'((id % 1024) * 64);
      aha_out_base = 18'h20000 + 18'((id % 1024) * 64);
      aha_in_beats = 1; aha_out_beats = 1; aha_out_tag = 16'(id);
      aha_out_tid = 12'(id); aha_out_fmt = 1; aha_last_be = '1;
      @(negedge clk); aha_cfg_valid = 1;
      do @(posedge clk); while (!aha_cfg_ready);
      @(negedge clk); aha_cfg_valid = 0;
      configure_matrix(0, 0, address, 16'(id), 12'(id), 1);
      write_matrix_beat(address, data, '1);
      wait(matrix_done_count == matrix_prior + 1);
      wait(aha_eos);
      configure_matrix(1, 0, address, 16'(id), 12'(id), 1);
      read_matrix_beat(address, data);
      wait(matrix_done_count == matrix_prior + 2);
      wait(aha_done_count == aha_prior + 1);
      completed = completed + 1;
    end
  endtask

  task automatic run_kv_pair(input integer id);
    logic [511:0] data, expected;
    logic [63:0] mask;
    logic [11:0] address;
    integer matrix_prior, kv_prior;
    begin
      data = {8{64'(id) ^ 64'hbb67_ae85_84ca_a73b}};
      mask = id[0] ? 64'hffff_0000_ffff_0000 : 64'hffff_ffff_ffff_ffff;
      address = 12'(id); matrix_prior = matrix_done_count; kv_prior = kv_done_count;
      kv_cfg_dir = 0; kv_cfg_base = 19'((id % 8192) * 64); kv_cfg_beats = 1;
      kv_cfg_tag = 16'(id); kv_cfg_tid = 12'(id); kv_cfg_fmt = 2; kv_last_be = mask;
      @(negedge clk); kv_cfg_valid = 1;
      do @(posedge clk); while (!kv_cfg_ready);
      @(negedge clk); kv_cfg_valid = 0;
      configure_matrix(0, 1, address, 16'(id), 12'(id), 2);
      write_matrix_beat(address, data, mask);
      wait(matrix_done_count == matrix_prior + 1);
      wait(kv_done_count == kv_prior + 1);

      expected = kv_mem[kv_cfg_base[18:6]];
      kv_cfg_dir = 1; kv_last_be = '1;
      @(negedge clk); kv_cfg_valid = 1;
      do @(posedge clk); while (!kv_cfg_ready);
      @(negedge clk); kv_cfg_valid = 0;
      configure_matrix(1, 1, address, 16'(id), 12'(id), 2);
      read_matrix_beat(address, expected);
      wait(matrix_done_count == matrix_prior + 2);
      wait(kv_done_count == kv_prior + 2);
      completed = completed + 2;
    end
  endtask

  initial begin
    clk = 0; rst_n = 0; completed = 0;
    m_cfg_valid = 0; m_cfg_dir = 0; m_cfg_route = 0; m_cfg_last = 0;
    m_cfg_tag = 0; m_cfg_tid = 0; m_cfg_fmt = 0; m_wvalid = 0; m_waddr = 0;
    m_wdata = 0; m_wmask = 0; m_rrvalid = 0; m_raddr = 0; m_rready = 0;
    aha_cfg_valid = 0; aha_in_base = 0; aha_out_base = 0; aha_in_beats = 0;
    aha_out_beats = 0; aha_out_tag = 0; aha_out_tid = 0; aha_out_fmt = 0;
    aha_last_be = 0; kv_cfg_valid = 0; kv_cfg_dir = 0; kv_cfg_base = 0;
    kv_cfg_beats = 0; kv_cfg_tag = 0; kv_cfg_tid = 0; kv_cfg_fmt = 0; kv_last_be = 0;
    for (int index = 0; index < 32768; index++) aha_mem[index] = 0;
    for (int index = 0; index < 8192; index++) kv_mem[index] = 0;
    seed = 32'h138f_2ca1;
    void'($urandom(seed));
    repeat (3) @(posedge clk); rst_n = 1;
    for (int transaction = 0; transaction < TARGET/2; transaction++) run_aha(transaction);
    for (int transaction = 0; transaction < TARGET/4; transaction++) run_kv_pair(transaction);
    if (completed != TARGET || m_errors != 0 || aha_errors != 0 || kv_errors != 0)
      $fatal(1, "stream complex accounting");
    $display("HETERO_L3_STREAM_COMPLEX_100K_PASS transfers=%0d matrix=%0d aha=%0d kv=%0d",
             completed, matrix_done_count, aha_done_count, kv_done_count);
    $finish;
  end

  initial begin
    repeat (TARGET*100 + 10000) @(posedge clk);
    $fatal(1, "stream complex timeout completed=%0d", completed);
  end
endmodule
