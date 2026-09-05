`timescale 1ns/1ps
module tb_captured_residual_l2_numeric;
 localparam integer ABEATS=1536,BBEATS=768,TILES=64;
 logic clk=0;always #0.625 clk=~clk;
 logic rst=0,req=0,ready,done,ack=0,host=1;
 logic[1:0]rv,rr,sv,sr,frv,frr,fsv,fsr;logic[29:0]ra,fra;logic[1023:0]sd,fsd;
 logic wv,wr,fwv,fwr;logic[14:0]wa,fwa;logic[511:0]wd,fwd;logic[63:0]be,fbe;
 logic hwv=0,hrv=0,hrs=0;logic[14:0]hwa=0,hra=0;logic[511:0]hwd=0;
 logic[7:0]status;logic[63:0]reads,writes,bytes,cycles,fcycles,freads,fwrites,conflicts,rstalls,wstalls;
 logic[511:0]amem[0:98303],bmem[0:49151],expected[0:98303];
 longint unsigned sum_cycles=0,sum_conflicts=0;integer checked=0,fd;
 residual_l2_tile dut(.clk_i(clk),.rst_ni(rst),.request_valid_i(req),.request_ready_o(ready),
 .source_a_i(64'd0),.source_b_i(64'h20000),.destination_i(64'h40000),.elements_i(32'd24576),.b_bf16_i(1'b1),
 .rd_valid_o(rv),.rd_ready_i(rr),.rd_addr_o(ra),.rsp_valid_i(sv),.rsp_ready_o(sr),.rsp_data_i(sd),.rsp_error_i(2'b00),
 .wr_valid_o(wv),.wr_ready_i(wr),.wr_addr_o(wa),.wr_data_o(wd),.wr_be_o(be),.completion_valid_o(done),.completion_ready_i(ack),.status_o(status),
 .read_beats_o(reads),.write_beats_o(writes),.written_payload_bytes_o(bytes),.cycles_o(cycles));
 shared_l2_fabric fabric(.clk_i(clk),.rst_ni(rst),.rd_valid_i(frv),.rd_ready_o(frr),.rd_addr_i(fra),
 .rd_resp_valid_o(fsv),.rd_resp_ready_i(fsr),.rd_data_o(fsd),.wr_valid_i(fwv),.wr_ready_o(fwr),.wr_addr_i(fwa),.wr_data_i(fwd),.wr_be_i(fbe),
 .cycle_count_o(fcycles),.read_count_o(freads),.write_count_o(fwrites),.bank_conflict_count_o(conflicts),.read_stall_count_o(rstalls),.write_stall_count_o(wstalls));
 assign frv=host?{1'b0,hrv}:rv;assign fra=host?{15'd0,hra}:ra;assign fsr=host?{1'b0,hrs}:sr;
 assign rr=host?2'b0:frr;assign sv=host?2'b0:fsv;assign sd=fsd;
 assign fwv=host?hwv:wv;assign fwa=host?hwa:wa;assign fwd=host?hwd:wd;assign fbe=host?64'hffffffffffffffff:be;
 assign wr=host?1'b0:fwr;
 task put(input integer address,input logic[511:0]data);
  begin @(negedge clk);hwv=1;hwa=15'(address);hwd=data;do @(posedge clk);while(!fwr);@(negedge clk);hwv=0;end
 endtask
 task get(input integer address,output logic[511:0]data);
  begin @(negedge clk);hrv=1;hra=15'(address);do @(posedge clk);while(!frr[0]);@(negedge clk);hrv=0;hrs=1;
   do @(posedge clk);while(!fsv[0]);data=fsd[511:0];@(negedge clk);hrs=0;end
 endtask
 initial begin
  string apath,directory,outpath;logic[511:0]value;logic[63:0]rbeg,wbeg,cbeg;
  if(!$value$plusargs("ACTUAL_OPROJ=%s",apath)||!$value$plusargs("VECTORS=%s",directory)||!$value$plusargs("OUTPUT=%s",outpath))$fatal(1,"paths");
  $readmemh(apath,amem);$readmemh({directory,"/hidden_memory.memh"},bmem);$readmemh({directory,"/expected.memh"},expected);
  fd=$fopen(outpath,"w");if(!fd)$fatal(1,"output open");repeat(5)@(negedge clk);rst=1;
  for(int tile=0;tile<TILES;tile++)begin
   host=1;
   for(int i=0;i<ABEATS;i++)put(i,amem[tile*ABEATS+i]);
   for(int i=0;i<BBEATS;i++)put(2048+i,bmem[tile*BBEATS+i]);
   // Poison destination through the public write port, never load golden there.
   for(int i=0;i<ABEATS;i++)put(4096+i,'1);
   @(negedge clk);host=0;if(!ready||fsv!=0)$fatal(1,"not quiescent");rbeg=freads;wbeg=fwrites;cbeg=conflicts;
   req=1;@(posedge clk);@(negedge clk);req=0;wait(done);@(negedge clk);
   if(status||reads!=2304||writes!=1536||bytes!=98304||freads-rbeg!=2304||fwrites-wbeg!=1536||fsv!=0)$fatal(1,"tile%0d counts/status",tile);
   sum_cycles+=cycles;sum_conflicts+=conflicts-cbeg;host=1;
   for(int i=0;i<ABEATS;i++)begin
    get(4096+i,value);if(value!==expected[tile*ABEATS+i])$fatal(1,"numerical tile=%0d beat=%0d",tile,i);
    $fdisplay(fd,"%0128h",value);checked+=16;
   end
   @(negedge clk);ack=1;@(posedge clk);@(negedge clk);ack=0;
  end
  if(checked!=1572864||sum_conflicts==0)$fatal(1,"coverage");$fclose(fd);
  $display("CAPTURED_RESIDUAL_L2_NUMERICAL_PASS tiles=64 values=%0d local_cycles_sum=%0d bank_conflicts=%0d behavioral_bank_storage=1",checked,sum_cycles,sum_conflicts);$finish;
 end
 initial begin repeat(10000000)@(posedge clk);$fatal(1,"watchdog");end
endmodule
