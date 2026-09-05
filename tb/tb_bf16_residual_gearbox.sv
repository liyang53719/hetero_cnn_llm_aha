`timescale 1ns/1ps
module tb_bf16_residual_gearbox;
 logic clk=0;always #1 clk=~clk;
 logic rst=0,iv=0,ir,il=0,ov,orr=0,ol;logic[511:0]idata=0,odata;
 logic[31:0]ik=0,first=0,chunk;logic[15:0]ok;logic[7:0]status;logic[63:0]accepted,emitted;
 logic[511:0]expdata[0:199];logic[31:0]expchunk[0:199];logic[15:0]expkeep[0:199];logic explast[0:199];logic[7:0]expstatus[0:199];
 integer nexpected=0,received=0;logic[31:0]rng=32'hb167abcd;
 logic held=0;logic[511:0]hd;logic[31:0]hc;logic[15:0]hk;logic hl;logic[7:0]hs;
 bf16_residual_gearbox dut(.clk_i(clk),.rst_ni(rst),.in_valid_i(iv),.in_ready_o(ir),.in_data_i(idata),.in_keep_i(ik),.in_first_chunk_i(first),.in_last_i(il),
 .out_valid_o(ov),.out_ready_i(orr),.out_data_o(odata),.out_keep_o(ok),.out_chunk_o(chunk),.out_last_o(ol),.out_status_o(status),.accepted_beats_o(accepted),.emitted_chunks_o(emitted));
 function automatic[31:0]mask(input integer n);
  case(n%5)0:return 32'hffffffff;1:return 32'h0000007f;2:return 32'h007f0000;3:return 32'hf0f0000f;default:return 0;endcase
 endfunction
 function automatic[511:0]payload(input integer n);logic[511:0]v;begin for(int i=0;i<32;i++)v[i*16+:16]=16'(n*97+i*13);return v;end endfunction
 always @(posedge clk)if(rst)begin
  rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(held&&(!ov||odata!==hd||chunk!==hc||ok!==hk||ol!==hl||status!==hs))$fatal(1,"stability");
  held<=ov&&!orr;hd<=odata;hc<=chunk;hk<=ok;hl<=ol;hs<=status;
  if(ov&&orr)begin
   if(received>=nexpected||odata!==expdata[received]||chunk!==expchunk[received]||ok!==expkeep[received]||ol!==explast[received]||status!==expstatus[received])$fatal(1,"output %0d",received);
   received++;
  end
 end
 always @(negedge clk)orr=rng[0]&&rng[4];
 initial begin
  for(int n=0;n<100;n++)begin
   logic[511:0]v;logic[31:0]k,idx;logic last;
   v=payload(n);k=n==99?32'hffffffff:mask(n);idx=n==99?32'hffffffff:32'(n*2);last=(n%7==6)||n==99;
   if(k==0||n==99)begin
    expdata[nexpected]=0;expkeep[nexpected]=0;expchunk[nexpected]=idx;explast[nexpected]=last;expstatus[nexpected]=5;nexpected++;
   end else for(int half=0;half<2;half++)if(k[half*16+:16]!=0)begin
    expdata[nexpected]={256'd0,v[half*256+:256]};expkeep[nexpected]=k[half*16+:16];expchunk[nexpected]=idx+half;
    explast[nexpected]=last&&(half==1||k[31:16]==0);expstatus[nexpected]=0;nexpected++;
   end
  end
  repeat(3)@(negedge clk);if(ir)$fatal(1,"ready during reset");rst=1;
  for(int n=0;n<100;n++)begin
   @(negedge clk);iv=1;idata=payload(n);ik=n==99?32'hffffffff:mask(n);first=n==99?32'hffffffff:32'(n*2);il=(n%7==6)||n==99;
   do @(posedge clk);while(!ir);@(negedge clk);iv=0;
  end
  wait(received==nexpected);@(negedge clk);
  if(accepted!=100||emitted!=nexpected)$fatal(1,"counters");
  $display("BF16_RESIDUAL_GEARBOX_PASS input_beats=100 output_chunks=%0d no_duplicate_read_required=1 tails=1 index_overflow=1 backpressure=1",received);$finish;
 end
 initial begin repeat(10000)@(posedge clk);$fatal(1,"timeout");end
endmodule
