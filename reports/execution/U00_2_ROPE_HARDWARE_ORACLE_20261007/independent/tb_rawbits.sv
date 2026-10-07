`timescale 1ns/1ps
module rope_review_rawbits;
  localparam N=10000;
  logic clk=0,rst_n=0,iv=0;
  always #5 clk=~clk;
  logic [31:0] e,o,c,s;
  wire ir0,ir1,ov0,ov1;wire [31:0] e0,o0,e1,o1,accepted,completed;wire [4:0] f0,f1;
  integer count0=0,count1=0,cyc=0;wire ready=(cyc%13)>=4;
  logic[199:0] vec[0:N-1]; string vector_path;
  fp32_rope_pair a(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir0),.even_i(e),.odd_i(o),.cos_i(c),.sin_i(s),.out_valid_o(ov0),.out_ready_i(ready),.even_o(e0),.odd_o(o0),.exception_flags_o(f0),.accepted_pairs_o(accepted),.completed_pairs_o(completed));
  fp32_rope_pair_pipe b(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir1),.even_i(e),.odd_i(o),.cos_i(c),.sin_i(s),.out_valid_o(ov1),.out_ready_i(ready),.even_o(e1),.odd_o(o1),.exception_flags_o(f1));
  always @(posedge clk) if(rst_n) begin
    cyc<=cyc+1;
    if(ov0&&ready) begin
      if(count0>=N || {3'd0,f0,o0,e0}!==vec[count0][199:128]) $fatal(1,"comb mismatch i=%0d got=%08h,%08h,%02h expected=%018h",count0,e0,o0,f0,vec[count0][199:128]);
      count0<=count0+1;
    end
    if(ov1&&ready) begin
      if(count1>=N || {3'd0,f1,o1,e1}!==vec[count1][199:128]) $fatal(1,"pipe mismatch i=%0d got=%08h,%08h,%02h expected=%018h",count1,e1,o1,f1,vec[count1][199:128]);
      count1<=count1+1;
    end
  end
  initial begin
    e=0;o=0;c=0;s=0;if(!$value$plusargs("VECTORS=%s",vector_path)) $fatal(1,"missing vectors");$readmemh(vector_path,vec);
    repeat(3) @(negedge clk);rst_n=1;
    for(integer i=0;i<N;i++) begin
      do @(negedge clk);while(!(ir0&&ir1));
      {s,c,o,e}=vec[i][127:0];iv=1;
      @(negedge clk);iv=0;
      wait(count0==i+1&&count1==i+1);
    end
    repeat(30) @(negedge clk);
    if(count0!=N||count1!=N||accepted!=N||completed!=N) $fatal(1,"count mismatch");
    $display("REVIEW RAWBITS PASS both_wrappers=%0d cycles=%0d",N,cyc);$finish;
  end
  initial begin repeat(N*60) @(posedge clk);$fatal(1,"timeout");end
endmodule
