// SPDX-License-Identifier: Apache-2.0
// Split one project 512-bit payload beat into eight official Garnet 64-bit
// proc_packet writes.  The caller supplies an already resolved Global Buffer
// packet address; this module deliberately does not invent AHA bank mapping.
`timescale 1ns/1ps
module aha_garnet_proc_packet_writer (
  input  logic          clk_i,
  input  logic          rst_ni,

  input  logic          packet_valid_i,
  output logic          packet_ready_o,
  input  logic [17:0]   packet_addr_i,
  input  logic [511:0]  packet_data_i,
  input  logic [63:0]   packet_strb_i,

  output logic          proc_packet_wr_en_o,
  output logic [17:0]   proc_packet_wr_addr_o,
  output logic [63:0]   proc_packet_wr_data_o,
  output logic [7:0]    proc_packet_wr_strb_o,
  output logic          packet_done_o
);
  logic active_q;
  logic [2:0] chunk_q;
  logic [17:0] addr_q;
  logic [511:0] data_q;
  logic [63:0] strb_q;

  assign packet_ready_o       = !active_q;
  assign proc_packet_wr_en_o  = active_q;
  assign proc_packet_wr_addr_o = addr_q + {12'd0, chunk_q, 3'b000};
  assign proc_packet_wr_data_o = data_q[chunk_q * 64 +: 64];
  assign proc_packet_wr_strb_o = strb_q[chunk_q * 8 +: 8];

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      active_q      <= 1'b0;
      chunk_q       <= '0;
      addr_q        <= '0;
      data_q        <= '0;
      strb_q        <= '0;
      packet_done_o <= 1'b0;
    end else begin
      packet_done_o <= 1'b0;
      if (!active_q) begin
        if (packet_valid_i && packet_ready_o) begin
          active_q <= 1'b1;
          chunk_q  <= '0;
          addr_q   <= packet_addr_i;
          data_q   <= packet_data_i;
          strb_q   <= packet_strb_i;
        end
      end else if (chunk_q == 3'd7) begin
        active_q      <= 1'b0;
        packet_done_o <= 1'b1;
      end else begin
        chunk_q <= chunk_q + 1'b1;
      end
    end
  end
endmodule
