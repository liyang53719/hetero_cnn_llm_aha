// SPDX-License-Identifier: Apache-2.0
module operator_sfu_online_softmax_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,req_variant_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic score_valid_i,output logic score_ready_o,input logic[31:0]score_i,input logic score_mask_i,
 input logic merge_header_valid_i,output logic merge_header_ready_o,input logic[31:0]ma_i,la_i,mb_i,lb_i,
 input logic merge_beat_valid_i,output logic merge_beat_ready_o,input logic[127:0]oa_i,ob_i,input logic merge_beat_last_i,
 output logic header_valid_o,input logic header_ready_i,output logic[31:0]m_o,l_o,
 output logic weight_valid_o,input logic weight_ready_i,output logic[31:0]weight_o,output logic weight_last_o,
 output logic beat_valid_o,input logic beat_ready_i,output logic[127:0]o_o,output logic beat_last_o,
 output logic[4:0]exception_flags_o,output logic completion_valid_o,input logic completion_ready_i,
 output logic[15:0]completion_tag_o,output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
 localparam logic[1:0]IDLE=0,START=1,RUN=2,COMPLETE=3;logic[1:0]st;logic mode_merge_q;
 logic[15:0]tag_q;logic[7:0]parent_q,terminal_q,status_q;logic b_hv,b_wv,b_wl,b_busy;logic[31:0]b_m,b_l,b_w;logic[4:0]b_flags;
 logic m_hr,m_br,m_hv,m_bv,m_bl;logic[31:0]m_m,m_l;logic[127:0]merge_o;
 fp32_block32_softmax_weights block32(.clk_i,.rst_ni,.start_i(st==START&&!mode_merge_q),.score_valid_i(score_valid_i&&st==RUN&&!mode_merge_q),.score_ready_o(score_ready_o),.score_i,.mask_i(score_mask_i),.summary_valid_o(b_hv),.summary_ready_i(header_ready_i&&st==RUN&&!mode_merge_q),.m_o(b_m),.l_o(b_l),.weight_valid_o(b_wv),.weight_ready_i(weight_ready_i&&st==RUN&&!mode_merge_q),.weight_o(b_w),.weight_last_o(b_wl),.exception_flags_o(b_flags),.busy_o(b_busy));
 fp32_mlo_summary_merge_stream#(.LANES(4))merge128(.clk_i,.rst_ni,.header_valid_i(merge_header_valid_i&&st==RUN&&mode_merge_q),.header_ready_o(m_hr),.ma_i,.la_i,.mb_i,.lb_i,.beat_valid_i(merge_beat_valid_i&&st==RUN&&mode_merge_q),.beat_ready_o(m_br),.oa_i,.ob_i,.beat_last_i(merge_beat_last_i),.header_valid_o(m_hv),.header_ready_i(header_ready_i&&st==RUN&&mode_merge_q),.m_o(m_m),.l_o(m_l),.beat_valid_o(m_bv),.beat_ready_i(beat_ready_i&&st==RUN&&mode_merge_q),.o_o(merge_o),.beat_last_o(m_bl));
 assign req_ready_o=st==IDLE;assign merge_header_ready_o=st==RUN&&mode_merge_q&&m_hr;assign merge_beat_ready_o=st==RUN&&mode_merge_q&&m_br;
 assign header_valid_o=st==RUN&&(mode_merge_q?m_hv:b_hv);assign m_o=mode_merge_q?m_m:b_m;assign l_o=mode_merge_q?m_l:b_l;
 assign weight_valid_o=st==RUN&&!mode_merge_q&&b_wv;assign weight_o=b_w;assign weight_last_o=b_wl;
 assign beat_valid_o=st==RUN&&mode_merge_q&&m_bv;assign o_o=merge_o;assign beat_last_o=m_bl;assign exception_flags_o=mode_merge_q?0:b_flags;
 assign completion_valid_o=st==COMPLETE;assign completion_tag_o=tag_q;assign completion_parent_phase_o=parent_q;assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;mode_merge_q<=0;tag_q<=0;parent_q<=0;terminal_q<=0;status_q<=0;end else case(st)
  IDLE:if(req_valid_i)begin tag_q<=req_tag_i;parent_q<=req_parent_phase_i;terminal_q<=req_terminal_phase_i;status_q<=0;mode_merge_q<=req_variant_i[0];if(req_opcode_i!=8'h40||req_variant_i>1)begin status_q<=4;st<=COMPLETE;end else st<=START;end
  START:st<=RUN;
  RUN:if((!mode_merge_q&&b_wv&&weight_ready_i&&b_wl)||(mode_merge_q&&m_bv&&beat_ready_i&&m_bl))st<=COMPLETE;
  COMPLETE:if(completion_ready_i)st<=IDLE;default:st<=IDLE;endcase end
endmodule
