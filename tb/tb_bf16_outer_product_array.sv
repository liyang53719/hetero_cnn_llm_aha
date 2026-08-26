`timescale 1ns/1ps
module tb_bf16_outer_product_array;
  parameter integer ROWS=2,COLS=2,STEPS=4;localparam integer LANES=ROWS*COLS;
  logic clk;/* verilator lint_off SYNCASYNCNET */logic rst_n;/* verilator lint_on SYNCASYNCNET */always #5 clk=~clk;
  logic iv,ir,ov,orr;logic[ROWS*16-1:0]a;logic[COLS*16-1:0]b;logic[LANES*32-1:0]acc,out;
  logic[4:0]flags;logic[31:0]accepted,completed;logic[31:0]expected[0:LANES-1];integer cycles;
  logic stalled;logic[LANES*32-1:0]held;logic throughput_mode,burst_active;integer burst_outputs;
  bf16_outer_product_array #(.ROWS(ROWS),.COLS(COLS))dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),
    .a_i(a),.b_i(b),.acc_i(acc),.out_valid_o(ov),.out_ready_i(orr),.acc_o(out),
    .exception_flags_o(flags),.accepted_steps_o(accepted),.completed_steps_o(completed));
  function automatic[15:0]bf16_int(input integer v);begin case(v)
    -4:bf16_int=16'hc080;-3:bf16_int=16'hc040;-2:bf16_int=16'hc000;-1:bf16_int=16'hbf80;
    0:bf16_int=0;1:bf16_int=16'h3f80;2:bf16_int=16'h4000;3:bf16_int=16'h4040;
    4:bf16_int=16'h4080;default:bf16_int=0;endcase end endfunction
  function automatic integer aval(input integer i,input integer k);aval=i%5-2+k%3-1;endfunction
  function automatic integer bval(input integer j,input integer k);bval=j%7-3+(k&1);endfunction
  function automatic[63:0]hash_acc(input[LANES*32-1:0]data);reg[63:0]h;
    begin h=64'hcbf29ce484222325;for(int l=0;l<LANES;l++)h=(h^{32'd0,data[l*32 +:32]})*64'h00000100000001b3;hash_acc=h;end endfunction
  always_comb orr=throughput_mode?1'b1:(cycles%4)!=1;
  always @(posedge clk)begin if(!rst_n)begin cycles<=0;stalled<=0;held<=0;end else begin cycles<=cycles+1;
    if(stalled&&(!ov||out!==held))$fatal(1,"BF16 array stalled output changed");stalled<=ov&&!orr;if(ov&&!orr)held<=out;
    if(burst_active&&ov&&orr)begin for(int l=0;l<LANES;l++)if(out[l*32 +:32]!==32'h3f800000)
      $fatal(1,"BF16 array burst mapping lane=%0d",l);if(flags!=0)$fatal(1,"BF16 array burst flags");burst_outputs<=burst_outputs+1;end end end
  initial begin clk=0;rst_n=0;iv=0;a=0;b=0;acc=0;throughput_mode=0;burst_active=0;burst_outputs=0;
    $readmemh("work/results/l5_bf16_array/expected.memh",expected);
    repeat(3)@(posedge clk);rst_n=1;
    for(int k=0;k<STEPS;k++)begin for(int i=0;i<ROWS;i++)a[i*16 +:16]=bf16_int(aval(i,k));
      for(int j=0;j<COLS;j++)b[j*16 +:16]=bf16_int(bval(j,k));
      @(negedge clk);iv=1;do @(posedge clk);while(!ir);@(negedge clk);iv=0;
      do @(posedge clk);while(!(ov&&orr));@(negedge clk);acc=out;
      if(flags!=0)$fatal(1,"BF16 array unexpected exception step=%0d flags=%h",k,flags);end
    for(int l=0;l<LANES;l++)if(acc[l*32 +:32]!==expected[l])$fatal(1,"BF16 array mismatch lane=%0d got=%h exp=%h",l,acc[l*32 +:32],expected[l]);
    if(accepted!=STEPS||completed!=STEPS)$fatal(1,"BF16 array counters");
    throughput_mode=1;burst_active=1;acc=0;for(int i=0;i<ROWS;i++)a[i*16 +:16]=16'h3f80;
    for(int j=0;j<COLS;j++)b[j*16 +:16]=16'h3f80;
    for(int t=0;t<8;t++)begin @(negedge clk);iv=1;#1;if(!ir)$fatal(1,"BF16 array burst bubble t=%0d",t);@(posedge clk);end
    @(negedge clk);iv=0;wait(completed==STEPS+8);@(negedge clk);burst_active=0;
    if(accepted!=STEPS+8||burst_outputs!=8)$fatal(1,"BF16 array burst counters");
    $display("BF16_OUTER_PRODUCT_ARRAY_PASS rows=%0d cols=%0d steps=%0d macs_per_step=%0d cycles=%0d burst=8 interval=1 final_fnv64=%016h",ROWS,COLS,STEPS,LANES,cycles,hash_acc(acc));$finish;end
endmodule
