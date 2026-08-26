// SPDX-License-Identifier: Apache-2.0
// Fair completion merger. Input 6 is reserved for watchdog completion.
`timescale 1ns/1ps
module engine_completion_rr_arbiter #(
  parameter integer INPUTS = 7,
  parameter integer WIDTH = 56,
  localparam integer INDEX_W = (INPUTS <= 2) ? 1 : $clog2(INPUTS)
) (
  input  logic                    clk_i,
  input  logic                    rst_ni,
  input  logic [INPUTS-1:0]       in_valid_i,
  output logic [INPUTS-1:0]       in_ready_o,
  input  logic [INPUTS*WIDTH-1:0] in_data_i,
  output logic                    out_valid_o,
  input  logic                    out_ready_i,
  output logic [WIDTH-1:0]        out_data_o,
  output logic [31:0]             grants_o
);
  logic pending_q;
  logic [INDEX_W-1:0] owner_q, rr_q;
  logic [WIDTH-1:0] data_q;
  logic select_valid;
  logic [INDEX_W-1:0] select_index;
  integer offset;
  integer candidate;

  always_comb begin
    select_valid = 0;
    select_index = 0;
    for (offset = 0; offset < INPUTS; offset++) begin
      candidate = 32'(rr_q) + offset;
      if (candidate >= INPUTS)
        candidate = candidate - INPUTS;
      if (!select_valid && in_valid_i[candidate]) begin
        select_valid = 1;
        select_index = INDEX_W'(candidate);
      end
    end
  end

  always_comb begin
    in_ready_o = 0;
    if (!pending_q && select_valid)
      in_ready_o[select_index] = 1;
  end
  assign out_valid_o = pending_q;
  assign out_data_o = data_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      pending_q <= 0;
      owner_q <= 0;
      rr_q <= 0;
      data_q <= 0;
      grants_o <= 0;
    end else begin
      if (!pending_q && select_valid && in_ready_o[select_index]) begin
        pending_q <= 1;
        owner_q <= select_index;
        data_q <= in_data_i[select_index*WIDTH +: WIDTH];
      end
      if (pending_q && out_ready_i) begin
        pending_q <= 0;
        grants_o <= grants_o + 1'b1;
        rr_q <= owner_q == INDEX_W'(INPUTS-1) ? 0 : owner_q + 1'b1;
      end
    end
  end
endmodule
