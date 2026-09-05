`timescale 1ns/1ps
module tb_matrix_tile_step_guard;
 logic clk_i=0;always #1 clk_i=~clk_i;
 logic rst_ni=0,start_i=0;logic[15:0]depth_i=4;
 logic step_valid_i=0,step_ready_i=0;logic[2:0]context_i=2;
 logic clear_i=0,last_i=0,result_fire_i=0,result_last_i=0;
 logic[2:0]result_context_i=2;logic allow_step_o,done_o,fault_o;
 matrix_tile_step_guard dut(.*);
 task tick;@(posedge clk_i);@(negedge clk_i);endtask
 task reset_start;
   rst_ni=0;start_i=0;step_valid_i=0;result_fire_i=0;context_i=2;
   result_context_i=2;depth_i=4;tick();rst_ni=1;start_i=1;tick();start_i=0;
 endtask
 initial begin
   reset_start();
   for(int k=0;k<4;k++)begin
     step_valid_i=1;step_ready_i=0;clear_i=k==0;last_i=k==3;
     tick();tick();if(fault_o||done_o)$fatal(1,"backpressure");
     step_ready_i=1;tick();step_valid_i=0;
     result_fire_i=1;result_last_i=k==3;tick();result_fire_i=0;
     if(fault_o||done_o!=(k==3))$fatal(1,"legal K progression");
   end
   reset_start();step_valid_i=1;step_ready_i=1;clear_i=1;last_i=1;
   tick();if(!fault_o||done_o)$fatal(1,"early last accepted");
   start_i=1;tick();if(!fault_o||allow_step_o)$fatal(1,"fault not sticky");
   reset_start();step_valid_i=1;clear_i=1;last_i=0;tick();
   clear_i=0;context_i=3;tick();if(!fault_o)$fatal(1,"context switch");
   reset_start();step_valid_i=1;clear_i=1;last_i=0;tick();step_valid_i=0;
   result_fire_i=1;result_last_i=1;tick();if(!fault_o||done_o)$fatal(1,"early result last");
   reset_start();result_fire_i=1;result_last_i=0;tick();
   if(!fault_o)$fatal(1,"unsolicited return");
   $display("MATRIX_TILE_STEP_GUARD_PASS legal_depth=4 fault_cases=4 backpressure=8");$finish;
 end
 initial begin repeat(200)tick();$fatal(1,"watchdog");end
endmodule
