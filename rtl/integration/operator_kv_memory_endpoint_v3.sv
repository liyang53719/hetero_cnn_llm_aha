// SPDX-License-Identifier: Apache-2.0
module operator_kv_memory_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic config_valid_i,output logic config_ready_o,input logic[31:0]sequence_id_i,input logic[11:0]layer_id_i,kv_head_id_i,
 input logic[31:0]token_start_i,token_count_i,generation_i,physical_page_limit_i,bytes_per_token_i,
 input logic[63:0]table_base_i,data_base_i,k_address_i,v_address_i,output_address_i,input logic[7:0]format_i,
 output logic ddr_req_valid_o,input logic ddr_req_ready_i,output logic ddr_req_write_o,output logic[63:0]ddr_req_addr_o,output logic[127:0]ddr_req_wdata_o,output logic[15:0]ddr_req_wstrb_o,
 input logic ddr_rsp_valid_i,output logic ddr_rsp_ready_o,input logic[127:0]ddr_rsp_rdata_i,input logic ddr_rsp_error_i,
 output logic page_req_valid_o,input logic page_req_ready_i,output logic page_req_free_o,output logic[31:0]page_req_id_o,
 input logic page_rsp_valid_i,output logic page_rsp_ready_o,input logic[31:0]page_rsp_id_i,input logic page_rsp_error_i,
 output logic idma_req_valid_o,input logic idma_req_ready_i,output logic[63:0]idma_src_addr_o,idma_dst_addr_o,output logic[31:0]idma_length_o,
 input logic idma_rsp_valid_i,output logic idma_rsp_ready_o,input logic idma_rsp_error_i,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o,output logic[63:0]bytes_moved_o);
 localparam logic[7:0]APPEND=8'h50,GATHER=8'h51,ALLOC=8'h52,FREE=8'h53,RANGE=5,PROTOCOL=7;
 localparam logic[3:0]IDLE=0,CONFIG=1,RESOLVE_ISSUE=2,RESOLVE_WAIT=3,K_REQ=4,K_RSP=5,V_REQ=6,V_RSP=7,NEXT=8,COMPLETE=9;
 logic[3:0]st;logic[7:0]opcode_q,status_q;logic[15:0]tag_q;logic[7:0]parent_q,terminal_q;logic[31:0]seq_q,token_start_q,token_count_q,generation_q,limit_q,bytes_token_q,processed_q,page_id_q;logic[11:0]layer_q,head_q;logic[63:0]table_q,data_q,k_q,v_q,out_q,total_bytes_q,bytes_moved_q;logic[7:0]format_q;
 logic[32:0]last_token_wide,config_last_token,absolute_token;logic[31:0]remaining;logic[4:0]page_room,chunk_tokens;logic[63:0]chunk_bytes,token_byte_offset,page_data_addr,source_offset;logic[27:0]logical_page;
 logic resolve_start,resolve_ready,resolve_done;logic[7:0]resolve_status;logic[31:0]resolve_page;
 assign last_token_wide={1'b0,token_start_q}+{1'b0,token_count_q}-1'b1;assign config_last_token={1'b0,token_start_i}+{1'b0,token_count_i}-1'b1;assign absolute_token={1'b0,token_start_q}+{1'b0,processed_q};assign logical_page=absolute_token[31:4];assign remaining=token_count_q-processed_q;assign page_room=5'd16-{1'b0,absolute_token[3:0]};assign chunk_tokens=remaining<page_room?remaining[4:0]:page_room;assign chunk_bytes=chunk_tokens*bytes_token_q;assign token_byte_offset=absolute_token[3:0]*bytes_token_q;assign page_data_addr=data_q+{18'd0,page_id_q,14'b0}+token_byte_offset;assign source_offset=processed_q*bytes_token_q;
 assign resolve_start=st==RESOLVE_ISSUE;
 kv_ddr_pte_resolver_v3 resolver(.clk_i,.rst_ni,.start_i(resolve_start),.ready_o(resolve_ready),.allocate_on_miss_i(opcode_q==APPEND||opcode_q==ALLOC),.free_i(opcode_q==FREE),.table_base_i(table_q),.root_index_i(logical_page[19:10]),.leaf_index_i(logical_page[9:0]),.generation_i(generation_q),.physical_page_limit_i(limit_q),.format_i(format_q),
  .ddr_req_valid_o,.ddr_req_ready_i,.ddr_req_write_o,.ddr_req_addr_o,.ddr_req_wdata_o,.ddr_req_wstrb_o,.ddr_rsp_valid_i,.ddr_rsp_ready_o,.ddr_rsp_rdata_i,.ddr_rsp_error_i,
  .page_req_valid_o,.page_req_ready_i,.page_req_free_o,.page_req_id_o,.page_rsp_valid_i,.page_rsp_ready_o,.page_rsp_id_i,.page_rsp_error_i,.done_o(resolve_done),.status_o(resolve_status),.data_page_o(resolve_page));
 assign req_ready_o=st==IDLE;assign config_ready_o=st==CONFIG;assign idma_req_valid_o=st==K_REQ||st==V_REQ;assign idma_rsp_ready_o=st==K_RSP||st==V_RSP;assign idma_length_o=chunk_bytes[31:0];
 always_comb begin idma_src_addr_o=0;idma_dst_addr_o=0;if(opcode_q==APPEND)begin idma_src_addr_o=(st==K_REQ?k_q:v_q)+source_offset;idma_dst_addr_o=page_data_addr+(st==V_REQ?64'd8192:0);end else begin idma_src_addr_o=page_data_addr+(st==V_REQ?64'd8192:0);idma_dst_addr_o=out_q+source_offset+(st==V_REQ?total_bytes_q:0);end end
 assign completion_valid_o=st==COMPLETE;assign completion_tag_o=tag_q;assign completion_parent_phase_o=parent_q;assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;assign bytes_moved_o=bytes_moved_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin st<=IDLE;opcode_q<=0;status_q<=0;tag_q<=0;parent_q<=0;terminal_q<=0;seq_q<=0;layer_q<=0;head_q<=0;token_start_q<=0;token_count_q<=0;generation_q<=0;limit_q<=0;bytes_token_q<=0;processed_q<=0;page_id_q<=0;table_q<=0;data_q<=0;k_q<=0;v_q<=0;out_q<=0;format_q<=0;total_bytes_q<=0;bytes_moved_q<=0;end else case(st)
  IDLE:if(req_valid_i)begin opcode_q<=req_opcode_i;tag_q<=req_tag_i;parent_q<=req_parent_phase_i;terminal_q<=req_terminal_phase_i;status_q<=0;bytes_moved_q<=0;if(req_opcode_i inside{APPEND,GATHER,ALLOC,FREE})st<=CONFIG;else begin status_q<=4;st<=COMPLETE;end end
  CONFIG:if(config_valid_i)begin seq_q<=sequence_id_i;layer_q<=layer_id_i;head_q<=kv_head_id_i;token_start_q<=token_start_i;token_count_q<=token_count_i;generation_q<=generation_i;limit_q<=physical_page_limit_i;bytes_token_q<=bytes_per_token_i;table_q<=table_base_i;data_q<=data_base_i;k_q<=k_address_i;v_q<=v_address_i;out_q<=output_address_i;format_q<=format_i;processed_q<=0;total_bytes_q<=token_count_i*bytes_per_token_i;if(token_count_i==0||bytes_per_token_i==0||bytes_per_token_i>512||physical_page_limit_i<2||table_base_i[3:0]!=0||data_base_i[13:0]!=0||(|config_last_token[32:24]))begin status_q<=RANGE;st<=COMPLETE;end else st<=RESOLVE_ISSUE;end
  RESOLVE_ISSUE:if(resolve_ready)st<=RESOLVE_WAIT;
  RESOLVE_WAIT:if(resolve_done)begin if(resolve_status!=0)begin status_q<=resolve_status;st<=COMPLETE;end else begin page_id_q<=resolve_page;if(opcode_q==APPEND||opcode_q==GATHER)st<=K_REQ;else st<=NEXT;end end
  K_REQ:if(idma_req_ready_i)st<=K_RSP;K_RSP:if(idma_rsp_valid_i)begin if(idma_rsp_error_i)begin status_q<=PROTOCOL;st<=COMPLETE;end else begin bytes_moved_q<=bytes_moved_q+chunk_bytes;st<=V_REQ;end end
  V_REQ:if(idma_req_ready_i)st<=V_RSP;V_RSP:if(idma_rsp_valid_i)begin if(idma_rsp_error_i)begin status_q<=PROTOCOL;st<=COMPLETE;end else begin bytes_moved_q<=bytes_moved_q+chunk_bytes;st<=NEXT;end end
  NEXT:if(processed_q+chunk_tokens>=token_count_q)st<=COMPLETE;else begin processed_q<=processed_q+chunk_tokens;st<=RESOLVE_ISSUE;end
  COMPLETE:if(completion_ready_i)st<=IDLE;default:st<=IDLE;endcase end
endmodule
