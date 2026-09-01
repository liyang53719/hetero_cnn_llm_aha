// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module qwen2_rms_stage_top #(parameter integer ADDR_W=15)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[127:0]command_i,input logic[31:0]token_index_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,output logic[23:0]descriptor_req_index_o,
 input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
 output logic dma_req_valid_o,input logic dma_req_ready_i,output logic[1:0]dma_req_kind_o,output logic[63:0]dma_src_addr_o,dma_dst_addr_o,
 output logic[31:0]dma_row_bytes_o,dma_rows_o,dma_src_stride_o,dma_dst_stride_o,input logic dma_rsp_valid_i,output logic dma_rsp_ready_o,input logic dma_rsp_error_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic done_o,output logic[7:0]status_o,output logic[63:0]ddr_read_bytes_o,output logic[31:0]l2_read_beats_o,l2_write_beats_o
);
 typedef enum logic[3:0]{I,CWAIT,L0Q,L0P,L1Q,L1P,PAY,D}st_e;st_e st;logic ctx_start,ctxv,ctxr,ctxlegal;logic[7:0]ctxstatus;logic[167:0]addr;logic[127:0]cmdq;
 logic pstart,pdone,spv,spr,sov,sor,scv,sready,cmdpend,sseen;logic[49151:0]sx,sw,sy;logic[55:0]scd;logic[4:0]flags;logic[31:0]token_q,token_safe;
 always_comb token_safe=(^token_index_i===1'bx)?0:token_index_i;
 qwen2_rms_descriptor_context u_context(.clk_i,.rst_ni,.start_i(ctx_start),.command_i(cmdq),.descriptor_req_valid_o,.descriptor_req_ready_i,.descriptor_req_index_o,.descriptor_rsp_valid_i,.descriptor_rsp_ready_o,.descriptor_rsp_data_i,.descriptor_rsp_error_i,.context_valid_o(ctxv),.context_ready_i(ctxr),.context_legal_o(ctxlegal),.context_status_o(ctxstatus),.tensor_address_o(addr));assign ctxr=st==CWAIT;
 qwen2_shared_l2_rms_payload #(.ADDR_W(ADDR_W))payload(.clk_i,.rst_ni,.start_i(pstart),.hidden_local_i(64'h40000),.weight_local_i(64'h41000),.norm_local_i(64'h43000),.l2_rd_valid_o,.l2_rd_ready_i,.l2_rd_addr_o,.l2_rsp_valid_i,.l2_rsp_ready_o,.l2_rsp_data_i,.l2_wr_valid_o,.l2_wr_ready_i,.l2_wr_addr_o,.l2_wr_data_o,.l2_wr_be_o,.sfu_payload_valid_o(spv),.sfu_payload_ready_i(spr),.sfu_x_o(sx),.sfu_weight_o(sw),.sfu_out_valid_i(sov),.sfu_out_ready_o(sor),.sfu_y_i(sy),.done_o(pdone),.read_beats_o(l2_read_beats_o),.write_beats_o(l2_write_beats_o));
 qwen2_sfu_command_endpoint sfu(.clk_i,.rst_ni,.cmd_valid_i(cmdpend),.cmd_ready_o(sready),.cmd_i(cmdq),.payload_valid_i(spv),.payload_ready_o(spr),.payload_x_i(sx),.payload_weight_i(sw),.out_valid_o(sov),.out_ready_i(sor),.out_y_o(sy),.completion_valid_o(scv),.completion_ready_i(1'b1),.completion_data_o(scd),.exception_flags_o(flags));
 assign dma_req_valid_o=st==L0Q||st==L1Q;assign dma_req_kind_o=0;assign dma_src_addr_o=st==L0Q?{8'd0,addr[0+:56]}+64'(token_q)*3072:{8'd0,addr[56+:56]};assign dma_dst_addr_o=st==L0Q?64'h40000:64'h41000;assign dma_row_bytes_o=st==L0Q?3072:6144;assign dma_rows_o=1;assign dma_src_stride_o=dma_row_bytes_o;assign dma_dst_stride_o=dma_row_bytes_o;assign dma_rsp_ready_o=st==L0P||st==L1P;assign done_o=st==D&&sseen;assign ddr_read_bytes_o=st>=PAY?9216:0;
 always_comb begin if(ctxstatus!=0)status_o=ctxstatus;else if(flags[4:1]||scd[39:32]!=0)status_o=7;else status_o=0;end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;ctx_start<=0;pstart<=0;cmdq<=0;cmdpend<=0;sseen<=0;token_q<=0;end else begin ctx_start<=0;pstart<=0;if(start_i&&st==I)begin cmdq<=command_i;token_q<=token_safe;ctx_start<=1;cmdpend<=1;sseen<=0;st<=CWAIT;end if(cmdpend&&sready)cmdpend<=0;if(scv)sseen<=1;case(st)
  CWAIT:if(ctxv&&ctxr)begin if(ctxlegal)st<=L0Q;else st<=D;end L0Q:if(dma_req_valid_o&&dma_req_ready_i)st<=L0P;L0P:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)st<=D;else st<=L1Q;end L1Q:if(dma_req_valid_o&&dma_req_ready_i)st<=L1P;L1P:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)st<=D;else begin pstart<=1;st<=PAY;end end PAY:if(pdone)st<=D;D:if(sseen)st<=I;default:begin end endcase end end
endmodule
