// SPDX-License-Identifier: Apache-2.0
// L5.3 source-ready command controller for QK -> Block128 M/L/O -> PV.
// QK and PV share one Matrix port. Score/probability remain on chip.
module blocked_attention_stream_controller #(
  parameter integer SEQUENCE_W=16,
  parameter integer TASK_ID_W=20,
  parameter integer QUERY_TILE_W=7,
  parameter integer KV_TILE_W=10,
  parameter integer SCORE_FIFO_DEPTH=2,
  parameter integer PROB_FIFO_DEPTH=2,
  localparam integer SCORE_LEVEL_W=$clog2(SCORE_FIFO_DEPTH+1),
  localparam integer PROB_LEVEL_W=$clog2(PROB_FIFO_DEPTH+1),
  localparam integer META_W=64
)(
 input logic clk_i,rst_ni,start_i,input logic[SEQUENCE_W-1:0]sequence_tokens_i,output logic busy_o,done_o,
 output logic matrix_cmd_valid_o,input logic matrix_cmd_ready_i,output logic matrix_cmd_kind_o,
 output logic[TASK_ID_W-1:0]matrix_cmd_task_id_o,output logic[QUERY_TILE_W-1:0]matrix_cmd_query_tile_o,
 output logic[KV_TILE_W-1:0]matrix_cmd_kv_tile_o,output logic[3:0]matrix_cmd_q_head_o,output logic[1:0]matrix_cmd_kv_head_o,
 output logic[4:0]matrix_cmd_valid_rows_o,output logic matrix_cmd_close_block_o,matrix_cmd_merge_global_o,matrix_cmd_last_kv_o,
 input logic matrix_done_valid_i,output logic matrix_done_ready_o,input logic matrix_done_kind_i,input logic[TASK_ID_W-1:0]matrix_done_task_id_i,
 output logic sfu_cmd_valid_o,input logic sfu_cmd_ready_i,output logic[TASK_ID_W-1:0]sfu_cmd_task_id_o,
 output logic[QUERY_TILE_W-1:0]sfu_cmd_query_tile_o,output logic[KV_TILE_W-1:0]sfu_cmd_kv_tile_o,
 output logic[3:0]sfu_cmd_q_head_o,output logic[1:0]sfu_cmd_kv_head_o,output logic[4:0]sfu_cmd_valid_rows_o,
 output logic sfu_cmd_close_block_o,sfu_cmd_merge_global_o,sfu_cmd_last_kv_o,
 input logic sfu_done_valid_i,output logic sfu_done_ready_o,input logic[TASK_ID_W-1:0]sfu_done_task_id_i,
 output logic[31:0]qk_issued_o,qk_completed_o,sfu_completed_o,pv_completed_o,summary_merge_rows_o,
 output logic[SCORE_LEVEL_W-1:0]score_fifo_level_o,output logic[PROB_LEVEL_W-1:0]probability_fifo_level_o,output logic protocol_error_o
);
 localparam logic MATRIX_QK=1'b0,MATRIX_PV=1'b1;
 logic busy_q,done_q,protocol_error_q;logic[SEQUENCE_W-1:0]sequence_tokens_q;logic[QUERY_TILE_W-1:0]query_tile_q;logic[KV_TILE_W-1:0]kv_tile_q;logic[3:0]q_head_q;logic[TASK_ID_W-1:0]next_task_id_q;logic generator_done_q;
 logic matrix_busy_q,matrix_kind_q;logic[META_W-1:0]matrix_meta_q;logic matrix_offer_valid_q,matrix_offer_kind_q;logic[META_W-1:0]matrix_offer_meta_q;logic sfu_busy_q;logic[META_W-1:0]sfu_meta_q;
 logic[31:0]qk_issued_q,qk_completed_q,sfu_completed_q,pv_completed_q,summary_merge_rows_q;
 logic[META_W-1:0]score_in_data,score_out_data,probability_in_data,probability_out_data;logic score_in_valid,score_in_ready,score_out_valid,score_out_ready,probability_in_valid,probability_in_ready,probability_out_valid,probability_out_ready;logic[SCORE_LEVEL_W-1:0]score_level;logic[PROB_LEVEL_W-1:0]probability_level;
 logic[SEQUENCE_W:0]query_limit,query_base;logic[KV_TILE_W:0]kv_tiles_current;logic[QUERY_TILE_W-1:0]last_query_tile;logic[4:0]current_valid_rows;logic current_last_kv,current_close_block,current_merge_global;logic[META_W-1:0]current_qk_meta;logic choose_probability,all_drained;

 function automatic logic[META_W-1:0]pack_meta(input logic[TASK_ID_W-1:0]task_id,input logic[QUERY_TILE_W-1:0]query_tile,input logic[KV_TILE_W-1:0]kv_tile,input logic[3:0]q_head,input logic[1:0]kv_head,input logic[4:0]valid_rows,input logic close_block,input logic merge_global,input logic last_kv);
  logic[META_W-1:0]v;begin v='0;v[19:0]=task_id;v[26:20]=query_tile;v[36:27]=kv_tile;v[40:37]=q_head;v[42:41]=kv_head;v[47:43]=valid_rows;v[48]=close_block;v[49]=merge_global;v[50]=last_kv;pack_meta=v;end
 endfunction
 function automatic logic[TASK_ID_W-1:0]meta_task(input logic[META_W-1:0]v);meta_task=v[19:0];endfunction
 function automatic logic[QUERY_TILE_W-1:0]meta_qtile(input logic[META_W-1:0]v);meta_qtile=v[26:20];endfunction
 function automatic logic[KV_TILE_W-1:0]meta_ktile(input logic[META_W-1:0]v);meta_ktile=v[36:27];endfunction
 function automatic logic[3:0]meta_qhead(input logic[META_W-1:0]v);meta_qhead=v[40:37];endfunction
 function automatic logic[1:0]meta_kvhead(input logic[META_W-1:0]v);meta_kvhead=v[42:41];endfunction
 function automatic logic[4:0]meta_rows(input logic[META_W-1:0]v);meta_rows=v[47:43];endfunction

 rv_fifo#(.WIDTH(META_W),.DEPTH(SCORE_FIFO_DEPTH))score_fifo(.clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(score_in_valid),.in_ready_o(score_in_ready),.in_data_i(score_in_data),.out_valid_o(score_out_valid),.out_ready_i(score_out_ready),.out_data_o(score_out_data),.level_o(score_level));
 rv_fifo#(.WIDTH(META_W),.DEPTH(PROB_FIFO_DEPTH))probability_fifo(.clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(probability_in_valid),.in_ready_o(probability_in_ready),.in_data_i(probability_in_data),.out_valid_o(probability_out_valid),.out_ready_i(probability_out_ready),.out_data_o(probability_out_data),.level_o(probability_level));

 always_comb begin
  query_base=(SEQUENCE_W+1)'(query_tile_q)<<4;query_limit=((SEQUENCE_W+1)'(query_tile_q)+1'b1)<<4;if(query_limit>{1'b0,sequence_tokens_q})query_limit={1'b0,sequence_tokens_q};kv_tiles_current=(query_limit+31)>>5;last_query_tile=(sequence_tokens_q-1'b1)>>4;
  if({1'b0,sequence_tokens_q}-query_base>=16)current_valid_rows=5'd16;else current_valid_rows=5'({1'b0,sequence_tokens_q}-query_base);
  current_last_kv=({1'b0,kv_tile_q}+1'b1==kv_tiles_current);current_close_block=(kv_tile_q[1:0]==2'b11)||current_last_kv;current_merge_global=current_close_block&&(kv_tile_q>=4);
  current_qk_meta=pack_meta(next_task_id_q,query_tile_q,kv_tile_q,q_head_q,2'(q_head_q/6),current_valid_rows,current_close_block,current_merge_global,current_last_kv);
 end
 assign choose_probability=probability_out_valid&&((score_level>=SCORE_LEVEL_W'(SCORE_FIFO_DEPTH-1))||generator_done_q);
 assign matrix_cmd_valid_o=matrix_offer_valid_q;assign matrix_cmd_kind_o=matrix_offer_kind_q;assign matrix_cmd_task_id_o=meta_task(matrix_offer_meta_q);assign matrix_cmd_query_tile_o=meta_qtile(matrix_offer_meta_q);assign matrix_cmd_kv_tile_o=meta_ktile(matrix_offer_meta_q);assign matrix_cmd_q_head_o=meta_qhead(matrix_offer_meta_q);assign matrix_cmd_kv_head_o=meta_kvhead(matrix_offer_meta_q);assign matrix_cmd_valid_rows_o=meta_rows(matrix_offer_meta_q);assign matrix_cmd_close_block_o=matrix_offer_meta_q[48];assign matrix_cmd_merge_global_o=matrix_offer_meta_q[49];assign matrix_cmd_last_kv_o=matrix_offer_meta_q[50];
 assign probability_out_ready=matrix_offer_valid_q&&matrix_cmd_ready_i&&(matrix_offer_kind_q==MATRIX_PV);
 assign matrix_done_ready_o=matrix_busy_q&&((matrix_kind_q==MATRIX_PV)||score_in_ready);assign score_in_valid=matrix_done_valid_i&&matrix_done_ready_o&&(matrix_kind_q==MATRIX_QK);assign score_in_data=matrix_meta_q;
 assign sfu_cmd_valid_o=!sfu_busy_q&&score_out_valid;assign sfu_cmd_task_id_o=meta_task(score_out_data);assign sfu_cmd_query_tile_o=meta_qtile(score_out_data);assign sfu_cmd_kv_tile_o=meta_ktile(score_out_data);assign sfu_cmd_q_head_o=meta_qhead(score_out_data);assign sfu_cmd_kv_head_o=meta_kvhead(score_out_data);assign sfu_cmd_valid_rows_o=meta_rows(score_out_data);assign sfu_cmd_close_block_o=score_out_data[48];assign sfu_cmd_merge_global_o=score_out_data[49];assign sfu_cmd_last_kv_o=score_out_data[50];assign score_out_ready=sfu_cmd_valid_o&&sfu_cmd_ready_i;
 assign sfu_done_ready_o=sfu_busy_q&&probability_in_ready;assign probability_in_valid=sfu_done_valid_i&&sfu_done_ready_o;assign probability_in_data=sfu_meta_q;
 assign all_drained=generator_done_q&&!matrix_busy_q&&!matrix_offer_valid_q&&!sfu_busy_q&&(score_level=='0)&&(probability_level=='0)&&(pv_completed_q==qk_issued_q);
 assign busy_o=busy_q;assign done_o=done_q;assign protocol_error_o=protocol_error_q;assign qk_issued_o=qk_issued_q;assign qk_completed_o=qk_completed_q;assign sfu_completed_o=sfu_completed_q;assign pv_completed_o=pv_completed_q;assign summary_merge_rows_o=summary_merge_rows_q;assign score_fifo_level_o=score_level;assign probability_fifo_level_o=probability_level;

 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin busy_q<=0;done_q<=0;protocol_error_q<=0;sequence_tokens_q<='0;query_tile_q<='0;kv_tile_q<='0;q_head_q<='0;next_task_id_q<='0;generator_done_q<=1;matrix_busy_q<=0;matrix_kind_q<=MATRIX_QK;matrix_meta_q<='0;matrix_offer_valid_q<=0;matrix_offer_kind_q<=MATRIX_QK;matrix_offer_meta_q<='0;sfu_busy_q<=0;sfu_meta_q<='0;qk_issued_q<='0;qk_completed_q<='0;sfu_completed_q<='0;pv_completed_q<='0;summary_merge_rows_q<='0;end
  else begin done_q<=0;
   if(start_i&&!busy_q)begin if(sequence_tokens_i=='0)protocol_error_q<=1;else begin busy_q<=1;protocol_error_q<=0;sequence_tokens_q<=sequence_tokens_i;query_tile_q<='0;kv_tile_q<='0;q_head_q<='0;next_task_id_q<='0;generator_done_q<=0;matrix_busy_q<=0;matrix_offer_valid_q<=0;sfu_busy_q<=0;qk_issued_q<='0;qk_completed_q<='0;sfu_completed_q<='0;pv_completed_q<='0;summary_merge_rows_q<='0;end end
   if(busy_q&&!matrix_busy_q&&!matrix_offer_valid_q)begin if(choose_probability)begin matrix_offer_valid_q<=1;matrix_offer_kind_q<=MATRIX_PV;matrix_offer_meta_q<=probability_out_data;end else if(!generator_done_q&&(score_level<SCORE_LEVEL_W'(SCORE_FIFO_DEPTH)))begin matrix_offer_valid_q<=1;matrix_offer_kind_q<=MATRIX_QK;matrix_offer_meta_q<=current_qk_meta;end else if(probability_out_valid)begin matrix_offer_valid_q<=1;matrix_offer_kind_q<=MATRIX_PV;matrix_offer_meta_q<=probability_out_data;end end
   if(matrix_offer_valid_q&&matrix_cmd_ready_i)begin matrix_offer_valid_q<=0;matrix_busy_q<=1;matrix_kind_q<=matrix_offer_kind_q;matrix_meta_q<=matrix_offer_meta_q;if(matrix_offer_kind_q==MATRIX_QK)begin qk_issued_q<=qk_issued_q+1;next_task_id_q<=next_task_id_q+1;if(current_last_kv)begin kv_tile_q<='0;if(q_head_q==11)begin q_head_q<='0;if(query_tile_q==last_query_tile)generator_done_q<=1;else query_tile_q<=query_tile_q+1;end else q_head_q<=q_head_q+1;end else kv_tile_q<=kv_tile_q+1;end end
   if(matrix_done_valid_i&&matrix_done_ready_o)begin if((matrix_done_kind_i!=matrix_kind_q)||(matrix_done_task_id_i!=meta_task(matrix_meta_q)))protocol_error_q<=1;matrix_busy_q<=0;if(matrix_kind_q==MATRIX_QK)qk_completed_q<=qk_completed_q+1;else pv_completed_q<=pv_completed_q+1;end
   if(sfu_cmd_valid_o&&sfu_cmd_ready_i)begin sfu_busy_q<=1;sfu_meta_q<=score_out_data;end
   if(sfu_done_valid_i&&sfu_done_ready_o)begin if(sfu_done_task_id_i!=meta_task(sfu_meta_q))protocol_error_q<=1;sfu_busy_q<=0;sfu_completed_q<=sfu_completed_q+1;if(sfu_meta_q[49])summary_merge_rows_q<=summary_merge_rows_q+meta_rows(sfu_meta_q);end
   if(busy_q&&all_drained)begin busy_q<=0;done_q<=1;end
  end
 end
`ifndef SYNTHESIS
 initial begin assert(TASK_ID_W==20);assert(QUERY_TILE_W==7);assert(KV_TILE_W==10);assert(SCORE_FIFO_DEPTH>=2);assert(PROB_FIFO_DEPTH>=2);end
`endif
endmodule
