// SPDX-License-Identifier: Apache-2.0
// Four 128-bit Gemmini ExtMemIO scratchpad banks <-> one 512-bit Tensor Stream.
`timescale 1ns/1ps
module gemmini_spad_tensor_gateway(
  input logic clk_i,input logic rst_ni,
  input logic cfg_valid_i,output logic cfg_ready_o,input logic cfg_direction_i,
  input logic cfg_route_i,input logic[11:0]cfg_last_addr_i,input logic[15:0]cfg_tag_i,
  input logic[11:0]cfg_tensor_id_i,input logic[3:0]cfg_format_i,
  input logic[3:0]spad_write_valid_i,output logic[3:0]spad_write_ready_o,
  input logic[4*12-1:0]spad_write_addr_i,input logic[4*128-1:0]spad_write_data_i,
  input logic[4*16-1:0]spad_write_mask_i,
  input logic[3:0]spad_read_req_valid_i,output logic[3:0]spad_read_req_ready_o,
  input logic[4*12-1:0]spad_read_req_addr_i,
  output logic[3:0]spad_read_resp_valid_o,input logic[3:0]spad_read_resp_ready_i,
  output logic[4*128-1:0]spad_read_resp_data_o,
  output logic tx_valid_o,input logic tx_ready_i,output logic tx_route_o,
  output logic[511:0]tx_data_o,output logic[63:0]tx_be_o,output logic[15:0]tx_tag_o,
  output logic[11:0]tx_tensor_id_o,output logic tx_last_o,output logic[3:0]tx_format_o,
  input logic rx_valid_i,output logic rx_ready_o,input logic rx_route_i,
  input logic[511:0]rx_data_i,input logic[63:0]rx_be_i,input logic[15:0]rx_tag_i,
  input logic[11:0]rx_tensor_id_i,input logic rx_last_i,input logic[3:0]rx_format_i,
  output logic transfer_done_o,output logic[31:0]protocol_error_count_o
);
  logic active_q,direction_q,route_q;logic[11:0]last_addr_q;logic[15:0]tag_q;
  logic[11:0]tensor_id_q;logic[3:0]format_q;
  logic[3:0]wfull_q,rreq_full_q,rresp_valid_q;logic[11:0]waddr_q[0:3],raddr_q[0:3];
  logic[127:0]wdata_q[0:3],rdata_q[0:3];logic[15:0]wmask_q[0:3];
  logic wall,rall,wmatch,rmatch,rx_meta_match;
  assign cfg_ready_o=!active_q;
  assign wall=&wfull_q;assign rall=&rreq_full_q;
  always_comb begin
    wmatch=wall;rmatch=rall;
    for(int unsigned match_idx=1;match_idx<4;match_idx++)begin
      if(waddr_q[match_idx]!=waddr_q[0])wmatch=0;
      if(raddr_q[match_idx]!=raddr_q[0])rmatch=0;
    end
  end
  assign spad_write_ready_o={4{active_q&&!direction_q}}&~wfull_q;
  assign spad_read_req_ready_o={4{active_q&&direction_q}}&~rreq_full_q;
  assign spad_read_resp_valid_o=rresp_valid_q;
  assign spad_read_resp_data_o={rdata_q[3],rdata_q[2],rdata_q[1],rdata_q[0]};
  assign tx_valid_o=active_q&&!direction_q&&wall&&wmatch;
  assign tx_route_o=route_q;assign tx_data_o={wdata_q[3],wdata_q[2],wdata_q[1],wdata_q[0]};
  assign tx_be_o={wmask_q[3],wmask_q[2],wmask_q[1],wmask_q[0]};
  assign tx_tag_o=tag_q;assign tx_tensor_id_o=tensor_id_q;assign tx_format_o=format_q;
  assign tx_last_o=wall&&waddr_q[0]==last_addr_q;
  assign rx_meta_match=rx_route_i==route_q&&rx_be_i==64'hffff_ffff_ffff_ffff&&
                       rx_tag_i==tag_q&&rx_tensor_id_i==tensor_id_q&&
                       rx_format_i==format_q&&rx_last_i==(raddr_q[0]==last_addr_q);
  assign rx_ready_o=active_q&&direction_q&&rall&&rmatch&&!(|rresp_valid_q)&&rx_meta_match;
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin active_q<=0;direction_q<=0;route_q<=0;last_addr_q<=0;tag_q<=0;
      tensor_id_q<=0;format_q<=0;wfull_q<=0;rreq_full_q<=0;rresp_valid_q<=0;
      transfer_done_o<=0;protocol_error_count_o<=0;
      for(int unsigned reset_idx=0;reset_idx<4;reset_idx++)begin
        waddr_q[reset_idx]<=0;wdata_q[reset_idx]<=0;wmask_q[reset_idx]<=0;
        raddr_q[reset_idx]<=0;rdata_q[reset_idx]<=0;
      end
    end else begin
      transfer_done_o<=0;
      if(cfg_valid_i&&cfg_ready_o)begin active_q<=1;direction_q<=cfg_direction_i;route_q<=cfg_route_i;
        last_addr_q<=cfg_last_addr_i;tag_q<=cfg_tag_i;tensor_id_q<=cfg_tensor_id_i;
        format_q<=cfg_format_i;wfull_q<=0;rreq_full_q<=0;rresp_valid_q<=0;end
      for(int unsigned bank_idx=0;bank_idx<4;bank_idx++)begin
        if(spad_write_valid_i[bank_idx]&&spad_write_ready_o[bank_idx])begin
          wfull_q[bank_idx]<=1;
          waddr_q[bank_idx]<=spad_write_addr_i[bank_idx*12 +: 12];
          wdata_q[bank_idx]<=spad_write_data_i[bank_idx*128 +: 128];
          wmask_q[bank_idx]<=spad_write_mask_i[bank_idx*16 +: 16];
        end
        if(spad_read_req_valid_i[bank_idx]&&spad_read_req_ready_o[bank_idx])begin
          rreq_full_q[bank_idx]<=1;
          raddr_q[bank_idx]<=spad_read_req_addr_i[bank_idx*12 +: 12];
        end
        if(rresp_valid_q[bank_idx]&&spad_read_resp_ready_i[bank_idx])
          rresp_valid_q[bank_idx]<=0;
      end
      if(active_q&&!direction_q&&wall&&!wmatch)begin
        protocol_error_count_o<=protocol_error_count_o+1'b1;wfull_q<=0;active_q<=0;
      end else if(tx_valid_o&&tx_ready_i)begin
        wfull_q<=0;if(tx_last_o)begin active_q<=0;transfer_done_o<=1;end
      end
      if(active_q&&direction_q&&rall&&!rmatch)begin
        protocol_error_count_o<=protocol_error_count_o+1'b1;rreq_full_q<=0;active_q<=0;
      end else if(active_q&&direction_q&&rall&&rmatch&&rx_valid_i&&!rx_meta_match)begin
        protocol_error_count_o<=protocol_error_count_o+1'b1;rreq_full_q<=0;active_q<=0;
      end else if(rx_valid_i&&rx_ready_o)begin
        for(int unsigned response_idx=0;response_idx<4;response_idx++)begin
          rdata_q[response_idx]<=rx_data_i[response_idx*128 +: 128];
          rresp_valid_q[response_idx]<=1;
        end
        rreq_full_q<=0;if(rx_last_i)begin active_q<=0;transfer_done_o<=1;end
      end
    end
  end
endmodule
