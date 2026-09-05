`timescale 1ns/1ps
module tb_matrix_memory_runtime_k;
 logic clk,rst=0,start=0;initial clk=0;always #0.625 clk=~clk;
 logic[15:0]depth;logic[63:0]ab=0,wb=64'h20000,ob=64'h40000;
 logic rv,rr,rsv,rsr,wv,wr,sv,sr,clear,last,ov,ol,done,cv,cr,ready,err,mor;
 logic[14:0]ra,wa;logic[511:0]rd,wd,b;logic[255:0]a;
 logic[63:0]be;logic[2:0]ctx,octx;logic[16383:0]acc;
 logic[4:0]flags;logic[15:0]tag;logic[7:0]pp,tp,status;
 logic[31:0]reads,writes,steps,lfsr;
 logic[511:0]mem[0:8191];logic pending;logic[511:0]pending_data;
 integer completions;longint unsigned cycles,begin_cycle;
 qwen2_shared_l2_matrix_tile16_payload payload(
  .clk_i(clk),.rst_ni(rst),.start_i(start),.depth_i(depth),
  .activation_local_i(ab),.weight_local_i(wb),.output_local_i(ob),
  .l2_rd_valid_o(rv),.l2_rd_ready_i(rr),.l2_rd_addr_o(ra),
  .l2_rsp_valid_i(rsv),.l2_rsp_ready_o(rsr),.l2_rsp_data_i(rd),
  .l2_wr_valid_o(wv),.l2_wr_ready_i(wr),.l2_wr_addr_o(wa),.l2_wr_data_o(wd),.l2_wr_be_o(be),
  .matrix_step_valid_o(sv),.matrix_step_ready_i(sr),.matrix_context_o(ctx),
  .matrix_clear_o(clear),.matrix_last_o(last),.matrix_a_o(a),.matrix_b_o(b),
  .matrix_out_valid_i(ov),.matrix_out_ready_o(mor),.matrix_out_last_i(ol),.matrix_acc_i(acc),
  .done_o(done),.read_beats_o(reads),.write_beats_o(writes),.matrix_steps_o(steps));
 operator_matrix_bf16_endpoint_v3 matrix(
  .clk_i(clk),.rst_ni(rst),.req_valid_i(start),.req_ready_o(ready),.req_opcode_i(8'h20),
  .req_tag_i(16'h1234),.req_parent_phase_i(8'd1),.req_terminal_phase_i(8'd2),
  .req_rows_i(16'd16),.req_columns_i(16'd32),.req_depth_i(depth),
  .step_valid_i(sv),.step_ready_o(sr),.step_context_i(ctx),.step_clear_i(clear),.step_last_i(last),
  .step_a_i(a),.step_b_i(b),.out_valid_o(ov),.out_ready_i(mor),.out_context_o(octx),
  .out_last_o(ol),.out_acc_o(acc),.exception_flags_o(flags),
  .completion_valid_o(cv),.completion_ready_i(1'b1),.completion_tag_o(tag),
  .completion_parent_phase_o(pp),.completion_terminal_phase_o(tp),
  .completion_status_o(status),.protocol_error_o(err));
 assign rr=!pending&&(lfsr[0]||lfsr[3]);assign rsv=pending;
 assign rd=pending_data;assign wr=lfsr[1]||lfsr[5];
 always @(posedge clk or negedge rst) if(!rst)begin
  cycles<=0;completions<=0;lfsr<=32'hdeaf1234;pending<=0;pending_data<=0;
 end else begin
  cycles<=cycles+1;lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
  if(rv&&rr)begin pending<=1;pending_data<=mem[ra];end
  if(rsv&&rsr)pending<=0;
  if(wv&&wr)begin if(be!='1)$fatal(1,"byte enables");mem[wa]<=wd;end
  if(cv)begin
   if(status||tag!=16'h1234||pp!=1||tp!=2)$fatal(1,"completion metadata");
   completions<=completions+1;
  end
  if(err)$fatal(1,"protocol");
 end
 task run_case(input integer k,input logic[15:0]expected,input integer count);
  @(negedge clk);depth=16'(k);ab=0;wb=64'h20000;ob=64'h40000;
  for(int i=0;i<k;i++)begin mem[i]={16{32'h00003f80}};
    // A is packed in the low 256 bits of each 512-bit beat.
    mem[i][255:0]={16{16'h3f80}};mem[2048+i]={32{16'h4000}};end
  for(int i=0;i<16;i++)mem[4096+i]='1;
  if(!ready)$fatal(1,"not ready");begin_cycle=cycles;start=1;
  @(posedge clk);@(negedge clk);start=0;
  // Descriptor snapshot: changes after acceptance must have no effect.
  ab=64'h70000;wb=64'h70000;ob=64'h70000;depth=1;
  wait(done);@(negedge clk);
  if(reads!=2*k||steps!=k||writes!=16||completions!=count)$fatal(1,"counts");
  for(int i=0;i<16;i++)for(int j=0;j<32;j++)
   if(mem[4096+i][j*16+:16]!=expected)$fatal(1,"payload k=%0d row=%0d col=%0d",k,i,j);
  $display("MEMORY_RUNTIME_K_CASE k=%0d cycles=%0d macs=%0d reads=%0d writes=%0d",k,cycles-begin_cycle,512*k,reads,writes);
  repeat(3)@(negedge clk);
 endtask
 initial begin
  depth=1;repeat(4)@(negedge clk);rst=1;
  run_case(1,16'h4000,1);run_case(4,16'h4100,2);
  run_case(17,16'h4208,3);run_case(1536,16'h4540,4);
  $display("MATRIX_MEMORY_RUNTIME_K_PASS cases=4 checked_bf16=2048 same_rtl=1");$finish;
 end
 initial begin repeat(100000)@(posedge clk);$fatal(1,"watchdog");end
endmodule
