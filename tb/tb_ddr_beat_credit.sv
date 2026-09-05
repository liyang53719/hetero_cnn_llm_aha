`timescale 1ns/1ps
module tb_ddr_beat_credit;
 logic clk_i=0;always #0.625 clk_i=~clk_i;
 logic rst_ni=0,valid_i=1,ready=1,wa,ra,wf,rf;
 logic[63:0]wb,rb,ws,rs;logic[31:0]lfsr=32'h12345678;
 ddr_beat_credit #(.BYTES_PER_CYCLE(50)) w(.clk_i,.rst_ni,.valid_i,.fire_i(wf),.allow_o(wa),.bytes_o(wb),.throttled_cycles_o(ws));
 ddr_beat_credit #(.BYTES_PER_CYCLE(125)) r(.clk_i,.rst_ni,.valid_i,.fire_i(rf),.allow_o(ra),.bytes_o(rb),.throttled_cycles_o(rs));
 assign wf=valid_i&&ready&&wa;assign rf=valid_i&&ready&&ra;
 task tick;@(posedge clk_i);@(negedge clk_i);endtask
 initial begin
  tick();rst_ni=1;
  for(int i=1;i<=10000;i++)begin
   tick();if(wb>64'(i)*50||rb>64'(i)*125)$fatal(1,"prefix envelope");
  end
  if(wb<499872||wb>500000||rb!=9999*64||ws==0)$fatal(1,"saturated rates %0d/%0d",wb,rb);
  for(int i=0;i<10000;i++)begin
   lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};ready=lfsr[0];
   tick();if(wb>64'(10001+i)*50||rb>64'(10001+i)*125)$fatal(1,"backpressure envelope");
  end
  ready=0;repeat(8)tick();if(!wa||!ra)$fatal(1,"idle refill");
  rst_ni=0;tick();if(wb||rb||ws||rs||wa||ra)$fatal(1,"reset");
  $display("DDR_BEAT_CREDIT_PASS saturated_cycles=10000 random_cycles=10000 read_Bpc=125 write_Bpc=50 burst_bytes=128");$finish;
 end
endmodule
