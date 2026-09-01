// SPDX-License-Identifier: Apache-2.0
// Snapshots the first RMSNorm -> Matrix tensor roots before any payload issue.
`timescale 1ns/1ps
module qwen2_descriptor_tile_context(
  input logic clk_i,input logic rst_ni,input logic start_i,
  input logic[127:0] rms_command_i,input logic[127:0] matrix_command_i,
  output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,
  output logic[23:0] descriptor_req_index_o,
  input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,
  input logic[127:0] descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
  output logic context_valid_o,input logic context_ready_i,
  output logic context_legal_o,output logic[7:0] context_status_o,
  output logic[6*56-1:0] tensor_address_o,
  output logic[6*4-1:0] tensor_dtype_o,
  output logic[6*72-1:0] tensor_shape_o,
  output logic[6*24-1:0] tensor_root_o
);
  localparam logic[7:0] ST_OK=0,ST_MALFORMED=2,ST_FETCH=3,ST_UNSUPPORTED=4;
  typedef enum logic[2:0]{S_IDLE,S_ROOT_REQ,S_ROOT_RSP,S_SHAPE_REQ,S_SHAPE_RSP,S_VALIDATE,S_CONTEXT}state_e;
  state_e state_q;logic[2:0]slot_q;logic[7:0]status_q;
  logic[23:0]roots_q[0:5],shape_index_q;logic[55:0]addresses_q[0:5];
  logic[3:0]dtypes_q[0:5];logic[71:0]shapes_q[0:5];
  logic root_common_legal,root_dtype_legal,root_semantic_legal,shape_semantic_legal;
  integer comb_i,seq_i;
  assign descriptor_req_valid_o=state_q==S_ROOT_REQ||state_q==S_SHAPE_REQ;
  assign descriptor_req_index_o=state_q==S_ROOT_REQ?roots_q[slot_q]:shape_index_q;
  assign descriptor_rsp_ready_o=state_q==S_ROOT_RSP||state_q==S_SHAPE_RSP;
  assign context_valid_o=state_q==S_CONTEXT;assign context_legal_o=status_q==ST_OK;
  assign context_status_o=status_q;
  always_comb begin
    root_common_legal=descriptor_rsp_data_i[31:8]==0;
    root_dtype_legal=descriptor_rsp_data_i[111:108]==4'd5||descriptor_rsp_data_i[111:108]==4'd7;
    root_semantic_legal=descriptor_rsp_data_i[7:0]==8'h01&&root_common_legal&&
      descriptor_rsp_data_i[107:104]==0&&descriptor_rsp_data_i[115:112]==0&&
      descriptor_rsp_data_i[119:116]>=1&&descriptor_rsp_data_i[119:116]<=4&&root_dtype_legal;
    shape_semantic_legal=descriptor_rsp_data_i[7:0]==8'h02&&descriptor_rsp_data_i[31:8]==0;
    tensor_address_o='0;tensor_dtype_o='0;tensor_shape_o='0;tensor_root_o='0;
    for(comb_i=0;comb_i<6;comb_i++)begin
      tensor_address_o[comb_i*56+:56]=addresses_q[comb_i];tensor_dtype_o[comb_i*4+:4]=dtypes_q[comb_i];
      tensor_shape_o[comb_i*72+:72]=shapes_q[comb_i];tensor_root_o[comb_i*24+:24]=roots_q[comb_i];
    end
  end
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin state_q<=S_IDLE;slot_q<=0;status_q<=ST_OK;shape_index_q<=0;
      for(seq_i=0;seq_i<6;seq_i++)begin roots_q[seq_i]<=24'hffffff;addresses_q[seq_i]<=0;dtypes_q[seq_i]<=0;shapes_q[seq_i]<=0;end
    end else case(state_q)
      S_IDLE:if(start_i)begin
        roots_q[0]<=rms_command_i[79:56];roots_q[1]<=rms_command_i[103:80];roots_q[2]<=rms_command_i[127:104];
        roots_q[3]<=matrix_command_i[79:56];roots_q[4]<=matrix_command_i[103:80];roots_q[5]<=matrix_command_i[127:104];
        slot_q<=0;status_q<=ST_OK;
        if(rms_command_i[7:0]!=8'h32||rms_command_i[10:8]!=3'd3||matrix_command_i[7:0]!=8'h20||
           matrix_command_i[10:8]!=3'd2||matrix_command_i[39:24]!=rms_command_i[55:40]||
           rms_command_i[79:56]==24'hffffff||rms_command_i[103:80]==24'hffffff||
           rms_command_i[127:104]==24'hffffff||matrix_command_i[79:56]==24'hffffff||
           matrix_command_i[103:80]==24'hffffff||matrix_command_i[127:104]==24'hffffff)begin
          status_q<=ST_MALFORMED;state_q<=S_CONTEXT;
        end else state_q<=S_ROOT_REQ;
      end
      S_ROOT_REQ:if(descriptor_req_valid_o&&descriptor_req_ready_i)state_q<=S_ROOT_RSP;
      S_ROOT_RSP:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin
        if(descriptor_rsp_error_i)begin status_q<=ST_FETCH;state_q<=S_CONTEXT;end
        else if(!root_common_legal)begin status_q<=ST_MALFORMED;state_q<=S_CONTEXT;end
        else if(!root_semantic_legal||descriptor_rsp_data_i[55:32]==24'hffffff)begin
          status_q<=ST_UNSUPPORTED;state_q<=S_CONTEXT;
        end else begin
          addresses_q[slot_q]<={descriptor_rsp_data_i[127:120],descriptor_rsp_data_i[103:56]};
          dtypes_q[slot_q]<=descriptor_rsp_data_i[111:108];shape_index_q<=descriptor_rsp_data_i[55:32];
          state_q<=S_SHAPE_REQ;
        end
      end
      S_SHAPE_REQ:if(descriptor_req_valid_o&&descriptor_req_ready_i)state_q<=S_SHAPE_RSP;
      S_SHAPE_RSP:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin
        if(descriptor_rsp_error_i)begin status_q<=ST_FETCH;state_q<=S_CONTEXT;end
        else if(!shape_semantic_legal)begin status_q<=descriptor_rsp_data_i[31:8]!=0?ST_MALFORMED:ST_UNSUPPORTED;state_q<=S_CONTEXT;end
        else begin shapes_q[slot_q]<=descriptor_rsp_data_i[127:56];
          if(slot_q==5)state_q<=S_VALIDATE;
          else begin slot_q<=slot_q+1'b1;state_q<=S_ROOT_REQ;end
        end
      end
      S_VALIDATE:begin
        if(dtypes_q[0]!=5||dtypes_q[1]!=7||dtypes_q[2]!=5||dtypes_q[3]!=5||dtypes_q[4]!=5||dtypes_q[5]!=5||
           addresses_q[2]!=addresses_q[3]||shapes_q[0]!={18'd1,18'd1,18'd1536,18'd1024}||
           shapes_q[1]!={18'd1,18'd1,18'd1,18'd1536}||shapes_q[2]!=shapes_q[0]||
           shapes_q[3]!=shapes_q[0]||shapes_q[4]!={18'd1,18'd1,18'd1536,18'd1536}||
           shapes_q[5]!=shapes_q[0])status_q<=ST_UNSUPPORTED;
        state_q<=S_CONTEXT;
      end
      S_CONTEXT:if(context_valid_o&&context_ready_i)state_q<=S_IDLE;
      default:state_q<=S_IDLE;
    endcase
  end
endmodule
