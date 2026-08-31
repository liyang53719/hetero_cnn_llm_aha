`timescale 1ns/1ps
module tb_fp32_probability_to_bf16_hilo;
 logic clk,rst_n,iv,ir,ov,or_;logic[31:0]x;logic[15:0]hi,lo;logic[4:0]flags;integer seen;
 always #0.5 clk=~clk;
 fp32_probability_to_bf16_hilo dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.weight_i(x),.out_valid_o(ov),.out_ready_i(or_),.hi_o(hi),.lo_o(lo),.exception_flags_o(flags));
 task automatic send(input[31:0]value,input[15:0]eh,input[15:0]el);begin @(negedge clk);x=value;iv=1;do@(posedge clk);while(!ir);@(negedge clk);iv=0;do@(posedge clk);while(!ov);if(hi!==eh||lo!==el)$fatal(1,"hilo x=%h hi=%h lo=%h",value,hi,lo);seen++;end endtask
 initial begin clk=0;rst_n=0;iv=0;or_=1;x=0;seen=0;repeat(6)@(posedge clk);rst_n=1;send(32'h3f800000,16'h3f80,16'h0000);send(32'h3f808000,16'h3f80,16'h3b80);send(32'h3f7f0000,16'h3f7f,16'h0000);if(flags[4:1]!=0)$fatal(1,"flags");$display("FP32_PROBABILITY_HILO_PASS cases=%0d",seen);$finish;end
endmodule
