// SPDX-License-Identifier: Apache-2.0
// Generic BF16 Matrix projection tensor/shape snapshot for Q, K, or V.
`timescale 1ns/1ps
module qwen2_projection_descriptor_context #(parameter bit ALLOW_FP32_OUTPUT=0)(
 input logic clk_i,input logic rst_ni,input logic start_i,input logic[127:0]command_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,output logic[23:0]descriptor_req_index_o,
 input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
 output logic context_valid_o,input logic context_ready_i,output logic context_legal_o,output logic[7:0]context_status_o,
 output logic[3*56-1:0]tensor_address_o,output logic[3*72-1:0]tensor_shape_o,
 output logic[17:0]output_columns_o,output logic[31:0]weight_row_bytes_o,output logic[5:0]column_tiles_o,
 output logic output_fp32_o
);
 localparam logic[7:0]OK=0,MALFORMED=2,FETCH=3,UNSUPPORTED=4;
 typedef enum logic[2:0]{S_IDLE,S_ROOT_REQ,S_ROOT_RSP,S_SHAPE_REQ,S_SHAPE_RSP,S_VALIDATE,S_CONTEXT}state_e;
 state_e state_q;logic[1:0]slot_q;logic[7:0]status_q;logic[23:0]roots_q[0:2],shape_index_q;
 logic[55:0]addr_q[0:2];logic[71:0]shape_q[0:2];integer comb_c,seq_c;
 assign descriptor_req_valid_o=state_q==S_ROOT_REQ||state_q==S_SHAPE_REQ;
 assign descriptor_req_index_o=state_q==S_ROOT_REQ?roots_q[slot_q]:shape_index_q;
 assign descriptor_rsp_ready_o=state_q==S_ROOT_RSP||state_q==S_SHAPE_RSP;
 assign context_valid_o=state_q==S_CONTEXT;assign context_legal_o=status_q==OK;assign context_status_o=status_q;
 assign output_columns_o=shape_q[2][35:18];assign weight_row_bytes_o={13'd0,shape_q[1][35:18],1'b0};
 assign column_tiles_o=6'((output_columns_o+31)/32);
 always_comb begin tensor_address_o='0;tensor_shape_o='0;for(comb_c=0;comb_c<3;comb_c++)begin tensor_address_o[comb_c*56+:56]=addr_q[comb_c];tensor_shape_o[comb_c*72+:72]=shape_q[comb_c];end end
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=S_IDLE;slot_q<=0;status_q<=OK;shape_index_q<=0;output_fp32_o<=0;for(seq_c=0;seq_c<3;seq_c++)begin roots_q[seq_c]<=24'hffffff;addr_q[seq_c]<=0;shape_q[seq_c]<=0;end end
  else case(state_q)
   S_IDLE:if(start_i)begin roots_q[0]<=command_i[79:56];roots_q[1]<=command_i[103:80];roots_q[2]<=command_i[127:104];slot_q<=0;status_q<=OK;output_fp32_o<=0;
    if(command_i[7:0]!=8'h20||command_i[10:8]!=3'd2||command_i[79:56]==24'hffffff||command_i[103:80]==24'hffffff||command_i[127:104]==24'hffffff)begin status_q<=MALFORMED;state_q<=S_CONTEXT;end else state_q<=S_ROOT_REQ;end
   S_ROOT_REQ:if(descriptor_req_valid_o&&descriptor_req_ready_i)state_q<=S_ROOT_RSP;
   S_ROOT_RSP:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin
    if(descriptor_rsp_error_i)begin status_q<=FETCH;state_q<=S_CONTEXT;end
    else if(descriptor_rsp_data_i[31:8]!=0)begin status_q<=MALFORMED;state_q<=S_CONTEXT;end
    else if(descriptor_rsp_data_i[7:0]!=8'h01||descriptor_rsp_data_i[107:104]!=0||
      !(descriptor_rsp_data_i[111:108]==5||(ALLOW_FP32_OUTPUT&&slot_q==2&&descriptor_rsp_data_i[111:108]==7))||
      descriptor_rsp_data_i[115:112]!=0||descriptor_rsp_data_i[55:32]==24'hffffff)begin status_q<=UNSUPPORTED;state_q<=S_CONTEXT;end
    else begin addr_q[slot_q]<={descriptor_rsp_data_i[127:120],descriptor_rsp_data_i[103:56]};shape_index_q<=descriptor_rsp_data_i[55:32];
     if(slot_q==2)output_fp32_o<=descriptor_rsp_data_i[111:108]==7;
     state_q<=S_SHAPE_REQ;end end
   S_SHAPE_REQ:if(descriptor_req_valid_o&&descriptor_req_ready_i)state_q<=S_SHAPE_RSP;
   S_SHAPE_RSP:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin
    if(descriptor_rsp_error_i)begin status_q<=FETCH;state_q<=S_CONTEXT;end
    else if(descriptor_rsp_data_i[31:8]!=0)begin status_q<=MALFORMED;state_q<=S_CONTEXT;end
    else if(descriptor_rsp_data_i[7:0]!=8'h02)begin status_q<=UNSUPPORTED;state_q<=S_CONTEXT;end
    else begin shape_q[slot_q]<=descriptor_rsp_data_i[127:56];if(slot_q==2)state_q<=S_VALIDATE;else begin slot_q<=slot_q+1;state_q<=S_ROOT_REQ;end end end
   S_VALIDATE:begin
    if(shape_q[0][17:0]!=1024||shape_q[0][35:18]!=1536||shape_q[1][17:0]!=1536||
       shape_q[1][35:18]==0||shape_q[1][35:18]>1536||shape_q[1][22:18]!=0||
       shape_q[2][17:0]!=1024||shape_q[2][35:18]!=shape_q[1][35:18])status_q<=UNSUPPORTED;
    state_q<=S_CONTEXT;end
   S_CONTEXT:if(context_valid_o&&context_ready_i)state_q<=S_IDLE;
   default:state_q<=S_IDLE;
  endcase
 end
endmodule
