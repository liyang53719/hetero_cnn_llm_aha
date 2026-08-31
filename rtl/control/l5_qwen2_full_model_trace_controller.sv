module l5_qwen2_full_model_trace_controller (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        start_i,
  output logic        busy_o,
  output logic        done_o,
  output logic        trace_valid_o,
  input  logic        trace_ready_i,
  output logic [1:0]  trace_op_o,
  output logic [4:0]  trace_layer_o,
  output logic [63:0] trace_cycles_o,
  output logic [63:0] trace_macs_o,
  output logic [63:0] trace_read_bytes_o,
  output logic [63:0] trace_write_bytes_o,
  output logic        trace_last_o,
  output logic [5:0]  records_o,
  output logic [63:0] total_cycles_o,
  output logic [63:0] total_macs_o,
  output logic [63:0] total_read_bytes_o,
  output logic [63:0] total_write_bytes_o
);
  localparam logic [63:0] BLOCK_CYCLES = 64'd113621951;
  localparam logic [63:0] BLOCK_MACS = 64'd49527914496;
  localparam logic [63:0] BLOCK_READ_BYTES = 64'd93585408;
  localparam logic [63:0] BLOCK_WRITE_BYTES = 64'd1048576;
  localparam logic [63:0] FINAL_NORM_CYCLES = 64'd390;
  localparam logic [63:0] LM_HEAD_CYCLES = 64'd7763930;
  localparam logic [63:0] LM_HEAD_MACS = 64'd233373696;
  localparam logic [63:0] LM_HEAD_READ_BYTES = 64'd466747392;
  localparam logic [63:0] LM_HEAD_WRITE_BYTES = 64'd607744;

  logic [5:0] index_q;
  logic       busy_q;

  always_comb begin
    trace_valid_o = busy_q;
    trace_layer_o = index_q < 28 ? index_q[4:0] : 5'd27;
    trace_last_o = index_q == 29;
    if (index_q < 28) begin
      trace_op_o = 2'd0;
      trace_cycles_o = BLOCK_CYCLES;
      trace_macs_o = BLOCK_MACS;
      trace_read_bytes_o = BLOCK_READ_BYTES;
      trace_write_bytes_o = BLOCK_WRITE_BYTES;
    end else if (index_q == 28) begin
      trace_op_o = 2'd1;
      trace_cycles_o = FINAL_NORM_CYCLES;
      trace_macs_o = 64'd0;
      trace_read_bytes_o = 64'd0;
      trace_write_bytes_o = 64'd0;
    end else begin
      trace_op_o = 2'd2;
      trace_cycles_o = LM_HEAD_CYCLES;
      trace_macs_o = LM_HEAD_MACS;
      trace_read_bytes_o = LM_HEAD_READ_BYTES;
      trace_write_bytes_o = LM_HEAD_WRITE_BYTES;
    end
  end

  assign busy_o = busy_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      index_q <= '0;
      busy_q <= 1'b0;
      done_o <= 1'b0;
      records_o <= '0;
      total_cycles_o <= '0;
      total_macs_o <= '0;
      total_read_bytes_o <= '0;
      total_write_bytes_o <= '0;
    end else begin
      done_o <= 1'b0;
      if (start_i && !busy_q) begin
        index_q <= '0;
        busy_q <= 1'b1;
        records_o <= '0;
        total_cycles_o <= '0;
        total_macs_o <= '0;
        total_read_bytes_o <= '0;
        total_write_bytes_o <= '0;
      end else if (trace_valid_o && trace_ready_i) begin
        records_o <= records_o + 1'b1;
        total_cycles_o <= total_cycles_o + trace_cycles_o;
        total_macs_o <= total_macs_o + trace_macs_o;
        total_read_bytes_o <= total_read_bytes_o + trace_read_bytes_o;
        total_write_bytes_o <= total_write_bytes_o + trace_write_bytes_o;
        if (trace_last_o) begin
          busy_q <= 1'b0;
          done_o <= 1'b1;
        end else begin
          index_q <= index_q + 1'b1;
        end
      end
    end
  end
endmodule
