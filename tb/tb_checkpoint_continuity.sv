`timescale 1ns/1ps
module tb_checkpoint_continuity;
 logic clk=0,rst=0;always #0.625 clk=~clk;
 logic[31:0]cycle,lfsr,digest,pipeline[0:3],mem[0:31];logic[3:0]valid;
 logic[31:0]ddr[longint unsigned];logic[31:0]queue[$];
 logic[31:0]next_digest,popped,final_digest;
 always @(posedge clk)begin
  if(!rst)begin cycle<=0;lfsr<=32'h72451abc;digest<=0;valid<=0;
   for(int i=0;i<4;i++)pipeline[i]<=0;
   for(int i=0;i<32;i++)mem[i]<=0;
   ddr.delete();queue.delete();
  end else begin
   cycle<=cycle+1;lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
   next_digest={digest[30:0],digest[31]};
   if(valid[3])next_digest^=pipeline[3];
   if(cycle%3==0)queue.push_back(lfsr);
   if(cycle%5==0&&queue.size()>0)begin popped=queue.pop_front();next_digest^=popped;end
   digest<=next_digest;
   valid<={valid[2:0],lfsr[0]};pipeline[0]<=lfsr;
   for(int i=1;i<4;i++)pipeline[i]<=pipeline[i-1];
   mem[cycle%32]<=lfsr;
   ddr[64'h100000000+64'(cycle%64)]=lfsr^cycle;
  end
 end
 initial begin
  repeat(4)@(negedge clk);rst=1;
  wait(cycle==1000);@(negedge clk);
  final_digest=digest;
  foreach(mem[i])final_digest^=mem[i];
  foreach(ddr[i])final_digest^=ddr[i];
  foreach(queue[i])final_digest^=queue[i];
  foreach(pipeline[i])final_digest^=pipeline[i];
  if(ddr.num()!=64||queue.size()==0)$fatal(1,"fixture state coverage");
  $display("CHECK_STATE_SCALARS %0d %08h %08h %h",cycle,lfsr,digest,valid);
  foreach(mem[i])$display("CHECK_STATE_MEM %0d %08h",i,mem[i]);
  foreach(ddr[i])$display("CHECK_STATE_DDR %016h %08h",i,ddr[i]);
  foreach(queue[i])$display("CHECK_STATE_QUEUE %0d %08h",i,queue[i]);
  foreach(pipeline[i])$display("CHECK_STATE_PIPE %0d %08h",i,pipeline[i]);
  $display("SAVE_RESTORE_CONTINUITY_PASS cycles=%0d digest=%08h queue=%0d pending=%h",cycle,final_digest,queue.size(),valid);
  $finish;
 end
endmodule
