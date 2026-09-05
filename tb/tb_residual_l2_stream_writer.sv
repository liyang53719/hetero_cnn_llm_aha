`timescale 1ns/1ps
module tb_residual_l2_stream_writer;
 logic clk=0;always #1 clk=~clk;
 logic rst=0,req=0,ready,iv=0,ir,il=0,wv,wr,done,ack=0;
 logic[63:0]base=64'h1000,received,writes,bytes;logic[31:0]elements=1,index=0;
 logic[511:0]data=0,wd,mem[0:15];logic[15:0]keep=1;logic[63:0]be;logic[14:0]addr;logic[7:0]istatus=0,status;
 logic[31:0]rng=32'hbeef9812;logic held=0;logic[511:0]hd;logic[63:0]hb;logic[14:0]ha;integer cases=0;
 residual_l2_stream_writer dut(.clk_i(clk),.rst_ni(rst),.request_valid_i(req),.request_ready_o(ready),.destination_i(base),.elements_i(elements),
 .in_valid_i(iv),.in_ready_o(ir),.in_data_i(data),.in_keep_i(keep),.in_chunk_i(index),.in_last_i(il),.in_status_i(istatus),
 .wr_valid_o(wv),.wr_ready_i(wr),.wr_addr_o(addr),.wr_data_o(wd),.wr_be_o(be),.completion_valid_o(done),.completion_ready_i(ack),.status_o(status),
 .received_chunks_o(received),.written_beats_o(writes),.written_payload_bytes_o(bytes));
 assign wr=rng[0]&&rng[4];
 function automatic[31:0]word(input integer i);return 32'h3f801123+32'(i);endfunction
 always @(posedge clk)if(rst)begin
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(held&&(!wv||wd!==hd||be!==hb||addr!==ha))$fatal(1,"write stability");
  held<=wv&&!wr;hd<=wd;hb<=be;ha<=addr;
  if(wv&&wr)begin
   if(addr<64||addr>=80)$fatal(1,"write range");
   for(int b=0;b<64;b++)if(be[b])mem[addr-64][b*8+:8]<=wd[b*8+:8];
  end
  if(done&&wv)$fatal(1,"completion before grant");
 end
 task tick;@(posedge clk);@(negedge clk);endtask
 task launch(input integer n);
  begin base=64'h1000;elements=n;req=1;tick();req=0;base=0;elements=0;end
 endtask
 task finish_case(input integer expected_status);
  begin wait(done);@(negedge clk);if(status!=expected_status)$fatal(1,"status");
   repeat(3)begin tick();if(!done||wv||ir)$fatal(1,"completion hold");end ack=1;tick();ack=0;
  end
 endtask
 task run_case(input integer n);
  begin
   for(int b=0;b<16;b++)mem[b]='1;
   launch(n);
   for(int chunk=0;chunk<(n+15)/16;chunk++)begin
    iv=1;index=chunk;il=(chunk+1)*16>=n;keep=0;data=0;
    for(int j=0;j<16;j++)begin data[j*32+:32]=word(chunk*16+j);if(chunk*16+j<n)keep[j]=1;end
    do @(posedge clk);while(!ir);@(negedge clk);iv=0;data='1;
   end
   wait(done);@(negedge clk);
   if(writes!=(n+15)/16||received!=writes||bytes!=n*4)$fatal(1,"counts");
   for(int b=0;b<16;b++)for(int j=0;j<16;j++)if(mem[b][j*32+:32]!==((b*16+j<n)?word(b*16+j):32'hffffffff))$fatal(1,"data");
   finish_case(0);cases++;
  end
 endtask
 initial begin
  repeat(3)tick();if(ready||ir)$fatal(1,"reset ready");rst=1;tick();
  run_case(1);run_case(16);run_case(17);run_case(31);run_case(32);run_case(33);run_case(95);
  for(int bad=0;bad<4;bad++)begin
   launch(1);iv=1;keep=1;index=0;il=1;istatus=0;
   case(bad)0:index=1;1:keep=3;2:il=0;3:istatus=6;endcase
   do @(posedge clk);while(!ir);@(negedge clk);iv=0;
   if(writes||bytes)$fatal(1,"error packet wrote data");finish_case(bad==3?6:7);istatus=0;
  end
  for(int bad=0;bad<4;bad++)begin
   elements=17;base=64'h1000;case(bad)0:elements=0;1:base=1;2:base=64'h17ffc0;3:base=64'hffffffffffffffc0;endcase
   req=1;tick();req=0;if(!done||status!=5||wv||ir||writes||bytes||received)$fatal(1,"admission");finish_case(5);
  end
  run_case(17);
  $display("RESIDUAL_L2_WRITER_PASS data_cases=%0d protocol_errors=4 range_errors=4 tail_preservation=1 grant_before_completion=1",cases);$finish;
 end
 initial begin repeat(10000)tick();$fatal(1,"timeout");end
endmodule
