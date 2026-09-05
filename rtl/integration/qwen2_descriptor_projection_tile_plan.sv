// SPDX-License-Identifier: Apache-2.0
// Preserve the existing public descriptor parser and delegate tile enumeration.
// This planning adapter is not a DMA/Matrix payload engine.
module qwen2_descriptor_projection_tile_plan(
 input logic clk_i,rst_ni,request_valid_i,output logic request_ready_o,
 input logic[127:0]command_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,
 output logic[23:0]descriptor_req_index_o,input logic descriptor_rsp_valid_i,
 output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
 output logic tile_valid_o,input logic tile_ready_i,output logic[31:0]row_o,column_o,
 output logic[15:0]rows_o,columns_o,depth_o,output logic[63:0]a_addr_o,b_addr_o,c_addr_o,
 input logic tile_done_valid_i,output logic tile_done_ready_o,input logic[7:0]tile_status_i,
 output logic completion_valid_o,input logic completion_ready_i,output logic[7:0]status_o,
 output logic[63:0]completed_tiles_o,useful_macs_o
);
 typedef enum logic[1:0]{IDLE,FETCH,RUN,ERROR}state_t;state_t state_q;
 logic cv,cr,cl,ir,iv,iterator_request,iterator_complete_ready;logic[7:0]ds,is;
 logic[63:0]iterator_tiles,iterator_macs;
 logic[167:0]addr;logic[215:0]shape;logic[17:0]cols;logic[31:0]stride;logic[5:0]tiles;
 qwen2_projection_descriptor_context decoder(
  .clk_i,.rst_ni,.start_i(request_valid_i&&request_ready_o),.command_i,
  .descriptor_req_valid_o,.descriptor_req_ready_i,.descriptor_req_index_o,
  .descriptor_rsp_valid_i,.descriptor_rsp_ready_o,.descriptor_rsp_data_i,.descriptor_rsp_error_i,
  .context_valid_o(cv),.context_ready_i(cr),.context_legal_o(cl),.context_status_o(ds),
  .tensor_address_o(addr),.tensor_shape_o(shape),.output_columns_o(cols),
  .weight_row_bytes_o(stride),.column_tiles_o(tiles));
 assign request_ready_o=state_q==IDLE;
 assign cr=state_q==FETCH&&(!cl||ir);
 assign completion_valid_o=state_q==ERROR||(state_q==RUN&&iv);
 assign status_o=state_q==ERROR?ds:is;
 assign completed_tiles_o=state_q==ERROR?0:iterator_tiles;
 assign useful_macs_o=state_q==ERROR?0:iterator_macs;
 assign iterator_request=state_q==FETCH&&cv&&cl;
 assign iterator_complete_ready=completion_ready_i&&state_q==RUN;
 bf16_projection_tile_iterator iterator(
  .clk_i,.rst_ni,.request_valid_i(iterator_request),.request_ready_o(ir),
  .m_i({14'd0,shape[0+:18]}),.n_i({14'd0,cols}),.k_i({14'd0,shape[18+:18]}),
  .a_stride_i({13'd0,shape[18+:18],1'b0}),.b_stride_i(stride),.c_stride_i(stride),
  .a_base_i({8'd0,addr[0+:56]}),.b_base_i({8'd0,addr[56+:56]}),.c_base_i({8'd0,addr[112+:56]}),
  .tile_valid_o,.tile_ready_i,.row_o,.column_o,.rows_o,.columns_o,.depth_o,
  .a_addr_o,.b_addr_o,.c_addr_o,.tile_done_valid_i,.tile_done_ready_o,.tile_status_i,
  .completion_valid_o(iv),.completion_ready_i(iterator_complete_ready),
  .status_o(is),.completed_tiles_o(iterator_tiles),.useful_macs_o(iterator_macs));
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)state_q<=IDLE;
  else case(state_q)
   IDLE:if(request_valid_i)state_q<=FETCH;
   FETCH:if(cv&&cr)state_q<=cl?RUN:ERROR;
   RUN,ERROR:if(completion_valid_o&&completion_ready_i)state_q<=IDLE;
   default:state_q<=IDLE;
  endcase
 end
endmodule
