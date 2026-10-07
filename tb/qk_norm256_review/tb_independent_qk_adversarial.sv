`timescale 1ns/1ps
module tb_independent_qk_adversarial;
logic clk=0; always #5 clk=~clk;
logic rst=0,iv=0,ir,ov,orr=0;
logic[8191:0] packed_x=0; logic[4095:0] weight=0,norm,gate;
logic[1:0] role=0; logic[15:0] dim=256; logic[7:0] policy=8'hc1;
logic[31:0] eps=32'h358637bd,tag=0,otag,mean,inv,acc,comp;
logic[3:0] status;logic[4:0] flags;
integer passed=0,flushed=0,expected_acc=0,expected_comp=0;
qk_norm256_bf16_candidate dut(.clk_i(clk),.rst_ni(rst),.in_valid_i(iv),.in_ready_o(ir),.packed_i(packed_x),.weight_i(weight),.role_i(role),.head_dim_i(dim),.policy_i(policy),.epsilon_i(eps),.tag_i(tag),.out_valid_o(ov),.out_ready_i(orr),.norm_o(norm),.gate_o(gate),.status_o(status),.tag_o(otag),.exception_flags_o(flags),.mean_eps_o(mean),.inv_o(inv),.accepted_o(acc),.completed_o(comp));
task automatic reset_all;
 @(negedge clk);rst=0;iv=0;orr=0;repeat(3)@(negedge clk);
 if(ov||ir||acc||comp||norm||gate||otag||flags||mean||inv)$fatal(1,"reset did not clear/suppress outputs");
 rst=1;expected_acc=0;expected_comp=0;@(negedge clk);if(!ir||ov)$fatal(1,"reset did not restore idle");
endtask
// All valid arithmetic cases use gamma=RN32(1 + -1)=+0, giving independently
// predictable signed-zero norms even for full supported exponent extremes.
task automatic setup(input integer mode);
 role=mode[0];dim=256;policy=8'hc1;eps=32'h358637bd;tag=32'ha00b0000+mode;
 for(integer l=0;l<256;l++) begin
  packed_x[l*16+:16]={l[0],8'(95+((l+mode)%64)),7'((l*13+mode)%128)};
  weight[l*16+:16]=16'hbf80;
  packed_x[4096+l*16+:16]=16'((l*257)^mode);
 end
 packed_x[0+:16]=16'h0000;packed_x[16+:16]=16'h8000;
 packed_x[32+:16]=16'h2f80;packed_x[48+:16]=16'hcf7f;
 packed_x[4096+:64]=64'hff817fc17f800001;
 case(mode)
  40:begin role=2;packed_x[0+:16]=16'h7f81;end
  41:begin policy=0;weight[0+:16]=16'h0001;end
  42:begin dim=128;packed_x[0+:16]=16'h7f80;end
  43:begin eps=32'h358637bc;packed_x[0+:16]=16'h2f00;end
  44:begin packed_x[0+:16]=16'h7fc0;weight[16+:16]=16'h0001;end
  45:begin weight[16+:16]=16'hff80;packed_x[0+:16]=16'h4f80;end
  46:packed_x[0+:16]=16'h2f7f;
  47:weight[0+:16]=16'h4f80;
  48:packed_x[0+:16]=16'h0001;
  49:weight[0+:16]=16'h8001;
 endcase
endtask
task automatic run_case(input integer mode,input integer expected_status);
 logic[4095:0] en,eg;logic[31:0] et;logic[8296:0] held;integer timeout;
 @(negedge clk);setup(mode);en=0;eg=role==0?packed_x[8191:4096]:4096'b0;et=tag;
 for(integer l=0;l<256;l++)en[l*16+:16]={packed_x[l*16+15],15'b0};
 if(expected_status!=0)begin en=0;eg=0;end
 if(!ir)$fatal(1,"not ready at start");iv=1;
 @(negedge clk);expected_acc++;if(acc!=expected_acc||ir)$fatal(1,"request capture mismatch");
 // Unaccepted changing inputs must not corrupt a captured transaction.
 iv=1;packed_x='1;weight='1;role=3;dim=0;policy=0;eps=0;tag='1;
 timeout=0;
 while(!ov)begin @(negedge clk);timeout++;if(timeout>3000)$fatal(1,"timeout");if(ir)$fatal(1,"busy unexpectedly ready");end
 if(status!==4'(expected_status)||norm!==en||gate!==eg||otag!==et)$fatal(1,"adversarial mismatch mode=%0d status=%0d normlow=%h explow=%h tag=%h",mode,status,norm[63:0],en[63:0],otag);
 if(expected_status!=0 && (flags||mean||inv))$fatal(1,"preflight error exposed arithmetic state");
 if(expected_status==0 && (flags[4:1]||mean[31]||inv[31]||mean[30:23]==0||inv[30:23]==0))$fatal(1,"valid domain error");
 held={norm,gate,status,otag,flags,mean,inv};
 repeat(17)begin @(negedge clk);packed_x=$random;weight=$random;tag=$random;
  if(!ov||ir||{norm,gate,status,otag,flags,mean,inv}!==held||acc!=expected_acc||comp!=expected_comp)$fatal(1,"stalled response changed");
 end
 iv=0;orr=1;@(negedge clk);expected_comp++;if(comp!=expected_comp||ov||!ir)$fatal(1,"completion mismatch");orr=0;passed++;
endtask
initial begin
 reset_all();
 for(integer k=0;k<50;k++)run_case(k,k<40?0:(k<44?1:(k<46?2:3)));
 // Reset aborts requests throughout issue/reduction/rsqrt/output/backpressure.
 for(integer kind=0;kind<10;kind++)begin
  @(negedge clk);setup(kind);iv=1;@(negedge clk);iv=0;
  case(kind)
   0:begin end
   1:wait(dut.norm_core.st==1);
   2:wait(dut.norm_core.st==2&&dut.norm_core.red.level_q==0);
   3:wait(dut.norm_core.st==2&&dut.norm_core.red.level_q==3);
   4:wait(dut.norm_core.st==2&&dut.norm_core.chunk==15);
   5:wait(dut.norm_core.st==3);
   6:wait(dut.norm_core.st==4);
   7:wait(dut.norm_core.st==5&&dut.norm_core.chunk==0);
   8:wait(dut.norm_core.st==5&&dut.norm_core.chunk==15);
   9:wait(ov);
  endcase
  reset_all();flushed++;repeat(700)begin @(negedge clk);if(ov||acc||comp)$fatal(1,"aborted transaction reappeared");end
  run_case(kind,0);
 end
 $display("INDEPENDENT_QK_ADVERSARIAL_PASS checked=%0d reset_flushes=%0d",passed,flushed);$finish;
end
initial begin #20000000;$fatal(1,"watchdog");end
endmodule
