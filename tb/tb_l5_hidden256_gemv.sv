`timescale 1ns/1ps
module tb_l5_hidden256_gemv;logic clk;/* verilator lint_off SYNCASYNCNET */logic rst_n;/* verilator lint_on SYNCASYNCNET */always #5 clk=~clk;integer cycles;
 logic iv,ir,ov,orr;logic[255:0]a;logic[511:0]b;logic[16383:0]acc,out;logic[4:0]flags,flags_or;logic[31:0]accepted,completed;
 logic[15:0]x[0:255],w[0:65535];logic[31:0]expected[0:255],result[0:255];logic[63:0]hash;
 bf16_outer_product_array #(.ROWS(16),.COLS(32))dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.a_i(a),.b_i(b),.acc_i(acc),.out_valid_o(ov),.out_ready_i(orr),.acc_o(out),.exception_flags_o(flags),.accepted_steps_o(accepted),.completed_steps_o(completed));
 always_comb orr=(cycles%7)!=1;always @(posedge clk)if(!rst_n)cycles<=0;else cycles<=cycles+1;
 initial begin clk=0;rst_n=0;iv=0;a=0;b=0;acc=0;flags_or=0;hash=64'hcbf29ce484222325;
  $readmemh("work/results/l5_hidden256_gemv/vectors/x_bf16.memh",x);$readmemh("work/results/l5_hidden256_gemv/vectors/weights_bf16.memh",w);$readmemh("work/results/l5_hidden256_gemv/vectors/expected.memh",expected);repeat(3)@(posedge clk);rst_n=1;
  for(int tile=0;tile<8;tile++)begin acc=0;
   for(int k=0;k<256;k++)begin a=0;b=0;a[15:0]=x[k];for(int j=0;j<32;j++)b[j*16+:16]=w[k*256+tile*32+j];
    @(negedge clk);iv=1;do @(posedge clk);while(!ir);@(negedge clk);iv=0;do @(posedge clk);while(!(ov&&orr));@(negedge clk);acc=out;flags_or|=flags;end
   for(int j=0;j<32;j++)result[tile*32+j]=acc[j*32+:32];end
  for(int j=0;j<256;j++)begin if(result[j]!==expected[j])$fatal(1,"hidden256 GEMV mismatch j=%0d",j);hash=(hash^{32'd0,result[j]})*64'h100000001b3;end
  if(accepted!=2048||completed!=2048||flags_or[4:1]!=0)$fatal(1,"hidden256 GEMV accounting");
  $display("L5_HIDDEN256_GEMV_PASS steps=2048 column_tiles=8 cycles=%0d output_fnv64=%016h flags_or=%h",cycles,hash,flags_or);$finish;end
 initial begin repeat(20000)@(posedge clk);$fatal(1,"hidden256 GEMV timeout");end
endmodule
