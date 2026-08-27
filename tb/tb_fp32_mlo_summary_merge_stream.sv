`timescale 1ns/1ps
module tb_fp32_mlo_summary_merge_stream;
 logic clk=0,rst_n=0,hv,hr,bv,br,hov,hor,bov,bor,last_i,last_o;
 logic[31:0]ma,la,mb,lb,mo,lo;logic[127:0]oa,ob,oo;
 integer fd,rc,n;logic[31:0]a0,a1,a2,a3,b0,b1,b2,b3,em,el,e0,e1,e2,e3;
 always #5 clk=~clk;
 fp32_mlo_summary_merge_stream #(.LANES(4)) dut(.clk_i(clk),.rst_ni(rst_n),.header_valid_i(hv),.header_ready_o(hr),.ma_i(ma),.la_i(la),.mb_i(mb),.lb_i(lb),.beat_valid_i(bv),.beat_ready_o(br),.oa_i(oa),.ob_i(ob),.beat_last_i(last_i),.header_valid_o(hov),.header_ready_i(hor),.m_o(mo),.l_o(lo),.beat_valid_o(bov),.beat_ready_i(bor),.o_o(oo),.beat_last_o(last_o));
 initial begin hv=0;bv=0;hor=0;bor=0;last_i=0;n=0;fd=$fopen("tests/vectors/fp32_mlo_merge_vectors.txt","r");if(!fd)$fatal(1,"open");repeat(4)@(posedge clk);rst_n=1;
  while(!$feof(fd))begin rc=$fscanf(fd,"%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\n",ma,la,mb,lb,a0,a1,a2,a3,b0,b1,b2,b3,em,el,e0,e1,e2,e3);if(rc==18)begin oa={a3,a2,a1,a0};ob={b3,b2,b1,b0};@(negedge clk);hv=1;do @(posedge clk);while(!hr);@(negedge clk);hv=0;do @(posedge clk);while(!hov);if(mo!==em||lo!==el)$fatal(1,"header %0d",n);repeat(n%3)@(posedge clk);@(negedge clk);hor=1;@(posedge clk);@(negedge clk);hor=0;bv=1;last_i=1;do @(posedge clk);while(!br);@(negedge clk);bv=0;last_i=0;do @(posedge clk);while(!bov);if(oo!=={e3,e2,e1,e0}||!last_o)$fatal(1,"beat %0d",n);repeat(n%5)@(posedge clk);@(negedge clk);bor=1;@(posedge clk);@(negedge clk);bor=0;n=n+1;end end
  if(n!=132)$fatal(1,"count %0d",n);$display("BLOCK128_MLO_VECTOR_PASS cases=%0d",n);$finish;end
 initial begin repeat(500000)@(posedge clk);$fatal(1,"timeout");end
endmodule
