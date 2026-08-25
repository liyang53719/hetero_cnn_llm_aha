// Simulation-only monitor bound into the unmodified generated Gemmini macro.
module gemmini_busy_monitor (
  input logic clock,
  input logic reset,
  input logic io_busy,
  input logic io_cmd_valid,
  input logic io_cmd_ready,
  input logic [6:0] io_cmd_bits_inst_funct
);
  longint unsigned cycle_q;
  longint unsigned accepted_q;
  logic busy_q;
  always_ff @(posedge clock) begin
    if (reset) begin
      cycle_q <= 0;
      accepted_q <= 0;
      busy_q <= 0;
    end else begin
      cycle_q <= cycle_q + 1;
      if (io_cmd_valid && io_cmd_ready) begin
        accepted_q <= accepted_q + 1;
        $display("GEMMINI_MON_CMD cycle=%0d count=%0d funct=%0d",
                 cycle_q, accepted_q + 1, io_cmd_bits_inst_funct);
      end
      if (io_busy && !busy_q)
        $display("GEMMINI_MON_BUSY_ASSERT cycle=%0d accepted=%0d", cycle_q, accepted_q);
      if (!io_busy && busy_q)
        $display("GEMMINI_MON_BUSY_CLEAR cycle=%0d accepted=%0d", cycle_q, accepted_q);
      busy_q <= io_busy;
    end
  end
endmodule

bind Gemmini gemmini_busy_monitor u_l2_busy_monitor (
  .clock(clock), .reset(reset), .io_busy(io_busy),
  .io_cmd_valid(io_cmd_valid), .io_cmd_ready(io_cmd_ready),
  .io_cmd_bits_inst_funct(io_cmd_bits_inst_funct)
);
