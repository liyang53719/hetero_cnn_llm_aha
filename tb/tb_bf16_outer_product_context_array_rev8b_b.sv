`timescale 1ns/1ps
module tb_bf16_outer_product_context_array_rev8b_b;
  localparam integer ROWS=16,COLS=32,LANES=512,MAIN_STEPS=1_000_000,RANDOM_STEPS=10_000;
  logic clk,rst_n,in_valid,in_ready,clear,last,out_valid,out_ready,out_last;
  logic[2:0]context_in,context_out;
  logic[ROWS*16-1:0]a;
  logic[COLS*16-1:0]b;
  logic[LANES*32-1:0]acc;
  logic[4:0]flags,flags_or,busy,accumulator_valid;
  logic[31:0]accepted,completed,lfsr;
  logic protocol_error;
  integer cycles,issue_count,completion_count,last_count,first_issue_cycle,last_issue_cycle;
  integer context_steps[0:4];
  always #0.5 clk=~clk;
  always @(posedge clk or negedge rst_n)if(!rst_n)cycles<=0;else cycles<=cycles+1;
  bf16_outer_product_context_array_rev8b_b_candidate dut(
    .clk_i(clk),.rst_ni(rst_n),.in_valid_i(in_valid),.in_ready_o(in_ready),.context_i(context_in),
    .clear_i(clear),.last_i(last),.a_i(a),.b_i(b),.out_valid_o(out_valid),.out_ready_i(out_ready),
    .context_o(context_out),.last_o(out_last),.acc_o(acc),.exception_flags_o(flags),.busy_o(busy),
    .accumulator_valid_o(accumulator_valid),.accepted_steps_o(accepted),.completed_steps_o(completed),
    .protocol_error_o(protocol_error));
  function automatic[31:0]fp32_expected(input integer value);
    case(value)200000:fp32_expected=32'h48435000;2000:fp32_expected=32'h44fa0000;default:fp32_expected=32'hffff_ffff;endcase
  endfunction
  task automatic initialize;
    begin
      in_valid=0;out_ready=0;context_in=0;clear=0;last=0;a={ROWS{16'h3f80}};b={COLS{16'h3f80}};
      flags_or=0;issue_count=0;completion_count=0;last_count=0;first_issue_cycle=-1;last_issue_cycle=-1;
      for(integer c=0;c<5;c++)context_steps[c]=0;
    end
  endtask
  task automatic reset_dut;
    begin rst_n=0;repeat(6)@(posedge clk);rst_n=1;@(negedge clk);end
  endtask
  task automatic run_phase(input integer target,input logic random_mode);
    integer expected_context,expected_value;
    begin
      while(completion_count<target)begin
        @(negedge clk);lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
        in_valid=issue_count<target&&(!random_mode||lfsr[2]||lfsr[7]);
        context_in=issue_count%5;clear=context_steps[context_in]==0;last=issue_count>=target-5;
        out_ready=!random_mode||lfsr[0]||lfsr[5];
        @(posedge clk);
        if(in_valid&&in_ready)begin
          if(first_issue_cycle<0)first_issue_cycle=cycles;last_issue_cycle=cycles;
          context_steps[context_in]=context_steps[context_in]+1;issue_count=issue_count+1;
        end
        if(out_valid&&out_ready)begin
          expected_context=completion_count%5;
          if(context_out!==expected_context[2:0])$fatal(1,"context reorder completion=%0d got=%0d",completion_count,context_out);
          if(out_last)begin
            last_count=last_count+1;expected_value=target/5;
            for(integer lane=0;lane<LANES;lane++)if(acc[lane*32+:32]!==fp32_expected(expected_value))
              $fatal(1,"final mismatch context=%0d lane=%0d got=%08x expected=%08x",context_out,lane,acc[lane*32+:32],fp32_expected(expected_value));
          end
          flags_or=flags_or|flags;completion_count=completion_count+1;
        end
        if(protocol_error)$fatal(1,"protocol error");
      end
      @(negedge clk);in_valid=0;out_ready=1;repeat(10)@(posedge clk);
      if(accepted!=target||completed!=target)$fatal(1,"counter mismatch %0d %0d",accepted,completed);
      if(last_count!=5)$fatal(1,"last count=%0d",last_count);
      if(flags_or[4:1]!=0)$fatal(1,"flags=%h",flags_or);
      for(integer c=0;c<5;c++)if(context_steps[c]!=target/5)$fatal(1,"context %0d steps=%0d",c,context_steps[c]);
    end
  endtask
  initial begin
    clk=0;rst_n=0;lfsr=32'h8bb5_c0de;initialize();reset_dut();run_phase(MAIN_STEPS,0);
    if(last_issue_cycle-first_issue_cycle+1>MAIN_STEPS+5)$fatal(1,"II1 fail window=%0d",last_issue_cycle-first_issue_cycle+1);
    $display("BF16_CONTEXT5_MAIN_PASS steps=%0d issue_window=%0d",MAIN_STEPS,last_issue_cycle-first_issue_cycle+1);
    initialize();reset_dut();run_phase(RANDOM_STEPS,1);
    $display("BF16_CONTEXT5_ARRAY_E1_PASS main_steps=%0d random_steps=%0d contexts=5 lanes=512",MAIN_STEPS,RANDOM_STEPS);
    $finish;
  end
  initial begin repeat(3_000_000)@(posedge clk);$fatal(1,"timeout");end
endmodule
