`timescale 1ns/1ps
module tb_idma_flat_wrap;
  import hetero_idma_512_pkg::*;
  logic clk=0,rst_n=0;always #5 clk=~clk;logic req_valid,req_ready,rsp_valid,rsp_ready,rsp_error;
  logic[63:0]src,dst;logic[31:0]length;logic[7:0]busy;
  axi_req_t read_req,write_req,joined_req;axi_rsp_t read_rsp,write_rsp,joined_rsp;
  idma_backend_rw_axi_flat_wrap dut(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(req_valid),
    .req_ready_o(req_ready),.src_addr_i(src),.dst_addr_i(dst),.length_i(length),
    .rsp_valid_o(rsp_valid),.rsp_ready_i(rsp_ready),.rsp_error_o(rsp_error),
    .axi_read_req_o(read_req),.axi_read_rsp_i(read_rsp),.axi_write_req_o(write_req),
    .axi_write_rsp_i(write_rsp),.busy_o(busy));
  axi_rw_join #(.axi_req_t(axi_req_t),.axi_resp_t(axi_rsp_t))i_join(
    .clk_i(clk),.rst_ni(rst_n),.slv_read_req_i(read_req),.slv_read_resp_o(read_rsp),
    .slv_write_req_i(write_req),.slv_write_resp_o(write_rsp),.mst_req_o(joined_req),.mst_resp_i(joined_rsp));
  axi_sim_mem #(.AddrWidth(64),.DataWidth(512),.IdWidth(4),.UserWidth(1),
    .axi_req_t(axi_req_t),.axi_rsp_t(axi_rsp_t),.WarnUninitialized(1'b0),
    .ClearErrOnAccess(1'b1),.ApplDelay(1ns),.AcqDelay(9ns))mem(
    .clk_i(clk),.rst_ni(rst_n),.axi_req_i(joined_req),.axi_rsp_o(joined_rsp),
    .mon_r_last_o(),.mon_r_beat_count_o(),.mon_r_user_o(),.mon_r_id_o(),
    .mon_r_data_o(),.mon_r_addr_o(),.mon_r_valid_o(),.mon_w_last_o(),
    .mon_w_beat_count_o(),.mon_w_user_o(),.mon_w_id_o(),.mon_w_data_o(),
    .mon_w_addr_o(),.mon_w_valid_o());
  initial begin req_valid=0;rsp_ready=1;src=64'h1000;dst=64'h2000;length=96;
    for(int i=0;i<96;i++)mem.mem[src+i]=8'h40+i;
    repeat(3)@(posedge clk);rst_n=1;@(negedge clk);req_valid=1;
    do @(posedge clk);while(!req_ready);@(negedge clk);req_valid=0;
    do @(posedge clk);while(!(rsp_valid&&rsp_ready));if(rsp_error)$fatal(1,"iDMA response error");
    for(int i=0;i<96;i++)if(mem.mem[dst+i]!==8'h40+i)$fatal(1,"copy mismatch %0d",i);
    if(busy!=0)$fatal(1,"busy did not clear");
    $display("IDMA_FLAT_WRAP_PASS length=%0d",length);$finish;
  end
  initial begin repeat(5000)@(posedge clk);$fatal(1,"timeout");end
endmodule
