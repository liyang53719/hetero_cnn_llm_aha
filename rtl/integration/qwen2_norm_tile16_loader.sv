// SPDX-License-Identifier: Apache-2.0
// Load sixteen token-major norm rows from DDR and transpose to K-major Shared-L2.
`timescale 1ns/1ps
module qwen2_norm_tile16_loader #(parameter integer ADDR_W=15)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[63:0]norm_ddr_base_i,input logic[31:0]token_base_i,
 output logic dma_req_valid_o,input logic dma_req_ready_i,output logic[1:0]dma_req_kind_o,output logic[63:0]dma_src_addr_o,dma_dst_addr_o,output logic[31:0]dma_row_bytes_o,dma_rows_o,dma_src_stride_o,dma_dst_stride_o,input logic dma_rsp_valid_i,output logic dma_rsp_ready_o,input logic dma_rsp_error_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic done_o,output logic[7:0]status_o,output logic[31:0]values_o,output logic[63:0]ddr_read_bytes_o
);
 typedef enum logic[2:0]{I,LQ,LP,TQ,TP,D}st_e;st_e st;logic ts,td;logic[31:0]reads,writes,rmsv,tvalues;logic[4:0]flags;
 qwen2_shared_l2_rms_tile16_stager stager(.clk_i,.rst_ni,.start_i(ts),.transpose_only_i(1'b1),.hidden_local_i(0),.weight_local_i(0),.norm_token_local_i(64'h60000),.norm_kmajor_local_i(64'h80000),.l2_rd_valid_o,.l2_rd_ready_i,.l2_rd_addr_o,.l2_rsp_valid_i,.l2_rsp_ready_o,.l2_rsp_data_i,.l2_wr_valid_o,.l2_wr_ready_i,.l2_wr_addr_o,.l2_wr_data_o,.l2_wr_be_o,.done_o(td),.read_beats_o(reads),.write_beats_o(writes),.rms_vectors_o(rmsv),.transpose_values_o(tvalues),.exception_flags_o(flags));
 assign dma_req_valid_o=st==LQ;assign dma_req_kind_o=1;assign dma_src_addr_o=norm_ddr_base_i+64'(token_base_i)*3072;assign dma_dst_addr_o=64'h60000;assign dma_row_bytes_o=3072;assign dma_rows_o=16;assign dma_src_stride_o=3072;assign dma_dst_stride_o=3072;assign dma_rsp_ready_o=st==LP;assign done_o=st==D;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;ts<=0;status_o<=0;values_o<=0;ddr_read_bytes_o<=0;end else begin ts<=0;case(st)I:if(start_i)begin status_o<=0;values_o<=0;ddr_read_bytes_o<=0;st<=LQ;end LQ:if(dma_req_valid_o&&dma_req_ready_i)st<=LP;LP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)begin status_o<=7;st<=D;end else begin ddr_read_bytes_o<=49152;ts<=1;st<=TQ;end end TQ:st<=TP;TP:if(td)begin values_o<=tvalues;if(flags[4:1]||rmsv!=0)status_o<=7;st<=D;end D:st<=I;default:st<=I;endcase end end
endmodule
