`timescale 1ns/1ps
module tb_residual_l2_tile_control;
 logic clk=0;always #1 clk=~clk;
 logic rst=0,req=0,ready,bshort=1,wv,wr,done,ack=0;
 logic[63:0]abase=0,bbase=64'h10000,cbase=64'h20000,reads,writes,bytes,cycles;
 logic[31:0]elements=95;logic[1:0]rv,rr,sv,sr,se,pending=0;logic[29:0]ra;logic[1023:0]sd;logic[14:0]wa;logic[511:0]wd;
 logic[63:0]be;logic[7:0]status;logic[511:0]mem[0:4095];integer delay_q[0:1],rnum[0:1];
 logic[31:0]rng=32'hdeadbac8;integer fail_port=-1,fail_read=1;integer cases=0;
 logic wh=0;logic[511:0]whd;logic[63:0]whbe;logic[14:0]wha;
 residual_l2_tile dut(.clk_i(clk),.rst_ni(rst),.request_valid_i(req),.request_ready_o(ready),.source_a_i(abase),.source_b_i(bbase),.destination_i(cbase),.elements_i(elements),.b_bf16_i(bshort),
 .rd_valid_o(rv),.rd_ready_i(rr),.rd_addr_o(ra),.rsp_valid_i(sv),.rsp_ready_o(sr),.rsp_data_i(sd),.rsp_error_i(se),
 .wr_valid_o(wv),.wr_ready_i(wr),.wr_addr_o(wa),.wr_data_o(wd),.wr_be_o(be),.completion_valid_o(done),.completion_ready_i(ack),.status_o(status),
 .read_beats_o(reads),.write_beats_o(writes),.written_payload_bytes_o(bytes),.cycles_o(cycles));
 assign wr=rng[0]&&rng[4];
 for(genvar g=0;g<2;g++)begin
  assign rr[g]=!pending[g]&&rng[g+2];assign sv[g]=pending[g]&&delay_q[g]==0;
 end
 always @(posedge clk)if(!rst)begin pending<=0;delay_q[0]<=0;delay_q[1]<=0;rnum[0]<=0;rnum[1]<=0;wh<=0;rng<=32'hdeadbac8;end else begin
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  for(int g=0;g<2;g++)begin
   if(rv[g]&&rr[g])begin
    pending[g]<=1;delay_q[g]<=g==1?9:2;rnum[g]<=rnum[g]+1;
    sd[g*512+:512]<=mem[ra[g*15+:15]];se[g]<=g==fail_port&&rnum[g]+1==fail_read;
   end
   if(pending[g]&&delay_q[g]>0)delay_q[g]<=delay_q[g]-1;
   if(sv[g]&&sr[g])pending[g]<=0;
  end
  if(wh&&(!wv||wd!==whd||be!==whbe||wa!==wha))$fatal(1,"writer request withdrawn");
  wh<=wv&&!wr;whd<=wd;whbe<=be;wha<=wa;
  if(wv&&wr)for(int i=0;i<64;i++)if(be[i])mem[wa][i*8+:8]<=wd[i*8+:8];
  if(done&&(pending!=0||rv!=0||wv))$fatal(1,"completion with outstanding memory traffic");
 end
 function automatic[31:0]a_word(input integer i);return 32'h3f800101+32'(i);endfunction
 function automatic[31:0]b_word(input integer i);return 32'h40000101+32'(i);endfunction
 task tick;@(posedge clk);@(negedge clk);endtask
 task run_case(input bit bf,input integer n,input integer error_port=-1,input integer at_read=1,input bit reset_global=1);
  integer expected_reads;logic[31:0]expected;
  begin
   if(reset_global)begin rst=0;repeat(2)tick();end
   else if(!ready||pending!=0)$fatal(1,"not quiescent for next request");
   fail_port=error_port;fail_read=at_read;
   for(int i=0;i<16;i++)begin mem[i]=0;mem[1024+i]=0;mem[2048+i]='1;end
   for(int i=0;i<256;i++)begin mem[i/16][(i%16)*32+:32]=a_word(i);
    if(bf)mem[1024+i/32][(i%32)*16+:16]=16'h3f00+16'(i);else mem[1024+i/16][(i%16)*32+:32]=b_word(i);
   end
   abase=0;bbase=64'h10000;cbase=64'h20000;elements=n;bshort=bf;rst=1;tick();req=1;tick();req=0;
   abase=64'hffffff00;bbase=0;cbase=0;elements=0;bshort=!bf;
   wait(done);@(negedge clk);
   if(error_port<0)begin
    expected_reads=(n+15)/16+(n+(bf?31:15))/(bf?32:16);
    if(status||reads!=expected_reads||writes!=(n+15)/16||bytes!=n*4)$fatal(1,"normal counters status=%0d",status);
    for(int i=0;i<256;i++)begin expected=i<n?(a_word(i)^(bf?{(16'h3f00+16'(i)),16'd0}:b_word(i))):32'hffffffff;
     if(mem[2048+i/16][(i%16)*32+:32]!==expected)$fatal(1,"payload %0d",i);
    end
   end else if(status!=3)$fatal(1,"read error not propagated");
   repeat(4)begin tick();if(!done||ready||rv||wv||pending)$fatal(1,"completion hold");end
   ack=1;tick();ack=0;cases++;
  end
 endtask
 initial begin
  run_case(1,95);run_case(0,95);run_case(1,17);run_case(0,1);
  run_case(1,95,0,1);run_case(0,95,1,2);run_case(1,95,0,2);run_case(1,33,-1,1,0);
  fail_port=-1;abase=0;bbase=64'h10000;cbase=0;elements=17;req=1;tick();req=0;
  if(!done||status!=5||rv||wv||reads||writes)$fatal(1,"overlap admission");
  $display("RESIDUAL_L2_TILE_CONTROL_PASS cases=%0d overlap_rejected=1 drain_before_completion=1 arithmetic_mocked=1",cases);$finish;
 end
 initial begin repeat(20000)tick();$fatal(1,"timeout state=%0d abort=%0d readers=%b writer=%0d",dut.state_q,dut.abort_q,dut.rdone,dut.wdone);end
endmodule
// Protocol fixture only: compilation excludes the production fp32_vector_alu.
module fp32_vector_alu #(parameter integer LANES=16)(input logic op_i,input logic[LANES*32-1:0]a_i,b_i,output logic[LANES*32-1:0]out_o,output logic[4:0]exception_flags_o);
 assign out_o=a_i^b_i;assign exception_flags_o=0;
endmodule
