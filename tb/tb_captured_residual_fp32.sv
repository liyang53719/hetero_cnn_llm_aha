`timescale 1ns/1ps
module tb_captured_residual_fp32;
 localparam integer BEATS=98304;
 logic clk=0;always #0.625 clk=~clk;
 logic rst=0,av=0,ar,bv=0,br,ov,orr=0,ol,fault;
 logic[511:0]a=0,b=0,result,amem[0:BEATS-1],bmem[0:BEATS-1],expected[0:BEATS-1];
 logic[15:0]at=0,bt=0,tag,keep;logic al=0,bl=0;logic[4:0]flags;logic[7:0]status;
 logic[31:0]rng=32'hcaff1234;integer na=0,nb=0,nout=0,fd;longint unsigned cycles=0;
 fp32_residual_stream dut(.clk_i(clk),.rst_ni(rst),.a_valid_i(av),.a_ready_o(ar),.a_data_i(a),.a_tag_i(at),.a_keep_i(16'hffff),.a_last_i(al),
 .b_valid_i(bv),.b_ready_o(br),.b_data_i(b),.b_bf16_i(1'b1),.b_tag_i(bt),.b_keep_i(16'hffff),.b_last_i(bl),
 .out_valid_o(ov),.out_ready_i(orr),.out_data_o(result),.out_tag_o(tag),.out_keep_o(keep),.out_last_o(ol),.out_flags_o(flags),.out_status_o(status),.fault_o(fault));
 always @(posedge clk)if(rst)begin
  cycles<=cycles+1;rng<={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(av&&ar)na<=na+1;
  if(bv&&br)nb<=nb+1;
  if(fault)$fatal(1,"protocol fault");
  if(ov&&orr)begin
   if(nout>=BEATS||tag!==16'(nout)||keep!==16'hffff||ol!==(nout==BEATS-1)||status||flags[4:1]||result!==expected[nout])$fatal(1,"residual mismatch beat=%0d",nout);
   $fdisplay(fd,"%0128h",result);nout<=nout+1;
  end
 end
 always @(negedge clk)if(rst)begin
  if(!av||at!=16'(na))begin av=na<BEATS&&(rng[0]||rng[2]);if(av)begin a=amem[na];at=16'(na);al=na==BEATS-1;end end
  if(!bv||bt!=16'(nb))begin bv=nb<BEATS&&(rng[1]||rng[3]);if(bv)begin b=bmem[nb];bt=16'(nb);bl=nb==BEATS-1;end end
  orr=rng[4]||rng[5];
 end
 initial begin string directory,apath,outpath;
  if(!$value$plusargs("VECTORS=%s",directory)||!$value$plusargs("ACTUAL_OPROJ=%s",apath)||!$value$plusargs("OUTPUT=%s",outpath))$fatal(1,"paths");
  $readmemh(apath,amem);$readmemh({directory,"/hidden.memh"},bmem);$readmemh({directory,"/expected.memh"},expected);
  fd=$fopen(outpath,"w");if(!fd)$fatal(1,"output open");
  repeat(4)@(negedge clk);rst=1;wait(nout==BEATS);@(negedge clk);
  if(na!=BEATS||nb!=BEATS)$fatal(1,"input count");$fclose(fd);
  $display("CAPTURED_RESIDUAL_FP32_PASS rows=1024 values=1572864 beats=%0d cycles=%0d actual_oproj_input=1",BEATS,cycles);$finish;
 end
 initial begin repeat(2000000)@(posedge clk);$fatal(1,"watchdog");end
endmodule
