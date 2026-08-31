`timescale 1ns/1ps
module tb_l5_qwen2_full_model_trace_controller;
  logic clk=0,rst_n=0,start=0,busy,done,valid,ready,last;
  logic[1:0]op;logic[4:0]layer;logic[5:0]records;
  logic[63:0]cycles,macs,reads,writes,total_cycles,total_macs,total_reads,total_writes;
  logic[31:0]lfsr;integer accepted,block_count,norm_count,head_count,wall_cycles;
  always #0.5 clk=~clk;
  assign ready=lfsr[0]||lfsr[3];
  l5_qwen2_full_model_trace_controller dut(.clk_i(clk),.rst_ni(rst_n),.start_i(start),.busy_o(busy),.done_o(done),.trace_valid_o(valid),.trace_ready_i(ready),.trace_op_o(op),.trace_layer_o(layer),.trace_cycles_o(cycles),.trace_macs_o(macs),.trace_read_bytes_o(reads),.trace_write_bytes_o(writes),.trace_last_o(last),.records_o(records),.total_cycles_o(total_cycles),.total_macs_o(total_macs),.total_read_bytes_o(total_reads),.total_write_bytes_o(total_writes));
  always_ff@(posedge clk)begin
    if(!rst_n)begin lfsr<=32'h56f28a13;accepted<=0;block_count<=0;norm_count<=0;head_count<=0;wall_cycles<=0;end else begin
      lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};wall_cycles<=wall_cycles+1;
      if(valid&&ready)begin
        if(op==0)begin if(layer!==accepted[4:0]||cycles!=64'd113726399||macs!=64'd49527914496||reads!=64'd93585408||writes!=64'd1048576||last)$fatal(1,"block record");block_count<=block_count+1;end
        else if(op==1)begin if(accepted!=28||cycles!=64'd441||macs||reads||writes||last)$fatal(1,"norm record");norm_count<=norm_count+1;end
        else if(op==2)begin if(accepted!=29||cycles!=64'd7763930||macs!=64'd233373696||reads!=64'd466747392||writes!=64'd607744||!last)$fatal(1,"head record");head_count<=head_count+1;end
        else $fatal(1,"illegal op");accepted<=accepted+1;
      end
    end
  end
  initial begin
    repeat(6)@(posedge clk);rst_n=1;@(negedge clk);start=1;@(posedge clk);@(negedge clk);start=0;
    while(!done&&wall_cycles<1000)@(posedge clk);
    if(!done||busy||accepted!=30||block_count!=28||norm_count!=1||head_count!=1||records!=30)$fatal(1,"record accounting");
    if(total_cycles!=64'd3192103543||total_macs!=64'd1387014979584||total_reads!=64'd3087138816||total_writes!=64'd29967872)$fatal(1,"total accounting cycles=%0d macs=%0d read=%0d write=%0d",total_cycles,total_macs,total_reads,total_writes);
    $display("L5_QWEN2_FULL_MODEL_TRACE_PASS records=%0d blocks=%0d final_rmsnorm=1 last_token_lm_head=1 total_cycles=%0d total_macs=%0d ddr_read_bytes=%0d ddr_write_bytes=%0d tokens_per_second_milli=320791",records,block_count,total_cycles,total_macs,total_reads,total_writes);$finish;
  end
endmodule
