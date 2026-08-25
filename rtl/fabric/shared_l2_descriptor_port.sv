// SPDX-License-Identifier: Apache-2.0
// One-outstanding 128-bit descriptor port over one 512-bit Shared-L2 read
// client. Four consecutive descriptor records occupy one fabric beat.
`timescale 1ns/1ps
module shared_l2_descriptor_port #(
  parameter integer ADDR_W = 15,
  parameter logic [63:0] SRAM_BYTES = 64'd1572864
) (
  input logic clk_i,input logic rst_ni,
  input logic[63:0] descriptor_base_i,
  input logic descriptor_req_valid_i,output logic descriptor_req_ready_o,
  input logic[23:0] descriptor_req_index_i,
  output logic descriptor_rsp_valid_o,input logic descriptor_rsp_ready_i,
  output logic[127:0] descriptor_rsp_data_o,output logic descriptor_rsp_error_o,
  output logic fabric_req_valid_o,input logic fabric_req_ready_i,
  output logic[ADDR_W-1:0] fabric_req_addr_o,
  input logic fabric_rsp_valid_i,output logic fabric_rsp_ready_o,
  input logic[511:0] fabric_rsp_data_i,input logic fabric_rsp_error_i
);
  typedef enum logic[1:0]{S_IDLE,S_WAIT,S_RESP}state_e;
  state_e state_q;
  logic[64:0] request_byte_addr;
  logic request_address_legal;
  logic[1:0] lane_q;
  logic[127:0] response_data_q;
  logic response_error_q;

  assign request_byte_addr={1'b0,descriptor_base_i}+{37'd0,descriptor_req_index_i,4'b0};
  assign request_address_legal=!request_byte_addr[64]&&descriptor_base_i[3:0]==0&&
                               request_byte_addr[63:0]<SRAM_BYTES;
  assign fabric_req_valid_o=state_q==S_IDLE&&descriptor_req_valid_i&&request_address_legal;
  assign fabric_req_addr_o=request_byte_addr[6 +: ADDR_W];
  assign descriptor_req_ready_o=state_q==S_IDLE&&
                                (request_address_legal?fabric_req_ready_i:1'b1);
  assign fabric_rsp_ready_o=state_q==S_WAIT;
  assign descriptor_rsp_valid_o=state_q==S_RESP;
  assign descriptor_rsp_data_o=response_data_q;
  assign descriptor_rsp_error_o=response_error_q;

  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin
      state_q<=S_IDLE;lane_q<='0;response_data_q<='0;response_error_q<=0;
    end else begin
      case(state_q)
        S_IDLE:if(descriptor_req_valid_i&&descriptor_req_ready_o)begin
          lane_q<=request_byte_addr[5:4];response_data_q<='0;
          response_error_q<=!request_address_legal;
          state_q<=request_address_legal?S_WAIT:S_RESP;
        end
        S_WAIT:if(fabric_rsp_valid_i&&fabric_rsp_ready_o)begin
          response_data_q<=fabric_rsp_data_i[lane_q*128 +: 128];
          response_error_q<=fabric_rsp_error_i;state_q<=S_RESP;
        end
        S_RESP:if(descriptor_rsp_valid_o&&descriptor_rsp_ready_i)state_q<=S_IDLE;
        default:state_q<=S_IDLE;
      endcase
    end
  end
endmodule
