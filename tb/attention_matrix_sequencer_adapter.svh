// Testbench tensor-memory adapter only. Matrix iteration is production RTL.
// Memory timing and SFU service remain TB-side: not full-model performance.
 logic am_req=0,am_ready,am_pv=0,am_fetch,am_fetch_ready,am_rsp=0,am_rsp_ready;
 logic[19:0]am_task=0,am_done_task;logic[4:0]am_rows=0;logic[5:0]am_keys=0;
 logic[7:0]am_index;logic[2:0]am_group,am_result_group;logic am_low,am_fetch_pv;
 logic[255:0]am_a=0;logic[511:0]am_b=0;
 logic am_result,am_result_ready,am_result_pv,am_done,am_done_pv;logic[7:0]am_status;
 logic[16383:0]am_data;logic[63:0]am_steps,am_math,am_active;
 integer am_qt=0,am_kt=0,am_qh=0,am_kh=0;
 attention_matrix_tile_sequencer matrix_sequencer(
  .clk_i(clk),.rst_ni(rst_n),.req_valid_i(am_req),.req_ready_o(am_ready),
  .req_pv_i(am_pv),.req_task_i(am_task),.req_rows_i(am_rows),.req_keys_i(am_keys),.req_head_dim_i(9'd128),
  .operand_valid_o(am_fetch),.operand_ready_i(am_fetch_ready),.operand_index_o(am_index),
  .operand_group_o(am_group),.operand_low_term_o(am_low),.operand_pv_o(am_fetch_pv),
  .operand_rsp_valid_i(am_rsp),.operand_rsp_ready_o(am_rsp_ready),.operand_error_i(1'b0),
  .operand_a_i(am_a),.operand_b_i(am_b),.matrix_valid_o(minv),.matrix_ready_i(minr),
  .matrix_context_o(mcontext_i),.matrix_clear_o(mclear),.matrix_last_o(mlast_i),.matrix_a_o(ma),.matrix_b_o(mb),
  .matrix_rsp_valid_i(moutv),.matrix_rsp_ready_o(moutr),.matrix_rsp_context_i(mcontext_o),
  .matrix_rsp_last_i(mlast_o),.matrix_error_i(merror),.matrix_acc_i(macc),
  .result_valid_o(am_result),.result_ready_i(am_result_ready),.result_pv_o(am_result_pv),
  .result_group_o(am_result_group),.result_data_o(am_data),.done_valid_o(am_done),.done_ready_i(1'b1),
  .done_task_o(am_done_task),.done_pv_o(am_done_pv),.done_status_o(am_status),
  .accepted_steps_o(am_steps),.tile_math_macs_o(am_math),.active_bf16_macs_o(am_active));
 assign am_fetch_ready=!am_rsp&&(lfsr[0]||lfsr[2]);
 assign am_result_ready=lfsr[3]||lfsr[5];
 always @(posedge clk)if(rst_n)begin
  if(am_fetch&&am_fetch_ready)begin
   am_rsp<=1;am_a<=0;am_b<=0;
   for(integer row=0;row<16;row++)if(row<am_rows)begin
    if(am_fetch_pv)am_a[row*16+:16]<=am_low?weight_lo_slot[am_task&1][row*32+am_index][31:16]:weight_hi_slot[am_task&1][row*32+am_index][31:16];
    else am_a[row*16+:16]<=qmem[qidx(am_qh,am_qt*16+row,am_index)];
   end
   for(integer col=0;col<32;col++)begin
    if(am_fetch_pv)begin if(am_kt*32+am_index<seq_len)am_b[col*16+:16]<=vmem[kidx(am_kh,am_kt*32+am_index,am_group*32+col)];end
    else if(am_kt*32+col<seq_len)am_b[col*16+:16]<=kmem[kidx(am_kh,am_kt*32+col,am_index)];
   end
  end
  if(am_rsp&&am_rsp_ready)am_rsp<=0;
  if(am_result&&am_result_ready)begin
   if(am_result_pv)begin
    for(integer row=0;row<16;row++)for(integer col=0;col<32;col++)
     tile_o[am_task&1][row*128+am_result_group*32+col]<=am_data[(row*32+col)*32+:32];
   end else for(integer lane=0;lane<512;lane++)score_slot[am_task&1][lane]<=am_data[lane*32+:32];
  end
 end
 task automatic run_matrix_tile(input logic pv,input integer task_id,qt,kt,qh,kh,rows);
  begin
   @(negedge clk);am_pv=pv;am_task=20'(task_id);am_qt=qt;am_kt=kt;am_qh=qh;am_kh=kh;
   am_rows=5'(rows);am_keys=6'((seq_len-kt*32)>=32?32:(seq_len-kt*32));am_req=1;
   do @(posedge clk);while(!am_ready);@(negedge clk);am_req=0;
   do @(posedge clk);while(!am_done);
   if(am_status||am_done_task!=task_id||am_done_pv!=pv||am_steps!=(pv?256:128))$fatal(1,"Matrix tile completion");
   @(negedge clk);
  end
 endtask
