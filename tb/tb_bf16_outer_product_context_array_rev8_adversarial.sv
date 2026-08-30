`timescale 1ns/1ps
`ifndef L5_CONTEXT_ARRAY_DUT
`define L5_CONTEXT_ARRAY_DUT bf16_outer_product_context_array_rev8_candidate
`endif
module tb_bf16_outer_product_context_array_rev8_adversarial;
  localparam integer ROWS=16, COLS=32, LANES=ROWS*COLS;
  localparam integer TARGET=50_000;
  logic clk, rst_n;
  logic in_valid,in_ready,clear,last,out_valid,out_ready,out_last;
  logic [1:0] context_in,context_out;
  logic [ROWS*16-1:0] a;
  logic [COLS*16-1:0] b;
  logic [LANES*32-1:0] acc;
  logic [4:0] flags;
  logic [3:0] busy,accumulator_valid;
  logic [31:0] accepted,completed;
  logic protocol_error;
  logic [31:0] lfsr;
  integer issued,received,cycles;
  integer expected_count[0:3];
  logic pending;
  logic [1:0] pending_context;
  logic pending_clear,pending_last;
  logic [1:0] response_context[0:TARGET-1];
  integer response_value[0:TARGET-1];
  logic response_last[0:TARGET-1];
  integer wp,rp;

  always #0.5 clk=~clk;

  `L5_CONTEXT_ARRAY_DUT dut(
    .clk_i(clk),.rst_ni(rst_n),.in_valid_i(in_valid),.in_ready_o(in_ready),
    .context_i(context_in),.clear_i(clear),.last_i(last),.a_i(a),.b_i(b),
    .out_valid_o(out_valid),.out_ready_i(out_ready),.context_o(context_out),
    .last_o(out_last),.acc_o(acc),.exception_flags_o(flags),.busy_o(busy),
    .accumulator_valid_o(accumulator_valid),.accepted_steps_o(accepted),
    .completed_steps_o(completed),.protocol_error_o(protocol_error)
  );

  function automatic [31:0] uint_to_fp32(input integer value);
    integer msb,i;
    reg [31:0] shifted;
    reg [7:0] exponent;
    begin
      if(value==0) uint_to_fp32=32'h0;
      else begin
        msb=0;
        for(i=30;i>=0;i=i-1) if((value&(1<<i)) != 0) begin msb=i;i=-1;end
        if(msb<=23) shifted=value<<(23-msb); else shifted=value>>(msb-23);
        exponent=8'(127+msb);
        uint_to_fp32={1'b0,exponent,shifted[22:0]};
      end
    end
  endfunction

  initial begin
    clk=0;rst_n=0;
    a={ROWS{16'h3f80}}; b={COLS{16'h3f80}};
    in_valid=0;context_in=0;clear=0;last=0;out_ready=0;
    lfsr=32'h8a17c0de;issued=0;received=0;cycles=0;pending=0;wp=0;rp=0;
    for(integer c=0;c<4;c=c+1)expected_count[c]=0;
    repeat(8)@(posedge clk);rst_n=1;
    while(received<TARGET) begin
      @(negedge clk);
      cycles=cycles+1;
      lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
      if(!pending&&issued<TARGET) begin
        pending=1;
        pending_context=lfsr[3:2];
        pending_clear=(expected_count[pending_context]==0)||(lfsr[15:8]==8'h00);
        pending_last=lfsr[7];
      end
      in_valid=pending;
      context_in=pending_context;
      clear=pending_clear;
      last=pending_last;
      out_ready=lfsr[0]||lfsr[5]||lfsr[9];
      @(posedge clk);
      if(in_valid&&in_ready) begin
        if(clear)expected_count[context_in]=1;else expected_count[context_in]=expected_count[context_in]+1;
        response_context[wp]=context_in;
        response_value[wp]=expected_count[context_in];
        response_last[wp]=last;
        wp=wp+1;issued=issued+1;pending=0;
      end
      if(out_valid&&out_ready) begin
        if(rp>=wp)$fatal(1,"response without request");
        if(context_out!==response_context[rp])$fatal(1,"context mismatch got=%0d exp=%0d",context_out,response_context[rp]);
        if(out_last!==response_last[rp])$fatal(1,"last mismatch");
        for(integer lane=0;lane<LANES;lane=lane+1)
          if(acc[lane*32+:32]!==uint_to_fp32(response_value[rp]))
            $fatal(1,"value mismatch response=%0d lane=%0d got=%08x exp=%08x",rp,lane,acc[lane*32+:32],uint_to_fp32(response_value[rp]));
        rp=rp+1;received=received+1;
      end
      if(protocol_error)$fatal(1,"protocol error");
      if(flags[4:1]!=0)$fatal(1,"flags=%h",flags);
      if(cycles>2_000_000)$fatal(1,"timeout");
    end
    @(negedge clk);in_valid=0;out_ready=1;
    repeat(8)@(posedge clk);
    if(accepted!=TARGET||completed!=TARGET)$fatal(1,"counter mismatch %0d %0d",accepted,completed);
    $display("BF16_CONTEXT_REV8_ADVERSARIAL_PASS steps=%0d cycles=%0d contexts=4 lanes=512",TARGET,cycles);
    $finish;
  end
endmodule
