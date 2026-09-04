`timescale 1ns/1ps
module tb_fp32_pwl_nonlinear_pipe;
 logic clk,rst_n;initial begin clk=0;rst_n=0;end always #1 clk=~clk;logic iv,ir,ov,orr;logic[7:0]variant;logic[31:0]x,y,expected;logic[4:0]flags;integer fd,rc,count,vread;logic[31:0]xread,eread;string line;
 fp32_pwl_nonlinear_pipe dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.variant_i(variant),.x_i(x),.out_valid_o(ov),.out_ready_i(orr),.y_o(y),.exception_flags_o(flags));
 initial begin repeat(500000)@(posedge clk);$fatal(1,"timeout");end
 initial begin iv=0;orr=0;variant=0;x=0;count=0;fd=$fopen("tests/vectors/fp32_pwl_nonlinear_vectors.txt","r");if(!fd)$fatal(1,"vectors");repeat(4)@(posedge clk);rst_n=1;while(!$feof(fd))begin line="";void'($fgets(line,fd));rc=$sscanf(line,"%d %h %h",vread,xread,eread);if(rc==3)begin @(negedge clk);variant=vread[7:0];x=xread;expected=eread;iv=1;do @(posedge clk);while(!ir);@(negedge clk);iv=0;wait(ov);if(y!==expected)$fatal(1,"mismatch count=%0d variant=%0d x=%h y=%h expected=%h",count,variant,x,y,expected);repeat(count%3)@(posedge clk);if(!ov||y!==expected)$fatal(1,"stall");orr=1;@(posedge clk);@(negedge clk);orr=0;count=count+1;end end $fclose(fd);if(count!=20000)$fatal(1,"count=%0d",count);$display("FP32_PWL_NONLINEAR_PIPE_PASS vectors=20000 variants=2");$finish;end
endmodule
