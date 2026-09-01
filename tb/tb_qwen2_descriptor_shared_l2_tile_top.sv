`timescale 1ns/1ps
module tb_qwen2_descriptor_shared_l2_tile_top;
 localparam integer AW=15,DBEATS=1547;logic clk=0,rst_n=0,start,done;always #0.5 clk=~clk;
 logic[127:0]cmd[0:1];logic dqv,dqr,dsv,dsr,dse;logic[23:0]dqi;logic[127:0]dsd;
 logic fqv,fqr,frv,frr;logic[AW-1:0]fqa;logic[511:0]frd;
 logic dmv,dmr;logic[1:0]dmk;logic[63:0]dms,dmd;logic[31:0]dmrb,dmrows,dmss,dmds;logic drsv,drsr,drse;
 logic trv,trr,trsv,trsr,twv,twr;logic[AW-1:0]tra,twa;logic[511:0]trd,twd;logic[63:0]tbe;
 logic[7:0]status;logic[63:0]ddrr,ddrw;logic[31:0]l2r,l2w;
 logic[1:0]mrv,mrr,mrsv,mrsr;logic[2*AW-1:0]mra;logic[1023:0]mrd;logic mwv,mwr;logic[AW-1:0]mwa;logic[511:0]mwd;logic[63:0]mbe;logic[63:0]cy,reads,writes,conflicts,rstalls,wstalls;
 logic host_mode,hwv;logic[AW-1:0]hwa;logic[511:0]hwd;logic[511:0]db[0:DBEATS-1],hidden[0:47],rw[0:95],qw[0:1535],enorm[0:47],eq[0:0];logic[55:0]eaddr[0:5];
 logic[31:0]lfsr;logic dma_pending;integer dma_delay,dma_requests,dma_responses;
 shared_l2_descriptor_port #(.ADDR_W(AW),.SRAM_BYTES(64'd1572864))port(.clk_i(clk),.rst_ni(rst_n),.descriptor_base_i(0),.descriptor_req_valid_i(dqv),.descriptor_req_ready_o(dqr),.descriptor_req_index_i(dqi),.descriptor_rsp_valid_o(dsv),.descriptor_rsp_ready_i(dsr),.descriptor_rsp_data_o(dsd),.descriptor_rsp_error_o(dse),.fabric_req_valid_o(fqv),.fabric_req_ready_i(fqr),.fabric_req_addr_o(fqa),.fabric_rsp_valid_i(frv),.fabric_rsp_ready_o(frr),.fabric_rsp_data_i(frd),.fabric_rsp_error_i(1'b0));
 shared_l2_fabric #(.ADDR_W(AW),.ROWS_PER_BANK(6144))mem(.clk_i(clk),.rst_ni(rst_n),.rd_valid_i(mrv),.rd_ready_o(mrr),.rd_addr_i(mra),.rd_resp_valid_o(mrsv),.rd_resp_ready_i(mrsr),.rd_data_o(mrd),.wr_valid_i(mwv),.wr_ready_o(mwr),.wr_addr_i(mwa),.wr_data_i(mwd),.wr_be_i(mbe),.cycle_count_o(cy),.read_count_o(reads),.write_count_o(writes),.bank_conflict_count_o(conflicts),.read_stall_count_o(rstalls),.write_stall_count_o(wstalls));
 qwen2_descriptor_shared_l2_tile_top #(.ADDR_W(AW))top(.clk_i(clk),.rst_ni(rst_n),.start_i(start),.rms_command_i(cmd[0]),.matrix_command_i(cmd[1]),.q_column_tile_i(6'd0),.descriptor_req_valid_o(dqv),.descriptor_req_ready_i(dqr),.descriptor_req_index_o(dqi),.descriptor_rsp_valid_i(dsv),.descriptor_rsp_ready_o(dsr),.descriptor_rsp_data_i(dsd),.descriptor_rsp_error_i(dse),.dma_req_valid_o(dmv),.dma_req_ready_i(dmr),.dma_req_kind_o(dmk),.dma_src_addr_o(dms),.dma_dst_addr_o(dmd),.dma_row_bytes_o(dmrb),.dma_rows_o(dmrows),.dma_src_stride_o(dmss),.dma_dst_stride_o(dmds),.dma_rsp_valid_i(drsv),.dma_rsp_ready_o(drsr),.dma_rsp_error_i(drse),.l2_rd_valid_o(trv),.l2_rd_ready_i(trr),.l2_rd_addr_o(tra),.l2_rsp_valid_i(trsv),.l2_rsp_ready_o(trsr),.l2_rsp_data_i(trd),.l2_wr_valid_o(twv),.l2_wr_ready_i(twr),.l2_wr_addr_o(twa),.l2_wr_data_o(twd),.l2_wr_be_o(tbe),.done_o(done),.status_o(status),.ddr_read_bytes_o(ddrr),.ddr_write_bytes_o(ddrw),.l2_read_beats_o(l2r),.l2_write_beats_o(l2w));
 assign mrv={fqv,trv&&(lfsr[0]||lfsr[4])};assign mra={fqa,tra};assign trr=mrr[0]&&(lfsr[0]||lfsr[4]);assign fqr=mrr[1];assign trsv=mrsv[0]&&(lfsr[1]||lfsr[6]);assign trd=mrd[0+:512];assign frv=mrsv[1];assign frd=mrd[512+:512];assign mrsr={frr,trsr&&(lfsr[1]||lfsr[6])};
 assign mwv=host_mode?hwv:(twv&&(lfsr[2]||lfsr[7]));assign mwa=host_mode?hwa:twa;assign mwd=host_mode?hwd:twd;assign mbe=host_mode?'1:tbe;assign twr=!host_mode&&mwr&&(lfsr[2]||lfsr[7]);assign drse=0;assign dmr=!dma_pending&&!drsv&&(lfsr[3]||lfsr[8]);
 always_ff@(posedge clk or negedge rst_n)begin if(!rst_n)begin lfsr<=32'h91ac573d;dma_pending<=0;dma_delay<=0;dma_requests<=0;dma_responses<=0;drsv<=0;end else begin
  lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
  if(dmv&&dmr)begin
   case(dma_requests)
    0:if(dmk!=0||dms!={8'd0,eaddr[0]}||dmd!=64'h40000||dmrb!=3072||dmrows!=1)$fatal(1,"dma0");
    1:if(dmk!=0||dms!={8'd0,eaddr[1]}||dmd!=64'h41000||dmrb!=6144||dmrows!=1)$fatal(1,"dma1");
    2:if(dmk!=1||dms!={8'd0,eaddr[4]}||dmd!=64'h44000||dmrb!=64||dmrows!=1536||dmss!=3072||dmds!=64)$fatal(1,"dma2");
    3:if(dmk!=2||dms!=64'h5c000||dmd!={8'd0,eaddr[5]}||dmrb!=64||dmrows!=1)$fatal(1,"dma3");
   endcase dma_requests<=dma_requests+1;dma_pending<=1;dma_delay<=lfsr[5+:3];end
  if(dma_pending&&!drsv)begin if(dma_delay==0)drsv<=1;else dma_delay<=dma_delay-1;end
  if(drsv&&drsr)begin drsv<=0;dma_pending<=0;dma_responses<=dma_responses+1;end
 end end
 task automatic hwrite(input[AW-1:0]a,input[511:0]d);begin @(negedge clk);hwa=a;hwd=d;hwv=1;do@(posedge clk);while(!mwr);@(negedge clk);hwv=0;end endtask
 task automatic hread(input[AW-1:0]a,input[511:0]e);begin @(negedge clk);force mrv[0]=1;force mra[0+:AW]=a;force mrsr[0]=0;do@(posedge clk);while(!mrr[0]);@(negedge clk);release mrv[0];wait(mrsv[0]);if(mrd[0+:512]!==e)$fatal(1,"readback %0d",a);@(negedge clk);force mrsr[0]=1;@(posedge clk);@(negedge clk);release mra[0+:AW];release mrsr[0];end endtask
 initial begin start=0;host_mode=1;hwv=0;hwa=0;hwd=0;
  $readmemh("work/results/qwen2_descriptor_shared_l2_tile_top/beats.memh",db);$readmemh("work/results/qwen2_descriptor_shared_l2_tile_top/commands.memh",cmd);$readmemh("work/results/qwen2_descriptor_shared_l2_tile_top/addresses.memh",eaddr);$readmemh("work/results/qwen2_shared_l2_tile_payload/hidden_beats.memh",hidden);$readmemh("work/results/qwen2_shared_l2_tile_payload/rms_weight_beats.memh",rw);$readmemh("work/results/qwen2_shared_l2_tile_payload/q_weight_beats.memh",qw);$readmemh("work/results/qwen2_shared_l2_tile_payload/norm_expected_beats.memh",enorm);$readmemh("work/results/qwen2_shared_l2_tile_payload/q_expected_beat.memh",eq);
  repeat(6)@(posedge clk);rst_n=1;repeat(2)@(posedge clk);for(integer i=0;i<DBEATS;i++)hwrite(1024+i,db[i]);for(integer i=0;i<48;i++)hwrite(4096+i,hidden[i]);for(integer i=0;i<96;i++)hwrite(4160+i,rw[i]);for(integer i=0;i<1536;i++)hwrite(4352+i,qw[i]);
  @(negedge clk);host_mode=0;start=1;@(posedge clk);@(negedge clk);start=0;wait(done);if(status||dma_requests!=4||dma_responses!=4||ddrr!=107520||ddrw!=64||l2r!=1680||l2w!=49)$fatal(1,"top accounting status=%0d dma=%0d/%0d ddr=%0d/%0d l2=%0d/%0d",status,dma_requests,dma_responses,ddrr,ddrw,l2r,l2w);
  for(integer i=0;i<48;i++)hread(4288+i,enorm[i]);hread(5888,eq[0]);$display("QWEN2_DESCRIPTOR_SHARED_L2_TILE_TOP_PASS commands=2 descriptor_fetches=12 dma_requests=4 ddr_read_bytes=107520 ddr_write_bytes=64 l2_read_beats=1680 l2_write_beats=49 bf16_bit_exact=1568 engine_completions=2 random_backpressure=1");$finish;end
 initial begin repeat(500000)@(posedge clk);$fatal(1,"timeout status=%0d dma=%0d/%0d topactive=%0d",status,dma_requests,dma_responses,top.active_q);end
endmodule
