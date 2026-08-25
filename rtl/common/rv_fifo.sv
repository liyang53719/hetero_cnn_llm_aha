// SPDX-License-Identifier: Apache-2.0
// Small ready/valid FIFO used only by the clean-room integration shell.
module rv_fifo #(
  parameter integer WIDTH = 32,
  parameter integer DEPTH = 4,
  localparam integer PTR_W = (DEPTH <= 2) ? 1 : $clog2(DEPTH),
  localparam integer CNT_W = $clog2(DEPTH + 1)
) (
  input  logic                 clk_i,
  input  logic                 rst_ni,
  input  logic                 in_valid_i,
  output logic                 in_ready_o,
  input  logic [WIDTH-1:0]     in_data_i,
  output logic                 out_valid_o,
  input  logic                 out_ready_i,
  output logic [WIDTH-1:0]     out_data_o,
  output logic [CNT_W-1:0]     level_o
);
  logic [WIDTH-1:0] mem_q [0:DEPTH-1];
  logic [PTR_W-1:0] rd_ptr_q, wr_ptr_q;
  logic [CNT_W-1:0] count_q;

  logic push, pop;
  assign in_ready_o  = (count_q < DEPTH);
  assign out_valid_o = (count_q != '0);
  assign out_data_o  = mem_q[rd_ptr_q];
  assign level_o     = count_q;
  assign push        = in_valid_i && in_ready_o;
  assign pop         = out_valid_o && out_ready_i;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rd_ptr_q <= '0;
      wr_ptr_q <= '0;
      count_q  <= '0;
    end else begin
      if (push) begin
        mem_q[wr_ptr_q] <= in_data_i;
        wr_ptr_q <= (wr_ptr_q == DEPTH-1) ? '0 : wr_ptr_q + 1'b1;
      end
      if (pop) begin
        rd_ptr_q <= (rd_ptr_q == DEPTH-1) ? '0 : rd_ptr_q + 1'b1;
      end
      unique case ({push, pop})
        2'b10: count_q <= count_q + 1'b1;
        2'b01: count_q <= count_q - 1'b1;
        default: count_q <= count_q;
      endcase
    end
  end

`ifndef SYNTHESIS
  initial begin
    assert (DEPTH >= 2) else $fatal(1, "rv_fifo DEPTH must be >= 2");
  end
`endif
endmodule
