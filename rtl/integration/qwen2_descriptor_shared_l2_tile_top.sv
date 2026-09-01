// SPDX-License-Identifier: Apache-2.0
// Monolithic two-command descriptor -> DMA plan -> Shared-L2 -> SFU/Matrix tile path.
`timescale 1ns/1ps
module qwen2_descriptor_shared_l2_tile_top #(
  parameter integer ADDR_W=15
)(
  input logic clk_i,input logic rst_ni,input logic start_i,
  input logic[127:0]rms_command_i,input logic[127:0]matrix_command_i,
  output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,
  output logic[23:0]descriptor_req_index_o,input logic descriptor_rsp_valid_i,
  output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,
  input logic descriptor_rsp_error_i,
  output logic dma_req_valid_o,input logic dma_req_ready_i,output logic[1:0]dma_req_kind_o,
  output logic[63:0]dma_src_addr_o,dma_dst_addr_o,output logic[31:0]dma_row_bytes_o,
  output logic[31:0]dma_rows_o,dma_src_stride_o,dma_dst_stride_o,
  input logic dma_rsp_valid_i,output logic dma_rsp_ready_o,input logic dma_rsp_error_i,
  output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,
  input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
  output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,
  output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
  output logic done_o,output logic[7:0]status_o,output logic[63:0]ddr_read_bytes_o,
  output logic[63:0]ddr_write_bytes_o,output logic[31:0]l2_read_beats_o,
  output logic[31:0]l2_write_beats_o
);
  logic[127:0]rms_q,matrix_q;logic context_start_q,context_valid,context_ready,context_legal;
  logic[7:0]context_status;logic[335:0]addresses;logic[23:0]dtypes;logic[431:0]shapes;logic[143:0]roots;
  logic store_start_q,loads_done,plan_done;logic[7:0]plan_status;logic payload_start_q,payload_done,payload_started_q;
  logic[63:0]hidden_local,rms_weight_local,norm_local,q_weight_local,q_output_local;
  logic s_cmd_pending_q,m_cmd_pending_q,s_cmd_ready,m_cmd_ready;
  logic spv,spr,sov,sor,scv;logic[49151:0]sx,sw,sy;logic[55:0]scd;logic[4:0]sflags;
  logic mpv,mpr,mov,mor,mlast,mcv,merr;logic[2:0]mpctx,moctx;logic mpclear,mplast;
  logic[255:0]mpa;logic[511:0]mpb;logic[16383:0]macc;logic[55:0]mcd;
  logic scomp_seen_q,mcomp_seen_q,active_q;
  qwen2_descriptor_tile_context u_context(.clk_i,.rst_ni,.start_i(context_start_q),.rms_command_i(rms_q),
    .matrix_command_i(matrix_q),.descriptor_req_valid_o,.descriptor_req_ready_i,.descriptor_req_index_o,
    .descriptor_rsp_valid_i,.descriptor_rsp_ready_o,.descriptor_rsp_data_i,.descriptor_rsp_error_i,
    .context_valid_o(context_valid),.context_ready_i(context_ready),.context_legal_o(context_legal),
    .context_status_o(context_status),.tensor_address_o(addresses),.tensor_dtype_o(dtypes),
    .tensor_shape_o(shapes),.tensor_root_o(roots));
  qwen2_tile_dma_plan plan(.clk_i,.rst_ni,.context_valid_i(context_valid),.context_ready_o(context_ready),
    .context_legal_i(context_legal),.tensor_address_i(addresses),.start_store_i(store_start_q),
    .dma_req_valid_o,.dma_req_ready_i,.dma_req_kind_o,.dma_src_addr_o,.dma_dst_addr_o,
    .dma_row_bytes_o,.dma_rows_o,.dma_src_stride_o,.dma_dst_stride_o,.dma_rsp_valid_i,
    .dma_rsp_ready_o,.dma_rsp_error_i,.loads_done_o(loads_done),.done_o(plan_done),
    .status_o(plan_status),.ddr_read_bytes_o,.ddr_write_bytes_o,.hidden_local_o(hidden_local),
    .rms_weight_local_o(rms_weight_local),.norm_local_o(norm_local),.q_weight_local_o(q_weight_local),
    .q_output_local_o(q_output_local));
  qwen2_shared_l2_tile_payload #(.ADDR_W(ADDR_W))payload(.clk_i,.rst_ni,.start_i(payload_start_q),
    .hidden_local_i(hidden_local),.rms_weight_local_i(rms_weight_local),.norm_local_i(norm_local),
    .q_weight_local_i(q_weight_local),.q_output_local_i(q_output_local),.l2_rd_valid_o,
    .l2_rd_ready_i,.l2_rd_addr_o,.l2_rsp_valid_i,.l2_rsp_ready_o,.l2_rsp_data_i,
    .l2_wr_valid_o,.l2_wr_ready_i,.l2_wr_addr_o,.l2_wr_data_o,.l2_wr_be_o,
    .sfu_payload_valid_o(spv),.sfu_payload_ready_i(spr),.sfu_x_o(sx),.sfu_weight_o(sw),
    .sfu_out_valid_i(sov),.sfu_out_ready_o(sor),.sfu_y_i(sy),.matrix_step_valid_o(mpv),
    .matrix_step_ready_i(mpr),.matrix_context_o(mpctx),.matrix_clear_o(mpclear),
    .matrix_last_o(mplast),.matrix_a_o(mpa),.matrix_b_o(mpb),.matrix_out_valid_i(mov),
    .matrix_out_ready_o(mor),.matrix_out_last_i(mlast),.matrix_acc_i(macc),.done_o(payload_done),
    .read_beats_o(l2_read_beats_o),.write_beats_o(l2_write_beats_o));
  qwen2_sfu_command_endpoint sfu(.clk_i,.rst_ni,.cmd_valid_i(s_cmd_pending_q),.cmd_ready_o(s_cmd_ready),
    .cmd_i(rms_q),.payload_valid_i(spv),.payload_ready_o(spr),.payload_x_i(sx),.payload_weight_i(sw),
    .out_valid_o(sov),.out_ready_i(sor),.out_y_o(sy),.completion_valid_o(scv),
    .completion_ready_i(1'b1),.completion_data_o(scd),.exception_flags_o(sflags));
  qwen2_matrix_command_endpoint matrix(.clk_i,.rst_ni,.cmd_valid_i(m_cmd_pending_q),.cmd_ready_o(m_cmd_ready),
    .cmd_i(matrix_q),.step_valid_i(mpv),.step_ready_o(mpr),.step_context_i(mpctx),
    .step_clear_i(mpclear),.step_last_i(mplast),.step_a_i(mpa),.step_b_i(mpb),
    .out_valid_o(mov),.out_ready_i(mor),.out_context_o(moctx),.out_last_o(mlast),
    .out_acc_o(macc),.completion_valid_o(mcv),.completion_ready_i(1'b1),
    .completion_data_o(mcd),.protocol_error_o(merr));
  assign done_o=plan_done&&((scomp_seen_q&&mcomp_seen_q)||plan_status!=0);
  always_comb begin
    if(context_status!=0)status_o=context_status;else if(plan_status!=0)status_o=plan_status;
    else if(merr||sflags[4:1]||scd[39:32]!=0||mcd[39:32]!=0)status_o=8'd7;else status_o=0;
  end
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin rms_q<=0;matrix_q<=0;context_start_q<=0;store_start_q<=0;payload_start_q<=0;
      payload_started_q<=0;s_cmd_pending_q<=0;m_cmd_pending_q<=0;scomp_seen_q<=0;mcomp_seen_q<=0;active_q<=0;
    end else begin
      context_start_q<=0;store_start_q<=0;payload_start_q<=0;
      if(start_i&&!active_q)begin rms_q<=rms_command_i;matrix_q<=matrix_command_i;context_start_q<=1;
        s_cmd_pending_q<=1;m_cmd_pending_q<=1;scomp_seen_q<=0;mcomp_seen_q<=0;payload_started_q<=0;active_q<=1;end
      if(s_cmd_pending_q&&s_cmd_ready)s_cmd_pending_q<=0;if(m_cmd_pending_q&&m_cmd_ready)m_cmd_pending_q<=0;
      if(scv)scomp_seen_q<=1;if(mcv)mcomp_seen_q<=1;
      if(loads_done&&!payload_started_q&&!s_cmd_pending_q&&!m_cmd_pending_q)begin payload_start_q<=1;payload_started_q<=1;end
      if(payload_done)store_start_q<=1;
      if(done_o)active_q<=0;
    end
  end
endmodule
