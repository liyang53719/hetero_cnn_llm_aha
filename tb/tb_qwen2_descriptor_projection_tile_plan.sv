`timescale 1ns/1ps
module tb_qwen2_descriptor_projection_tile_plan;
 logic clk_i=0;always #0.625 clk_i=~clk_i;
 logic rst_ni=0,request_valid_i=0,request_ready_o;
 logic[127:0]command_i,descriptor_rsp_data_i,records[0:5];
 logic descriptor_req_valid_o,descriptor_req_ready_i,descriptor_rsp_valid_i=0;
 logic[23:0]descriptor_req_index_o;logic descriptor_rsp_ready_o,descriptor_rsp_error_i=0;
 logic tile_valid_o,tile_ready_i=0,tile_done_valid_i=0,tile_done_ready_o;
 logic[31:0]row_o,column_o;logic[15:0]rows_o,columns_o,depth_o;
 logic[63:0]a_addr_o,b_addr_o,c_addr_o;logic[7:0]tile_status_i=0;
 logic completion_valid_o,completion_ready_i=0;logic[7:0]status_o;
 logic[63:0]completed_tiles_o,useful_macs_o;
 integer seen,expected_r,expected_c;logic[63:0]saved_a;
 qwen2_descriptor_projection_tile_plan dut(.*);
 assign descriptor_req_ready_i=!descriptor_rsp_valid_i;
 always @(posedge clk_i)begin
  if(descriptor_req_valid_o&&descriptor_req_ready_i)begin
   descriptor_rsp_valid_i<=1;descriptor_rsp_data_i<=records[descriptor_req_index_o];
  end
  if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)descriptor_rsp_valid_i<=0;
 end
 task tick;@(posedge clk_i);@(negedge clk_i);endtask
 task launch;
  request_valid_i=1;tick();request_valid_i=0;
 endtask
 initial begin
  command_i=0;command_i[7:0]=8'h20;command_i[10:8]=2;
  command_i[79:56]=0;command_i[103:80]=2;command_i[127:104]=4;
  for(int i=0;i<3;i++)begin
   records[i*2]=0;records[i*2][7:0]=1;records[i*2][55:32]=24'(i*2+1);
   records[i*2][111:108]=5;records[i*2][103:56]=48'h100000+48'(i)*48'h1000000;
   records[i*2+1]=0;records[i*2+1][7:0]=2;
   records[i*2+1][73:56]=(i==1)?18'd1536:18'd1024;
   records[i*2+1][91:74]=18'd1536;
  end
  tick();rst_ni=1;tick();launch();seen=0;
  for(int t=0;t<3072;t++)begin
   wait(tile_valid_o);@(negedge clk_i);expected_r=(t/48)*16;expected_c=(t%48)*32;
   if(row_o!=expected_r||column_o!=expected_c||rows_o!=16||columns_o!=32||depth_o!=1536)$fatal(1,"tile %0d geometry",t);
   if(a_addr_o!=64'h100000+64'(expected_r)*3072||
      b_addr_o!=64'h1100000+64'(expected_c)*2||
      c_addr_o!=64'h2100000+64'(expected_r)*3072+64'(expected_c)*2)$fatal(1,"tile address");
   saved_a=a_addr_o;repeat(t%3+1)tick();
   if(a_addr_o!=saved_a||!tile_valid_o||completion_valid_o)$fatal(1,"issue stability");
   tile_ready_i=1;tick();tile_ready_i=0;
   repeat(t%4+1)tick();if(tile_valid_o||completion_valid_o)$fatal(1,"early advance");
   tile_done_valid_i=1;tick();tile_done_valid_i=0;seen++;
  end
  wait(completion_valid_o);if(status_o||completed_tiles_o!=3072||useful_macs_o!=64'd2415919104)$fatal(1,"aggregate");
  repeat(4)tick();if(!completion_valid_o)$fatal(1,"completion stability");
  completion_ready_i=1;tick();completion_ready_i=0;
  launch();wait(tile_valid_o);@(negedge clk_i);tile_ready_i=1;tick();tile_ready_i=0;
  tile_status_i=7;tile_done_valid_i=1;tick();tile_done_valid_i=0;
  if(!completion_valid_o||status_o!=7||completed_tiles_o!=0)$fatal(1,"tile failure");
  completion_ready_i=1;tick();completion_ready_i=0;
  command_i[7:0]=0;launch();wait(completion_valid_o);
  if(status_o!=2||completed_tiles_o||useful_macs_o||tile_valid_o)$fatal(1,"bad command");
  $display("QWEN2_DESCRIPTOR_TILE_PLAN_PASS tiles=3072 useful_macs=2415919104 payload_executed=0");$finish;
 end
 initial begin repeat(100000)tick();$fatal(1,"watchdog seen=%0d wrapper=%0d decoder=%0d iter=%0d status=%0d",seen,dut.state_q,dut.decoder.state_q,dut.iterator.state_q,status_o);end
endmodule
