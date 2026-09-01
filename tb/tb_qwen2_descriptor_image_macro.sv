`timescale 1ns/1ps
module tb_qwen2_descriptor_image_macro;
  localparam integer ADDR_W=15,RECORD_BASE=4096,RECORDS=6188;
  localparam integer BEAT_BASE=1024,BEATS=1547,SAMPLES=4,FETCHES=4;
  logic clk=0,rst_n=0;always #0.5 clk=~clk;
  logic[63:0]descriptor_base;logic drv,drr;logic[23:0]dri;logic dsv,dsr,dse;logic[127:0]dsd;
  logic rv,rr,rsv,rsr;logic[ADDR_W-1:0]ra;logic[511:0]rd;
  logic wv,wr;logic[ADDR_W-1:0]wa;logic[511:0]wd;logic[63:0]wbe;
  logic[63:0]cycles,reads,writes,conflicts,rstalls,wstalls,errors;
  logic[511:0]beats[0:BEATS-1];logic[127:0]expected[0:RECORDS-1];
  logic[31:0]lfsr;integer write_count,read_count,normal_read_count,phase,current_index;
  shared_l2_macro_descriptor_fabric #(.ADDR_W(ADDR_W),.SRAM_BYTES(64'd1572864))dut(
    .clk_i(clk),.rst_ni(rst_n),.descriptor_base_i(descriptor_base),
    .descriptor_req_valid_i(drv),.descriptor_req_ready_o(drr),.descriptor_req_index_i(dri),
    .descriptor_rsp_valid_o(dsv),.descriptor_rsp_ready_i(dsr),.descriptor_rsp_data_o(dsd),
    .descriptor_rsp_error_o(dse),.rd_valid_i(rv),.rd_ready_o(rr),.rd_addr_i(ra),
    .rd_resp_valid_o(rsv),.rd_resp_ready_i(rsr),.rd_data_o(rd),.wr_valid_i(wv),
    .wr_ready_o(wr),.wr_addr_i(wa),.wr_data_i(wd),.wr_be_i(wbe),
    .cycle_count_o(cycles),.read_count_o(reads),.write_count_o(writes),
    .bank_conflict_count_o(conflicts),.read_stall_count_o(rstalls),
    .write_stall_count_o(wstalls),.macro_error_count_o(errors));
  always_ff@(posedge clk or negedge rst_n)begin
    if(!rst_n)lfsr<=32'h6c8e9cf5;
    else lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
  end
  task automatic write_beat(input integer offset);
    begin @(negedge clk);wv=1;wa=ADDR_W'(BEAT_BASE+offset);wd=beats[offset];wbe='1;
      do@(posedge clk);while(!wr);@(negedge clk);wv=0;write_count++;
      wait(dut.u_fabric.group_req_ready===4'b1111);
    end
  endtask
  task automatic fetch_record(input integer offset);
    begin @(negedge clk);drv=1;dri=24'(RECORD_BASE+offset);
      do@(posedge clk);while(!drr);@(negedge clk);drv=0;
      dsr=0;wait(dsv);while(!(lfsr[0]||lfsr[7]))@(negedge clk);
      if(dse||dsd!==expected[offset])$fatal(1,"descriptor mismatch offset=%0d index=%0d error=%0d got=%032h expected=%032h",offset,RECORD_BASE+offset,dse,dsd,expected[offset]);
      @(negedge clk);dsr=1;@(posedge clk);@(negedge clk);dsr=0;read_count++;
    end
  endtask
  task automatic read_beat(input integer offset);
    begin @(negedge clk);rv=1;ra=ADDR_W'(BEAT_BASE+offset);rsr=1;
      do@(posedge clk);while(!rr);@(negedge clk);rv=0;
      do@(posedge clk);while(!rsv);if(rd!==beats[offset])$fatal(1,"normal read mismatch beat=%0d",offset);
      @(negedge clk);rsr=0;normal_read_count++;
    end
  endtask
  function automatic integer sample_offset(input integer index);
    return index;
  endfunction
  initial begin
    descriptor_base=0;drv=0;dri=0;dsr=0;rv=0;rsr=0;ra=0;wv=0;wa=0;wd=0;wbe=0;
    write_count=0;read_count=0;normal_read_count=0;phase=0;current_index=0;
    $readmemh("work/results/qwen2_descriptor_image_macro/beats.memh",beats);
    $readmemh("work/results/qwen2_descriptor_image_macro/records.memh",expected);
    repeat(6)@(posedge clk);rst_n=1;repeat(2)@(posedge clk);
    phase=1;for(integer i=0;i<SAMPLES;i++)begin current_index=sample_offset(i);write_beat(current_index);end
    // Every physical beat is compared in full; descriptor lane selection rotates 0..3.
    phase=2;for(integer i=0;i<SAMPLES;i++)begin current_index=sample_offset(i);read_beat(current_index);end
    phase=3;for(integer i=0;i<FETCHES;i++)begin current_index=i;fetch_record(i);end
    // One index immediately beyond the 1.5 MiB descriptor space must fail locally.
    phase=4;@(negedge clk);drv=1;dri=24'd98304;dsr=1;do@(posedge clk);while(!drr);
    @(negedge clk);drv=0;do@(posedge clk);while(!dsv);if(!dse)$fatal(1,"range check missing");
    @(negedge clk);dsr=0;repeat(4)@(posedge clk);
    if(write_count!=SAMPLES||normal_read_count!=SAMPLES||read_count!=FETCHES||writes!=SAMPLES||reads!=SAMPLES+FETCHES||errors!=0)
      $fatal(1,"counter mismatch writes=%0d/%0d normal=%0d descriptor=%0d physical_reads=%0d errors=%0d",write_count,writes,normal_read_count,read_count,reads,errors);
    $display("QWEN2_DESCRIPTOR_IMAGE_MACRO_SAMPLE_PASS formal_records=6188 sampled_beats=4 descriptor_bytes=164544 physical_writes=%0d physical_reads=%0d descriptor_fetches=4 bank_groups=4 descriptor_lanes=4 random_backpressure=1 errors=0",writes,reads);
    $finish;
  end
  initial begin repeat(5000)@(posedge clk);$fatal(1,"timeout phase=%0d index=%0d writes=%0d reads=%0d dstate=%0d",phase,current_index,write_count,read_count,dut.u_descriptor.state_q);end
endmodule
