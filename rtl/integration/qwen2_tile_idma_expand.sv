// SPDX-License-Identifier: Apache-2.0
// Expand every byte of each strided row into bounded pinned-iDMA requests.
`timescale 1ns/1ps
module qwen2_tile_idma_expand(
 input logic clk_i,rst_ni,req_valid_i,output logic req_ready_o,input logic[1:0]req_kind_i,
 input logic[63:0]src_addr_i,dst_addr_i,input logic[31:0]row_bytes_i,rows_i,src_stride_i,dst_stride_i,
 output logic rsp_valid_o,input logic rsp_ready_i,output logic rsp_error_o,
 output logic idma_req_valid_o,input logic idma_req_ready_i,
 output logic[63:0]idma_src_addr_o,idma_dst_addr_o,output logic[31:0]idma_length_o,
 input logic idma_rsp_valid_i,output logic idma_rsp_ready_o,input logic idma_rsp_error_i,
 output logic[31:0]flat_requests_o,output logic local_source_o
);
 typedef enum logic[1:0]{S_IDLE,S_REQ,S_RSP,S_OUT}state_e;state_e state_q;
 logic[1:0]kind_q;logic[63:0]src_q,dst_q;
 logic[31:0]bytes_q,rows_q,ss_q,ds_q,row_q,offset_q,chunk_q;
 logic error_q,coalesce,is2d,legal;
 logic[63:0]total_bytes;logic[64:0]src_end,dst_end;
 assign is2d=req_kind_i==1||req_kind_i==3;
 assign total_bytes=64'(row_bytes_i)*rows_i;
 assign coalesce=is2d&&rows_i>1&&src_stride_i==row_bytes_i&&dst_stride_i==row_bytes_i&&total_bytes<=64'hffffffff;
 assign src_end={1'b0,src_addr_i}+(is2d?65'(rows_i-1)*src_stride_i:65'd0)+row_bytes_i;
 assign dst_end={1'b0,dst_addr_i}+(is2d?65'(rows_i-1)*dst_stride_i:65'd0)+row_bytes_i;
 assign legal=row_bytes_i!=0&&(!is2d||rows_i!=0)&&src_end<=65'h10000000000000000&&dst_end<=65'h10000000000000000;
 assign req_ready_o=state_q==S_IDLE;assign idma_req_valid_o=state_q==S_REQ;
 assign idma_rsp_ready_o=state_q==S_RSP;assign rsp_valid_o=state_q==S_OUT;assign rsp_error_o=error_q;
 assign idma_src_addr_o=src_q+64'(row_q)*ss_q+offset_q;
 assign idma_dst_addr_o=dst_q+64'(row_q)*ds_q+offset_q;
 assign idma_length_o=bytes_q-offset_q>chunk_q?chunk_q:bytes_q-offset_q;
 assign local_source_o=(kind_q==2||kind_q==3)&&state_q!=S_IDLE;
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=S_IDLE;kind_q<=0;src_q<=0;dst_q<=0;bytes_q<=0;rows_q<=0;
   ss_q<=0;ds_q<=0;row_q<=0;offset_q<=0;chunk_q<=0;error_q<=0;flat_requests_o<=0;end
  else case(state_q)
   S_IDLE:if(req_valid_i)begin
    kind_q<=req_kind_i;src_q<=src_addr_i;dst_q<=dst_addr_i;
    bytes_q<=coalesce?total_bytes[31:0]:row_bytes_i;
    rows_q<=coalesce||!is2d?1:rows_i;ss_q<=src_stride_i;ds_q<=dst_stride_i;
    row_q<=0;offset_q<=0;chunk_q<=req_kind_i[1]?64:1024;
    error_q<=!legal;state_q<=legal?S_REQ:S_OUT;
   end
   S_REQ:if(idma_req_ready_i)begin flat_requests_o<=flat_requests_o+1;state_q<=S_RSP;end
   S_RSP:if(idma_rsp_valid_i)begin
    if(idma_rsp_error_i)begin error_q<=1;state_q<=S_OUT;end
    else if(bytes_q-offset_q>chunk_q)begin offset_q<=offset_q+chunk_q;state_q<=S_REQ;end
    else if(row_q+1<rows_q)begin row_q<=row_q+1;offset_q<=0;state_q<=S_REQ;end
    else state_q<=S_OUT;
   end
   S_OUT:if(rsp_ready_i)state_q<=S_IDLE;
   default:state_q<=S_IDLE;
  endcase
 end
endmodule
