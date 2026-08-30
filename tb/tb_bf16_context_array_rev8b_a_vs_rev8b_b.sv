`timescale 1ns/1ps
module tb_bf16_context_array_rev8b_a_vs_rev8b_b;
  localparam integer ROWS=16,COLS=32,LANES=512,TARGET=120000;
  logic clk,rst_n,in_valid,clear,last;
  logic[1:0]context_in;
  logic[ROWS*16-1:0]a;logic[COLS*16-1:0]b;
  logic ready_a,valid_a,last_a;logic[1:0]context_a;logic[LANES*32-1:0]acc_a;
  logic[4:0]flags_a,busy_a,acc_valid_a;logic[31:0]accepted_a,completed_a;logic error_a;
  logic ready_b,valid_b,last_b;logic[2:0]context_b;logic[LANES*32-1:0]acc_b;
  logic[4:0]flags_b,busy_b,acc_valid_b;logic[31:0]accepted_b,completed_b;logic error_b;
  logic saved_valid,saved_last;logic[1:0]saved_context;logic[LANES*32-1:0]saved_acc;logic[4:0]saved_flags;
  integer cycles,issued,compared,saved_cycle;
  always #0.5 clk=~clk;
  bf16_outer_product_context_array_rev8b_a_candidate rev8b_a(
    .clk_i(clk),.rst_ni(rst_n),.in_valid_i(in_valid),.in_ready_o(ready_a),.context_i(context_in),
    .clear_i(clear),.last_i(last),.a_i(a),.b_i(b),.out_valid_o(valid_a),.out_ready_i(1'b1),
    .context_o(context_a),.last_o(last_a),.acc_o(acc_a),.exception_flags_o(flags_a),.busy_o(busy_a[3:0]),
    .accumulator_valid_o(acc_valid_a[3:0]),.accepted_steps_o(accepted_a),.completed_steps_o(completed_a),.protocol_error_o(error_a));
  assign busy_a[4]=0;assign acc_valid_a[4]=0;
  bf16_outer_product_context_array_rev8b_b_candidate rev8b_b(
    .clk_i(clk),.rst_ni(rst_n),.in_valid_i(in_valid),.in_ready_o(ready_b),.context_i({1'b0,context_in}),
    .clear_i(clear),.last_i(last),.a_i(a),.b_i(b),.out_valid_o(valid_b),.out_ready_i(1'b1),
    .context_o(context_b),.last_o(last_b),.acc_o(acc_b),.exception_flags_o(flags_b),.busy_o(busy_b),
    .accumulator_valid_o(acc_valid_b),.accepted_steps_o(accepted_b),.completed_steps_o(completed_b),.protocol_error_o(error_b));
  initial begin
    clk=0;rst_n=0;in_valid=0;context_in=0;clear=0;last=0;a={ROWS{16'h3f80}};b={COLS{16'h3f80}};
    cycles=0;issued=0;compared=0;saved_valid=0;saved_cycle=0;
    repeat(8)@(posedge clk);rst_n=1;
    while(compared<TARGET)begin
      @(negedge clk);cycles=cycles+1;
      in_valid=(issued<TARGET)&&(cycles%7==0);context_in=issued[1:0];clear=issued<4;last=issued>=TARGET-4;
      if(in_valid&&(!ready_a||!ready_b))$fatal(1,"scheduled issue not ready cycle=%0d A=%b B=%b",cycles,ready_a,ready_b);
      @(posedge clk);
      if(in_valid&&ready_a&&ready_b)issued=issued+1;
      if(valid_a)begin
        if(saved_valid)$fatal(1,"overlapping saved result");
        saved_valid=1;saved_context=context_a;saved_last=last_a;saved_acc=acc_a;saved_flags=flags_a;saved_cycle=cycles;
      end
      if(valid_b)begin
        if(!saved_valid)$fatal(1,"8B-B result without 8B-A result");
        if(cycles-saved_cycle!=1)$fatal(1,"latency shift=%0d expected=1",cycles-saved_cycle);
        if(context_b!=={1'b0,saved_context}||last_b!==saved_last||acc_b!==saved_acc||flags_b!==saved_flags)
          $fatal(1,"value/metadata mismatch completion=%0d",compared);
        saved_valid=0;compared=compared+1;
      end
      if(error_a||error_b)$fatal(1,"protocol error A=%b B=%b",error_a,error_b);
      if(cycles>1000000)$fatal(1,"timeout issued=%0d compared=%0d",issued,compared);
    end
    @(negedge clk);in_valid=0;repeat(10)@(posedge clk);
    if(issued!=TARGET||accepted_a!=TARGET||accepted_b!=TARGET||completed_a!=TARGET||completed_b!=TARGET)$fatal(1,"counter mismatch");
    $display("L5_REV8B_A_VS_REV8B_B_PASS compared=%0d latency_shift=1 lanes=512",TARGET);$finish;
  end
endmodule
