// SPDX-License-Identifier: Apache-2.0
// Expands the tile planner's 2D request into ordered pinned-iDMA 1D transfers.
`timescale 1ns/1ps
module qwen2_tile_idma_expand(
 input logic clk_i,input logic rst_ni,
 input logic req_valid_i,output logic req_ready_o,input logic[1:0]req_kind_i,
 input logic[63:0]src_addr_i,dst_addr_i,input logic[31:0]row_bytes_i,rows_i,
 input logic[31:0]src_stride_i,dst_stride_i,
 output logic rsp_valid_o,input logic rsp_ready_i,output logic rsp_error_o,
 output logic idma_req_valid_o,input logic idma_req_ready_i,
 output logic[63:0]idma_src_addr_o,idma_dst_addr_o,output logic[31:0]idma_length_o,
 input logic idma_rsp_valid_i,output logic idma_rsp_ready_o,input logic idma_rsp_error_i,
 output logic[31:0]flat_requests_o,output logic local_source_o
);
 typedef enum logic[1:0]{S_IDLE,S_REQ,S_RSP,S_OUT}state_e;state_e state_q;
 logic[1:0]kind_q;logic[63:0]src_q,dst_q;logic[31:0]bytes_q,rows_q,ss_q,ds_q,row_q;logic error_q;
 assign req_ready_o=state_q==S_IDLE;assign idma_req_valid_o=state_q==S_REQ;
 assign idma_rsp_ready_o=state_q==S_RSP;assign rsp_valid_o=state_q==S_OUT;assign rsp_error_o=error_q;
 assign idma_src_addr_o=src_q+64'(row_q)*ss_q;assign idma_dst_addr_o=dst_q+64'(row_q)*ds_q;
 assign idma_length_o=bytes_q;
 assign local_source_o=(kind_q==2||kind_q==3)&&state_q!=S_IDLE;
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=S_IDLE;kind_q<=0;src_q<=0;dst_q<=0;bytes_q<=0;rows_q<=0;ss_q<=0;ds_q<=0;row_q<=0;error_q<=0;flat_requests_o<=0;end
  else case(state_q)
   S_IDLE:if(req_valid_i&&req_ready_o)begin kind_q<=req_kind_i;src_q<=src_addr_i;dst_q<=dst_addr_i;
    bytes_q<=row_bytes_i;rows_q<=(req_kind_i==1||req_kind_i==3)?rows_i:1;ss_q<=src_stride_i;ds_q<=dst_stride_i;
    row_q<=0;error_q<=row_bytes_i==0||((req_kind_i==1||req_kind_i==3)&&rows_i==0);state_q<=row_bytes_i==0||((req_kind_i==1||req_kind_i==3)&&rows_i==0)?S_OUT:S_REQ;end
   S_REQ:if(idma_req_valid_o&&idma_req_ready_i)begin flat_requests_o<=flat_requests_o+1;state_q<=S_RSP;end
   S_RSP:if(idma_rsp_valid_i&&idma_rsp_ready_o)begin
    if(idma_rsp_error_i)begin error_q<=1;state_q<=S_OUT;end
    else if(row_q+1<rows_q)begin row_q<=row_q+1;state_q<=S_REQ;end else state_q<=S_OUT;end
   S_OUT:if(rsp_valid_o&&rsp_ready_i)state_q<=S_IDLE;
   default:state_q<=S_IDLE;
  endcase
 end
endmodule
