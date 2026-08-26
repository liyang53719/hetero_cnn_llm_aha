`timescale 1ns/1ps
module tb_fp32_alu;parameter integer COUNT=10000;logic clk,reset,op;always #5 clk=~clk;logic[31:0]x,y,out;logic[4:0]flags;logic[96:0]v[0:COUNT-1];logic[63:0]hash;
  HeteroFP32Alu dut(.clock(clk),.reset(reset),.io_op(op),.io_x(x),.io_y(y),.io_out(out),.io_exceptionFlags(flags));
  initial begin clk=0;reset=1;op=0;x=0;y=0;hash=64'hcbf29ce484222325;$readmemh("work/results/l5_fp32_alu/vectors.memh",v);repeat(2)@(posedge clk);reset=0;
    for(int i=0;i<COUNT;i++)begin @(negedge clk);x=v[i][31:0];y=v[i][63:32];op=v[i][96];#1;if(out!==v[i][95:64])$fatal(1,"FP32 ALU mismatch i=%0d",i);hash=(hash^{32'd0,out})*64'h00000100000001b3;end
    @(negedge clk);op=1;x=32'h7f800000;y=0;#1;if(out[30:23]!=8'hff||out[22:0]==0||!flags[4])$fatal(1,"FP32 mul invalid");
    $display("FP32_HARDFLOAT_ALU_PASS vectors=%0d output_fnv64=%016h invalid_flags=%h",COUNT,hash,flags);$finish;end
endmodule
