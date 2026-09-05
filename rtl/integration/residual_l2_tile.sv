// SPDX-License-Identifier: Apache-2.0
`default_nettype none
// Two local read ports + FP32 residual stream + one masked write port.
// Error completion waits for reader draining and pending writer completion.
module residual_l2_tile #(
 parameter integer ADDR_W=15,parameter logic[63:0]SRAM_BYTES=64'd1572864
)(
 input logic clk_i,rst_ni,request_valid_i,output logic request_ready_o,
 input logic[63:0]source_a_i,source_b_i,destination_i,input logic[31:0]elements_i,input logic b_bf16_i,
 output logic[1:0]rd_valid_o,input logic[1:0]rd_ready_i,output logic[2*ADDR_W-1:0]rd_addr_o,
 input logic[1:0]rsp_valid_i,output logic[1:0]rsp_ready_o,input logic[1023:0]rsp_data_i,input logic[1:0]rsp_error_i,
 output logic wr_valid_o,input logic wr_ready_i,output logic[ADDR_W-1:0]wr_addr_o,output logic[511:0]wr_data_o,output logic[63:0]wr_be_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[7:0]status_o,
 output logic[63:0]read_beats_o,write_beats_o,written_payload_bytes_o,cycles_o
);
 typedef enum logic[1:0]{IDLE,LAUNCH,RUN,DONE}state_t;state_t state_q;
 logic child_active_q,child_reset_n,launch,abort_q,bshort_q;
 logic[63:0]source_q[0:1],dest_q;logic[31:0]count_q,write_index_q;
 logic[64:0]a_end,b_end,c_end,a_bytes,b_bytes;logic legal;
 assign a_bytes=((65'(elements_i)+15)>>4)<<6;
 assign b_bytes=((65'(elements_i)+(b_bf16_i?31:15))>>(b_bf16_i?5:4))<<6;
 assign a_end={1'b0,source_a_i}+a_bytes;assign b_end={1'b0,source_b_i}+b_bytes;assign c_end={1'b0,destination_i}+a_bytes;
 assign legal=elements_i!=0&&source_a_i[5:0]==0&&source_b_i[5:0]==0&&destination_i[5:0]==0&&
  a_end<={1'b0,SRAM_BYTES}&&b_end<={1'b0,SRAM_BYTES}&&c_end<={1'b0,SRAM_BYTES}&&
  a_end<=(65'd1<<(ADDR_W+6))&&b_end<=(65'd1<<(ADDR_W+6))&&c_end<=(65'd1<<(ADDR_W+6))&&
  (c_end<={1'b0,source_a_i}||a_end<={1'b0,destination_i})&&
  (c_end<={1'b0,source_b_i}||b_end<={1'b0,destination_i});
 assign child_reset_n=rst_ni&&child_active_q;
 assign request_ready_o=rst_ni&&state_q==IDLE;assign completion_valid_o=state_q==DONE;
 logic[1:0]rrdy,rdone,rv,rr,rl,alu_ready;
 logic[511:0]rdata[0:1];logic[15:0]rkeep[0:1];logic[31:0]rindex[0:1];logic[7:0]rstatus[0:1];
 logic[63:0]rreads[0:1],rchunks[0:1];
 logic wreq_ready,wdone,wi_ready,wiv;
 logic[7:0]wstatus,winput_status;logic[63:0]wreceived,wbeats,wbytes;
 logic av,ar,al,afault;logic[511:0]adata;logic[15:0]atag,akeep;logic[4:0]aflags;logic[7:0]astatus;
 logic error_present;logic[7:0]first_error;
 assign launch=state_q==LAUNCH&&(&rrdy)&&wreq_ready;
 for(genvar g=0;g<2;g++)begin:readers
  residual_l2_stream_reader #(.ADDR_W(ADDR_W),.SRAM_BYTES(SRAM_BYTES))reader(
   .clk_i,.rst_ni(child_reset_n),.request_valid_i(launch),.request_ready_o(rrdy[g]),.source_i(source_q[g]),.elements_i(count_q),.bf16_i(g==1?bshort_q:1'b0),
   .rd_valid_o(rd_valid_o[g]),.rd_ready_i(rd_ready_i[g]),.rd_addr_o(rd_addr_o[g*ADDR_W+:ADDR_W]),
   .rsp_valid_i(rsp_valid_i[g]),.rsp_ready_o(rsp_ready_o[g]),.rsp_data_i(rsp_data_i[g*512+:512]),.rsp_error_i(rsp_error_i[g]),
   .out_valid_o(rv[g]),.out_ready_i(rr[g]),.out_data_o(rdata[g]),.out_keep_o(rkeep[g]),.out_chunk_o(rindex[g]),.out_last_o(rl[g]),
   .completion_valid_o(rdone[g]),.completion_ready_i(1'b0),.status_o(rstatus[g]),.read_beats_o(rreads[g]),.output_chunks_o(rchunks[g]));
  assign rr[g]=abort_q?1'b1:alu_ready[g];
 end
 fp32_residual_stream alu(.clk_i,.rst_ni(child_reset_n),
  .a_valid_i(rv[0]&&!abort_q),.a_ready_o(alu_ready[0]),.a_data_i(rdata[0]),.a_tag_i(rindex[0][15:0]),.a_keep_i(rkeep[0]),.a_last_i(rl[0]),
  .b_valid_i(rv[1]&&!abort_q),.b_ready_o(alu_ready[1]),.b_data_i(rdata[1]),.b_bf16_i(bshort_q),.b_tag_i(rindex[1][15:0]),.b_keep_i(rkeep[1]),.b_last_i(rl[1]),
  .out_valid_o(av),.out_ready_i(ar),.out_data_o(adata),.out_tag_o(atag),.out_keep_o(akeep),.out_last_o(al),.out_flags_o(aflags),.out_status_o(astatus),.fault_o(afault));
 assign ar=abort_q?1'b1:wi_ready;assign wiv=abort_q?1'b1:av;
 assign winput_status=abort_q?status_o:(astatus!=0?astatus:((atag!=write_index_q[15:0]||aflags[4:1]!=0)?8'd7:8'd0));
 residual_l2_stream_writer #(.ADDR_W(ADDR_W),.SRAM_BYTES(SRAM_BYTES))writer(
  .clk_i,.rst_ni(child_reset_n),.request_valid_i(launch),.request_ready_o(wreq_ready),.destination_i(dest_q),.elements_i(count_q),
  .in_valid_i(wiv),.in_ready_o(wi_ready),.in_data_i(adata),.in_keep_i(akeep),.in_chunk_i(write_index_q),.in_last_i(al),.in_status_i(winput_status),
  .wr_valid_o,.wr_ready_i,.wr_addr_o,.wr_data_o,.wr_be_o,
  .completion_valid_o(wdone),.completion_ready_i(1'b0),.status_o(wstatus),.received_chunks_o(wreceived),.written_beats_o(wbeats),.written_payload_bytes_o(wbytes));
 always_comb begin
  first_error=0;
  if(rdone[0]&&rstatus[0]!=0)first_error=rstatus[0];
  else if(rdone[1]&&rstatus[1]!=0)first_error=rstatus[1];
  else if(wdone&&wstatus!=0)first_error=wstatus;
  else if(afault)first_error=7;
  error_present=first_error!=0;
 end
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=IDLE;child_active_q<=0;abort_q<=0;bshort_q<=0;source_q[0]<=0;source_q[1]<=0;dest_q<=0;count_q<=0;write_index_q<=0;status_o<=0;read_beats_o<=0;write_beats_o<=0;written_payload_bytes_o<=0;cycles_o<=0;end
  else case(state_q)
   IDLE:if(request_valid_i&&request_ready_o)begin
    source_q[0]<=source_a_i;source_q[1]<=source_b_i;dest_q<=destination_i;count_q<=elements_i;bshort_q<=b_bf16_i;
    abort_q<=0;write_index_q<=0;status_o<=legal?0:5;read_beats_o<=0;write_beats_o<=0;written_payload_bytes_o<=0;cycles_o<=0;
    child_active_q<=legal;state_q<=legal?LAUNCH:DONE;
   end
   LAUNCH:begin cycles_o<=cycles_o+1;if(launch)state_q<=RUN;end
   RUN:begin
    cycles_o<=cycles_o+1;read_beats_o<=rreads[0]+rreads[1];write_beats_o<=wbeats;written_payload_bytes_o<=wbytes;
    if(av&&ar&&!abort_q)write_index_q<=write_index_q+1;
    if(!abort_q&&error_present)begin abort_q<=1;status_o<=first_error;end
    if((&rdone)&&wdone)begin child_active_q<=0;state_q<=DONE;end
   end
   DONE:if(completion_ready_i)state_q<=IDLE;
   default:state_q<=IDLE;
  endcase
 end
endmodule
`default_nettype wire
