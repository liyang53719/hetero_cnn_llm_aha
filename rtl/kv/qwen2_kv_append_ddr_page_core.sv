// SPDX-License-Identifier: Apache-2.0
// DDR-resident q1024 KV append schedule. PTE semantics stay explicit here;
// packing the not-yet-frozen flags field is a separate boundary.
`timescale 1ns/1ps
module qwen2_kv_append_ddr_page_core(
 input logic clk_i,input logic rst_ni,input logic start_i,
 input logic[63:0]k_address_i,v_address_i,data_address_i,
 input logic[31:0]token_start_i,token_count_i,generation_i,logical_page_count_i,
 input logic[23:0]physical_page_limit_i,input logic[4:0]page_tokens_log2_i,
 output logic pte_valid_o,input logic pte_ready_i,output logic pte_level_o,
 output logic[9:0]pte_index_o,output logic[31:0]pte_physical_page_o,pte_generation_o,pte_refcount_o,
 output logic pte_entry_valid_o,
 output logic idma_req_valid_o,input logic idma_req_ready_i,output logic[63:0]idma_src_addr_o,idma_dst_addr_o,
 output logic[31:0]idma_length_o,input logic idma_rsp_valid_i,output logic idma_rsp_ready_o,input logic idma_rsp_error_i,
 output logic done_o,output logic[7:0]status_o,output logic[31:0]pte_updates_o,idma_requests_o,
 output logic[63:0]payload_bytes_o
);
 localparam logic[7:0]OK=0,RANGE=5,PROTOCOL=7;typedef enum logic[3:0]{I,ROOT,LEAF,KQ,KP,VQ,VP,D}st_e;st_e st;logic[31:0]page_q,pages_q;logic[63:0]page_bytes,k_or_v_page_bytes;
 assign page_bytes=64'd16384;assign k_or_v_page_bytes=64'd8192;
 assign pte_valid_o=st==ROOT||st==LEAF;assign pte_level_o=st==LEAF;assign pte_index_o=st==ROOT?10'd0:page_q[9:0];assign pte_physical_page_o=st==ROOT?0:page_q;assign pte_generation_o=generation_i;assign pte_refcount_o=1;assign pte_entry_valid_o=1;
 assign idma_req_valid_o=st==KQ||st==VQ;assign idma_src_addr_o=(st==KQ?k_address_i:v_address_i)+page_q*k_or_v_page_bytes;assign idma_dst_addr_o=data_address_i+page_q*page_bytes+(st==VQ?k_or_v_page_bytes:0);assign idma_length_o=8192;assign idma_rsp_ready_o=st==KP||st==VP;assign done_o=st==D;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=I;page_q<=0;pages_q<=0;status_o<=OK;pte_updates_o<=0;idma_requests_o<=0;payload_bytes_o<=0;end else case(st)
  I:if(start_i)begin page_q<=0;pages_q<=logical_page_count_i;status_o<=OK;pte_updates_o<=0;idma_requests_o<=0;payload_bytes_o<=0;if(token_start_i!=0||token_count_i==0||page_tokens_log2_i!=4||token_count_i[3:0]!=0||logical_page_count_i!=(token_count_i>>4)||logical_page_count_i>1024||logical_page_count_i>physical_page_limit_i)begin status_o<=RANGE;st<=D;end else st<=ROOT;end
  ROOT:if(pte_valid_o&&pte_ready_i)begin pte_updates_o<=pte_updates_o+1;st<=LEAF;end
  LEAF:if(pte_valid_o&&pte_ready_i)begin pte_updates_o<=pte_updates_o+1;st<=KQ;end
  KQ:if(idma_req_valid_o&&idma_req_ready_i)begin idma_requests_o<=idma_requests_o+1;st<=KP;end
  KP:if(idma_rsp_valid_i&&idma_rsp_ready_o)begin if(idma_rsp_error_i)begin status_o<=PROTOCOL;st<=D;end else begin payload_bytes_o<=payload_bytes_o+k_or_v_page_bytes;st<=VQ;end end
  VQ:if(idma_req_valid_o&&idma_req_ready_i)begin idma_requests_o<=idma_requests_o+1;st<=VP;end
  VP:if(idma_rsp_valid_i&&idma_rsp_ready_o)begin if(idma_rsp_error_i)begin status_o<=PROTOCOL;st<=D;end else begin payload_bytes_o<=payload_bytes_o+k_or_v_page_bytes;if(page_q+1==pages_q)st<=D;else begin page_q<=page_q+1;st<=LEAF;end end end
  D:st<=I;default:st<=I;endcase end
endmodule
