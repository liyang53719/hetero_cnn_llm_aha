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
  // Current flat ABI has no transaction tags: one request until its response.
  // Fail closed on AXI errors; partially written destinations require reset.
  // Keep upstream NO_ERROR_HANDLING (one final response) and capture bus faults
  // here rather than silently inheriting its constant-zero rsp.error signal.
  logic active_q,axi_fault_q,read_fault,write_fault,response_pending_q,response_error_q;
  logic backend_req_ready,backend_req_valid,backend_rsp_valid;
  assign read_fault=active_q&&axi_read_rsp_i.r_valid&&axi_read_rsp_i.r.resp[1];
  assign write_fault=active_q&&axi_write_rsp_i.b_valid&&axi_write_rsp_i.b.resp[1];
  assign req_ready_o=backend_req_ready&&!active_q&&!axi_fault_q;
  assign backend_req_valid=req_valid_i&&!active_q&&!axi_fault_q;
  // Fall through when the consumer is ready; retain only stalled responses.
  assign rsp_valid_o=response_pending_q||(active_q&&backend_rsp_valid);
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin active_q<=0;axi_fault_q<=0;response_pending_q<=0;response_error_q<=0;end
    else begin
      if(req_valid_i&&req_ready_o)active_q<=1;
      if(read_fault||write_fault)axi_fault_q<=1;
      if(active_q&&!response_pending_q&&backend_rsp_valid&&!rsp_ready_i)begin
        response_pending_q<=1;
        response_error_q<=rsp.error||axi_fault_q||read_fault||write_fault;
      end
      if(rsp_valid_o&&rsp_ready_i)begin active_q<=0;response_pending_q<=0;end
    end
  end
  always_comb begin
    req='0;req.length=length_i;req.src_addr=src_addr_i;req.dst_addr=dst_addr_i;
    req.opt.src_protocol=idma_pkg::AXI;req.opt.dst_protocol=idma_pkg::AXI;
    req.opt.src.burst=axi_pkg::BURST_INCR;req.opt.dst.burst=axi_pkg::BURST_INCR;
    req.opt.beo.decouple_aw=1;req.opt.beo.decouple_rw=1;
    req.opt.beo.src_max_llen=3'd4;req.opt.beo.dst_max_llen=3'd4;
    req.opt.beo.src_reduce_len=1;req.opt.beo.dst_reduce_len=1;
    req.opt.compute.enable=0;req.opt.last=1;eh_req='0;
  end
  assign rsp_error_o=response_pending_q?response_error_q:(rsp.error||axi_fault_q||read_fault||write_fault);assign busy_o=busy;
  idma_backend_rw_axi #(.DataWidth(512),.AddrWidth(64),.UserWidth(1),.AxiIdWidth(4),
    .NumAxInFlight(4),.BufferDepth(3),.TFLenWidth(32),.HardwareLegalizer(1),
    .RejectZeroTransfers(1),.EnableCompute(0),.ErrorCap(idma_pkg::NO_ERROR_HANDLING),.idma_req_t(idma_req_t),.idma_rsp_t(idma_rsp_t),
    .idma_eh_req_t(idma_pkg::idma_eh_req_t),.idma_busy_t(idma_pkg::idma_busy_t),
    .axi_req_t(axi_req_t),.axi_rsp_t(axi_rsp_t),.read_meta_channel_t(read_meta_channel_t),
    .write_meta_channel_t(write_meta_channel_t))u_backend(
    .clk_i,.rst_ni,.idma_req_i(req),.req_valid_i(backend_req_valid),.req_ready_o(backend_req_ready),.idma_rsp_o(rsp),
    .rsp_valid_o(backend_rsp_valid),.rsp_ready_i(active_q&&!response_pending_q),.idma_eh_req_i(eh_req),.eh_req_valid_i(1'b0),
    .eh_req_ready_o(eh_ready),.axi_read_req_o,.axi_read_rsp_i,.axi_write_req_o,
    .axi_write_rsp_i,.busy_o(busy));
endmodule
