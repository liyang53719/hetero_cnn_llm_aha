`timescale 1ns/1ps
module tb_l5_revision8b_b_lane_gate_compare;
  localparam integer TARGET=120032;
  logic clk,rst_n,input_write,pre_write,mul_write,post_write,output_write,issue_clear,output_pop;
  logic[15:0]a,b;logic[2:0]issue_context,early_context;
  logic[31:0]out;logic[4:0]flags,bank_valid;logic[31:0]lfsr;integer cycles,fd;reg[1023:0]trace_path;
  always #0.5 clk=~clk;
  bf16_context_fma_pipeline_lane5_rev8b_b_candidate dut(
    .clk_i(clk),.rst_ni(rst_n),.input_write_i(input_write),.pre_write_i(pre_write),.mul_write_i(mul_write),
    .post_write_i(post_write),.output_write_i(output_write),.a_i(a),.b_i(b),.issue_context_i(issue_context),
    .issue_clear_i(issue_clear),.early_commit_context_i(early_context),.output_pop_i(output_pop),
    .out_o(out),.flags_o(flags),.bank_valid_o(bank_valid));
  initial begin
    clk=0;rst_n=0;input_write=0;pre_write=0;mul_write=0;post_write=0;output_write=0;issue_clear=0;
    a=16'h3f80;b=16'h3f80;issue_context=0;early_context=0;output_pop=0;lfsr=32'h8bb5_1200;cycles=0;fd=0;
    if($value$plusargs("TRACE=%s",trace_path))begin fd=$fopen(trace_path,"w");if(!fd)$fatal(1,"trace open");end
    repeat(8)@(posedge clk);rst_n=1;
    repeat(TARGET)begin
      @(negedge clk);lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
      input_write=lfsr[0]||lfsr[3];pre_write=lfsr[1]||lfsr[4];mul_write=lfsr[2]||lfsr[5];
      post_write=lfsr[6]||lfsr[9];output_write=lfsr[7]||lfsr[10];issue_clear=lfsr[11];
      a=lfsr[15:0];b={lfsr[7:0],lfsr[23:16]};issue_context=lfsr%5;early_context=(lfsr>>3)%5;output_pop=lfsr[12];
      @(posedge clk);@(negedge clk);cycles=cycles+1;if(fd)$fwrite(fd,"%08x %02x %02x\n",out,flags,bank_valid);
    end
    if(fd)$fclose(fd);$display("REV8B_B_LANE_TRACE_PASS cycles=%0d",cycles);$finish;
  end
endmodule
