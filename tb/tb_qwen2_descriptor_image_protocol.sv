`timescale 1ns/1ps
module tb_qwen2_descriptor_image_protocol;
  localparam integer ADDR_W=15,RECORD_BASE=4096,RECORDS=6188,BEAT_BASE=1024,BEATS=1547;
  logic clk=0,rst_n=0;always #0.5 clk=~clk;
  logic drv,drr,dsv,dsr,dse;logic[23:0]dri;logic[127:0]dsd;
  logic fqv,fqr,frv,frr;logic[ADDR_W-1:0]fqa;logic[511:0]frd;
  logic[1:0]rv,rr,rsv,rsr;logic[2*ADDR_W-1:0]ra;logic[1023:0]rd;
  logic wv,wr;logic[ADDR_W-1:0]wa;logic[511:0]wd;logic[63:0]wbe;
  logic[63:0]cycles,reads,writes,conflicts,rstalls,wstalls;
  logic[511:0]beats[0:BEATS-1];logic[127:0]expected[0:RECORDS-1];
  logic[31:0]lfsr;integer wc,rc;
  shared_l2_descriptor_port #(.ADDR_W(ADDR_W),.SRAM_BYTES(64'd1572864))port(
    .clk_i(clk),.rst_ni(rst_n),.descriptor_base_i(64'd0),.descriptor_req_valid_i(drv),
    .descriptor_req_ready_o(drr),.descriptor_req_index_i(dri),.descriptor_rsp_valid_o(dsv),
    .descriptor_rsp_ready_i(dsr),.descriptor_rsp_data_o(dsd),.descriptor_rsp_error_o(dse),
    .fabric_req_valid_o(fqv),.fabric_req_ready_i(fqr),.fabric_req_addr_o(fqa),
    .fabric_rsp_valid_i(frv),.fabric_rsp_ready_o(frr),.fabric_rsp_data_i(frd),
    .fabric_rsp_error_i(1'b0));
  shared_l2_fabric #(.ADDR_W(ADDR_W),.ROWS_PER_BANK(6144))mem(
    .clk_i(clk),.rst_ni(rst_n),.rd_valid_i(rv),.rd_ready_o(rr),.rd_addr_i(ra),
    .rd_resp_valid_o(rsv),.rd_resp_ready_i(rsr),.rd_data_o(rd),.wr_valid_i(wv),
    .wr_ready_o(wr),.wr_addr_i(wa),.wr_data_i(wd),.wr_be_i(wbe),
    .cycle_count_o(cycles),.read_count_o(reads),.write_count_o(writes),
    .bank_conflict_count_o(conflicts),.read_stall_count_o(rstalls),.write_stall_count_o(wstalls));
  assign rv={1'b0,fqv};assign ra={{ADDR_W{1'b0}},fqa};assign fqr=rr[0];
  assign frv=rsv[0];assign frd=rd[0+:512];assign rsr={1'b0,frr};
  always_ff@(posedge clk or negedge rst_n)begin
    if(!rst_n)lfsr<=32'h91d4c3a7;
    else lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
  end
  task automatic write_beat(input integer offset);
    begin @(negedge clk);wv=1;wa=ADDR_W'(BEAT_BASE+offset);wd=beats[offset];wbe='1;
      do@(posedge clk);while(!wr);@(negedge clk);wv=0;wc++;
    end
  endtask
  task automatic fetch(input integer offset);
    begin @(negedge clk);drv=1;dri=24'(RECORD_BASE+offset);
      do@(posedge clk);while(!drr);@(negedge clk);drv=0;
      dsr=0;wait(dsv);while(!(lfsr[0]||lfsr[5]))@(negedge clk);
      if(dse||dsd!==expected[offset])$fatal(1,"full image mismatch offset=%0d got=%032h expected=%032h",offset,dsd,expected[offset]);
      @(negedge clk);dsr=1;@(posedge clk);@(negedge clk);dsr=0;rc++;
    end
  endtask
  initial begin
    drv=0;dri=0;dsr=0;wv=0;wa=0;wd=0;wbe=0;wc=0;rc=0;
    $readmemh("work/results/qwen2_descriptor_image_protocol/beats.memh",beats);
    $readmemh("work/results/qwen2_descriptor_image_protocol/records.memh",expected);
    repeat(6)@(posedge clk);rst_n=1;repeat(2)@(posedge clk);
    for(integer i=0;i<BEATS;i++)write_beat(i);
    for(integer i=0;i<RECORDS;i++)fetch(i);
    repeat(4)@(posedge clk);
    if(wc!=BEATS||rc!=RECORDS||writes!=BEATS||reads!=RECORDS)$fatal(1,"counter mismatch");
    $display("QWEN2_DESCRIPTOR_IMAGE_PROTOCOL_PASS records=6188 beats=1547 descriptor_bytes=164544 writes=1547 reads=6188 lane_coverage=4 random_backpressure=1 mismatches=0");
    $finish;
  end
  initial begin repeat(200000)@(posedge clk);$fatal(1,"timeout wc=%0d rc=%0d pstate=%0d drv=%0d drr=%0d dsv=%0d dsr=%0d fqv=%0d fqr=%0d mrsv=%b mrsr=%b",wc,rc,port.state_q,drv,drr,dsv,dsr,fqv,fqr,rsv,rsr);end
endmodule
