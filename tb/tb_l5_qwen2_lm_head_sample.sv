`timescale 1ns/1ps
module tb_l5_qwen2_lm_head_sample;
  localparam integer CONTEXTS=5,SAMPLES=160,K=1536,STEPS=7680;
  logic clk=0,rst_n=0,in_valid,in_ready,clear,last,out_valid,out_ready,out_last;
  logic[2:0]context_in,context_out;logic[255:0]a;logic[511:0]b;
  logic[16383:0]acc;logic[4:0]flags,busy,acc_valid;logic[31:0]accepted,completed,lfsr;logic protocol_error;
  logic[15:0]hidden[0:K-1];logic[15:0]weights[0:K*SAMPLES-1];integer fd,finals,cycles;
  string output_path;
  always #0.5 clk=~clk;
  assign out_ready=lfsr[0]||lfsr[4];
  bf16_outer_product_context_array_rev8b_b_candidate dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(in_valid),.in_ready_o(in_ready),.context_i(context_in),.clear_i(clear),.last_i(last),.a_i(a),.b_i(b),.out_valid_o(out_valid),.out_ready_i(out_ready),.context_o(context_out),.last_o(out_last),.acc_o(acc),.exception_flags_o(flags),.busy_o(busy),.accumulator_valid_o(acc_valid),.accepted_steps_o(accepted),.completed_steps_o(completed),.protocol_error_o(protocol_error));
  always_ff@(posedge clk)begin
    if(!rst_n)begin lfsr<=32'h51a8e7d3;finals<=0;cycles<=0;end else begin
      lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};cycles<=cycles+1;
      if(out_valid&&out_ready&&out_last)begin
        for(integer c=0;c<32;c++)$fdisplay(fd,"%08x",acc[c*32+:32]);finals<=finals+1;
      end
      if(protocol_error)$fatal(1,"protocol error");
    end
  end
  initial begin
    in_valid=0;clear=0;last=0;context_in=0;a='0;b='0;if(!$value$plusargs("OUTPUT=%s",output_path))output_path="work/results/l5_qwen2_lm_head_sample/rtl_output.memh";fd=$fopen(output_path,"w");if(!fd)$fatal(1,"output open");
    $readmemh("work/results/l5_qwen2_four_layer_reference/vectors/hidden_bf16.memh",hidden);$readmemh("work/results/l5_qwen2_four_layer_reference/vectors/weights_bf16.memh",weights);
    repeat(8)@(posedge clk);rst_n=1;@(negedge clk);
    for(integer k=0;k<K;k++)for(integer ctx=0;ctx<CONTEXTS;ctx++)begin
      a='0;a[15:0]=hidden[k];for(integer c=0;c<32;c++)b[c*16+:16]=weights[k*SAMPLES+ctx*32+c];context_in=ctx[2:0];clear=k==0;last=k==K-1;in_valid=1;
      do@(posedge clk);while(!in_ready);@(negedge clk);in_valid=0;
    end
    while(completed<STEPS&&cycles<20000)@(posedge clk);repeat(4)@(posedge clk);$fclose(fd);
    if(accepted!=STEPS||completed!=STEPS||finals!=CONTEXTS||busy||flags[4:1])$fatal(1,"accounting accepted=%0d completed=%0d finals=%0d busy=%h flags=%h",accepted,completed,finals,busy,flags);
    $display("L5_QWEN2_LM_HEAD_SAMPLE_RTL_PASS samples=160 contexts=5 steps=7680 cycles=%0d",cycles);$finish;
  end
  initial begin repeat(30000)@(posedge clk);$fatal(1,"timeout");end
endmodule
