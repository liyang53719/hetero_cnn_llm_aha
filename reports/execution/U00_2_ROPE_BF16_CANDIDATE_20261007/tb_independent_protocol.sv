// Independent review: ordering, all trace bits, internal-phase asynchronous reset.
`timescale 1ns/1ps
module tb_independent_protocol;
  parameter integer PIPE = 0;
  logic clk=0, rst=0, iv=0, ir, ov, ready;
  always #5 clk=~clk;
  logic [31:0] e=0, o=0, c=32'h3f800000, s=0;
  logic [15:0] eo, oo;
  logic [4:0] flags;
  logic [31:0] accepted, completed;
  logic [127:0] pf;
  logic [63:0] pb,sf;
  logic [19:0] mf,pflags;
  logic [9:0] af,tflags;
  logic [352:0] trace_all,held;
  logic was_stalled=0;
  integer sink=0, epoch_cycle=0, wr=0,rd=0;
  integer reset_cases=0, stall_checks=0, transfers=0;
  integer phase_mask=0;
  logic [15:0] queue[0:4095];
  wire [2:0] phase;
  assign ready=(sink==1)||((sink==2)&&((epoch_cycle%19)>6));
  assign trace_all={pf,pb,sf,mf,pflags,af,tflags,eo,oo,flags};
  generate if (PIPE==0) begin:g_comb
    fp32_rope_pair_bf16_candidate d(.clk_i(clk),.rst_ni(rst),.in_valid_i(iv),.in_ready_o(ir),.even_i(e),.odd_i(o),.cos_i(c),.sin_i(s),.out_valid_o(ov),.out_ready_i(ready),.even_o(eo),.odd_o(oo),.exception_flags_o(flags),.accepted_pairs_o(accepted),.completed_pairs_o(completed),.product_fp32_o(pf),.product_bf16_o(pb),.sum_fp32_o(sf),.mul_flags_o(mf),.product_conversion_flags_o(pflags),.add_flags_o(af),.terminal_conversion_flags_o(tflags));
    assign phase={1'b0,d.input_valid_q,d.output_valid_q};
  end else begin:g_pipe
    fp32_rope_pair_bf16_pipe_candidate d(.clk_i(clk),.rst_ni(rst),.in_valid_i(iv),.in_ready_o(ir),.even_i(e),.odd_i(o),.cos_i(c),.sin_i(s),.out_valid_o(ov),.out_ready_i(ready),.even_o(eo),.odd_o(oo),.exception_flags_o(flags),.accepted_pairs_o(accepted),.completed_pairs_o(completed),.product_fp32_o(pf),.product_bf16_o(pb),.sum_fp32_o(sf),.mul_flags_o(mf),.product_conversion_flags_o(pflags),.add_flags_o(af),.terminal_conversion_flags_o(tflags));
    assign phase=d.st;
  end endgenerate
  always @(posedge clk or negedge rst) begin
    if (!rst) begin
      wr=0; rd=0; was_stalled=0; epoch_cycle<=0;
    end else begin
      if (accepted!==wr || completed!==rd) $fatal(1,"counter drift");
      if (was_stalled && (!ov || trace_all!==held)) $fatal(1,"unstable valid/full trace");
      was_stalled=ov&&!ready;
      if (was_stalled) begin held=trace_all; stall_checks=stall_checks+1; end
      if (iv&&ir) begin queue[wr]=e[31:16]; wr=wr+1; end
      if (ov&&ready) begin
        if (rd>=wr) $fatal(1,"stale/duplicate output");
        if (eo!==queue[rd] || oo!==0 || flags!==0) $fatal(1,"reordered/wrong result");
        if (pf!=={96'd0,queue[rd],16'd0} || pb!=={48'd0,queue[rd]} || sf!=={32'd0,queue[rd],16'd0}) $fatal(1,"wrong trace order");
        if (mf!==0 || pflags!==0 || af!==0 || tflags!==0) $fatal(1,"wrong trace flags");
        rd=rd+1; transfers=transfers+1;
      end
      epoch_cycle<=epoch_cycle+1;
    end
  end
  task automatic reset_flush;
    begin
      // Assert away from either clock edge; check asynchronous external flush.
      #2; phase_mask=phase_mask|(1<<phase); rst=0; iv=0; sink=0;
      #1;
      if (ov!==0 || accepted!==0 || completed!==0 || trace_all!=='0) $fatal(1,"asynchronous flush failed");
      repeat(3) @(negedge clk);
      rst=1; sink=1;
      repeat(32) @(negedge clk);
      if (accepted!==0 || completed!==0 || ov!==0) $fatal(1,"late reset survivor");
      reset_cases=reset_cases+1;
    end
  endtask
  task automatic send_one(input logic[15:0] word);
    begin
      @(negedge clk); iv=1; e={word,16'b0};
      do @(posedge clk); while(!ir);
      @(negedge clk); iv=0;
    end
  endtask
  initial begin
    repeat(3) @(negedge clk); rst=1;
    @(negedge clk); reset_flush();
    for(integer age=0;age<17;age=age+1) begin
      sink=0;
      send_one(16'h3f80+16'(age));
      repeat(age) @(negedge clk);
      reset_flush();
    end
    if(PIPE==0) begin
      sink=0; send_one(16'h3f80); send_one(16'h4000);
      repeat(4) @(negedge clk); reset_flush();
      if((phase_mask&15)!=15) $fatal(1,"missing elastic state reset coverage %h",phase_mask);
    end else if((phase_mask&63)!=63) $fatal(1,"missing FSM phase reset coverage %h",phase_mask);
    sink=2;
    for(integer i=0;i<1024;i=i+1) begin
      @(negedge clk); iv=1; e={16'h3000+16'(i),16'b0};
      do @(posedge clk); while(!ir);
      if((i%23)==9) begin @(negedge clk); iv=0; repeat(3) @(negedge clk); end
    end
    @(negedge clk); iv=0; sink=1;
    while(rd<1024) @(negedge clk);
    repeat(40) @(negedge clk);
    if(accepted!==1024 || completed!==1024 || stall_checks==0) $fatal(1,"incomplete test");
    $display("INDEPENDENT_PROTOCOL_PASS pipe=%0d reset_cases=%0d reset_phase_mask=%0h transfers=%0d stall_checks=%0d",PIPE,reset_cases,phase_mask,transfers,stall_checks);
    $finish;
  end
  initial begin repeat(100000) @(posedge clk); $fatal(1,"timeout"); end
endmodule
