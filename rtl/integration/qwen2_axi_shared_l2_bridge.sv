// SPDX-License-Identifier: Apache-2.0
// Upstream axi_to_mem burst conversion onto one production Shared-L2 client.
`timescale 1ns/1ps
module qwen2_axi_shared_l2_bridge import hetero_idma_512_pkg::*;#(
 parameter integer ADDR_W=15
)(
 input logic clk_i,input logic rst_ni,input axi_req_t axi_req_i,output axi_rsp_t axi_rsp_o,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,
 input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,
 output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,output logic busy_o
);
 logic mem_req,mem_gnt,mem_we,mem_rvalid,converter_busy;logic[63:0]mem_addr;
 logic[511:0]mem_wdata,mem_rdata;logic[63:0]mem_strb;axi_pkg::atop_t mem_atop;
 logic[0:0]mem_req_bus,mem_gnt_bus,mem_we_bus,mem_rvalid_bus;
 logic[0:0][63:0]mem_addr_bus;logic[0:0][511:0]mem_wdata_bus,mem_rdata_bus;
 logic[0:0][63:0]mem_strb_bus;logic[0:0][$bits(axi_pkg::atop_t)-1:0]mem_atop_bus;
 logic write_response_q;
 axi_to_mem #(.axi_req_t(axi_req_t),.axi_resp_t(axi_rsp_t),.AddrWidth(64),.DataWidth(512),
  .IdWidth(4),.NumBanks(1),.BufDepth(1),.HideStrb(1'b0),.OutFifoDepth(1))convert(
  .clk_i(clk_i),.rst_ni(rst_ni),.busy_o(converter_busy),.axi_req_i(axi_req_i),.axi_resp_o(axi_rsp_o),
  .mem_req_o(mem_req_bus),.mem_gnt_i(mem_gnt_bus),.mem_addr_o(mem_addr_bus),.mem_wdata_o(mem_wdata_bus),
  .mem_strb_o(mem_strb_bus),.mem_atop_o(mem_atop_bus),.mem_we_o(mem_we_bus),
  .mem_rvalid_i(mem_rvalid_bus),.mem_rdata_i(mem_rdata_bus));
 assign mem_req=mem_req_bus[0];assign mem_addr=mem_addr_bus[0];assign mem_wdata=mem_wdata_bus[0];
 assign mem_strb=mem_strb_bus[0];assign mem_atop=mem_atop_bus[0];assign mem_we=mem_we_bus[0];
 assign mem_gnt_bus[0]=mem_gnt;assign mem_rvalid_bus[0]=mem_rvalid;assign mem_rdata_bus[0]=mem_rdata;
 assign busy_o=converter_busy;
 always_comb begin
  l2_rd_valid_o=mem_req&&!mem_we;l2_rd_addr_o=ADDR_W'(mem_addr[ADDR_W+5:6]);l2_rsp_ready_o=1'b1;
  l2_wr_valid_o=mem_req&&mem_we;l2_wr_addr_o=ADDR_W'(mem_addr[ADDR_W+5:6]);l2_wr_data_o=mem_wdata;l2_wr_be_o=mem_strb;
  mem_gnt=0;mem_rvalid=0;mem_rdata=0;
  if(mem_req)mem_gnt=mem_we?l2_wr_ready_i:l2_rd_ready_i;
  mem_rvalid=write_response_q||l2_rsp_valid_i;mem_rdata=l2_rsp_data_i;
 end
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)write_response_q<=1'b0;
  else write_response_q<=mem_req&&mem_gnt&&mem_we;
 end
endmodule
