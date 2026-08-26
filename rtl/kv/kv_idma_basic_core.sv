// SPDX-License-Identifier: Apache-2.0
// L2 single-sequence BF16 KV state machine driving the pinned iDMA flat front.
`timescale 1ns/1ps
module kv_idma_basic_core #(
  parameter logic[63:0] STAGING_BASE=64'h0010_0000,
  parameter integer STAGING_BYTES=512*1024
)(
  input logic clk_i,input logic rst_ni,
  input logic op_valid_i,output logic op_ready_o,input logic[7:0]opcode_i,
  input logic[15:0]event_id_i,input logic[11:0]sequence_id_i,input logic[9:0]layer_id_i,
  input logic[23:0]token_start_i,input logic[15:0]token_count_i,input logic[11:0]head_dim_i,
  input logic[63:0]k_addr_i,input logic[63:0]v_addr_i,input logic[63:0]output_addr_i,
  output logic idma_req_valid_o,input logic idma_req_ready_i,
  output logic[63:0]idma_src_addr_o,output logic[63:0]idma_dst_addr_o,
  output logic[31:0]idma_length_o,input logic idma_rsp_valid_i,
  output logic idma_rsp_ready_o,input logic idma_rsp_error_i,
  output logic event_valid_o,input logic event_ready_i,output logic[55:0]event_data_o
);
  localparam logic[7:0] OP_ALLOC=8'h40,OP_APPEND=8'h41,OP_GATHER=8'h42,OP_FREE=8'h44;
  localparam logic[7:0] ST_OK=0,ST_UNSUPPORTED=4,ST_RANGE=5,ST_PROTOCOL=7;
  localparam logic[2:0] ENGINE_KV=3'd4;
  localparam logic[63:0] HALF_BYTES=64'(STAGING_BYTES/2);
  typedef enum logic[2:0]{S_IDLE,S_REQ0,S_RSP0,S_REQ1,S_RSP1,S_EVENT}state_e;
  state_e state_q;
  logic allocated_q,is_append_q;logic[23:0]length_tokens_q,start_q;
  logic[15:0]count_q;logic[11:0]head_dim_q;logic[63:0]k_q,v_q,out_q;
  logic[31:0]bytes_q;logic[15:0]event_q;logic[7:0]status_q;
  logic[63:0]offset_wide,bytes_wide;
  logic[28:0]transfer_bytes;
  logic request_legal;
  assign bytes_wide={48'd0,token_count_i}*{52'd0,head_dim_i}*64'd2;
  assign offset_wide={40'd0,token_start_i}*{52'd0,head_dim_i}*64'd2;
  assign request_legal=sequence_id_i==0&&layer_id_i==0&&head_dim_i>0&&head_dim_i<=256;
  assign op_ready_o=state_q==S_IDLE;
  assign idma_req_valid_o=state_q==S_REQ0||state_q==S_REQ1;
  assign idma_rsp_ready_o=state_q==S_RSP0||state_q==S_RSP1;
  assign event_valid_o=state_q==S_EVENT;
  assign transfer_bytes={bytes_q[27:0],1'b0};
  assign event_data_o={event_q,status_q,ENGINE_KV,transfer_bytes};
  always_comb begin
    idma_src_addr_o=0;idma_dst_addr_o=0;idma_length_o=bytes_q;
    if(is_append_q)begin
      idma_src_addr_o=state_q==S_REQ0?k_q:v_q;
      idma_dst_addr_o=STAGING_BASE+(state_q==S_REQ1?HALF_BYTES:64'd0)+start_q*head_dim_q*2;
    end else begin
      idma_src_addr_o=STAGING_BASE+(state_q==S_REQ1?HALF_BYTES:64'd0)+start_q*head_dim_q*2;
      idma_dst_addr_o=out_q+(state_q==S_REQ1?{32'd0,bytes_q}:64'd0);
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin state_q<=S_IDLE;allocated_q<=0;length_tokens_q<=0;event_q<=0;
      status_q<=ST_OK;bytes_q<=0;is_append_q<=0;start_q<=0;count_q<=0;
      head_dim_q<=0;k_q<=0;v_q<=0;out_q<=0;
    end else case(state_q)
      S_IDLE:if(op_valid_i&&op_ready_o)begin
        event_q<=event_id_i;status_q<=ST_OK;bytes_q<=0;
        case(opcode_i)
          OP_ALLOC:begin
            if(!request_legal||allocated_q)status_q<=ST_UNSUPPORTED;
            else begin allocated_q<=1;length_tokens_q<=0;head_dim_q<=head_dim_i;end
            state_q<=S_EVENT;
          end
          OP_APPEND,OP_GATHER:begin
            is_append_q<=opcode_i==OP_APPEND;start_q<=token_start_i;count_q<=token_count_i;
            k_q<=k_addr_i;v_q<=v_addr_i;out_q<=output_addr_i;
            if(!allocated_q||!request_legal||head_dim_i!=head_dim_q||token_count_i==0||
               bytes_wide>HALF_BYTES||offset_wide+bytes_wide>HALF_BYTES||
               (opcode_i==OP_APPEND&&token_start_i!=length_tokens_q)||
               (opcode_i==OP_GATHER&&token_start_i+{8'd0,token_count_i}>length_tokens_q))begin
              status_q<=ST_RANGE;state_q<=S_EVENT;
            end else begin bytes_q<=bytes_wide[31:0];state_q<=S_REQ0;end
          end
          OP_FREE:begin
            if(!allocated_q||sequence_id_i!=0||layer_id_i!=0)status_q<=ST_RANGE;
            else begin allocated_q<=0;length_tokens_q<=0;head_dim_q<=0;end
            state_q<=S_EVENT;
          end
          default:begin status_q<=ST_UNSUPPORTED;state_q<=S_EVENT;end
        endcase
      end
      S_REQ0:if(idma_req_valid_o&&idma_req_ready_i)state_q<=S_RSP0;
      S_RSP0:if(idma_rsp_valid_i&&idma_rsp_ready_o)begin
        if(idma_rsp_error_i)begin status_q<=ST_PROTOCOL;state_q<=S_EVENT;end else state_q<=S_REQ1;
      end
      S_REQ1:if(idma_req_valid_o&&idma_req_ready_i)state_q<=S_RSP1;
      S_RSP1:if(idma_rsp_valid_i&&idma_rsp_ready_o)begin
        if(idma_rsp_error_i)status_q<=ST_PROTOCOL;
        else if(is_append_q)length_tokens_q<=length_tokens_q+{8'd0,count_q};
        state_q<=S_EVENT;
      end
      S_EVENT:if(event_valid_o&&event_ready_i)state_q<=S_IDLE;
      default:state_q<=S_IDLE;
    endcase
  end
endmodule
