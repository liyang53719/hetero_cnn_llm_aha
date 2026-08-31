// SPDX-License-Identifier: Apache-2.0
module fp32_mlo_merge4_candidate(
 input logic clk_i,rst_ni,input logic header_valid_i,output logic header_ready_o,input logic[127:0]ma_i,la_i,mb_i,lb_i,
 input logic beat_valid_i,output logic beat_ready_o,input logic[511:0]oa_i,ob_i,input logic beat_last_i,
 output logic header_valid_o,input logic header_ready_i,output logic[127:0]m_o,l_o,
 output logic beat_valid_o,input logic beat_ready_i,output logic[511:0]o_o,output logic beat_last_o
);
 logic[3:0]hir,hov,bir,bov,blast;genvar g;
 generate for(g=0;g<4;g++)begin:g_row
  fp32_mlo_summary_merge_stream_rawpipe row(.clk_i,.rst_ni,.header_valid_i(header_valid_i&&(&hir)),.header_ready_o(hir[g]),.ma_i(ma_i[g*32+:32]),.la_i(la_i[g*32+:32]),.mb_i(mb_i[g*32+:32]),.lb_i(lb_i[g*32+:32]),.beat_valid_i(beat_valid_i&&(&bir)),.beat_ready_o(bir[g]),.oa_i(oa_i[g*128+:128]),.ob_i(ob_i[g*128+:128]),.beat_last_i,.header_valid_o(hov[g]),.header_ready_i(header_ready_i&&(&hov)),.m_o(m_o[g*32+:32]),.l_o(l_o[g*32+:32]),.beat_valid_o(bov[g]),.beat_ready_i(beat_ready_i&&(&bov)),.o_o(o_o[g*128+:128]),.beat_last_o(blast[g]));
 end endgenerate
 assign header_ready_o=&hir;assign beat_ready_o=&bir;assign header_valid_o=&hov;assign beat_valid_o=&bov;assign beat_last_o=&blast;
`ifndef SYNTHESIS
 always_ff@(posedge clk_i)if(rst_ni&&(|hov))assert(&hov);always_ff@(posedge clk_i)if(rst_ni&&(|bov))begin assert(&bov);assert((blast==0)||(blast==4'hf));end
`endif
endmodule
