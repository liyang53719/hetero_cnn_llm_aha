// SPDX-License-Identifier: Apache-2.0
// Descriptor-driven BF16 Q/K/V projection with two overlapping weight buffers.
`timescale 1ns/1ps
module qwen2_projection_pingpong_top #(
 parameter integer ADDR_W=15
)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[127:0]matrix_command_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,output logic[23:0]descriptor_req_index_o,
 input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
 output logic dma_req_valid_o,input logic dma_req_ready_i,output logic[1:0]dma_req_kind_o,
 output logic[63:0]dma_src_addr_o,dma_dst_addr_o,output logic[31:0]dma_row_bytes_o,dma_rows_o,dma_src_stride_o,dma_dst_stride_o,
 input logic dma_rsp_valid_i,output logic dma_rsp_ready_o,input logic dma_rsp_error_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,
 input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,
 output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
 output logic done_o,output logic[7:0]status_o,output logic[17:0]output_columns_o,
 output logic[5:0]column_tiles_o,output logic[63:0]ddr_read_bytes_o,ddr_write_bytes_o,
 output logic[31:0]l2_read_beats_o,l2_write_beats_o,overlap_cycles_o
);
 logic[127:0]command_q;logic context_start_q,context_valid,context_ready,context_legal;logic[7:0]context_status;
 logic[167:0]proj_addr;logic[215:0]proj_shape;logic[31:0]weight_stride;logic[335:0]plan_addr;
 logic[1:0]pcv,pcr,pload,pdone,pstore_q,prearm_q;logic[1:0][7:0]pstatus;
 logic[1:0]prv,prr,prsv,prsr,prse;logic[1:0][1:0]prkind;logic[1:0][63:0]prsrc,prdst;
 logic[1:0][31:0]prbytes,prrows,prss,prds;logic[1:0][63:0]pread,pwrite,phidden,prmsw,pnorm,pqweight,pqout;
 logic payload_start_q,payload_done,payload_active_q,payload_launched_q;logic[5:0]tile_q,p0tile_q,p1tile_q;logic owner_q;
 logic mpv,mpr,mov,mor,mlast,mcv,merr;logic[2:0]mpctx,moctx;logic mpclear,mplast;logic[255:0]mpa;logic[511:0]mpb;logic[16383:0]macc;logic[55:0]mcd;
 logic m_pending_q,mready,mseen_q,active_q,final_pending_q,dma_active_q,dma_owner_q,dma_select,current_done,current_loaded;
 logic[31:0]payload_reads,payload_writes;logic[63:0]agg_read_q,agg_write_q;logic[31:0]agg_l2r_q,agg_l2w_q;
 qwen2_projection_descriptor_context u_context(.clk_i,.rst_ni,.start_i(context_start_q),.command_i(command_q),
  .descriptor_req_valid_o,.descriptor_req_ready_i,.descriptor_req_index_o,.descriptor_rsp_valid_i,
  .descriptor_rsp_ready_o,.descriptor_rsp_data_i,.descriptor_rsp_error_i,.context_valid_o(context_valid),
  .context_ready_i(context_ready),.context_legal_o(context_legal),.context_status_o(context_status),
  .tensor_address_o(proj_addr),.tensor_shape_o(proj_shape),.output_columns_o,
  .weight_row_bytes_o(weight_stride),.column_tiles_o);
 always_comb begin plan_addr='0;plan_addr[4*56+:56]=proj_addr[1*56+:56];plan_addr[5*56+:56]=proj_addr[2*56+:56];end
 assign pcv[0]=context_valid||prearm_q[0];assign pcv[1]=prearm_q[1];assign context_ready=pcr[0]&&!prearm_q[0];
 for(genvar g=0;g<2;g++)begin:g_plan
  qwen2_tile_dma_plan plan(.clk_i,.rst_ni,.context_valid_i(pcv[g]),.context_ready_o(pcr[g]),
   .context_legal_i(context_legal),.tensor_address_i(plan_addr),.q_column_tile_i(g==0?p0tile_q:p1tile_q),
   .weight_src_stride_i(weight_stride),.full_q_i(1'b1),.reuse_norm_i(1'b1),.start_store_i(pstore_q[g]),
   .dma_req_valid_o(prv[g]),.dma_req_ready_i(prr[g]),.dma_req_kind_o(prkind[g]),
   .dma_src_addr_o(prsrc[g]),.dma_dst_addr_o(prdst[g]),.dma_row_bytes_o(prbytes[g]),
   .dma_rows_o(prrows[g]),.dma_src_stride_o(prss[g]),.dma_dst_stride_o(prds[g]),
   .dma_rsp_valid_i(prsv[g]),.dma_rsp_ready_o(prsr[g]),.dma_rsp_error_i(prse[g]),
   .loads_done_o(pload[g]),.done_o(pdone[g]),.status_o(pstatus[g]),.ddr_read_bytes_o(pread[g]),
   .ddr_write_bytes_o(pwrite[g]),.hidden_local_o(phidden[g]),.rms_weight_local_o(prmsw[g]),
   .norm_local_o(pnorm[g]),.q_weight_local_o(pqweight[g]),.q_output_local_o(pqout[g]));
 end
 assign current_loaded=owner_q?pload[1]:pload[0];assign current_done=owner_q?pdone[1]:pdone[0];
 qwen2_shared_l2_tile_payload #(.ADDR_W(ADDR_W))payload(.clk_i,.rst_ni,.start_i(payload_start_q),
  .reuse_norm_i(tile_q!=0),.load_norm_i(tile_q==0),.hidden_local_i(owner_q?phidden[1]:phidden[0]),
  .rms_weight_local_i(owner_q?prmsw[1]:prmsw[0]),.norm_local_i(owner_q?pnorm[1]:pnorm[0]),
  .q_weight_local_i(owner_q?pqweight[1]:pqweight[0]),.q_output_local_i(owner_q?pqout[1]:pqout[0]),
  .l2_rd_valid_o,.l2_rd_ready_i,.l2_rd_addr_o,.l2_rsp_valid_i,.l2_rsp_ready_o,.l2_rsp_data_i,
  .l2_wr_valid_o,.l2_wr_ready_i,.l2_wr_addr_o,.l2_wr_data_o,.l2_wr_be_o,
  .sfu_payload_valid_o(),.sfu_payload_ready_i(1'b0),.sfu_x_o(),.sfu_weight_o(),
  .sfu_out_valid_i(1'b0),.sfu_out_ready_o(),.sfu_y_i('0),.matrix_step_valid_o(mpv),
  .matrix_step_ready_i(mpr),.matrix_context_o(mpctx),.matrix_clear_o(mpclear),.matrix_last_o(mplast),
  .matrix_a_o(mpa),.matrix_b_o(mpb),.matrix_out_valid_i(mov),.matrix_out_ready_o(mor),
  .matrix_out_last_i(mlast),.matrix_acc_i(macc),.done_o(payload_done),
  .read_beats_o(payload_reads),.write_beats_o(payload_writes));
 qwen2_matrix_command_endpoint matrix(.clk_i,.rst_ni,.cmd_valid_i(m_pending_q),.cmd_ready_o(mready),
  .cmd_i(command_q),.step_valid_i(mpv),.step_ready_o(mpr),.step_context_i(mpctx),.step_clear_i(mpclear),
  .step_last_i(mplast),.command_last_tile_i(tile_q+1==column_tiles_o),.step_a_i(mpa),.step_b_i(mpb),
  .out_valid_o(mov),.out_ready_i(mor),.out_context_o(moctx),.out_last_o(mlast),.out_acc_o(macc),
  .completion_valid_o(mcv),.completion_ready_i(1'b1),.completion_data_o(mcd),.protocol_error_o(merr));
 always_comb begin
  dma_select=owner_q;if(!dma_active_q)begin if(owner_q==0)dma_select=prv[0]?0:1;else dma_select=prv[1]?1:0;end
  dma_req_valid_o=!dma_active_q&&prv[dma_select];dma_req_kind_o=prkind[dma_select];dma_src_addr_o=prsrc[dma_select];dma_dst_addr_o=prdst[dma_select];dma_row_bytes_o=prbytes[dma_select];dma_rows_o=prrows[dma_select];dma_src_stride_o=prss[dma_select];dma_dst_stride_o=prds[dma_select];prr='0;prr[dma_select]=!dma_active_q&&dma_req_ready_i;prsv='0;prse='0;prsv[dma_owner_q]=dma_active_q&&dma_rsp_valid_i;prse[dma_owner_q]=dma_rsp_error_i;dma_rsp_ready_o=dma_active_q&&prsr[dma_owner_q];
 end
 assign done_o=final_pending_q&&mseen_q;assign ddr_read_bytes_o=agg_read_q;assign ddr_write_bytes_o=agg_write_q;assign l2_read_beats_o=agg_l2r_q;assign l2_write_beats_o=agg_l2w_q;
 always_comb begin if(context_status!=0)status_o=context_status;else if(|pstatus)status_o=pstatus[0]|pstatus[1];else if(merr||mcd[39:32]!=0)status_o=7;else status_o=0;end
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin command_q<=0;context_start_q<=0;prearm_q<=0;pstore_q<=0;payload_start_q<=0;payload_active_q<=0;payload_launched_q<=0;tile_q<=0;p0tile_q<=0;p1tile_q<=1;owner_q<=0;m_pending_q<=0;mseen_q<=0;active_q<=0;final_pending_q<=0;dma_active_q<=0;dma_owner_q<=0;agg_read_q<=0;agg_write_q<=0;agg_l2r_q<=0;agg_l2w_q<=0;overlap_cycles_o<=0;
  end else begin context_start_q<=0;pstore_q<=0;payload_start_q<=0;
   if(start_i&&!active_q)begin command_q<=matrix_command_i;context_start_q<=1;tile_q<=0;p0tile_q<=0;p1tile_q<=1;owner_q<=0;m_pending_q<=1;mseen_q<=0;active_q<=1;final_pending_q<=0;payload_launched_q<=0;agg_read_q<=0;agg_write_q<=0;agg_l2r_q<=0;agg_l2w_q<=0;overlap_cycles_o<=0;end
   if(prearm_q[0]&&pcr[0])prearm_q[0]<=0;if(prearm_q[1]&&pcr[1])prearm_q[1]<=0;if(m_pending_q&&mready)m_pending_q<=0;if(mcv)mseen_q<=1;
   if(dma_req_valid_o&&dma_req_ready_i)begin dma_active_q<=1;dma_owner_q<=dma_select;end if(dma_active_q&&dma_rsp_valid_i&&dma_rsp_ready_o)dma_active_q<=0;if(payload_active_q&&dma_active_q)overlap_cycles_o<=overlap_cycles_o+1;
   if(current_loaded&&!payload_launched_q&&!m_pending_q)begin payload_start_q<=1;payload_active_q<=1;payload_launched_q<=1;if(tile_q==0&&column_tiles_o>1)prearm_q[1]<=1;end
   if(payload_done)begin payload_active_q<=0;pstore_q[owner_q]<=1;end
   if(current_done)begin agg_read_q<=agg_read_q+(owner_q?pread[1]:pread[0]);agg_write_q<=agg_write_q+(owner_q?pwrite[1]:pwrite[0]);agg_l2r_q<=agg_l2r_q+payload_reads;agg_l2w_q<=agg_l2w_q+payload_writes;
    if(tile_q+1==column_tiles_o)final_pending_q<=1;else begin payload_launched_q<=0;if(owner_q==0)begin owner_q<=1;tile_q<=tile_q+1;if(tile_q+2<column_tiles_o)begin p0tile_q<=tile_q+2;prearm_q[0]<=1;end end else begin owner_q<=0;tile_q<=tile_q+1;if(tile_q+2<column_tiles_o)begin p1tile_q<=tile_q+2;prearm_q[1]<=1;end end end
   end if(done_o)active_q<=0;
  end
 end
endmodule
