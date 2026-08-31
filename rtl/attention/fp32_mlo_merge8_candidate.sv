// SPDX-License-Identifier: Apache-2.0
// L5.5 balanced candidate: eight lockstep M/L/O summary-merge rows.
// Each row reuses the accepted fp32_mlo_summary_merge_stream_rawpipe datapath.
module fp32_mlo_merge8_candidate(
  input  logic clk_i,input logic rst_ni,input logic header_valid_i,output logic header_ready_o,
  input logic [255:0] ma_i,la_i,mb_i,lb_i,
  input logic beat_valid_i,output logic beat_ready_o,input logic [1023:0] oa_i,ob_i,input logic beat_last_i,
  output logic header_valid_o,input logic header_ready_i,output logic [255:0] m_o,l_o,
  output logic beat_valid_o,input logic beat_ready_i,output logic [1023:0] o_o,output logic beat_last_o
);
  logic [7:0] header_ready,header_valid,row_beat_ready,row_beat_valid,row_beat_last,beat_last,bin_ready,bin_valid,bin_pop,bout_ready,bout_valid,bout_pop;logic[256:0]bin_data[0:7];logic[128:0]bout_data[0:7];logic[2:0]bin_level[0:7],bout_level[0:7];logic[1023:0]row_o;
  genvar row;
  generate for(row=0;row<8;row++)begin:g_row
    fp32_mlo_summary_merge_stream_rawpipe u_row(.clk_i,.rst_ni,
      .header_valid_i(header_valid_i&&(&header_ready)),.header_ready_o(header_ready[row]),
      .ma_i(ma_i[row*32+:32]),.la_i(la_i[row*32+:32]),.mb_i(mb_i[row*32+:32]),.lb_i(lb_i[row*32+:32]),
      .beat_valid_i(bin_valid[row]),.beat_ready_o(row_beat_ready[row]),
      .oa_i(bin_data[row][255:128]),.ob_i(bin_data[row][127:0]),.beat_last_i(bin_data[row][256]),
      .header_valid_o(header_valid[row]),.header_ready_i(header_ready_i&&(&header_valid)),
      .m_o(m_o[row*32+:32]),.l_o(l_o[row*32+:32]),
      .beat_valid_o(row_beat_valid[row]),.beat_ready_i(bout_ready[row]),
      .o_o(row_o[row*128+:128]),.beat_last_o(row_beat_last[row]));
    rv_fifo#(.WIDTH(257),.DEPTH(4))bin(.clk_i,.rst_ni,.in_valid_i(beat_valid_i&&(&bin_ready)),.in_ready_o(bin_ready[row]),.in_data_i({beat_last_i,oa_i[row*128+:128],ob_i[row*128+:128]}),.out_valid_o(bin_valid[row]),.out_ready_i(row_beat_ready[row]),.out_data_o(bin_data[row]),.level_o(bin_level[row]));
    rv_fifo#(.WIDTH(129),.DEPTH(4))bout(.clk_i,.rst_ni,.in_valid_i(row_beat_valid[row]),.in_ready_o(bout_ready[row]),.in_data_i({row_beat_last[row],row_o[row*128+:128]}),.out_valid_o(bout_valid[row]),.out_ready_i(beat_ready_i&&(&bout_valid)),.out_data_o(bout_data[row]),.level_o(bout_level[row]));
  end endgenerate
  always_comb begin for(integer r=0;r<8;r++)o_o[r*128+:128]=bout_data[r][127:0];end
  assign beat_last={bout_data[7][128],bout_data[6][128],bout_data[5][128],bout_data[4][128],bout_data[3][128],bout_data[2][128],bout_data[1][128],bout_data[0][128]};assign header_ready_o=&header_ready;assign beat_ready_o=&bin_ready;assign header_valid_o=&header_valid;assign beat_valid_o=&bout_valid;assign beat_last_o=&beat_last;
`ifndef SYNTHESIS
  always_ff@(posedge clk_i)begin
    if(rst_ni&&(|header_valid))assert(&header_valid) else $fatal(1,"merge8 header lanes diverged");
    if(rst_ni&&(|bout_valid))begin assert(&bout_valid) else $fatal(1,"merge8 beat lanes diverged");assert((beat_last==8'h00)||(beat_last==8'hff)) else $fatal(1,"merge8 last lanes diverged");end
  end
`endif
endmodule
