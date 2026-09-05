// SPDX-License-Identifier: Apache-2.0
// Synthesizable form of the validated do_qk/do_pv Matrix task ordering.
// Operand fetching and probability hi/lo conversion belong to memory/SFU adapters.
// tile_math_macs excludes row/key tails and PV's second partial term, but NOT
// causal pair masking; full-model useful MACs require the parent's causal count.
module attention_matrix_tile_sequencer(
 input logic clk_i,rst_ni,req_valid_i,output logic req_ready_o,
 input logic req_pv_i,input logic[19:0]req_task_i,input logic[4:0]req_rows_i,input logic[5:0]req_keys_i,
 input logic[8:0]req_head_dim_i,
 output logic operand_valid_o,input logic operand_ready_i,
 output logic[7:0]operand_index_o,output logic[2:0]operand_group_o,
 output logic operand_low_term_o,operand_pv_o,
 input logic operand_rsp_valid_i,output logic operand_rsp_ready_o,input logic operand_error_i,
 input logic[255:0]operand_a_i,input logic[511:0]operand_b_i,
 output logic matrix_valid_o,input logic matrix_ready_i,
 output logic[2:0]matrix_context_o,output logic matrix_clear_o,matrix_last_o,
 output logic[255:0]matrix_a_o,output logic[511:0]matrix_b_o,
 input logic matrix_rsp_valid_i,output logic matrix_rsp_ready_o,input logic[2:0]matrix_rsp_context_i,
 input logic matrix_rsp_last_i,matrix_error_i,input logic[16383:0]matrix_acc_i,
 output logic result_valid_o,input logic result_ready_i,output logic result_pv_o,
 output logic[2:0]result_group_o,output logic[16383:0]result_data_o,
 output logic done_valid_o,input logic done_ready_i,output logic[19:0]done_task_o,
 output logic done_pv_o,output logic[7:0]done_status_o,
 output logic[63:0]accepted_steps_o,tile_math_macs_o,active_bf16_macs_o
);
 typedef enum logic[2:0]{IDLE,FETCH,FETCH_WAIT,ISSUE,RETURN_WAIT,RESULT,DONE}state_t;
 state_t state_q;logic pv_q,low_q,fault_q;
 logic[7:0]index_q;logic[2:0]group_q;logic[4:0]rows_q;logic[5:0]keys_q;logic[8:0]head_dim_q;
 logic[255:0]a_q;logic[511:0]b_q;
 logic final_term,final_task;
 assign final_term=pv_q?(low_q&&index_q==31):(9'(index_q)+1==head_dim_q);
 assign final_task=final_term&&(!pv_q||group_q==(head_dim_q==128?3:7));
 assign req_ready_o=state_q==IDLE&&!fault_q;
 assign operand_valid_o=state_q==FETCH;
 assign operand_rsp_ready_o=state_q==FETCH_WAIT;
 assign operand_index_o=index_q;assign operand_group_o=group_q;
 assign operand_low_term_o=low_q;assign operand_pv_o=pv_q;
 assign matrix_valid_o=state_q==ISSUE;
 assign matrix_context_o=pv_q?{1'b0,group_q[1:0]}:3'd4;
 assign matrix_clear_o=index_q==0&&!low_q;assign matrix_last_o=final_term;
 assign matrix_a_o=a_q;assign matrix_b_o=b_q;
 assign matrix_rsp_ready_o=state_q==RETURN_WAIT;
 assign result_valid_o=state_q==RESULT;assign result_pv_o=pv_q;assign result_group_o=group_q;
 assign done_valid_o=state_q==DONE;assign done_pv_o=pv_q;
 task automatic advance_step;
  if(!pv_q)index_q<=index_q+1;
  else if(group_q[1:0]!=3)group_q<=group_q+1;
  else begin group_q<={group_q[2],2'b00};if(index_q!=31)index_q<=index_q+1;else begin index_q<=0;low_q<=1;end end
 endtask
 always_ff @(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=IDLE;pv_q<=0;low_q<=0;fault_q<=0;index_q<=0;group_q<=0;rows_q<=0;keys_q<=0;head_dim_q<=0;
   a_q<=0;b_q<=0;result_data_o<=0;done_task_o<=0;done_status_o<=0;accepted_steps_o<=0;tile_math_macs_o<=0;active_bf16_macs_o<=0;end
  else if(matrix_error_i&&state_q!=IDLE&&state_q!=DONE)begin
   fault_q<=1;done_status_o<=7;
   if(state_q!=RESULT||result_ready_i)state_q<=DONE;
  end else case(state_q)
   IDLE:if(req_valid_i&&req_ready_o)begin
    pv_q<=req_pv_i;low_q<=0;index_q<=0;group_q<=0;rows_q<=req_rows_i;keys_q<=req_keys_i;head_dim_q<=req_head_dim_i;done_task_o<=req_task_i;
    accepted_steps_o<=0;tile_math_macs_o<=0;active_bf16_macs_o<=0;done_status_o<=0;
    if(req_rows_i==0||req_rows_i>16||req_keys_i==0||req_keys_i>32||(req_head_dim_i!=128&&req_head_dim_i!=256))begin done_status_o<=5;state_q<=DONE;end else state_q<=FETCH;
   end
   FETCH:if(operand_ready_i)state_q<=FETCH_WAIT;
   FETCH_WAIT:if(operand_rsp_valid_i)begin
    if(operand_error_i)begin done_status_o<=3;state_q<=DONE;end
    else begin
     a_q<=0;for(integer r=0;r<16;r++)if(r<rows_q&&(!pv_q||index_q<keys_q))a_q[r*16+:16]<=operand_a_i[r*16+:16];
     b_q<=0;for(integer c=0;c<32;c++)if(pv_q?(index_q<keys_q):(c<keys_q))b_q[c*16+:16]<=operand_b_i[c*16+:16];
     state_q<=ISSUE;
    end
   end
   ISSUE:if(matrix_ready_i)begin
    accepted_steps_o<=accepted_steps_o+1;
    if(!pv_q)begin
     tile_math_macs_o<=tile_math_macs_o+64'(rows_q)*keys_q;
     active_bf16_macs_o<=active_bf16_macs_o+64'(rows_q)*keys_q;
    end else if(index_q<keys_q)begin
     active_bf16_macs_o<=active_bf16_macs_o+64'(rows_q)*32;
     // Hi/lo are two physical partial products for one mathematical PV MAC.
     if(!low_q)tile_math_macs_o<=tile_math_macs_o+64'(rows_q)*32;
    end
    state_q<=RETURN_WAIT;
   end
   RETURN_WAIT:if(matrix_rsp_valid_i)begin
    if(matrix_rsp_context_i!=matrix_context_o||matrix_rsp_last_i!=matrix_last_o)begin
     fault_q<=1;done_status_o<=7;state_q<=DONE;
    end else if(final_term)begin result_data_o<=matrix_acc_i;state_q<=RESULT;end
    else begin advance_step();state_q<=FETCH;end
   end
   RESULT:if(result_ready_i)begin
    if(fault_q||final_task)state_q<=DONE;
    else if(pv_q&&group_q==3&&head_dim_q==256)begin
     // Second128-column bank reuses contexts0..3 after all first-bank results drain.
     group_q<=4;index_q<=0;low_q<=0;state_q<=FETCH;
    end else begin advance_step();state_q<=FETCH;end
   end
   DONE:if(done_ready_i)state_q<=IDLE;
   default:state_q<=IDLE;
  endcase
 end
endmodule
