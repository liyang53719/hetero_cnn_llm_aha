`timescale 1ns/1ps
module tb_bf16_fma_lane;
  parameter integer COUNT=10000;logic clk,reset;always #5 clk=~clk;
  logic[15:0]a,b;logic[31:0]c,out;logic[4:0]flags;logic[96:0]vectors[0:COUNT-1];logic[63:0]hash;
  HeteroBF16FmaLane dut(.clock(clk),.reset(reset),.io_a(a),.io_b(b),.io_c(c),.io_out(out),.io_exceptionFlags(flags));
  function automatic[63:0]mix(input[63:0]h,input[31:0]v);begin mix=(h^{32'd0,v})*64'h00000100000001b3;end endfunction
  initial begin clk=0;reset=1;a=0;b=0;c=0;hash=64'hcbf29ce484222325;
    $readmemh("work/results/l5_bf16_fma/vectors.memh",vectors);repeat(2)@(posedge clk);reset=0;
    for(int i=0;i<COUNT;i++)begin @(negedge clk);a=vectors[i][15:0];b=vectors[i][31:16];c=vectors[i][63:32];#1;
      if(vectors[i][96]&&out!==vectors[i][95:64])$fatal(1,"BF16 FMA mismatch index=%0d a=%h b=%h c=%h got=%h exp=%h flags=%h",i,a,b,c,out,vectors[i][95:64],flags);
      if($isunknown({out,flags}))$fatal(1,"BF16 FMA X index=%0d",i);hash=mix(hash,out);end
    @(negedge clk);a=16'h7f80;b=0;c=32'h3f800000;#1;
    if(out[30:23]!=8'hff||out[22:0]==0||!flags[4])$fatal(1,"BF16 FMA invalid special case out=%h flags=%h",out,flags);
    $display("BF16_FP32_FMA_LANE_PASS vectors=%0d output_fnv64=%016h invalid_flags=%h",COUNT,hash,flags);$finish;end
endmodule
