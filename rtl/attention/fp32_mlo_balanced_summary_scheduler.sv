// SPDX-License-Identifier: Apache-2.0
// One-row balanced reduction for 2..8 FP32 M/L/O summaries. O is 128 values
// streamed as 32 beats of four FP32 lanes. Reuses one ext32 merge128 datapath.
`timescale 1ns/1ps
module fp32_mlo_balanced_summary_scheduler(
 input logic clk_i,rst_ni,start_i,input logic[3:0]summary_count_i,
 input logic header_valid_i,output logic header_ready_o,input logic[31:0]m_i,l_i,
 input logic beat_valid_i,output logic beat_ready_o,input logic[127:0]o_i,input logic beat_last_i,
 output logic header_valid_o,input logic header_ready_i,output logic[31:0]m_o,l_o,
 output logic beat_valid_o,input logic beat_ready_i,output logic[127:0]o_o,output logic beat_last_o,
 output logic busy_o,done_o,protocol_error_o,output logic[31:0]merges_completed_o
);
 typedef enum logic[3:0]{IDLE,LOAD_H,LOAD_B,ROUND_SELECT,MERGE_H_SEND,
  MERGE_H_WAIT,MERGE_B_SEND,MERGE_B_WAIT,COPY_B,ROUND_DONE,OUT_H,OUT_B}state_e;
 state_e state_q;
 logic[31:0]m_mem[0:7],l_mem[0:7];logic[127:0]o_mem[0:7][0:31];
 logic header_stalled_q,beat_stalled_q;logic[63:0]held_header_q;logic[128:0]held_beat_q;
 logic[3:0]load_summary_q,active_count_q,read_q,write_q,next_count;logic[5:0]beat_q;
 logic mhiv,mhir,mhov,mhor,mbiv,mbir,mbov,mbor,mblast_i,mblast_o;
 logic[31:0]mma,mla,mmb,mlb,mmo,mml;logic[127:0]moa,mob,moo;
 fp32_mlo_summary_merge_stream_rawpipe merge(
  .clk_i,.rst_ni,.header_valid_i(mhiv),.header_ready_o(mhir),.ma_i(mma),.la_i(mla),.mb_i(mmb),.lb_i(mlb),
  .beat_valid_i(mbiv),.beat_ready_o(mbir),.oa_i(moa),.ob_i(mob),.beat_last_i(mblast_i),
  .header_valid_o(mhov),.header_ready_i(mhor),.m_o(mmo),.l_o(mml),
  .beat_valid_o(mbov),.beat_ready_i(mbor),.o_o(moo),.beat_last_o(mblast_o));
 assign next_count=(active_count_q+1'b1)>>1;
 assign header_ready_o=state_q==LOAD_H;assign beat_ready_o=state_q==LOAD_B;
 assign header_valid_o=state_q==OUT_H;assign beat_valid_o=state_q==OUT_B;
 assign m_o=m_mem[0];assign l_o=l_mem[0];assign o_o=o_mem[0][beat_q];assign beat_last_o=beat_q==31;
 assign busy_o=state_q!=IDLE;assign done_o=(state_q==OUT_B)&&beat_ready_i&&(beat_q==31);
 assign mhiv=state_q==MERGE_H_SEND;assign mhor=state_q==MERGE_H_WAIT;
 assign mbiv=state_q==MERGE_B_SEND;assign mbor=state_q==MERGE_B_WAIT;
 assign mma=m_mem[read_q];assign mla=l_mem[read_q];assign mmb=m_mem[read_q+1'b1];assign mlb=l_mem[read_q+1'b1];
 assign moa=o_mem[read_q][beat_q];assign mob=o_mem[read_q+1'b1][beat_q];assign mblast_i=beat_q==31;
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=IDLE;load_summary_q<=0;active_count_q<=0;read_q<=0;write_q<=0;beat_q<=0;protocol_error_o<=0;merges_completed_o<=0;end
  else begin case(state_q)
   IDLE:if(start_i)begin protocol_error_o<=0;merges_completed_o<=0;load_summary_q<=0;beat_q<=0;if(summary_count_i<2||summary_count_i>8)begin protocol_error_o<=1;state_q<=IDLE;end else begin active_count_q<=summary_count_i;state_q<=LOAD_H;end end
   LOAD_H:if(header_valid_i)begin m_mem[load_summary_q]<=m_i;l_mem[load_summary_q]<=l_i;beat_q<=0;state_q<=LOAD_B;end
   LOAD_B:if(beat_valid_i)begin o_mem[load_summary_q][beat_q]<=o_i;if(beat_last_i!=(beat_q==31))protocol_error_o<=1;if(beat_q==31)begin if(load_summary_q+1'b1==active_count_q)begin read_q<=0;write_q<=0;state_q<=ROUND_SELECT;end else begin load_summary_q<=load_summary_q+1'b1;state_q<=LOAD_H;end end else beat_q<=beat_q+1'b1;end
   ROUND_SELECT:begin beat_q<=0;if(read_q+1'b1<active_count_q)state_q<=MERGE_H_SEND;else state_q<=COPY_B;end
   MERGE_H_SEND:if(mhir)state_q<=MERGE_H_WAIT;
   MERGE_H_WAIT:if(mhov)begin m_mem[write_q]<=mmo;l_mem[write_q]<=mml;beat_q<=0;state_q<=MERGE_B_SEND;end
   MERGE_B_SEND:if(mbir)state_q<=MERGE_B_WAIT;
   MERGE_B_WAIT:if(mbov)begin o_mem[write_q][beat_q]<=moo;if(mblast_o!=(beat_q==31))protocol_error_o<=1;if(beat_q==31)begin merges_completed_o<=merges_completed_o+1'b1;state_q<=ROUND_DONE;end else begin beat_q<=beat_q+1'b1;state_q<=MERGE_B_SEND;end end
   COPY_B:begin m_mem[write_q]<=m_mem[read_q];l_mem[write_q]<=l_mem[read_q];o_mem[write_q][beat_q]<=o_mem[read_q][beat_q];if(beat_q==31)state_q<=ROUND_DONE;else beat_q<=beat_q+1'b1;end
   ROUND_DONE:begin if(read_q+2>=active_count_q)begin active_count_q<=next_count;read_q<=0;write_q<=0;beat_q<=0;if(next_count==1)state_q<=OUT_H;else state_q<=ROUND_SELECT;end else begin read_q<=read_q+2;write_q<=write_q+1'b1;beat_q<=0;state_q<=ROUND_SELECT;end end
   OUT_H:if(header_ready_i)begin beat_q<=0;state_q<=OUT_B;end
   OUT_B:if(beat_ready_i)begin if(beat_q==31)state_q<=IDLE;else beat_q<=beat_q+1'b1;end
   default:state_q<=IDLE;
  endcase end
 end
`ifndef SYNTHESIS
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin header_stalled_q<=0;beat_stalled_q<=0;held_header_q<=0;held_beat_q<=0;end
  else begin
   if(header_stalled_q)assert(header_valid_o&&{m_o,l_o}==held_header_q);
   if(beat_stalled_q)assert(beat_valid_o&&{o_o,beat_last_o}==held_beat_q);
   header_stalled_q<=header_valid_o&&!header_ready_i;beat_stalled_q<=beat_valid_o&&!beat_ready_i;
   if(header_valid_o&&!header_ready_i)held_header_q<={m_o,l_o};
   if(beat_valid_o&&!beat_ready_i)held_beat_q<={o_o,beat_last_o};
  end
 end
`endif
endmodule
