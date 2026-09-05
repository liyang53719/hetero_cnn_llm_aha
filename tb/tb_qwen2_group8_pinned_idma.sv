`timescale 1ns/1ps
module tb_qwen2_group8_pinned_idma;
 import hetero_idma_512_pkg::*;localparam integer RECORDS=6188,BASE=4096,AW=15;logic clk=0,rst_n=0,start;always #0.625 clk=~clk;logic[127:0]rmscmd[0:1],pcmd[0:2],bcmd[0:2],ocmd[0:1],records[0:RECORDS-1];logic[55:0]rarea[0:5],pa[0:8],ba[0:8],oa[0:5];logic dqv,dqr,dsv,dsr,av,ar,asv,asr,ase,iv,ir,ior,iordy,ioe,local_source;logic[23:0]dqi;logic[127:0]dsd;logic[1:0]ak;logic[63:0]as,ad,isrc,idst;logic[31:0]ab,an,ass,ads,ilen,flat;logic trv,trr,trsv,trsr,twv,twr,brv,brr,brsv,brsr,bwv,bwr,bbusy,done;logic[AW-1:0]tra,twa,bra,bwa;logic[511:0]trd,twd,brd,bwd;logic[63:0]tbe,bbe;logic[1:0]mrv,mrr,mrsv,mrsr;logic[2*AW-1:0]mra;logic[1023:0]mrd;logic mwv,mwr;logic[AW-1:0]mwa;logic[511:0]mwd;logic[63:0]mbe;logic[63:0]cycles,lreads,lwrites,conflicts,rstalls,wstalls;logic[7:0]status,ibusy;logic[3:0]op;logic[31:0]completions,msteps,rsteps,values,lfsr;logic[63:0]dr,dw,lastar;logic[7:0]lastlen;logic[2:0]lastsize;logic[1:0]lastburst;axi_req_t iread,iwrite,local_req,ddr_req;axi_rsp_t iread_rsp,iwrite_rsp,local_rsp,ddr_rsp;logic dpending,l2pending;logic[127:0]dpending_data;logic l2owner;logic[511:0]l2pending_data,l2[0:24575],hidden[0:767],rweight[0:95],qweights[0:73727],kweights[0:12287],vweights[0:12287],qbias[0:95],kbias[0:15],vbias[0:15],positions[0:0],qexp[0:767],kexp[0:127],vexp[0:127],qbexp[0:767],kbexp[0:127],vbexp[0:127],qrexp[0:767],krexp[0:127];integer fetches,abstracts,flats,rbeats,wbeats,law,lwlast,lb,rar,rrlast;
 integer runtime_batches;logic[31:0]weight_loads,norm_loads;
 logic[63:0]roi_start_cycle;
 axi_req_t bandwidth_req;axi_rsp_t bandwidth_rsp;
 logic[63:0]budget_read_bytes,budget_write_bytes,budget_read_stall,budget_write_stall;
 axi_ddr_100_40_800mhz bandwidth(.clk_i(clk),.rst_ni(rst_n),
  .upstream_req_i(ddr_req),.upstream_rsp_o(ddr_rsp),.memory_req_o(bandwidth_req),.memory_rsp_i(bandwidth_rsp),
  .read_bytes_o(budget_read_bytes),.write_bytes_o(budget_write_bytes),
  .read_throttled_o(budget_read_stall),.write_throttled_o(budget_write_stall));
 qwen2_projection_q1024_group8_controller dut(
  .clk_i(clk),.rst_ni(rst_n),.start_i(start),.command_i(pcmd[0]),.trace_only_i(1'b0),.batch_count_i(runtime_batches),
  .descriptor_req_valid_o(dqv),.descriptor_req_ready_i(dqr),.descriptor_req_index_o(dqi),
  .descriptor_rsp_valid_i(dsv),.descriptor_rsp_ready_o(dsr),.descriptor_rsp_data_i(dsd),.descriptor_rsp_error_i(1'b0),
  .dma_req_valid_o(av),.dma_req_ready_i(ar),.dma_req_kind_o(ak),.dma_src_addr_o(as),.dma_dst_addr_o(ad),
  .dma_row_bytes_o(ab),.dma_rows_o(an),.dma_src_stride_o(ass),.dma_dst_stride_o(ads),
  .dma_rsp_valid_i(asv),.dma_rsp_ready_o(asr),.dma_rsp_error_i(ase),
  .l2_rd_valid_o(trv),.l2_rd_ready_i(trr),.l2_rd_addr_o(tra),.l2_rsp_valid_i(trsv),.l2_rsp_ready_o(trsr),.l2_rsp_data_i(trd),
  .l2_wr_valid_o(twv),.l2_wr_ready_i(twr),.l2_wr_addr_o(twa),.l2_wr_data_o(twd),.l2_wr_be_o(tbe),
  .done_o(done),.status_o(status),.matrix_steps_o(msteps),.values_o(values),
  .weight_tile_loads_o(weight_loads),.norm_batch_loads_o(norm_loads),.ddr_read_bytes_o(dr),.ddr_write_bytes_o(dw));
 qwen2_tile_idma_expand expand(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(av),.req_ready_o(ar),.req_kind_i(ak),.src_addr_i(as),.dst_addr_i(ad),.row_bytes_i(ab),.rows_i(an),.src_stride_i(ass),.dst_stride_i(ads),.rsp_valid_o(asv),.rsp_ready_i(asr),.rsp_error_o(ase),.idma_req_valid_o(iv),.idma_req_ready_i(ir),.idma_src_addr_o(isrc),.idma_dst_addr_o(idst),.idma_length_o(ilen),.idma_rsp_valid_i(ior),.idma_rsp_ready_o(iordy),.idma_rsp_error_i(ioe),.flat_requests_o(flat),.local_source_o(local_source));
 idma_backend_rw_axi_flat_wrap idma(.clk_i(clk),.rst_ni(rst_n),.req_valid_i(iv),.req_ready_o(ir),.src_addr_i(isrc),.dst_addr_i(idst),.length_i(ilen),.rsp_valid_o(ior),.rsp_ready_i(iordy),.rsp_error_o(ioe),.axi_read_req_o(iread),.axi_read_rsp_i(iread_rsp),.axi_write_req_o(iwrite),.axi_write_rsp_i(iwrite_rsp),.busy_o(ibusy));always_comb begin local_req=0;ddr_req=0;iread_rsp=0;iwrite_rsp=0;if(local_source)begin local_req=iread;ddr_req=iwrite;iread_rsp=local_rsp;iwrite_rsp=ddr_rsp;end else begin ddr_req=iread;local_req=iwrite;iread_rsp=ddr_rsp;iwrite_rsp=local_rsp;end end
 qwen2_axi_shared_l2_bridge #(.ADDR_W(AW))bridge(.clk_i(clk),.rst_ni(rst_n),.axi_req_i(local_req),.axi_rsp_o(local_rsp),.l2_rd_valid_o(brv),.l2_rd_ready_i(brr),.l2_rd_addr_o(bra),.l2_rsp_valid_i(brsv),.l2_rsp_ready_o(brsr),.l2_rsp_data_i(brd),.l2_wr_valid_o(bwv),.l2_wr_ready_i(bwr),.l2_wr_addr_o(bwa),.l2_wr_data_o(bwd),.l2_wr_be_o(bbe),.busy_o(bbusy));
 shared_l2_fabric #(.ADDR_W(AW),.ROWS_PER_BANK(6144))fabric(.clk_i(clk),.rst_ni(rst_n),.rd_valid_i(mrv),.rd_ready_o(mrr),.rd_addr_i(mra),.rd_resp_valid_o(mrsv),.rd_resp_ready_i(mrsr),.rd_data_o(mrd),.wr_valid_i(mwv),.wr_ready_o(mwr),.wr_addr_i(mwa),.wr_data_i(mwd),.wr_be_i(mbe),.cycle_count_o(cycles),.read_count_o(lreads),.write_count_o(lwrites),.bank_conflict_count_o(conflicts),.read_stall_count_o(rstalls),.write_stall_count_o(wstalls));
 axi_sim_mem#(.AddrWidth(64),.DataWidth(512),.IdWidth(4),.UserWidth(1),.axi_req_t(axi_req_t),.axi_rsp_t(axi_rsp_t),.WarnUninitialized(1'b0),.ClearErrOnAccess(1'b1),.ApplDelay(0ns),.AcqDelay(0ns))ddr(.clk_i(clk),.rst_ni(rst_n),.axi_req_i(bandwidth_req),.axi_rsp_o(bandwidth_rsp),.mon_r_last_o(),.mon_r_beat_count_o(),.mon_r_user_o(),.mon_r_id_o(),.mon_r_data_o(),.mon_r_addr_o(),.mon_r_valid_o(),.mon_w_last_o(),.mon_w_beat_count_o(),.mon_w_user_o(),.mon_w_id_o(),.mon_w_data_o(),.mon_w_addr_o(),.mon_w_valid_o());
 assign dqr=!dpending&&(lfsr[0]||lfsr[5]);assign dsv=dpending;assign dsd=dpending_data;assign mrv={brv,trv};assign mra={bra,tra};assign trr=mrr[0];assign brr=mrr[1];assign trsv=mrsv[0];assign brsv=mrsv[1];assign trd=mrd[0+:512];assign brd=mrd[512+:512];assign mrsr={brsr,trsr};assign mwv=bwv||twv;assign mwa=bwv?bwa:twa;assign mwd=bwv?bwd:twd;assign mbe=bwv?bbe:tbe;assign bwr=bwv&&mwr;assign twr=!bwv&&mwr;
 task automatic put(input[63:0]base_addr,input integer index,input[511:0]beat);for(integer b=0;b<64;b++)ddr.mem[{8'd0,base_addr}+index*64+b]=beat[b*8+:8];endtask
 task automatic chk(input[63:0]base_addr,input integer index,input[511:0]beat,input integer kind);for(integer b=0;b<64;b++)if(ddr.mem[{8'd0,base_addr}+index*64+b]!==beat[b*8+:8])$fatal(1,"kind=%0d beat=%0d byte=%0d",kind,index,b);endtask
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin lfsr<=32'h1d16a55a;dpending<=0;fetches<=0;abstracts<=0;flats<=0;rbeats<=0;wbeats<=0;end
  else begin
   lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
   if(dqv&&dqr)begin dpending<=1;dpending_data<=records[dqi-BASE];fetches<=fetches+1;end
   if(dsv&&dsr)dpending<=0;
   if(av&&ar)abstracts<=abstracts+1;
   if(iv&&ir)flats<=flats+1;
   if(iread_rsp.r_valid&&iread.r_ready)rbeats<=rbeats+1;
   if(iwrite.w_valid&&iwrite_rsp.w_ready)wbeats<=wbeats+1;
  end
 end
 initial begin
  string cp,rp,ap;
  start=0;
  if(!$value$plusargs("COMMANDS=%s",cp)||!$value$plusargs("RECORDS=%s",rp)||!$value$plusargs("ADDR=%s",ap))$fatal(1,"plusargs");
  if(!$value$plusargs("BATCHES=%d",runtime_batches))runtime_batches=2;
  if(runtime_batches<1||runtime_batches>2)$fatal(1,"fixture supports1or2 batches only");
  $readmemh(cp,pcmd);$readmemh(rp,records);$readmemh(ap,pa);
  $readmemh("work/results/qwen2_canonical_tile16_vectors/norm_token_major.memh",hidden);
  $readmemh("work/results/qwen2_canonical_q_tile16_all/q_weight_ddr_beats.memh",qweights);
  $readmemh("work/results/qwen2_canonical_q_tile16_all/q_expected_token_major.memh",qexp);
  // Projection inputs only; never preload L2 or destination/reference outputs.
  // Batch2 deliberately repeats canonical16 rows: not model rows16..31 evidence.
  for(int b=0;b<runtime_batches;b++)for(int i=0;i<768;i++)put({8'd0,pa[0]}+64'(b)*49152,i,hidden[i]);
  for(int k=0;k<1536;k++)for(int t=0;t<48;t++)put({8'd0,pa[1]}+64'(k)*3072,t,qweights[k*48+t]);
  repeat(8)@(posedge clk);rst_n=1;
  @(negedge clk);roi_start_cycle=cycles;start=1;@(posedge clk);@(negedge clk);start=0;
  wait(done);@(negedge clk);
  if(status||fetches!=6||abstracts!=6+54*runtime_batches||
     flats!=9216+1056*runtime_batches||flat!=flats||
     rbeats!=73728+5376*runtime_batches||wbeats!=rbeats||
     msteps!=73728*runtime_batches||values!=24576*runtime_batches||
     weight_loads!=48||norm_loads!=6*runtime_batches||
     dr!=4718592+294912*runtime_batches||dw!=49152*runtime_batches||
     budget_read_bytes!=dr||budget_write_bytes!=dw||ibusy!=0||bbusy)
     $fatal(1,"aggregate status=%0d fetch=%0d dma=%0d flat=%0d beats=%0d/%0d steps=%0d values=%0d bytes=%0d/%0d",status,fetches,abstracts,flats,rbeats,wbeats,msteps,values,dr,dw);
  for(int b=0;b<runtime_batches;b++)for(int i=0;i<768;i++)chk({8'd0,pa[2]}+64'(b)*49152,i,qexp[i],0);
  $display("GROUP8_PINNED_IDMA_NUMERICAL_PASS batches=%0d checked_bf16=%0d flat_requests=%0d wall_cycles=%0d useful_macs=%0d read_bytes=%0d write_bytes=%0d read_throttle=%0d write_throttle=%0d no_intermediate_injection=1",
   runtime_batches,24576*runtime_batches,flats,cycles-roi_start_cycle,64'(msteps)*512,dr,dw,budget_read_stall,budget_write_stall);
  $finish;
 end
 initial begin repeat(3500000)@(posedge clk);$fatal(1,"watchdog flat=%0d group=%0d batch=%0d state=%0d",flats,dut.group_base,dut.batch,dut.st);end
endmodule
