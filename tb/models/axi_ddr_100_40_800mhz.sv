// Test-only AXI bandwidth envelope. Not a DRAM bank/refresh/latency model.
`timescale 1ns/1ps
module axi_ddr_100_40_800mhz import hetero_idma_512_pkg::*;(
 input logic clk_i,rst_ni,input axi_req_t upstream_req_i,output axi_rsp_t upstream_rsp_o,
 output axi_req_t memory_req_o,input axi_rsp_t memory_rsp_i,
 output logic[63:0]read_bytes_o,write_bytes_o,read_throttled_o,write_throttled_o
);
 logic read_allow,write_allow,read_fire,write_fire;
 // At 800MHz:100GB/s=125B/cycle;40GB/s=50B/cycle.
 ddr_beat_credit #(.BYTES_PER_CYCLE(125)) rbudget(
  .clk_i,.rst_ni,.valid_i(memory_rsp_i.r_valid),.fire_i(read_fire),.allow_o(read_allow),
  .bytes_o(read_bytes_o),.throttled_cycles_o(read_throttled_o));
 ddr_beat_credit #(.BYTES_PER_CYCLE(50)) wbudget(
  .clk_i,.rst_ni,.valid_i(upstream_req_i.w_valid),.fire_i(write_fire),.allow_o(write_allow),
  .bytes_o(write_bytes_o),.throttled_cycles_o(write_throttled_o));
 always_comb begin
  memory_req_o=upstream_req_i;upstream_rsp_o=memory_rsp_i;
  memory_req_o.w_valid=upstream_req_i.w_valid&&write_allow;
  upstream_rsp_o.w_ready=memory_rsp_i.w_ready&&write_allow;
  upstream_rsp_o.r_valid=memory_rsp_i.r_valid&&read_allow;
  memory_req_o.r_ready=upstream_req_i.r_ready&&read_allow;
 end
 assign read_fire=upstream_rsp_o.r_valid&&upstream_req_i.r_ready;
 assign write_fire=memory_req_o.w_valid&&memory_rsp_i.w_ready;
 // Credits never decrease without handshake, so a presented valid cannot be
 // revoked by the limiter while its receiver is stalled. Check at AXI boundary.
 assert property(@(posedge clk_i) disable iff(!rst_ni)
  upstream_rsp_o.r_valid&&!upstream_req_i.r_ready |=> upstream_rsp_o.r_valid&&$stable(upstream_rsp_o.r));
 assert property(@(posedge clk_i) disable iff(!rst_ni)
  memory_req_o.w_valid&&!memory_rsp_i.w_ready |=> memory_req_o.w_valid&&$stable(memory_req_o.w));
endmodule
