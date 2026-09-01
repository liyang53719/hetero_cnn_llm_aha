`timescale 1ns/1ps
module tb_qwen2_idma_shared_l2_data;
 import hetero_idma_512_pkg::*;localparam integer AW=15;logic clk=0,rst_n=0;always #0.5 clk=~clk;
 logic rv,rr;logic[1:0]kind;logic[63:0]src,dst;logic[31:0]bytes,rows,ss,ds;logic sv,sr,se;
 logic iv,ir,ov,orr,oe,local_source;logic[63:0]isrc,idst;logic[31:0]ilen,flat;logic[7:0]busy;
 axi_req_t read_req,write_req,local_req,ddr_req;
 axi_rsp_t read_rsp,write_rsp,local_rsp,ddr_rsp;
 logic brv,brr,brsv,brsr,bwv,bwr,bbusy;logic[AW-1:0]bra,bwa;logic[511:0]brd,bwd;logic[63:0]bbe;
 logic[1:0]mrv,mrr,mrsv,mrsr;logic[2*AW-1:0]mra;logic[1023:0]mrd;logic mwv,mwr;logic[AW-1:0]mwa;logic[511:0]mwd;logic[63:0]mbe;logic[63:0]cy,lreads,lwrites,conflicts,rstalls,wstalls;
 logic host_write,hwv,hrv,hrsr;logic[AW-1:0]hwa,hra;logic[511:0]hwd;logic[55:0]a[0:5];logic[511:0]hidden[0:47],nw[0:95],qw[0:1535],eq[0:0];
 integer abstract_req,abstract_rsp,flat_seen,rbeats,wbeats,local_awhs,local_wlast,local_bhs,last_aw_len;
 qwen2_tile_idma_expand expand(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(rv),.req_ready_o(rr),
  .req_kind_i(kind),.src_addr_i(src),.dst_addr_i(dst),.row_bytes_i(bytes),.rows_i(rows),
  .src_stride_i(ss),.dst_stride_i(ds),.rsp_valid_o(sv),.rsp_ready_i(sr),.rsp_error_o(se),
  .idma_req_valid_o(iv),.idma_req_ready_i(ir),.idma_src_addr_o(isrc),.idma_dst_addr_o(idst),
  .idma_length_o(ilen),.idma_rsp_valid_i(ov),.idma_rsp_ready_o(orr),.idma_rsp_error_i(oe),
  .flat_requests_o(flat),.local_source_o(local_source));
 idma_backend_rw_axi_flat_wrap idma(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(iv),.req_ready_o(ir),
  .src_addr_i(isrc),.dst_addr_i(idst),.length_i(ilen),.rsp_valid_o(ov),.rsp_ready_i(orr),
  .rsp_error_o(oe),.axi_read_req_o(read_req),.axi_read_rsp_i(read_rsp),
  .axi_write_req_o(write_req),.axi_write_rsp_i(write_rsp),.busy_o(busy));
 always_comb begin local_req='0;ddr_req='0;read_rsp='0;write_rsp='0;
  if(local_source)begin local_req=read_req;ddr_req=write_req;read_rsp=local_rsp;write_rsp=ddr_rsp;end
  else begin ddr_req=read_req;local_req=write_req;read_rsp=ddr_rsp;write_rsp=local_rsp;end end
 qwen2_axi_shared_l2_bridge #(.ADDR_W(AW))bridge(.clk_i(clk),.rst_ni(rst_n),.axi_req_i(local_req),.axi_rsp_o(local_rsp),.l2_rd_valid_o(brv),.l2_rd_ready_i(brr),.l2_rd_addr_o(bra),.l2_rsp_valid_i(brsv),.l2_rsp_ready_o(brsr),.l2_rsp_data_i(brd),.l2_wr_valid_o(bwv),.l2_wr_ready_i(bwr),.l2_wr_addr_o(bwa),.l2_wr_data_o(bwd),.l2_wr_be_o(bbe),.busy_o(bbusy));
 axi_sim_mem#(.AddrWidth(64),.DataWidth(512),.IdWidth(4),.UserWidth(1),.axi_req_t(axi_req_t),.axi_rsp_t(axi_rsp_t),.WarnUninitialized(1'b0),.ClearErrOnAccess(1'b1),.ApplDelay(0ns),.AcqDelay(0ns))ddr(.clk_i(clk),.rst_ni(rst_n),.axi_req_i(ddr_req),.axi_rsp_o(ddr_rsp),.mon_r_last_o(),.mon_r_beat_count_o(),.mon_r_user_o(),.mon_r_id_o(),.mon_r_data_o(),.mon_r_addr_o(),.mon_r_valid_o(),.mon_w_last_o(),.mon_w_beat_count_o(),.mon_w_user_o(),.mon_w_id_o(),.mon_w_data_o(),.mon_w_addr_o(),.mon_w_valid_o());
 shared_l2_fabric #(.ADDR_W(AW),.ROWS_PER_BANK(6144))l2(.clk_i(clk),.rst_ni(rst_n),.rd_valid_i(mrv),.rd_ready_o(mrr),.rd_addr_i(mra),.rd_resp_valid_o(mrsv),.rd_resp_ready_i(mrsr),.rd_data_o(mrd),.wr_valid_i(mwv),.wr_ready_o(mwr),.wr_addr_i(mwa),.wr_data_i(mwd),.wr_be_i(mbe),.cycle_count_o(cy),.read_count_o(lreads),.write_count_o(lwrites),.bank_conflict_count_o(conflicts),.read_stall_count_o(rstalls),.write_stall_count_o(wstalls));
 assign mrv={hrv,brv};assign mra={hra,bra};assign brr=mrr[0];assign brsv=mrsv[0];assign brd=mrd[0+:512];assign mrsr={hrsr,brsr};assign mwv=host_write?hwv:bwv;assign mwa=host_write?hwa:bwa;assign mwd=host_write?hwd:bwd;assign mbe=host_write?'1:bbe;assign bwr=!host_write&&mwr;
 always_ff@(posedge clk or negedge rst_n)begin if(!rst_n)begin flat_seen<=0;rbeats<=0;wbeats<=0;local_awhs<=0;local_wlast<=0;local_bhs<=0;last_aw_len<=-1;end else begin if(iv&&ir)flat_seen<=flat_seen+1;if(read_rsp.r_valid&&read_req.r_ready)rbeats<=rbeats+1;if(write_req.w_valid&&write_rsp.w_ready)wbeats<=wbeats+1;if(local_req.aw_valid&&local_rsp.aw_ready)begin local_awhs<=local_awhs+1;last_aw_len<=local_req.aw.len;end if(local_req.w_valid&&local_rsp.w_ready&&local_req.w.last)local_wlast<=local_wlast+1;if(local_rsp.b_valid&&local_req.b_ready)local_bhs<=local_bhs+1;end end
 task automatic send(input[1:0]k,input[63:0]s,input[63:0]d,input[31:0]b,input[31:0]n,input[31:0]sx,input[31:0]dx);begin @(negedge clk);kind=k;src=s;dst=d;bytes=b;rows=n;ss=sx;ds=dx;rv=1;do@(posedge clk);while(!rr);@(negedge clk);rv=0;abstract_req++;do@(posedge clk);while(!(sv&&sr));if(se)$fatal(1,"response error");abstract_rsp++;end endtask
 task automatic hwrite(input[AW-1:0]ad,input[511:0]data);begin @(negedge clk);hwa=ad;hwd=data;hwv=1;do@(posedge clk);while(!mwr);@(negedge clk);hwv=0;end endtask
 task automatic hread(input[AW-1:0]ad,input[511:0]exp);begin @(negedge clk);hrv=1;hra=ad;hrsr=0;do@(posedge clk);while(!mrr[1]);@(negedge clk);hrv=0;wait(mrsv[1]);if(mrd[512+:512]!==exp)$fatal(1,"local compare %0d",ad);@(negedge clk);hrsr=1;@(posedge clk);@(negedge clk);hrsr=0;end endtask
 initial begin string ap,hp,np,qp,op;rv=0;sr=1;kind=0;src=0;dst=0;bytes=0;rows=0;ss=0;ds=0;host_write=0;hwv=0;hrv=0;hrsr=0;hwa=0;hra=0;hwd=0;abstract_req=0;abstract_rsp=0;
  if(!$value$plusargs("ADDR_MEM=%s",ap)||!$value$plusargs("HIDDEN=%s",hp)||!$value$plusargs("NORM_WEIGHT=%s",np)||!$value$plusargs("Q_WEIGHT=%s",qp)||!$value$plusargs("Q_OUT=%s",op))$fatal(1,"vector plusargs missing");$readmemh(ap,a);$readmemh(hp,hidden);$readmemh(np,nw);$readmemh(qp,qw);$readmemh(op,eq);
  for(integer i=0;i<48;i++)for(integer b=0;b<64;b++)ddr.mem[{8'd0,a[0]}+i*64+b]=hidden[i][b*8+:8];
  for(integer i=0;i<96;i++)for(integer b=0;b<64;b++)ddr.mem[{8'd0,a[1]}+i*64+b]=nw[i][b*8+:8];
  for(integer i=0;i<1536;i++)for(integer b=0;b<64;b++)ddr.mem[{8'd0,a[4]}+i*3072+b]=qw[i][b*8+:8];
  repeat(8)@(posedge clk);rst_n=1;send(0,{8'd0,a[0]},64'h40000,3072,1,3072,3072);send(0,{8'd0,a[1]},64'h41000,6144,1,6144,6144);send(1,{8'd0,a[4]},64'h44000,64,1536,3072,64);
  for(integer i=0;i<48;i++)hread(4096+i,hidden[i]);for(integer i=0;i<96;i++)hread(4160+i,nw[i]);for(integer i=0;i<1536;i++)hread(4352+i,qw[i]);
  host_write=1;hwrite(5888,eq[0]);host_write=0;send(2,64'h5c000,{8'd0,a[5]},64,1,64,64);for(integer b=0;b<64;b++)if(ddr.mem[{8'd0,a[5]}+b]!==eq[0][b*8+:8])$fatal(1,"DDR store byte %0d",b);
  repeat(10)@(posedge clk);if(abstract_req!=4||abstract_rsp!=4||flat_seen!=1546||flat!=1546||rbeats!=1681||wbeats!=1681||busy||bbusy)$fatal(1,"counts");
  $display("QWEN2_IDMA_SHARED_L2_DATA_PASS abstract_requests=4 flat_requests=1546 axi_read_beats=1681 axi_write_beats=1681 local_load_beats=1680 local_store_beats=1 byte_exact_load_beats=1680 byte_exact_store_bytes=64 q_weight_rows=1536 errors=0");$finish;end
 initial begin repeat(1000000)@(posedge clk);$fatal(1,"timeout flat=%0d abstract=%0d/%0d expand=%0d busy=%h cbusy=%0d l2=%0d/%0d beats=%0d/%0d awhs=%0d awlen=%0d wlast=%0d bhs=%0d memreq=%0d memwe=%0d gnt=%0d mrvalid=%0d axi_ar=%0d axi_r=%0d axi_aw=%0d axi_w=%0d axi_b=%0d",flat_seen,abstract_req,abstract_rsp,expand.state_q,busy,bridge.converter_busy,lreads,lwrites,rbeats,wbeats,local_awhs,last_aw_len,local_wlast,local_bhs,bridge.mem_req,bridge.mem_we,bridge.mem_gnt,bridge.mem_rvalid,read_req.ar_valid,read_rsp.r_valid,write_req.aw_valid,write_req.w_valid,write_rsp.b_valid);end
endmodule
