`timescale 1ns/1ps
module tb_bf16_tile_transpose_stager;
 logic clk_i=0;always #0.625 clk_i=~clk_i;
 logic rst_ni=0,request_valid_i=0,request_ready_o;
 logic[63:0]source_i,destination_i;logic[31:0]source_stride_i;
 logic[15:0]rows_i,depth_i;
 logic rd_valid_o,rd_ready_i,rsp_valid_i=0,rsp_ready_o,rsp_error_i=0;
 logic[14:0]rd_addr_o,wr_addr_o;logic[511:0]rsp_data_i,wr_data_o,mem[0:32767];
 logic wr_valid_o,wr_ready_i;logic[63:0]wr_be_o;
 logic completion_valid_o,completion_ready_i=0;logic[7:0]status_o;
 logic[63:0]read_beats_o,write_beats_o;logic[31:0]lfsr=32'h761249ac;
 integer checked=0;longint unsigned cycle=0,begin_cycle;
 bf16_tile_transpose_stager dut(.*);
 assign rd_ready_i=!rsp_valid_i&&(lfsr[0]||lfsr[3]);
 assign wr_ready_i=lfsr[2]||lfsr[7];
 always @(posedge clk_i)begin
  cycle<=cycle+1;lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
  if(rd_valid_o&&rd_ready_i)begin rsp_valid_i<=1;rsp_data_i<=mem[rd_addr_o];end
  if(rsp_valid_i&&rsp_ready_o)rsp_valid_i<=0;
  if(wr_valid_o&&wr_ready_i)begin
   if(wr_be_o!='1)$fatal(1,"byte enables");mem[wr_addr_o]<=wr_data_o;
  end
 end
 function automatic[15:0]value(input integer r,k);return 16'((r+1)*997+k*13);endfunction
 task tick;@(posedge clk_i);@(negedge clk_i);endtask
 task run(input integer nr,k);
  integer stride;
  stride=((k+31)/32)*64;
  source_i=0;destination_i=64'h100000;source_stride_i=stride;rows_i=16'(nr);depth_i=16'(k);
  for(int r=0;r<nr;r++)for(int j=0;j<(k+31)/32;j++)for(int lane=0;lane<32;lane++)
    mem[r*(stride/64)+j][16*lane+:16]=value(r,j*32+lane);
  mem[16384+k]='1;
  begin_cycle=cycle;request_valid_i=1;tick();request_valid_i=0;
  source_i=64'h1fff00;destination_i=0;source_stride_i=64;rows_i=1;depth_i=1;
  wait(completion_valid_o);@(negedge clk_i);
  if(status_o||read_beats_o!=nr*((k+31)/32)||write_beats_o!=k)$fatal(1,"counts");
  for(int j=0;j<k;j++)for(int lane=0;lane<32;lane++)begin
   if(mem[16384+j][lane*16+:16]!==((lane<nr)?value(lane,j):16'd0))$fatal(1,"transpose k=%0d lane=%0d",j,lane);
   checked++;
  end
  if(mem[16384+k]!=='1)$fatal(1,"write overrun");
  $display("TRANSPOSE_CASE rows=%0d k=%0d cycles=%0d read_beats=%0d write_beats=%0d",nr,k,cycle-begin_cycle,read_beats_o,write_beats_o);
  repeat(3)tick();if(!completion_valid_o)$fatal(1,"completion hold");
  completion_ready_i=1;tick();completion_ready_i=0;
 endtask
 initial begin
  source_i=0;destination_i=0;source_stride_i=64;rows_i=1;depth_i=1;
  tick();rst_ni=1;
  run(1,1);run(3,17);run(16,32);run(7,33);run(16,1536);run(16,8960);
  for(int bad=0;bad<5;bad++)begin
   source_i=0;destination_i=64'h100000;source_stride_i=64;rows_i=16;depth_i=32;
   case(bad)0:rows_i=0;1:source_i=1;2:source_stride_i=32;3:destination_i=0;4:destination_i=64'hffffffffffffffc0;endcase
   request_valid_i=1;tick();request_valid_i=0;
   if(!completion_valid_o||status_o!=5||rd_valid_o||wr_valid_o||read_beats_o||write_beats_o)$fatal(1,"admission %0d",bad);
   completion_ready_i=1;tick();completion_ready_i=0;
  end
  source_i=0;destination_i=64'h100000;source_stride_i=64;rows_i=1;depth_i=1;rsp_error_i=1;
  request_valid_i=1;tick();request_valid_i=0;wait(completion_valid_o);
  if(status_o!=3||write_beats_o)$fatal(1,"read error");
  $display("BF16_TRANSPOSE_STAGER_PASS cases=6 checked=%0d invalid=5 read_error=1 buffer_bytes=1024",checked);$finish;
 end
 initial begin repeat(100000)tick();$fatal(1,"watchdog");end
endmodule
