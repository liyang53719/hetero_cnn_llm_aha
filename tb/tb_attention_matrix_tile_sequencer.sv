`timescale 1ns/1ps
module tb_attention_matrix_tile_sequencer;
 logic clk_i=0;always #1 clk_i=~clk_i;
 logic rst_ni=0,req_valid_i=0,req_ready_o,req_pv_i=0;logic[19:0]req_task_i=17;logic[4:0]req_rows_i=3;
 logic[5:0]req_keys_i=7;
 logic[8:0]req_head_dim_i=128;
 logic operand_valid_o,operand_ready_i=1,operand_rsp_valid_i=0,operand_rsp_ready_o,operand_error_i=0;
 logic[7:0]operand_index_o;logic[2:0]operand_group_o;logic operand_low_term_o,operand_pv_o;
 logic[255:0]operand_a_i={16{16'h3f80}},matrix_a_o;logic[511:0]operand_b_i={32{16'h4000}},matrix_b_o;
 logic matrix_valid_o,matrix_ready_i=1,matrix_clear_o,matrix_last_o;
 logic[2:0]matrix_context_o,matrix_rsp_context_i;logic matrix_rsp_valid_i=0,matrix_rsp_ready_o,matrix_rsp_last_i,matrix_error_i=0;
 logic[16383:0]matrix_acc_i=0,result_data_o;
 logic result_valid_o,result_ready_i=0,result_pv_o;logic[2:0]result_group_o;
 logic done_valid_o,done_ready_i=0,done_pv_o;logic[19:0]done_task_o;logic[7:0]done_status_o;
 logic[63:0]accepted_steps_o,tile_math_macs_o,active_bf16_macs_o;
 logic held_valid=0;logic[16383:0]held_data;
 integer count,results,delay=0;logic[31:0]seed=32'h891238ab;
 logic corrupt_context=0;
 attention_matrix_tile_sequencer dut(.*);
 always @(posedge clk_i)if(rst_ni)begin
  if(held_valid&&(!result_valid_o||result_data_o!==held_data))$fatal(1,"result stability");
  held_valid<=result_valid_o&&!result_ready_i;held_data<=result_data_o;
 end
 always @(posedge clk_i)if(rst_ni)begin
  seed<={seed[30:0],seed[31]^seed[21]^seed[1]^seed[0]};
  if(operand_valid_o&&operand_ready_i)operand_rsp_valid_i<=1;
  if(operand_rsp_valid_i&&operand_rsp_ready_o)operand_rsp_valid_i<=0;
  if(matrix_valid_o&&matrix_ready_i)begin
   if(req_pv_i&&operand_index_o>=7)begin
    if(matrix_a_o||matrix_b_o)$fatal(1,"masked key");
   end else begin
    if(matrix_a_o[255:48]!=0||matrix_a_o[47:0]!={3{16'h3f80}})$fatal(1,"row mask");
    if(req_pv_i)begin if(matrix_b_o!=operand_b_i)$fatal(1,"V operand");end
    else if(matrix_b_o[511:112]!=0||matrix_b_o[111:0]!={7{16'h4000}})$fatal(1,"K mask");
   end
   if(!req_pv_i)begin
    if(operand_index_o!=count||matrix_context_o!=4||matrix_clear_o!=(count==0)||matrix_last_o!=(count==req_head_dim_i-1))$fatal(1,"QK order");
   end else begin
    if(operand_index_o!=(count/4)%32||operand_group_o!=(count/256)*4+count%4||operand_low_term_o!=((count%256)>=128)||
       matrix_context_o!=count%4||matrix_clear_o!=((count%256)<4)||matrix_last_o!=((count%256)>=252))$fatal(1,"PV order %0d",count);
   end
   count<=count+1;matrix_rsp_context_i<=corrupt_context?3'd7:matrix_context_o;matrix_rsp_last_i<=matrix_last_o;
   delay<=5;matrix_acc_i<=16384'(count+1);
  end
  if(delay>0)begin delay<=delay-1;if(delay==1)matrix_rsp_valid_i<=1;end
  if(matrix_rsp_valid_i&&matrix_rsp_ready_o)matrix_rsp_valid_i<=0;
  if(result_valid_o&&result_ready_i)begin
   if(result_data_o!==16384'(req_pv_i?(results/4)*256+253+results%4:req_head_dim_i)||result_pv_o!=req_pv_i||
      (req_pv_i&&result_group_o!=results))$fatal(1,"result order");
   results<=results+1;
  end
 end
 always @(negedge clk_i)begin operand_ready_i=seed[0]||seed[2];matrix_ready_i=seed[1]||seed[4];result_ready_i=seed[3]&&seed[5];end
 task tick;@(posedge clk_i);@(negedge clk_i);endtask
 initial begin
  tick();rst_ni=1;
  for(int mode=0;mode<4;mode++)begin
   req_pv_i=1'(mode%2);req_head_dim_i=mode<2?128:256;count=0;results=0;req_valid_i=1;tick();req_valid_i=0;
   wait(done_valid_o);@(negedge clk_i);
   if(done_status_o||done_task_o!=17||done_pv_o!=req_pv_i||count!=(req_pv_i?2*req_head_dim_i:req_head_dim_i)||
      results!=(req_pv_i?req_head_dim_i/32:1)||accepted_steps_o!=count||tile_math_macs_o!=21*req_head_dim_i||active_bf16_macs_o!=(req_pv_i?42:21)*req_head_dim_i)$fatal(1,"totals");
   repeat(3)tick();if(!done_valid_o)$fatal(1,"completion hold");
   done_ready_i=1;tick();done_ready_i=0;
  end
  req_rows_i=0;req_valid_i=1;tick();req_valid_i=0;
  if(!done_valid_o||done_status_o!=5||operand_valid_o||matrix_valid_o)$fatal(1,"illegal rows");
  done_ready_i=1;tick();done_ready_i=0;
  req_rows_i=3;req_pv_i=0;req_head_dim_i=128;count=0;operand_error_i=1;
  req_valid_i=1;tick();req_valid_i=0;wait(done_valid_o);@(negedge clk_i);
  if(done_status_o!=3||count!=0)$fatal(1,"operand fetch error");
  done_ready_i=1;tick();done_ready_i=0;operand_error_i=0;
  corrupt_context=1;req_valid_i=1;tick();req_valid_i=0;
  wait(done_valid_o);@(negedge clk_i);
  if(done_status_o!=7||count!=1)$fatal(1,"context mismatch");
  done_ready_i=1;tick();done_ready_i=0;
  req_valid_i=1;repeat(4)begin tick();if(req_ready_o||operand_valid_o||matrix_valid_o)$fatal(1,"fault lock");end
  $display("ATTENTION_MATRIX_TILE_SEQUENCER_PASS head_dims=128,256 qk_steps=128,256 pv_steps=256,512 numerical_datapath=not_in_this_test");$finish;
 end
 initial begin repeat(20000)tick();$fatal(1,"watchdog");end
endmodule
