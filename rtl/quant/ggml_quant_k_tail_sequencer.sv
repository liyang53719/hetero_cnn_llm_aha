// SPDX-License-Identifier: Apache-2.0
// Shared 16-value frontend sequencer for FP16/Q8_0/Q6_K/Q3_K K tails.
module ggml_quant_k_tail_sequencer #(
  parameter integer K_W = 32,
  parameter integer BLOCK_W = 32
) (
  input logic clk_i,rst_ni,start_i,
  input logic [1:0] format_i,
  input logic [K_W-1:0] k_values_i,
  output logic busy_o,beat_valid_o,
  input logic beat_ready_i,
  output logic [BLOCK_W-1:0] block_index_o,
  output logic [3:0] group_index_o,
  output logic [4:0] valid_count_o,
  output logic block_first_o,block_last_o,last_o,done_o
);
  logic busy_q,done_q;logic[1:0]format_q;logic[K_W-1:0]remaining_q;logic[BLOCK_W-1:0]block_q;logic[3:0]group_q;logic[4:0]block_beats,current_valid;logic fire;
  always_comb begin
    unique case(format_q)
      2'd0:block_beats=5'd1;
      2'd1:block_beats=5'd2;
      default:block_beats=5'd16;
    endcase
    current_valid=(remaining_q>=K_W'(16))?5'd16:5'(remaining_q);
  end
  assign busy_o=busy_q;assign done_o=done_q;assign beat_valid_o=busy_q;assign block_index_o=block_q;assign group_index_o=group_q;assign valid_count_o=current_valid;assign block_first_o=(group_q==4'd0);assign last_o=busy_q&&(remaining_q<=K_W'(16));assign block_last_o=last_o||({1'b0,group_q}+5'd1==block_beats);assign fire=beat_valid_o&&beat_ready_i;
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin busy_q<=0;done_q<=0;format_q<=0;remaining_q<='0;block_q<='0;group_q<='0;end
    else begin
      done_q<=0;
      if(start_i&&!busy_q)begin format_q<=format_i;remaining_q<=k_values_i;block_q<='0;group_q<='0;busy_q<=(k_values_i!='0);done_q<=(k_values_i=='0);end
      else if(fire)begin
        if(last_o)begin busy_q<=0;done_q<=1;remaining_q<='0;end
        else begin remaining_q<=remaining_q-K_W'(16);if(block_last_o)begin block_q<=block_q+1'b1;group_q<='0;end else group_q<=group_q+1'b1;end
      end
    end
  end
`ifndef SYNTHESIS
  always_ff@(posedge clk_i)begin
    if(rst_ni&&beat_valid_o)begin assert(valid_count_o>=1&&valid_count_o<=16)else$fatal(1,"invalid valid_count");assert(group_index_o<block_beats)else$fatal(1,"invalid group index");end
    if(rst_ni&&start_i)assert(!busy_q)else$fatal(1,"start while busy");
  end
`endif
endmodule
