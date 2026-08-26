// SPDX-License-Identifier: Apache-2.0
`include "axi/typedef.svh"
`include "idma/typedef.svh"
package hetero_idma_512_pkg;
  typedef logic[63:0] addr_t;typedef logic[511:0] data_t;typedef logic[63:0]strb_t;
  typedef logic[3:0]id_t;typedef logic user_t;typedef logic[31:0]tf_len_t;
  `AXI_TYPEDEF_AW_CHAN_T(axi_aw_t,addr_t,id_t,user_t)
  `AXI_TYPEDEF_W_CHAN_T(axi_w_t,data_t,strb_t,user_t)
  `AXI_TYPEDEF_B_CHAN_T(axi_b_t,id_t,user_t)
  `AXI_TYPEDEF_AR_CHAN_T(axi_ar_t,addr_t,id_t,user_t)
  `AXI_TYPEDEF_R_CHAN_T(axi_r_t,data_t,id_t,user_t)
  `AXI_TYPEDEF_REQ_T(axi_req_t,axi_aw_t,axi_w_t,axi_ar_t)
  `AXI_TYPEDEF_RESP_T(axi_rsp_t,axi_b_t,axi_r_t)
  `IDMA_TYPEDEF_FULL_REQ_T(idma_req_t,id_t,addr_t,tf_len_t)
  `IDMA_TYPEDEF_FULL_RSP_T(idma_rsp_t,addr_t)
  typedef struct packed{axi_ar_t ar_chan;}axi_read_meta_channel_t;
  typedef struct packed{axi_read_meta_channel_t axi;}read_meta_channel_t;
  typedef struct packed{axi_aw_t aw_chan;}axi_write_meta_channel_t;
  typedef struct packed{axi_write_meta_channel_t axi;}write_meta_channel_t;
endpackage
module idma_backend_rw_axi_flat_wrap import hetero_idma_512_pkg::*;(
  input logic clk_i,input logic rst_ni,
  input logic req_valid_i,output logic req_ready_o,input logic[63:0]src_addr_i,
  input logic[63:0]dst_addr_i,input logic[31:0]length_i,
  output logic rsp_valid_o,input logic rsp_ready_i,output logic rsp_error_o,
  output axi_req_t axi_read_req_o,input axi_rsp_t axi_read_rsp_i,
  output axi_req_t axi_write_req_o,input axi_rsp_t axi_write_rsp_i,
  output logic[7:0]busy_o
);
  idma_req_t req;idma_rsp_t rsp;idma_pkg::idma_eh_req_t eh_req;logic eh_ready;
  idma_pkg::idma_busy_t busy;
  always_comb begin
    req='0;req.length=length_i;req.src_addr=src_addr_i;req.dst_addr=dst_addr_i;
    req.opt.src_protocol=idma_pkg::AXI;req.opt.dst_protocol=idma_pkg::AXI;
    req.opt.src.burst=axi_pkg::BURST_INCR;req.opt.dst.burst=axi_pkg::BURST_INCR;
    req.opt.beo.decouple_aw=1;req.opt.beo.decouple_rw=1;
    req.opt.beo.src_max_llen=3'd4;req.opt.beo.dst_max_llen=3'd4;
    req.opt.beo.src_reduce_len=1;req.opt.beo.dst_reduce_len=1;
    req.opt.compute.enable=0;req.opt.last=1;eh_req='0;
  end
  assign rsp_error_o=rsp.error;assign busy_o=busy;
  idma_backend_rw_axi #(.DataWidth(512),.AddrWidth(64),.UserWidth(1),.AxiIdWidth(4),
    .NumAxInFlight(4),.BufferDepth(3),.TFLenWidth(32),.HardwareLegalizer(1),
    .RejectZeroTransfers(1),.EnableCompute(0),.idma_req_t(idma_req_t),.idma_rsp_t(idma_rsp_t),
    .idma_eh_req_t(idma_pkg::idma_eh_req_t),.idma_busy_t(idma_pkg::idma_busy_t),
    .axi_req_t(axi_req_t),.axi_rsp_t(axi_rsp_t),.read_meta_channel_t(read_meta_channel_t),
    .write_meta_channel_t(write_meta_channel_t))u_backend(
    .clk_i,.rst_ni,.idma_req_i(req),.req_valid_i,.req_ready_o,.idma_rsp_o(rsp),
    .rsp_valid_o,.rsp_ready_i,.idma_eh_req_i(eh_req),.eh_req_valid_i(1'b0),
    .eh_req_ready_o(eh_ready),.axi_read_req_o,.axi_read_rsp_i,.axi_write_req_o,
    .axi_write_rsp_i,.busy_o(busy));
endmodule
