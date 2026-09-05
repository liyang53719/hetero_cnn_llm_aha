// SPDX-License-Identifier: Apache-2.0
// Stage <=16 token rows into K-major 512-bit beats (low 16 BF16 lanes).
// A fixed 16x512-bit buffer reuses each source beat across up to 32 K values.
`timescale 1ns/1ps
module bf16_tile_transpose_stager #(parameter integer ADDR_W=15)(
 input logic clk_i,rst_ni,request_valid_i,output logic request_ready_o,
 input logic[63:0]source_i,destination_i,input logic[31:0]source_stride_i,
 input logic[15:0]rows_i,depth_i,
 output logic rd_valid_o,input logic rd_ready_i,output logic[ADDR_W-1:0]rd_addr_o,
 input logic rsp_valid_i,output logic rsp_ready_o,input logic[511:0]rsp_data_i,input logic rsp_error_i,
 output logic wr_valid_o,input logic wr_ready_i,output logic[ADDR_W-1:0]wr_addr_o,
 output logic[511:0]wr_data_o,output logic[63:0]wr_be_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[7:0]status_o,
 output logic[63:0]read_beats_o,write_beats_o
);
 typedef enum logic[2:0]{IDLE,READ_REQ,READ_RSP,WRITE,COMPLETE}state_t;state_t state_q;
 logic[63:0]source_q,dest_q;logic[31:0]stride_q;
 logic[15:0]rows_q,depth_q,k_q;logic[3:0]row_q;logic[4:0]lane_q;
 logic[511:0]buffer_q[0:15];
 logic[64:0]source_end,dest_end,padded_row_bytes;logic legal;
 localparam logic[64:0]CAPACITY=65'd1<<(ADDR_W+6);
 assign padded_row_bytes=((65'(depth_i)+31)>>5)<<6;
 assign source_end={1'b0,source_i}+65'(rows_i-1)*source_stride_i+padded_row_bytes;
 assign dest_end={1'b0,destination_i}+(65'(depth_i)<<6);
 assign legal=rows_i>0&&rows_i<=16&&depth_i>0&&source_i[5:0]==0&&destination_i[5:0]==0&&
  source_stride_i[5:0]==0&&65'(source_stride_i)>=padded_row_bytes&&
  source_end<=CAPACITY&&dest_end<=CAPACITY&&
  (source_end<={1'b0,destination_i}||dest_end<={1'b0,source_i});
 assign request_ready_o=state_q==IDLE;
 assign rd_valid_o=state_q==READ_REQ;assign rsp_ready_o=state_q==READ_RSP;
 assign rd_addr_o=ADDR_W'((source_q+64'(row_q)*stride_q+(64'(k_q)>>5)*64)>>6);
 assign wr_valid_o=state_q==WRITE;assign wr_be_o='1;
 assign wr_addr_o=ADDR_W'((dest_q>>6)+k_q+lane_q);
 assign completion_valid_o=state_q==COMPLETE;
 always_comb begin
  wr_data_o=0;
  for(integer r=0;r<16;r++)if(r<rows_q)wr_data_o[r*16+:16]=buffer_q[r][lane_q*16+:16];
 end
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=IDLE;source_q<=0;dest_q<=0;stride_q<=0;
   rows_q<=0;depth_q<=0;k_q<=0;row_q<=0;lane_q<=0;status_o<=0;
   read_beats_o<=0;write_beats_o<=0;
  end else case(state_q)
   IDLE:if(request_valid_i)begin source_q<=source_i;dest_q<=destination_i;stride_q<=source_stride_i;
    rows_q<=rows_i;depth_q<=depth_i;k_q<=0;row_q<=0;lane_q<=0;
    status_o<=legal?0:5;read_beats_o<=0;write_beats_o<=0;state_q<=legal?READ_REQ:COMPLETE;
   end
   READ_REQ:if(rd_ready_i)state_q<=READ_RSP;
   READ_RSP:if(rsp_valid_i)begin
    if(rsp_error_i)begin status_o<=3;state_q<=COMPLETE;end
    else begin buffer_q[row_q]<=rsp_data_i;read_beats_o<=read_beats_o+1;
     if(16'(row_q)+1==rows_q)begin lane_q<=0;state_q<=WRITE;end
     else begin row_q<=row_q+1;state_q<=READ_REQ;end
    end
   end
   WRITE:if(wr_ready_i)begin write_beats_o<=write_beats_o+1;
    if(17'(k_q)+17'(lane_q)+1==17'(depth_q))state_q<=COMPLETE;
    else if(lane_q==31)begin k_q<=k_q+32;row_q<=0;state_q<=READ_REQ;end
    else lane_q<=lane_q+1;
   end
   COMPLETE:if(completion_ready_i)state_q<=IDLE;
   default:state_q<=IDLE;
  endcase
 end
endmodule
