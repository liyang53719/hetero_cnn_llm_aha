// SPDX-License-Identifier: Apache-2.0
// One formal Q/K/V command, all 32-column tiles, sixteen output rows.
`timescale 1ns/1ps
module qwen2_projection_tile16_controller #(
 parameter integer ADDR_W=15,
 parameter bit EXPERIMENTAL_QK_NORM_ROPE=1'b0,
 parameter longint unsigned CANDIDATE_L2_BEATS=
  ADDR_W<15 ? (64'd1<<ADDR_W) : 64'd24576
)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[127:0]command_i,input logic[31:0]token_base_i,input logic[63:0]activation_local_i,weight_local_i,output_local_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,output logic[23:0]descriptor_req_index_o,input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
 output logic dma_req_valid_o,input logic dma_req_ready_i,output logic[1:0]dma_req_kind_o,output logic[63:0]dma_src_addr_o,dma_dst_addr_o,output logic[31:0]dma_row_bytes_o,dma_rows_o,dma_src_stride_o,dma_dst_stride_o,input logic dma_rsp_valid_i,output logic dma_rsp_ready_o,input logic dma_rsp_error_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic done_o,output logic[7:0]status_o,output logic[17:0]output_columns_o,output logic[5:0]column_tiles_o,output logic[31:0]matrix_steps_o,output logic[63:0]ddr_read_bytes_o,ddr_write_bytes_o,
 // Candidate-only descriptor bridge: one selected token and one Q/K head.
 input logic[1:0]candidate_role_i,input logic[15:0]candidate_head_i,
 input logic[7:0]candidate_policy_i,
 input logic[63:0]candidate_norm_weight_local_i,candidate_norm_output_local_i,
 input logic[63:0]candidate_rope_output_local_i,candidate_trig_local_i,
 input logic candidate_l2_rsp_error_i,candidate_l2_wr_rsp_valid_i,
 input logic candidate_l2_wr_rsp_error_i,
 output logic candidate_l2_wr_rsp_ready_o,output logic ready_o,
 output logic[4:0]candidate_exception_flags_o,
 output logic[3:0]candidate_norm_status_o,
 output logic[31:0]candidate_mean_eps_o,candidate_inv_o,
 input logic candidate_tensor_i,input logic candidate_tile16_i,input logic[7:0]candidate_token_count_i,
 input logic[63:0]candidate_norm_output_ddr_i,candidate_rope_output_ddr_i,
 output logic[7:0]candidate_total_column_tiles_o,
 output logic[15:0]candidate_completed_heads_o,
 output logic[7:0]candidate_completed_tokens_o
);
 // Retain the legacy diagnostic hierarchy used by existing watchdogs.
 wire[4:0]st;
 wire mpv,mpr;
 generate if(EXPERIMENTAL_QK_NORM_ROPE)begin:g_qk_candidate
  qwen2_projection_qk_norm_rope_candidate #(.ADDR_W(ADDR_W),
   .L2_BEATS(CANDIDATE_L2_BEATS)) candidate(.*);
 // Avoid hierarchical references into an unelaborated optional module:
 // legacy source lists need not include any candidate dependency.
 assign st='0;assign mpv=1'b0;assign mpr=1'b0;
 end else begin:g_legacy
 typedef enum logic[3:0]{I,CW,WQ,WP,PQ,PP,SQ,SP,FIN,D}st_e;st_e legacy_st;logic cs,cv,cr,cl;logic[7:0]cstatus;logic[167:0]addr;logic[215:0]shape;logic[31:0]weight_stride,token_base_safe;logic[5:0]tile_q;logic ps,pd;logic[7:0]pstatus;logic[31:0]pread,pwrite,psteps;logic legacy_mpv,legacy_mpr,mc,ml,mov,mor,mol,mcv,merr,cmd_pending,mseen;logic[2:0]mctx,moctx;logic[255:0]ma;logic[511:0]mb;logic[16383:0]macc;logic[55:0]mcd;always_comb token_base_safe=(^token_base_i===1'bx)?0:token_base_i;
 qwen2_projection_descriptor_context u_context(.clk_i,.rst_ni,.start_i(cs),.command_i,.descriptor_req_valid_o,.descriptor_req_ready_i,.descriptor_req_index_o,.descriptor_rsp_valid_i,.descriptor_rsp_ready_o,.descriptor_rsp_data_i,.descriptor_rsp_error_i,.context_valid_o(cv),.context_ready_i(cr),.context_legal_o(cl),.context_status_o(cstatus),.tensor_address_o(addr),.tensor_shape_o(shape),.output_columns_o,.weight_row_bytes_o(weight_stride),.column_tiles_o);assign cr=legacy_st==CW;
 qwen2_shared_l2_matrix_tile16_payload payload(.output_fp32_i(1'b0),.depth_i(16'd1536),.weight_k_stride_i(32'd64),.rows_i(16'd16),.columns_i(16'd32),.status_o(pstatus),.clk_i,.rst_ni,.start_i(ps),.activation_local_i,.weight_local_i,.output_local_i,.l2_rd_valid_o,.l2_rd_ready_i,.l2_rd_addr_o,.l2_rsp_valid_i,.l2_rsp_ready_o,.l2_rsp_data_i,.l2_wr_valid_o,.l2_wr_ready_i,.l2_wr_addr_o,.l2_wr_data_o,.l2_wr_be_o,.matrix_step_valid_o(legacy_mpv),.matrix_step_ready_i(legacy_mpr),.matrix_context_o(mctx),.matrix_clear_o(mc),.matrix_last_o(ml),.matrix_a_o(ma),.matrix_b_o(mb),.matrix_out_valid_i(mov),.matrix_out_ready_o(mor),.matrix_out_last_i(mol),.matrix_acc_i(macc),.done_o(pd),.read_beats_o(pread),.write_beats_o(pwrite),.matrix_steps_o(psteps));
 qwen2_matrix_command_endpoint matrix(.clk_i,.rst_ni,.cmd_valid_i(cmd_pending),.cmd_ready_o(),.cmd_i(command_i),.step_valid_i(legacy_mpv),.step_ready_o(legacy_mpr),.step_context_i(mctx),.step_clear_i(mc),.step_last_i(ml),.command_last_tile_i(tile_q+1==column_tiles_o),.step_a_i(ma),.step_b_i(mb),.out_valid_o(mov),.out_ready_i(mor),.out_context_o(moctx),.out_last_o(mol),.out_acc_o(macc),.completion_valid_o(mcv),.completion_ready_i(1'b1),.completion_data_o(mcd),.protocol_error_o(merr));
 assign dma_req_valid_o=legacy_st==WQ||legacy_st==SQ;assign dma_req_kind_o=legacy_st==WQ?1:3;assign dma_src_addr_o=legacy_st==WQ?{8'd0,addr[56+:56]}+64'(tile_q)*64:output_local_i;assign dma_dst_addr_o=legacy_st==WQ?weight_local_i:{8'd0,addr[112+:56]}+64'(token_base_safe)*output_columns_o*2+64'(tile_q)*64;assign dma_row_bytes_o=64;assign dma_rows_o=legacy_st==WQ?1536:16;assign dma_src_stride_o=legacy_st==WQ?weight_stride:64;assign dma_dst_stride_o=legacy_st==WQ?64:{13'd0,output_columns_o,1'b0};assign dma_rsp_ready_o=legacy_st==WP||legacy_st==SP;assign done_o=legacy_st==D;
 always_comb begin if(cstatus!=0)status_o=cstatus;else if(pstatus!=0)status_o=pstatus;else if(merr||mcd[39:32]!=0)status_o=7;else status_o=0;end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin legacy_st<=I;cs<=0;ps<=0;tile_q<=0;cmd_pending<=0;mseen<=0;matrix_steps_o<=0;ddr_read_bytes_o<=0;ddr_write_bytes_o<=0;end else begin cs<=0;ps<=0;if(mcv)mseen<=1;case(legacy_st)
  I:if(start_i)begin cs<=1;tile_q<=0;cmd_pending<=1;mseen<=0;matrix_steps_o<=0;ddr_read_bytes_o<=0;ddr_write_bytes_o<=0;legacy_st<=CW;end
  CW:if(cv&&cr)begin if(cl)legacy_st<=WQ;else legacy_st<=D;end WQ:if(dma_req_valid_o&&dma_req_ready_i)legacy_st<=WP;WP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)legacy_st<=D;else begin ddr_read_bytes_o<=ddr_read_bytes_o+98304;ps<=1;legacy_st<=PQ;end end
  PQ:begin cmd_pending<=0;legacy_st<=PP;end PP:if(pd)begin matrix_steps_o<=matrix_steps_o+psteps; legacy_st<=pstatus!=0?D:SQ;end SQ:if(dma_req_valid_o&&dma_req_ready_i)legacy_st<=SP;SP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin if(dma_rsp_error_i)legacy_st<=D;else begin ddr_write_bytes_o<=ddr_write_bytes_o+1024;if(tile_q+1==column_tiles_o)legacy_st<=FIN;else begin tile_q<=tile_q+1;legacy_st<=WQ;end end end FIN:if(mseen)legacy_st<=D;D:legacy_st<=I;default:legacy_st<=I;endcase end end
 assign st={1'b0,legacy_st};
 assign mpv=legacy_mpv;assign mpr=legacy_mpr;
 assign ready_o=rst_ni&&legacy_st==I;
 assign candidate_l2_wr_rsp_ready_o=1'b0;
 assign candidate_exception_flags_o='0;
 assign candidate_norm_status_o='0;
 assign candidate_mean_eps_o='0;
 assign candidate_inv_o='0;
 assign candidate_total_column_tiles_o='0;
 assign candidate_completed_heads_o='0;
 assign candidate_completed_tokens_o='0;
 end endgenerate
endmodule
