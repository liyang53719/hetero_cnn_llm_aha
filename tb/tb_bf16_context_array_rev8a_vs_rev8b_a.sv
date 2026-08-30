`timescale 1ns/1ps
module tb_bf16_context_array_rev8a_vs_rev8b_a;
  localparam integer ROWS=16, COLS=32, LANES=512, TARGET=120000;
  logic clk,rst_n,in_valid,clear,last,out_ready;
  logic [1:0] context_in;
  logic [ROWS*16-1:0] a;
  logic [COLS*16-1:0] b;
  logic ready_a,ready_b,valid_a,valid_b,last_a,last_b;
  logic [1:0] context_a,context_b;
  logic [LANES*32-1:0] acc_a,acc_b;
  logic [4:0] flags_a,flags_b;
  logic [3:0] busy_a,busy_b,acc_valid_a,acc_valid_b;
  logic [31:0] accepted_a,accepted_b,completed_a,completed_b;
  logic error_a,error_b;
  logic [31:0] lfsr;
  integer issued,cycles;

  always #0.5 clk=~clk;

  bf16_outer_product_context_array_rev8_candidate rev8a(
    .clk_i(clk),.rst_ni(rst_n),.in_valid_i(in_valid),.in_ready_o(ready_a),
    .context_i(context_in),.clear_i(clear),.last_i(last),.a_i(a),.b_i(b),
    .out_valid_o(valid_a),.out_ready_i(out_ready),.context_o(context_a),
    .last_o(last_a),.acc_o(acc_a),.exception_flags_o(flags_a),.busy_o(busy_a),
    .accumulator_valid_o(acc_valid_a),.accepted_steps_o(accepted_a),
    .completed_steps_o(completed_a),.protocol_error_o(error_a));

  bf16_outer_product_context_array_rev8b_a_candidate rev8b_a(
    .clk_i(clk),.rst_ni(rst_n),.in_valid_i(in_valid),.in_ready_o(ready_b),
    .context_i(context_in),.clear_i(clear),.last_i(last),.a_i(a),.b_i(b),
    .out_valid_o(valid_b),.out_ready_i(out_ready),.context_o(context_b),
    .last_o(last_b),.acc_o(acc_b),.exception_flags_o(flags_b),.busy_o(busy_b),
    .accumulator_valid_o(acc_valid_b),.accepted_steps_o(accepted_b),
    .completed_steps_o(completed_b),.protocol_error_o(error_b));

  task automatic compare_public;
    begin
      if(ready_a!==ready_b || valid_a!==valid_b || context_a!==context_b ||
         last_a!==last_b || acc_a!==acc_b || flags_a!==flags_b ||
         busy_a!==busy_b || acc_valid_a!==acc_valid_b ||
         accepted_a!==accepted_b || completed_a!==completed_b ||
         error_a!==error_b)
        $fatal(1,"Revision8A/8B-A mismatch cycle=%0d issued=%0d",cycles,issued);
    end
  endtask

  initial begin
    clk=0;rst_n=0;in_valid=0;clear=0;last=0;out_ready=0;context_in=0;
    a={ROWS{16'h3f80}};b={COLS{16'h3f80}};
    lfsr=32'h8ba8_1200;issued=0;cycles=0;
    repeat(8)@(posedge clk);rst_n=1;
    while(completed_a<TARGET) begin
      @(negedge clk);
      cycles=cycles+1;
      compare_public();
      lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
      out_ready=lfsr[0]||lfsr[5]||lfsr[9];
      if(issued<TARGET) begin
        in_valid=lfsr[2]||lfsr[7]||lfsr[13];
        context_in=lfsr[4:3];
        clear=(issued<4)||(lfsr[15:8]==8'h00);
        last=lfsr[17];
      end else begin
        in_valid=0;clear=0;last=0;out_ready=1;
      end
      @(posedge clk);
      if(in_valid&&ready_a)issued=issued+1;
      if(cycles>1000000)$fatal(1,"timeout issued=%0d completed=%0d",issued,completed_a);
    end
    @(negedge clk);in_valid=0;out_ready=1;compare_public();
    repeat(8)begin @(posedge clk);@(negedge clk);compare_public();end
    if(issued!=TARGET||accepted_a!=TARGET||completed_a!=TARGET)
      $fatal(1,"counter mismatch issued=%0d accepted=%0d completed=%0d",issued,accepted_a,completed_a);
    $display("L5_REV8A_VS_REV8B_A_PASS compared=%0d cycles=%0d contexts=4 lanes=512",TARGET,cycles);
    $finish;
  end
endmodule
