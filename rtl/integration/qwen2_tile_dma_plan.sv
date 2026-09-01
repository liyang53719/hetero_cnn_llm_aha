// SPDX-License-Identifier: Apache-2.0
// Descriptor-derived token0 / Q-column[0:31] tile DMA plan.
`timescale 1ns/1ps
module qwen2_tile_dma_plan #(
  parameter logic[63:0] LOCAL_BASE=64'h0004_0000
)(
  input logic clk_i,input logic rst_ni,
  input logic context_valid_i,output logic context_ready_o,
  input logic context_legal_i,input logic[6*56-1:0] tensor_address_i,
  input logic[5:0]q_column_tile_i,input logic full_q_i,input logic reuse_norm_i,input logic start_store_i,
  output logic dma_req_valid_o,input logic dma_req_ready_i,
  output logic[1:0] dma_req_kind_o,
  output logic[63:0] dma_src_addr_o,output logic[63:0] dma_dst_addr_o,
  output logic[31:0] dma_row_bytes_o,output logic[31:0] dma_rows_o,
  output logic[31:0] dma_src_stride_o,output logic[31:0] dma_dst_stride_o,
  input logic dma_rsp_valid_i,output logic dma_rsp_ready_o,input logic dma_rsp_error_i,
  output logic loads_done_o,output logic done_o,output logic[7:0] status_o,
  output logic[63:0] ddr_read_bytes_o,output logic[63:0] ddr_write_bytes_o,
  output logic[63:0] hidden_local_o,output logic[63:0] rms_weight_local_o,
  output logic[63:0] norm_local_o,output logic[63:0] q_weight_local_o,
  output logic[63:0] q_output_local_o
);
  localparam logic[1:0] DMA_LOAD_1D=0,DMA_LOAD_2D=1,DMA_STORE_1D=2;
  localparam logic[7:0] ST_OK=0,ST_UNSUPPORTED=4,ST_PROTOCOL=7;
  typedef enum logic[3:0]{S_IDLE,S_L0_REQ,S_L0_RSP,S_L1_REQ,S_L1_RSP,
    S_L2_REQ,S_L2_RSP,S_LOADED,S_STORE_REQ,S_STORE_RSP,S_DONE}state_e;
  state_e state_q;logic[55:0]addr_q[0:5];logic[5:0]tile_q;logic full_q_q,reuse_norm_q;integer i;
  assign context_ready_o=state_q==S_IDLE;
  assign dma_req_valid_o=state_q==S_L0_REQ||state_q==S_L1_REQ||state_q==S_L2_REQ||state_q==S_STORE_REQ;
  assign dma_rsp_ready_o=state_q==S_L0_RSP||state_q==S_L1_RSP||state_q==S_L2_RSP||state_q==S_STORE_RSP;
  assign loads_done_o=state_q==S_LOADED;assign done_o=state_q==S_DONE;
  assign hidden_local_o=LOCAL_BASE;assign rms_weight_local_o=LOCAL_BASE+64'h1000;
  assign norm_local_o=LOCAL_BASE+64'h3000;
  assign q_weight_local_o=full_q_q&&tile_q[0]?LOCAL_BASE+64'h1c000:LOCAL_BASE+64'h4000;
  assign q_output_local_o=full_q_q?LOCAL_BASE+64'h34000:LOCAL_BASE+64'h1c000;
  always_comb begin
    dma_req_kind_o=DMA_LOAD_1D;dma_src_addr_o=0;dma_dst_addr_o=0;
    dma_row_bytes_o=0;dma_rows_o=1;dma_src_stride_o=0;dma_dst_stride_o=0;
    case(state_q)
      S_L0_REQ:begin dma_src_addr_o={8'd0,addr_q[0]};dma_dst_addr_o=hidden_local_o;dma_row_bytes_o=3072;dma_src_stride_o=3072;dma_dst_stride_o=3072;end
      S_L1_REQ:begin dma_src_addr_o={8'd0,addr_q[1]};dma_dst_addr_o=rms_weight_local_o;dma_row_bytes_o=6144;dma_src_stride_o=6144;dma_dst_stride_o=6144;end
      S_L2_REQ:begin dma_req_kind_o=DMA_LOAD_2D;dma_src_addr_o={8'd0,addr_q[4]}+64'(tile_q)*64;dma_dst_addr_o=q_weight_local_o;dma_row_bytes_o=64;dma_rows_o=1536;dma_src_stride_o=3072;dma_dst_stride_o=64;end
      S_STORE_REQ:begin dma_req_kind_o=DMA_STORE_1D;dma_src_addr_o=q_output_local_o;dma_dst_addr_o={8'd0,addr_q[5]}+64'(tile_q)*64;dma_row_bytes_o=64;dma_src_stride_o=64;dma_dst_stride_o=64;end
      default:begin end
    endcase
  end
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin state_q<=S_IDLE;status_o<=ST_OK;ddr_read_bytes_o<=0;ddr_write_bytes_o<=0;tile_q<=0;full_q_q<=0;reuse_norm_q<=0;
      for(i=0;i<6;i++)addr_q[i]<=0;
    end else case(state_q)
      S_IDLE:if(context_valid_i&&context_ready_o)begin
        for(i=0;i<6;i++)addr_q[i]<=tensor_address_i[i*56+:56];tile_q<=q_column_tile_i;full_q_q<=full_q_i;reuse_norm_q<=reuse_norm_i;
        status_o<=context_legal_i?ST_OK:ST_UNSUPPORTED;ddr_read_bytes_o<=0;ddr_write_bytes_o<=0;
        state_q<=context_legal_i?(reuse_norm_i?S_L2_REQ:S_L0_REQ):S_DONE;
      end
      S_L0_REQ:if(dma_req_valid_o&&dma_req_ready_i)state_q<=S_L0_RSP;
      S_L0_RSP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)begin status_o<=ST_PROTOCOL;state_q<=S_DONE;end else begin ddr_read_bytes_o<=3072;state_q<=S_L1_REQ;end end
      S_L1_REQ:if(dma_req_valid_o&&dma_req_ready_i)state_q<=S_L1_RSP;
      S_L1_RSP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)begin status_o<=ST_PROTOCOL;state_q<=S_DONE;end else begin ddr_read_bytes_o<=ddr_read_bytes_o+6144;state_q<=S_L2_REQ;end end
      S_L2_REQ:if(dma_req_valid_o&&dma_req_ready_i)state_q<=S_L2_RSP;
      S_L2_RSP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)begin status_o<=ST_PROTOCOL;state_q<=S_DONE;end else begin ddr_read_bytes_o<=ddr_read_bytes_o+98304;state_q<=S_LOADED;end end
      S_LOADED:if(start_store_i)state_q<=S_STORE_REQ;
      S_STORE_REQ:if(dma_req_valid_o&&dma_req_ready_i)state_q<=S_STORE_RSP;
      S_STORE_RSP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)status_o<=ST_PROTOCOL;else ddr_write_bytes_o<=64;state_q<=S_DONE;end
      S_DONE:state_q<=S_IDLE;
      default:state_q<=S_IDLE;
    endcase
  end
endmodule
