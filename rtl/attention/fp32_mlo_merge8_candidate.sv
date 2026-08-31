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
  logic [7:0] header_ready,header_valid,beat_ready,beat_valid,beat_last;
  genvar row;
  generate for(row=0;row<8;row++)begin:g_row
    fp32_mlo_summary_merge_stream_rawpipe u_row(.clk_i,.rst_ni,
      .header_valid_i(header_valid_i&&(&header_ready)),.header_ready_o(header_ready[row]),
      .ma_i(ma_i[row*32+:32]),.la_i(la_i[row*32+:32]),.mb_i(mb_i[row*32+:32]),.lb_i(lb_i[row*32+:32]),
      .beat_valid_i(beat_valid_i&&(&beat_ready)),.beat_ready_o(beat_ready[row]),
      .oa_i(oa_i[row*128+:128]),.ob_i(ob_i[row*128+:128]),.beat_last_i,
      .header_valid_o(header_valid[row]),.header_ready_i(header_ready_i&&(&header_valid)),
      .m_o(m_o[row*32+:32]),.l_o(l_o[row*32+:32]),
      .beat_valid_o(beat_valid[row]),.beat_ready_i(beat_ready_i&&(&beat_valid)),
      .o_o(o_o[row*128+:128]),.beat_last_o(beat_last[row]));
  end endgenerate
  assign header_ready_o=&header_ready;assign beat_ready_o=&beat_ready;assign header_valid_o=&header_valid;assign beat_valid_o=&beat_valid;assign beat_last_o=&beat_last;
`ifndef SYNTHESIS
  always_ff@(posedge clk_i)begin
    if(rst_ni&&(|header_valid))assert(&header_valid)else$fatal(1,"merge8 header lanes diverged");
    if(rst_ni&&(|beat_valid))begin assert(&beat_valid)else$fatal(1,"merge8 beat lanes diverged");assert((beat_last==8'h00)||(beat_last==8'hff))else$fatal(1,"merge8 last lanes diverged");end
  end
`endif
endmodule
