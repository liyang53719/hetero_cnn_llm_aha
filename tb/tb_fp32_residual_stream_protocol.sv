`timescale 1ns/1ps
module tb_fp32_residual_stream_protocol;
 logic clk=0;always #1 clk=~clk;
 logic rst=0,av=0,ar,bv=0,br,bs=0,al=0,bl=0,ov,orr=0,ol,fault;
 logic[511:0]a,b,data;logic[15:0]at=0,bt=0,ak=16'hffff,bk=16'hffff,tag,keep;
 logic[4:0]flags;logic[7:0]status;logic[31:0]rng=32'hf32a4567;
 integer senta=0,sentb=0,received=0;logic phase_error=0;
 fp32_residual_stream dut(.clk_i(clk),.rst_ni(rst),.a_valid_i(av),.a_ready_o(ar),.a_data_i(a),.a_tag_i(at),.a_keep_i(ak),.a_last_i(al),
 .b_valid_i(bv),.b_ready_o(br),.b_data_i(b),.b_bf16_i(bs),.b_tag_i(bt),.b_keep_i(bk),.b_last_i(bl),
 .out_valid_o(ov),.out_ready_i(orr),.out_data_o(data),.out_tag_o(tag),.out_keep_o(keep),.out_last_o(ol),.out_flags_o(flags),.out_status_o(status),.fault_o(fault));
 function automatic[511:0]avec(input integer n);logic[511:0]v;begin for(int i=0;i<16;i++)v[i*32+:32]=32'h3f801101+32'(n*16+i);return v;end endfunction
 function automatic[511:0]bvec(input integer n);logic[511:0]v;begin v=0;for(int i=0;i<16;i++)if(n%2)v[i*16+:16]=16'h3f00+16'(i);else v[i*32+:32]=32'h3e800100+32'(n+i);return v;end endfunction
 function automatic[15:0]mask(input integer n);return n%3==0?16'h007f:16'hffff;endfunction
 logic held=0;logic[511:0]hd;logic[15:0]ht,hk;logic hl;logic[7:0]hs;
 always @(posedge clk)if(rst)begin
  if(held&&(!ov||data!==hd||tag!==ht||keep!==hk||ol!==hl||status!==hs))$fatal(1,"output stability");
  held<=ov&&!orr;hd<=data;ht<=tag;hk<=keep;hl<=ol;hs<=status;
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(!phase_error)begin
   if(av&&ar)senta++;
   if(bv&&br)sentb++;
   if(ov&&orr)begin
    logic[511:0]expected,x,y;
    x=avec(received);y=bvec(received);expected=0;
    for(int i=0;i<16;i++)if(mask(received)&(16'b1<<i))expected[i*32+:32]=x[i*32+:32]^((received%2)?{y[i*16+:16],16'b0}:y[i*32+:32]);
    if(status||flags||tag!=received||keep!=mask(received)||ol!=(received==99)||data!==expected)$fatal(1,"pairing %0d",received);
    received++;
   end
  end
 end
 always @(negedge clk)if(rst&&!phase_error)begin
  if(!av||senta!=int'(at))begin av=senta<100&&(rng[0]||rng[2]);a=avec(senta);at=16'(senta);ak=mask(senta);al=senta==99;end
  if(!bv||sentb!=int'(bt))begin bv=sentb<100&&(rng[1]||rng[3]);b=bvec(sentb);bt=16'(sentb);bk=mask(sentb);bl=sentb==99;bs=1'(sentb%2);end
  orr=rng[4]&&rng[6];
 end
 initial begin
  repeat(3)@(negedge clk);rst=1;wait(received==100);@(negedge clk);phase_error=1;
  av=1;bv=1;at=7;bt=8;ak=16'hffff;bk=16'hffff;al=0;bl=0;orr=0;
  do @(posedge clk);while(!(ar&&br));@(negedge clk);av=0;bv=0;
  wait(ov);@(negedge clk);if(status!=7||!fault||ar||br)$fatal(1,"mismatch status");
  repeat(4)@(negedge clk);orr=1;@(posedge clk);@(negedge clk);if(ov||ar||br)$fatal(1,"fault reset requirement");
  rst=0;@(negedge clk);rst=1;@(negedge clk);if(!ar||!br||fault)$fatal(1,"reset recovery");
  $display("FP32_RESIDUAL_STREAM_PROTOCOL_PASS packets=100 pairing=1 bf16_expand=1 backpressure=1 fault_reset=1 arithmetic_mocked=1");$finish;
 end
 initial begin repeat(10000)@(posedge clk);$fatal(1,"timeout");end
endmodule

// Deliberately NON-arithmetic fixture: checks exact operand widening and pairing.
module fp32_vector_alu #(parameter integer LANES=16)(input logic op_i,input logic[LANES*32-1:0]a_i,b_i,output logic[LANES*32-1:0]out_o,output logic[4:0]exception_flags_o);
 assign out_o=a_i^b_i;assign exception_flags_o=0;
 always @(*)if(op_i!==1'b0)$fatal(1,"residual must request add");
endmodule
