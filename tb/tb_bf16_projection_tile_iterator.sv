`timescale 1ns/1ps
module tb_bf16_projection_tile_iterator;
 logic clk_i=0;always #1 clk_i=~clk_i;
 logic rst_ni=0,request_valid_i=0,request_ready_o;
 logic[31:0]m_i=17,n_i=33,k_i=4,a_stride_i=8,b_stride_i=66,c_stride_i=66;
 logic[63:0]a_base_i=64'h100000000,b_base_i=64'h200000000,c_base_i=64'h300000000;
 logic tile_valid_o,tile_ready_i=0,tile_done_valid_i=0,tile_done_ready_o;
 logic[31:0]row_o,column_o;logic[15:0]rows_o,columns_o,depth_o;
 logic[63:0]a_addr_o,b_addr_o,c_addr_o;logic[7:0]tile_status_i=0;
 logic completion_valid_o,completion_ready_i=0;logic[7:0]status_o;
 logic[63:0]completed_tiles_o,useful_macs_o;
 bf16_projection_tile_iterator dut(.*);
 task tick;@(posedge clk_i);@(negedge clk_i);endtask
 initial begin
  tick();rst_ni=1;request_valid_i=1;tick();request_valid_i=0;
  // Change all live inputs: the accepted descriptor must remain a snapshot.
  m_i=0;n_i=0;k_i=0;a_base_i=0;b_base_i=0;c_base_i=0;
  for(int t=0;t<4;t++)begin
   wait(tile_valid_o);
   if(row_o!=(t/2)*16||column_o!=(t%2)*32||rows_o!=((t<2)?16:1)||
      columns_o!=((t%2==0)?32:1)||depth_o!=4)$fatal(1,"tail shape");
   if(a_addr_o!=64'h100000000+64'(row_o)*8||b_addr_o!=64'h200000000+64'(column_o)*2||
      c_addr_o!=64'h300000000+64'(row_o)*66+64'(column_o)*2)$fatal(1,"64-bit address");
   repeat(3)tick();tile_ready_i=1;tick();tile_ready_i=0;
   repeat(2)tick();tile_done_valid_i=1;tick();tile_done_valid_i=0;
  end
  if(!completion_valid_o||status_o||completed_tiles_o!=4||useful_macs_o!=2244)$fatal(1,"totals");
  completion_ready_i=1;tick();completion_ready_i=0;
  for(int bad=0;bad<5;bad++)begin
   m_i=17;n_i=33;k_i=4;a_stride_i=8;a_base_i=64'h100000000;
   case(bad)0:m_i=0;1:k_i=65536;2:a_base_i=1;3:a_stride_i=2;4:a_base_i=64'hfffffffffffffff8;endcase
   request_valid_i=1;tick();request_valid_i=0;
   if(!completion_valid_o||status_o!=5||tile_valid_o||completed_tiles_o||useful_macs_o)$fatal(1,"invalid %0d",bad);
   completion_ready_i=1;tick();completion_ready_i=0;
  end
  $display("BF16_TILE_ITERATOR_PASS tails=4 rejected=5 useful_macs=2244 addresses_above_4g=1 payload_executed=0");$finish;
 end
 initial begin repeat(1000)tick();$fatal(1,"watchdog");end
endmodule
