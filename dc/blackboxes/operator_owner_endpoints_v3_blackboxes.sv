module operator_control_endpoint_v3 #(
  parameter int DOMAINS = 10,
  parameter int DOMAIN_W = $clog2(DOMAINS)
) (
  input  logic                 clk_i,
  input  logic                 rst_ni,
  input  logic                 req_valid_i,
  output logic                 req_ready_o,
  input  logic [7:0]           req_opcode_i,
  input  logic [15:0]          req_tag_i,
  input  logic [7:0]           req_parent_phase_i,
  input  logic [7:0]           req_terminal_phase_i,
  input  logic [15:0]          req_index0_i,
  input  logic                 ack_valid_i,
  input  logic [DOMAIN_W-1:0]  ack_domain_i,
  input  logic                 fail_valid_i,
  output logic                 completion_valid_o,
  input  logic                 completion_ready_i,
  output logic [15:0]          completion_tag_o,
  output logic [7:0]           completion_parent_phase_o,
  output logic [7:0]           completion_terminal_phase_o,
  output logic [7:0]           completion_status_o,
  output logic                 protocol_error_o
);
endmodule

module operator_dma_endpoint_v3 (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        req_valid_i,
  output logic        req_ready_o,
  input  logic [7:0]  req_opcode_i,
  input  logic [15:0] req_tag_i,
  input  logic [7:0]  req_parent_phase_i,
  input  logic [7:0]  req_terminal_phase_i,
  input  logic [23:0] req_src0_i,
  input  logic [23:0] req_dst_i,
  input  logic [15:0] req_rows_i,
  output logic        descriptor_req_valid_o,
  input  logic        descriptor_req_ready_i,
  output logic [23:0] descriptor_req_index_o,
  output logic        descriptor_req_destination_o,
  input  logic        descriptor_rsp_valid_i,
  output logic        descriptor_rsp_ready_o,
  input  logic [7:0]  descriptor_rsp_status_i,
  input  logic [63:0] descriptor_rsp_address_i,
  input  logic [31:0] descriptor_rsp_row_bytes_i,
  input  logic [31:0] descriptor_rsp_rows_i,
  input  logic [31:0] descriptor_rsp_stride_i,
  output logic        idma_req_valid_o,
  input  logic        idma_req_ready_i,
  output logic [63:0] idma_src_addr_o,
  output logic [63:0] idma_dst_addr_o,
  output logic [31:0] idma_length_o,
  input  logic        idma_rsp_valid_i,
  output logic        idma_rsp_ready_o,
  input  logic        idma_rsp_error_i,
  output logic        completion_valid_o,
  input  logic        completion_ready_i,
  output logic [15:0] completion_tag_o,
  output logic [7:0]  completion_parent_phase_o,
  output logic [7:0]  completion_terminal_phase_o,
  output logic [7:0]  completion_status_o,
  output logic [31:0] flat_requests_o
);
endmodule

module operator_matrix_owner_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,input logic[15:0]req_flags_i,req_rows_i,req_columns_i,req_depth_i,input logic[23:0]req_src0_i,req_src1_i,req_dst_i,
 input logic step_valid_i,output logic step_ready_o,input logic[2:0]step_context_i,input logic step_clear_i,step_last_i,input logic[255:0]step_a_i,input logic[511:0]step_b_i,output logic out_valid_o,input logic out_ready_i,output logic[2:0]out_context_o,output logic out_last_o,output logic[16383:0]out_acc_o,output logic[4:0]exception_flags_o,
 output logic conv_command_valid_o,input logic conv_command_ready_i,output logic[127:0]conv_command_data_o,input logic conv_event_valid_i,output logic conv_event_ready_o,input logic[55:0]conv_event_data_i,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o,output logic protocol_error_o);
endmodule

module operator_sfu_owner_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,req_variant_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic req_scratch_valid_i,input logic[3:0]req_scratch_src0_i,req_scratch_src1_i,req_scratch_dst_i,input logic req_first_i,req_last_i,
 input logic payload_valid_i,output logic payload_ready_o,input logic[511:0]payload_a_i,payload_b_i,payload_c_i,
 input logic[15:0]payload_mask_i,input logic[31:0]payload_epsilon_i,input logic payload_last_i,
 output logic result_valid_o,input logic result_ready_i,output logic[511:0]result_data_o,output logic result_last_o,
 output logic[12:0]exception_flags_o,output logic domain_error_o,
 input logic soft_score_valid_i,output logic soft_score_ready_o,input logic[31:0]soft_score_i,input logic soft_score_mask_i,
 input logic soft_merge_header_valid_i,output logic soft_merge_header_ready_o,input logic[31:0]soft_ma_i,soft_la_i,soft_mb_i,soft_lb_i,
 input logic soft_merge_beat_valid_i,output logic soft_merge_beat_ready_o,input logic[127:0]soft_oa_i,soft_ob_i,input logic soft_merge_beat_last_i,
 output logic soft_header_valid_o,input logic soft_header_ready_i,output logic[31:0]soft_m_o,soft_l_o,
 output logic soft_weight_valid_o,input logic soft_weight_ready_i,output logic[31:0]soft_weight_o,output logic soft_weight_last_o,
 output logic soft_beat_valid_o,input logic soft_beat_ready_i,output logic[127:0]soft_o_o,output logic soft_beat_last_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
endmodule

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
endmodule

module operator_state_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,req_variant_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic config_valid_i,output logic config_ready_o,input logic[63:0]state_address_i,window_base_i,state_stride_i,
 input logic[511:0]write_data_i,input logic[31:0]decay_i,input logic[127:0]conv_weights_i,
 output logic mem_req_valid_o,input logic mem_req_ready_i,output logic mem_req_write_o,output logic[63:0]mem_req_addr_o,
 output logic[511:0]mem_req_wdata_o,output logic[63:0]mem_req_wstrb_o,input logic mem_rsp_valid_i,output logic mem_rsp_ready_o,input logic[511:0]mem_rsp_rdata_i,input logic mem_rsp_error_i,
 output logic result_valid_o,input logic result_ready_i,output logic[511:0]result_data_o,output logic[4:0]exception_flags_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o,output logic[15:0]generation_o);
endmodule

module operator_selection_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic config_valid_i,output logic config_ready_o,input logic[19:0]topk_item_count_i,input logic[8:0]topk_k_i,
 input logic[63:0]expand_base_i,expand_stride_i,input logic[31:0]route_token_i,input logic[4:0]route_count_i,
 input logic[18:0]pool_blocks_i,input logic[4:0]pool_ratio_i,input logic[8:0]pool_dimensions_i,input logic[5:0]mtp_step_count_i,
 input logic score_valid_i,output logic score_ready_o,input logic[31:0]score_i,score_index_i,
 output logic ranked_valid_o,input logic ranked_ready_i,output logic[31:0]ranked_score_o,ranked_index_o,output logic[8:0]ranked_rank_o,output logic ranked_last_o,
 output logic topk_sram_req_valid_o,input logic topk_sram_req_ready_i,output logic topk_sram_req_write_o,output logic[8:0]topk_sram_req_addr_o,output logic[64:0]topk_sram_req_wdata_o,input logic topk_sram_rsp_valid_i,output logic topk_sram_rsp_ready_o,input logic[64:0]topk_sram_rsp_rdata_i,input logic topk_sram_rsp_error_i,
 input logic expand_valid_i,output logic expand_ready_o,input logic[31:0]expand_index_i,input logic[8:0]expand_rank_i,input logic expand_last_i,output logic expand_out_valid_o,input logic expand_out_ready_i,output logic[63:0]expand_address_o,output logic[8:0]expand_out_rank_o,output logic expand_out_last_o,
 input logic route_valid_i,output logic route_ready_o,input logic[9:0]route_expert_i,input logic[31:0]route_weight_i,input logic route_shared_i,output logic dispatch_valid_o,input logic dispatch_ready_i,output logic[31:0]dispatch_token_o,output logic[9:0]dispatch_expert_o,output logic[31:0]dispatch_weight_o,output logic[3:0]dispatch_tag_o,output logic dispatch_shared_o,dispatch_last_o,
 input logic merge_result_valid_i,output logic merge_result_ready_o,input logic[3:0]merge_result_tag_i,input logic[511:0]merge_result_data_i,output logic merge_valid_o,input logic merge_ready_i,output logic[3:0]merge_tag_o,output logic[31:0]merge_weight_o,output logic[511:0]merge_data_o,output logic merge_first_o,merge_last_o,
 output logic pool_valid_o,input logic pool_ready_i,output logic[17:0]pool_block_o,output logic[21:0]pool_token_o,output logic[7:0]pool_dimension_o,output logic pool_first_token_o,pool_last_token_o,pool_last_dimension_o,pool_last_o,
 input logic mtp_valid_i,output logic mtp_ready_o,input logic[31:0]mtp_draft_i,mtp_target_i,input logic[5:0]mtp_step_i,input logic mtp_last_i,output logic mtp_result_valid_o,input logic mtp_result_ready_i,output logic[5:0]mtp_accepted_o,mtp_mismatch_step_o,output logic mtp_all_match_o,mtp_rollback_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o,output logic completion_predicate_o);
endmodule

module operator_vision_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic config_valid_i,output logic config_ready_o,input logic[31:0]cfg0_i,cfg1_i,cfg2_i,cfg3_i,cfg4_i,cfg5_i,cfg6_i,cfg7_i,cfg8_i,cfg9_i,
 input logic[191:0]cfg_multipliers_i,input logic[511:0]cfg_head_sizes_i,cfg_head_offsets_i,
 input logic ple_valid_i,output logic ple_ready_o,input logic[31:0]ple_token_i,ple_position_i,input logic ple_last_i,
 output logic map_valid_o,input logic map_ready_i,output logic[255:0]map_data_o,output logic map_last_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
endmodule
