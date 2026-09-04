`timescale 1ns/1ps
module tb_fp32_reduce_max16;logic clk_i=0,rst_ni=1;always #1 clk_i=~clk_i;logic in_valid_i,in_ready_o,out_valid_o,out_ready_i;logic[511:0]data_i;logic[31:0]max_o;logic[3:0]index_o;
 fp32_reduce_max16 dut(.*);task run(input[31:0]expected,input[3:0]idx);begin @(negedge clk_i);in_valid_i=1;@(posedge clk_i);@(negedge clk_i);in_valid_i=0;wait(out_valid_o);if(max_o!==expected||index_o!==idx)$fatal(1,"got %h %0d",max_o,index_o);repeat(2)@(posedge clk_i);out_ready_i=1;@(posedge clk_i);@(negedge clk_i);out_ready_i=0;end endtask
 initial begin #0.1 rst_ni=0;in_valid_i=0;out_ready_i=0;data_i=0;repeat(3)@(posedge clk_i);@(negedge clk_i);rst_ni=1;for(int i=0;i<16;i++)data_i[i*32+:32]=32'(i);data_i[7*32+:32]=32'h41200000;run(32'h41200000,7);
 data_i={16{32'h7fc00001}};data_i[5*32+:32]=32'h40000000;run(32'h40000000,5);data_i={16{32'h80000000}};data_i[3*32+:32]=0;run(32'h80000000,0);
 $display("FP32_REDUCE_MAX16_PASS cases=3 stable_ties=1 nan_last=1");$finish;end initial begin repeat(200)@(posedge clk_i);$fatal(1,"timeout");end endmodule
