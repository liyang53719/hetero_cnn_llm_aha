`timescale 1ns/1ps
module tb_idma_flat_error;
  import hetero_idma_512_pkg::*;
  logic clk=0,rst_n=0;always #5 clk=~clk;logic req_valid,req_ready,rsp_valid,rsp_ready,rsp_error;
  logic[63:0]src,dst;logic[31:0]length;logic[7:0]busy;
  axi_req_t read_req,write_req,joined_req;axi_rsp_t read_rsp,write_rsp,joined_rsp,raw_read_rsp,raw_write_rsp;
  integer mode;
  always_comb begin read_rsp=raw_read_rsp;write_rsp=raw_write_rsp;
    if(mode==1)read_rsp.r.resp=axi_pkg::RESP_SLVERR;
    if(mode==2)write_rsp.b.resp=axi_pkg::RESP_DECERR;
  end
  idma_backend_rw_axi_flat_wrap dut(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(req_valid),
    .req_ready_o(req_ready),.src_addr_i(src),.dst_addr_i(dst),.length_i(length),
    .rsp_valid_o(rsp_valid),.rsp_ready_i(rsp_ready),.rsp_error_o(rsp_error),
    .axi_read_req_o(read_req),.axi_read_rsp_i(read_rsp),.axi_write_req_o(write_req),
    .axi_write_rsp_i(write_rsp),.busy_o(busy));
  axi_rw_join #(.axi_req_t(axi_req_t),.axi_resp_t(axi_rsp_t))i_join(
    .clk_i(clk),.rst_ni(rst_n),.slv_read_req_i(read_req),.slv_read_resp_o(raw_read_rsp),
    .slv_write_req_i(write_req),.slv_write_resp_o(raw_write_rsp),.mst_req_o(joined_req),.mst_resp_i(joined_rsp));
  axi_sim_mem #(.AddrWidth(64),.DataWidth(512),.IdWidth(4),.UserWidth(1),
    .axi_req_t(axi_req_t),.axi_rsp_t(axi_rsp_t),.WarnUninitialized(1'b0),
    .ClearErrOnAccess(1'b1),.ApplDelay(1ns),.AcqDelay(9ns))mem(
    .clk_i(clk),.rst_ni(rst_n),.axi_req_i(joined_req),.axi_rsp_o(joined_rsp),
    .mon_r_last_o(),.mon_r_beat_count_o(),.mon_r_user_o(),.mon_r_id_o(),
    .mon_r_data_o(),.mon_r_addr_o(),.mon_r_valid_o(),.mon_w_last_o(),
    .mon_w_beat_count_o(),.mon_w_user_o(),.mon_w_id_o(),.mon_w_data_o(),
    .mon_w_addr_o(),.mon_w_valid_o());
  initial begin
    req_valid=0;rsp_ready=0;src=64'h1000;dst=64'h2000;length=96;mode=0;
    for(int trial=0;trial<4;trial++)begin
      @(negedge clk);rst_n=0;req_valid=0;rsp_ready=0;
      mode=trial==3?0:trial;
      repeat(3)@(negedge clk);rst_n=1;
      for(int i=0;i<96;i++)mem.mem[src+i]=8'(i+trial);
      @(negedge clk);req_valid=1;do @(posedge clk);while(!req_ready);
      @(negedge clk);req_valid=0;
      wait(rsp_valid);@(negedge clk);
      repeat(4)begin
        if(!rsp_valid||rsp_error!=(mode!=0)||req_ready)$fatal(1,"response stability mode=%0d",mode);
        @(negedge clk);
      end
      rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;
      if(mode==0)begin
        for(int i=0;i<96;i++)if(mem.mem[dst+i]!==8'(i+trial))$fatal(1,"copy %0d",i);
      end else begin
        req_valid=1;repeat(5)begin @(negedge clk);if(req_ready)$fatal(1,"error accepted new request");end
        req_valid=0;
      end
    end
    $display("IDMA_FLAT_ERROR_PASS good_copies=2 bytes_checked=192 read_SLVERR=1 write_DECERR=1 response_hold=4 fail_closed_until_reset=1");$finish;
  end
  initial begin repeat(5000)@(posedge clk);$fatal(1,"timeout");end
endmodule
