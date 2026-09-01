`timescale 1ns/1ps
module tb_qwen2_tile_idma_expand;
 import hetero_idma_512_pkg::*;logic clk=0,rst_n=0;always #0.5 clk=~clk;
 logic rv,rr;logic[1:0]kind;logic[63:0]src,dst;logic[31:0]bytes,rows,ss,ds;logic sv,sr,se;
 logic iv,ir,ov,orr,oe;logic[63:0]isrc,idst;logic[31:0]ilen,flat;logic[7:0]busy;
 axi_req_t read_req,write_req,joined_req;axi_rsp_t read_rsp,write_rsp,joined_rsp;
 logic[55:0]a[0:5];integer abstract_req,abstract_rsp,flat_seen,rbeats,wbeats;
 qwen2_tile_idma_expand expand(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(rv),.req_ready_o(rr),
  .req_kind_i(kind),.src_addr_i(src),.dst_addr_i(dst),.row_bytes_i(bytes),.rows_i(rows),
  .src_stride_i(ss),.dst_stride_i(ds),.rsp_valid_o(sv),.rsp_ready_i(sr),.rsp_error_o(se),
  .idma_req_valid_o(iv),.idma_req_ready_i(ir),.idma_src_addr_o(isrc),.idma_dst_addr_o(idst),
  .idma_length_o(ilen),.idma_rsp_valid_i(ov),.idma_rsp_ready_o(orr),.idma_rsp_error_i(oe),
  .flat_requests_o(flat));
 idma_backend_rw_axi_flat_wrap idma(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(iv),.req_ready_o(ir),
  .src_addr_i(isrc),.dst_addr_i(idst),.length_i(ilen),.rsp_valid_o(ov),.rsp_ready_i(orr),
  .rsp_error_o(oe),.axi_read_req_o(read_req),.axi_read_rsp_i(read_rsp),
  .axi_write_req_o(write_req),.axi_write_rsp_i(write_rsp),.busy_o(busy));
 axi_rw_join#(.axi_req_t(axi_req_t),.axi_resp_t(axi_rsp_t))u_join(.clk_i(clk),.rst_ni(rst_n),
  .slv_read_req_i(read_req),.slv_read_resp_o(read_rsp),.slv_write_req_i(write_req),
  .slv_write_resp_o(write_rsp),.mst_req_o(joined_req),.mst_resp_i(joined_rsp));
 axi_sim_mem#(.AddrWidth(64),.DataWidth(512),.IdWidth(4),.UserWidth(1),.axi_req_t(axi_req_t),
  .axi_rsp_t(axi_rsp_t),.WarnUninitialized(1'b0),.ClearErrOnAccess(1'b1),.ApplDelay(0ns),
  .AcqDelay(0ns))mem(.clk_i(clk),.rst_ni(rst_n),.axi_req_i(joined_req),.axi_rsp_o(joined_rsp),
  .mon_r_last_o(),.mon_r_beat_count_o(),.mon_r_user_o(),.mon_r_id_o(),.mon_r_data_o(),
  .mon_r_addr_o(),.mon_r_valid_o(),.mon_w_last_o(),.mon_w_beat_count_o(),.mon_w_user_o(),
  .mon_w_id_o(),.mon_w_data_o(),.mon_w_addr_o(),.mon_w_valid_o());
 always_ff@(posedge clk or negedge rst_n)begin if(!rst_n)begin flat_seen<=0;rbeats<=0;wbeats<=0;end else begin
  if(iv&&ir)begin
   if(flat_seen==0&&(isrc!={8'd0,a[0]}||idst!=64'h40000||ilen!=1024))$fatal(1,"flat0");
   if(flat_seen==2&&(isrc!={8'd0,a[0]}+2048||idst!=64'h40800||ilen!=1024))$fatal(1,"flat0_last");
   if(flat_seen==3&&(isrc!={8'd0,a[1]}||idst!=64'h41000||ilen!=1024))$fatal(1,"flat1");
   if(flat_seen==8&&(isrc!={8'd0,a[1]}+5120||idst!=64'h42400||ilen!=1024))$fatal(1,"flat1_last");
   if(flat_seen==9&&(isrc!={8'd0,a[4]}||idst!=64'h44000||ilen!=64))$fatal(1,"flat2");
   if(flat_seen==1544&&(isrc!={8'd0,a[4]}+64'd1535*3072||idst!=64'h44000+64'd1535*64||ilen!=64))$fatal(1,"flat_last_row");
   if(flat_seen==1545&&(isrc!=64'h5c000||idst!={8'd0,a[5]}||ilen!=64))$fatal(1,"flat_store");
   if(flat_seen==1546&&(isrc!=64'h70000000||idst!=64'h71000000||ilen!=1024))$fatal(1,"coalesced_load16");
   if(flat_seen==1593&&(isrc!=64'h7000bc00||idst!=64'h7100bc00||ilen!=1024))$fatal(1,"coalesced_load16_last");
   if(flat_seen==1594&&(isrc!=64'h72000000||idst!=64'h73000000||ilen!=64))$fatal(1,"coalesced_store16");
   if(flat_seen==2361&&(isrc!=64'h7200bfc0||idst!=64'h7300bfc0||ilen!=64))$fatal(1,"coalesced_store16_last");flat_seen<=flat_seen+1;end
  if(joined_rsp.r_valid&&joined_req.r_ready)rbeats<=rbeats+1;if(joined_req.w_valid&&joined_rsp.w_ready)wbeats<=wbeats+1;
 end end
 task automatic send(input[1:0]k,input[63:0]s,input[63:0]d,input[31:0]b,input[31:0]n,input[31:0]sx,input[31:0]dx);
  begin @(negedge clk);kind=k;src=s;dst=d;bytes=b;rows=n;ss=sx;ds=dx;rv=1;do@(posedge clk);while(!rr);@(negedge clk);rv=0;abstract_req++;
   do@(posedge clk);while(!(sv&&sr));if(se)$fatal(1,"abstract response error");abstract_rsp++;end endtask
 initial begin string path;rv=0;sr=1;kind=0;src=0;dst=0;bytes=0;rows=0;ss=0;ds=0;abstract_req=0;abstract_rsp=0;
  if(!$value$plusargs("ADDR_MEM=%s",path))$fatal(1,"ADDR_MEM missing");$readmemh(path,a);repeat(8)@(posedge clk);rst_n=1;
  send(0,{8'd0,a[0]},64'h40000,3072,1,3072,3072);send(0,{8'd0,a[1]},64'h41000,6144,1,6144,6144);
  send(1,{8'd0,a[4]},64'h44000,64,1536,3072,64);send(2,64'h5c000,{8'd0,a[5]},64,1,64,64);send(1,64'h70000000,64'h71000000,3072,16,3072,3072);send(3,64'h72000000,64'h73000000,3072,16,3072,3072);
  repeat(10)@(posedge clk);if(abstract_req!=6||abstract_rsp!=6||flat_seen!=2362||flat!=2362||rbeats!=3217||wbeats!=3217||busy!=0)$fatal(1,"counts abstract=%0d/%0d flat=%0d/%0d beats=%0d/%0d busy=%h",abstract_req,abstract_rsp,flat_seen,flat,rbeats,wbeats,busy);
  $display("QWEN2_PINNED_IDMA_TILE_PASS abstract_requests=6 flat_requests=2362 read_beats=3217 write_beats=3217 max_load_flat_bytes=1024 max_store_flat_bytes=64 coalesced_load16=48 coalesced_store16=768 idma_errors=0");$finish;end
 initial begin repeat(500000)@(posedge clk);$fatal(1,"timeout flat=%0d abstract=%0d/%0d",flat_seen,abstract_req,abstract_rsp);end
endmodule
