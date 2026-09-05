`timescale 1ns/1ps
module tb_residual_l2_stream_reader;
 logic clk=0;always #1 clk=~clk;
 logic rst=0,req=0,ready,short_i=0,rv,rr,sv=0,sr,se=0,ov,orr,ol,done,ack=0;
 logic[63:0]base=64'h1000,reads,outputs;logic[31:0]elements=1,index;logic[14:0]addr;
 logic[511:0]data,output_data;logic[15:0]keep;logic[7:0]status;logic[31:0]rng=32'h12987abc;
 integer n,got=0,cases=0;logic mode,inject_error=0;
 logic held=0;logic[511:0]saved;logic[15:0]sk;logic[31:0]si;logic sl;
 residual_l2_stream_reader dut(.clk_i(clk),.rst_ni(rst),.request_valid_i(req),.request_ready_o(ready),.source_i(base),.elements_i(elements),.bf16_i(short_i),
 .rd_valid_o(rv),.rd_ready_i(rr),.rd_addr_o(addr),.rsp_valid_i(sv),.rsp_ready_o(sr),.rsp_data_i(data),.rsp_error_i(se),
 .out_valid_o(ov),.out_ready_i(orr),.out_data_o(output_data),.out_keep_o(keep),.out_chunk_o(index),.out_last_o(ol),
 .completion_valid_o(done),.completion_ready_i(ack),.status_o(status),.read_beats_o(reads),.output_chunks_o(outputs));
 assign rr=!sv&&rng[0];assign orr=rng[3]&&rng[4];
 always @(posedge clk)if(rst)begin
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(held&&(!ov||output_data!==saved||keep!==sk||index!==si||ol!==sl))$fatal(1,"stability");
  held<=ov&&!orr;saved<=output_data;sk<=keep;si<=index;sl<=ol;
  if(rv&&rr)begin
   if(addr<64)$fatal(1,"truncated address");data<=0;sv<=1;se<=inject_error;
   if(mode)for(int j=0;j<32;j++)data[j*16+:16]<=16'h3f00+16'((addr-64)*32+j);
   else for(int j=0;j<16;j++)data[j*32+:32]<=32'h3f801001+32'((addr-64)*16+j);
  end
  if(sv&&sr)sv<=0;
  if(ov&&orr)begin
   logic[511:0]expected;logic[15:0]ek;
   expected=0;ek=0;
   for(int j=0;j<16;j++)if(got*16+j<n)begin
    ek[j]=1;if(mode)expected[j*16+:16]=16'h3f00+16'(got*16+j);
    else expected[j*32+:32]=32'h3f801001+32'(got*16+j);
   end
   if(index!=got||keep!==ek||output_data!==expected||ol!=((got+1)*16>=n))$fatal(1,"data n=%0d got=%0d",n,got);
   got++;
  end
 end
 task tick;@(posedge clk);@(negedge clk);endtask
 task run_case(input bit bf,input integer count);
  begin
   $display("CASE_START mode=%0d n=%0d",bf,count);
   mode=bf;n=count;got=0;short_i=bf;elements=count;base=64'h1000;req=1;tick();req=0;
   // Accepted geometry is immutable.
   short_i=!bf;elements=1;base=0;
   wait(done);@(negedge clk);
   if(status||reads!=(count+(bf?31:15))/(bf?32:16)||outputs!=(count+15)/16||got!=outputs)$fatal(1,"counts");
   repeat(3)begin tick();if(!done||rv||ov)$fatal(1,"completion hold");end
   ack=1;tick();ack=0;cases++;
  end
 endtask
 initial begin
  repeat(3)tick();if(ready)$fatal(1,"reset ready");rst=1;tick();
  for(int bf=0;bf<2;bf++)begin
   run_case(1'(bf),1);run_case(1'(bf),16);run_case(1'(bf),17);run_case(1'(bf),31);
   run_case(1'(bf),32);run_case(1'(bf),33);run_case(1'(bf),64);run_case(1'(bf),95);
  end
  for(int bad=0;bad<3;bad++)begin
   short_i=0;elements=17;base=64'h1000;
   case(bad)0:elements=0;1:base=1;2:base=64'h17ffc0;endcase
   req=1;tick();req=0;if(!done||status!=5||reads||outputs||rv||ov)$fatal(1,"bad address");ack=1;tick();ack=0;
  end
  inject_error=1;short_i=1;mode=1;elements=32;base=64'h1000;req=1;tick();req=0;
  wait(done);@(negedge clk);if(status!=3||reads!=1||outputs)$fatal(1,"read error");ack=1;tick();ack=0;inject_error=0;
  run_case(1,33);
  $display("RESIDUAL_L2_READER_PASS data_cases=%0d range_errors=3 read_errors=1 bf16_reads_once=1 backpressure=1 snapshot=1",cases);$finish;
 end
 initial begin repeat(10000)tick();$fatal(1,"timeout state=%0d bf=%0d reads=%0d chunks=%0d remaining=%0d gv=%0d gr=%0d gbfull=%0d",dut.state_q,dut.bf16_q,reads,outputs,dut.remaining_q,dut.gv,dut.gr,dut.gearbox.full_q);end
endmodule
