`timescale 1ns/1ps
// Directed numerical controller integration: real 512-lane Revision8B-B FMA.
// Not a complete attention operator or full-model performance measurement.
module tb_attention_matrix_tile_numerical;
 logic clk_i=0;always #1 clk_i=~clk_i;
 logic rst_ni=0,req_valid_i=0,req_ready_o,req_pv_i=0;
 logic[19:0]req_task_i=0;logic[4:0]req_rows_i=3;logic[5:0]req_keys_i=7;
 logic[8:0]req_head_dim_i=128;
 logic operand_valid_o,operand_ready_i,operand_rsp_valid_i=0,operand_rsp_ready_o,operand_error_i=0;
 logic[7:0]operand_index_o;logic[2:0]operand_group_o;logic operand_low_term_o,operand_pv_o;
 logic[255:0]operand_a_i=0,matrix_a_o;logic[511:0]operand_b_i={32{16'h4000}},matrix_b_o;
 logic matrix_valid_o,matrix_ready_i,matrix_clear_o,matrix_last_o;
 logic[2:0]matrix_context_o,matrix_rsp_context_i;
 logic matrix_rsp_valid_i,matrix_rsp_ready_o,matrix_rsp_last_i,matrix_error_i;
 logic[16383:0]matrix_acc_i,result_data_o;
 logic result_valid_o,result_ready_i,result_pv_o;logic[2:0]result_group_o;
 logic done_valid_o,done_ready_i=0,done_pv_o;logic[19:0]done_task_o;logic[7:0]done_status_o;
 logic[63:0]accepted_steps_o,tile_math_macs_o,active_bf16_macs_o;
 logic[4:0]flags,busy,acc_valid;logic[31:0]accepted,completed;
 logic[31:0]seed=32'h923bb882;integer results=0,comparisons=0;
 logic[31:0]expected;
 attention_matrix_tile_sequencer dut(.*);
 bf16_outer_product_context_array_rev8b_b_candidate matrix(
  .clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(matrix_valid_o),.in_ready_o(matrix_ready_i),
  .context_i(matrix_context_o),.clear_i(matrix_clear_o),.last_i(matrix_last_o),
  .a_i(matrix_a_o),.b_i(matrix_b_o),.out_valid_o(matrix_rsp_valid_i),.out_ready_i(matrix_rsp_ready_o),
  .context_o(matrix_rsp_context_i),.last_o(matrix_rsp_last_i),.acc_o(matrix_acc_i),
  .exception_flags_o(flags),.busy_o(busy),.accumulator_valid_o(acc_valid),
  .accepted_steps_o(accepted),.completed_steps_o(completed),.protocol_error_o(matrix_error_i));
 assign operand_ready_i=!operand_rsp_valid_i&&seed[0];
 assign result_ready_i=seed[2]&&seed[4];
 always @(posedge clk_i)if(rst_ni)begin
  seed<={seed[30:0],seed[31]^seed[21]^seed[1]^seed[0]};
  if(operand_valid_o&&operand_ready_i)begin
   operand_rsp_valid_i<=1;
   operand_a_i<={16{(operand_pv_o&&operand_low_term_o)?16'hbb00:16'h3f80}};
  end
  if(operand_rsp_valid_i&&operand_rsp_ready_o)operand_rsp_valid_i<=0;
  if(matrix_rsp_valid_i&&matrix_rsp_ready_o&&flags!=0)$fatal(1,"unexpected FMA flags %h",flags);
  if(result_valid_o&&result_ready_i)begin
   if(result_pv_o!=req_pv_i||(req_pv_i&&result_group_o!=results))$fatal(1,"result identity");
   for(int row=0;row<16;row++)for(int col=0;col<32;col++)begin
    expected=0;
    if(row<3&&(req_pv_i||col<7))expected=req_pv_i?32'h415f9000:(req_head_dim_i==128?32'h43800000:32'h44000000);
    if(result_data_o[(row*32+col)*32+:32]!==expected)
     $fatal(1,"FMA mismatch pv=%0d dim=%0d group=%0d row=%0d col=%0d got=%h expected=%h",req_pv_i,req_head_dim_i,result_group_o,row,col,result_data_o[(row*32+col)*32+:32],expected);
    comparisons++;
   end
   results++;
  end
 end
 task tick;@(posedge clk_i);@(negedge clk_i);endtask
 initial begin
  repeat(4)tick();rst_ni=1;repeat(4)tick();
  for(int mode=0;mode<4;mode++)begin
   req_pv_i=1'(mode%2);req_head_dim_i=mode<2?128:256;req_task_i=20'(mode);results=0;
   req_valid_i=1;tick();req_valid_i=0;
   wait(done_valid_o);@(negedge clk_i);
   if(done_status_o||done_task_o!=mode||results!=(req_pv_i?req_head_dim_i/32:1)||
      accepted_steps_o!=(req_pv_i?2*req_head_dim_i:req_head_dim_i)||tile_math_macs_o!=21*req_head_dim_i)
    $fatal(1,"completion counters/status");
   done_ready_i=1;tick();done_ready_i=0;
  end
  if(comparisons!=7168)$fatal(1,"coverage");
  $display("ATTENTION_MATRIX_NUMERICAL_PASS comparisons=%0d head_dims=128,256 full_attention=false",comparisons);$finish;
 end
 initial begin repeat(100000)tick();$fatal(1,"watchdog");end
endmodule
