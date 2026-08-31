// SPDX-License-Identifier: Apache-2.0
// Reopened L5.5 candidate: one 16x32 score tile, four lockstep FP32 lanes.
// Scores are pre-scaled. Weights stay on chip and stream as 16 rows/beat.
`timescale 1ns/1ps
module fp32_block32_softmax_tile16_candidate(
 input logic clk_i,rst_ni,start_i,
 input logic score_valid_i,output logic score_ready_o,input logic[511:0]scores_i,input logic[15:0]mask_i,
 output logic summary_valid_o,input logic summary_ready_i,output logic[511:0]m_o,l_o,
 output logic weight_valid_o,input logic weight_ready_i,output logic[511:0]weights_o,output logic weight_last_o,
 output logic busy_o,output logic[4:0]exception_flags_o,output logic[31:0]accepted_scores_o,issued_exp_groups_o,completed_exp_groups_o,reduction_ops_o
);
 typedef enum logic[2:0]{S_IDLE,S_LOAD,S_EXP,S_REDUCE,S_HEADER,S_OUTPUT}state_e;
 state_e state_q;
 logic[5:0]load_col_q,output_col_q;logic[7:0]exp_issue_q,exp_complete_q;logic[2:0]reduce_level_q;logic[8:0]reduce_issue_q,reduce_complete_q;logic[4:0]flags_q;
 logic[3:0]sub_iv,sub_ir,sub_ov,sub_or,mul_ir,mul_ov,mul_or,exp_ir,exp_ov,exp_or,add_iv,add_ir,add_ov,add_or;
 logic[31:0]sub_x[0:3],sub_y[0:3],sub_z[0:3],mul_z[0:3],exp_z[0:3],add_x[0:3],add_y[0:3],add_z[0:3];logic[4:0]sub_f[0:3],mul_f[0:3],add_f[0:3];logic[12:0]exp_f[0:3];
 logic exp_issue_fire,exp_input_fire,add_issue_fire,add_input_fire,add_complete_fire,exp_read_pending_q,reduce_read_pending_q;logic[3:0]exp_lane_fire;logic[2:0]exp_fire_count;logic[9:0]exp_weights_complete_q;logic[7:0]exp_lane_complete_q[0:3];logic[8:0]reduce_total,reduce_read_base;logic[6:0]exp_read_group;logic[27:0]store_exp_groups;logic[127:0]store_exp_scores,store_exp_max,store_exp_weights,store_reduce_x,store_reduce_y,store_reduce_results,exp_scores_q,exp_max_q,reduce_x_q,reduce_y_q;
 genvar g;generate for(g=0;g<4;g++)begin:g_pipe
  fp32_block32_softmax_tile_math_lane lane(.clk_i,.rst_ni,.sub_valid_i(sub_iv[g]),.sub_ready_o(sub_ir[g]),.sub_x_i(sub_x[g]),.sub_y_i(sub_y[g]),.sub_valid_o(sub_ov[g]),.sub_ready_i(sub_or[g]),.sub_z_o(sub_z[g]),.sub_flags_o(sub_f[g]),.scale_ready_o(mul_ir[g]),.scale_valid_o(mul_ov[g]),.scale_ready_i(mul_or[g]),.scale_z_o(mul_z[g]),.scale_flags_o(mul_f[g]),.exp_ready_o(exp_ir[g]),.exp_valid_o(exp_ov[g]),.exp_ready_i(exp_or[g]),.exp_z_o(exp_z[g]),.exp_flags_o(exp_f[g]),.add_valid_i(add_iv[g]),.add_ready_o(add_ir[g]),.add_x_i(add_x[g]),.add_y_i(add_y[g]),.add_valid_o(add_ov[g]),.add_ready_i(add_or[g]),.add_z_o(add_z[g]),.add_flags_o(add_f[g]));
 end endgenerate
 fp32_block32_softmax_tile_store store(.clk_i,.rst_ni,.start_i(start_i&&(state_q==S_IDLE)),.load_valid_i((state_q==S_LOAD)&&score_valid_i),.load_col_i(load_col_q[4:0]),.load_scores_i(scores_i),.load_mask_i(mask_i),.exp_read_group_i(exp_read_group),.exp_scores_o(store_exp_scores),.exp_max_o(store_exp_max),.exp_write_valid_i(exp_lane_fire),.exp_write_groups_i(store_exp_groups),.exp_weights_i(store_exp_weights),.reduce_level_i(reduce_level_q),.reduce_read_base_i(reduce_read_base),.reduce_x_o(store_reduce_x),.reduce_y_o(store_reduce_y),.reduce_write_valid_i(add_complete_fire),.reduce_write_base_i(reduce_complete_q),.reduce_results_i(store_reduce_results),.output_col_i(output_col_q[4:0]),.m_o,.l_o,.weights_o);
 always_comb begin:map_inputs
  integer exp_map,reduce_map;
  exp_map=exp_issue_q<128?exp_issue_q:127;reduce_map=reduce_issue_q<reduce_total?reduce_issue_q:reduce_total-4;exp_read_group=exp_map[6:0];reduce_read_base=reduce_map[8:0];
  for(integer k=0;k<4;k++)begin
   sub_x[k]=exp_scores_q[k*32+:32];sub_y[k]={~exp_max_q[k*32+31],exp_max_q[k*32+:31]};add_x[k]=reduce_x_q[k*32+:32];add_y[k]=reduce_y_q[k*32+:32];store_exp_weights[k*32+:32]=exp_z[k];store_exp_groups[k*7+:7]=exp_lane_complete_q[k][6:0];store_reduce_results[k*32+:32]=add_z[k];
  end
 end
 always_comb begin case(reduce_level_q)0:reduce_total=256;1:reduce_total=128;2:reduce_total=64;3:reduce_total=32;default:reduce_total=16;endcase end
 assign exp_input_fire=exp_read_pending_q&&(&sub_ir);assign exp_issue_fire=(state_q==S_EXP)&&(exp_issue_q<128)&&(!exp_read_pending_q||exp_input_fire);assign sub_iv={4{exp_read_pending_q}};assign sub_or={4{&mul_ir}};assign mul_or={4{&exp_ir}};assign exp_lane_fire=exp_ov&{4{state_q==S_EXP}};assign exp_or={4{state_q==S_EXP}};always_comb begin exp_fire_count=exp_lane_fire[0]+exp_lane_fire[1]+exp_lane_fire[2]+exp_lane_fire[3];end
 assign add_input_fire=reduce_read_pending_q&&(&add_ir);assign add_issue_fire=(state_q==S_REDUCE)&&(reduce_issue_q<reduce_total)&&(!reduce_read_pending_q||add_input_fire);assign add_iv={4{reduce_read_pending_q}};assign add_complete_fire=(state_q==S_REDUCE)&&(&add_ov);assign add_or={4{add_complete_fire}};
 assign score_ready_o=state_q==S_LOAD;assign summary_valid_o=state_q==S_HEADER;assign weight_valid_o=state_q==S_OUTPUT;assign weight_last_o=output_col_q==31;assign busy_o=state_q!=S_IDLE;assign exception_flags_o=flags_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin state_q<=S_IDLE;load_col_q<=0;output_col_q<=0;exp_issue_q<=0;exp_complete_q<=0;reduce_level_q<=0;reduce_issue_q<=0;reduce_complete_q<=0;flags_q<=0;accepted_scores_o<=0;issued_exp_groups_o<=0;completed_exp_groups_o<=0;reduction_ops_o<=0;exp_read_pending_q<=0;reduce_read_pending_q<=0;exp_scores_q<=0;exp_max_q<=0;reduce_x_q<=0;reduce_y_q<=0;exp_weights_complete_q<=0;for(integer k=0;k<4;k++)exp_lane_complete_q[k]<=0;end
  else case(state_q)
   S_IDLE:if(start_i)begin state_q<=S_LOAD;load_col_q<=0;flags_q<=0;accepted_scores_o<=0;issued_exp_groups_o<=0;completed_exp_groups_o<=0;reduction_ops_o<=0;exp_read_pending_q<=0;reduce_read_pending_q<=0;end
   S_LOAD:if(score_valid_i)begin accepted_scores_o<=accepted_scores_o+16;if(load_col_q==31)begin state_q<=S_EXP;exp_issue_q<=0;exp_complete_q<=0;exp_read_pending_q<=0;exp_weights_complete_q<=0;for(integer k=0;k<4;k++)exp_lane_complete_q[k]<=0;end else load_col_q<=load_col_q+1'b1;end
   S_EXP:begin
    if(exp_issue_fire)begin exp_scores_q<=store_exp_scores;exp_max_q<=store_exp_max;exp_read_pending_q<=1;exp_issue_q<=exp_issue_q+1'b1;issued_exp_groups_o<=issued_exp_groups_o+1;end else if(exp_input_fire)exp_read_pending_q<=0;
    if(|exp_lane_fire)begin for(integer k=0;k<4;k++)if(exp_lane_fire[k])exp_lane_complete_q[k]<=exp_lane_complete_q[k]+1'b1;flags_q<=flags_q|(exp_lane_fire[0]?exp_f[0][4:0]:0)|(exp_lane_fire[1]?exp_f[1][4:0]:0)|(exp_lane_fire[2]?exp_f[2][4:0]:0)|(exp_lane_fire[3]?exp_f[3][4:0]:0);exp_weights_complete_q<=exp_weights_complete_q+exp_fire_count;completed_exp_groups_o<=(exp_weights_complete_q+exp_fire_count)>>2;if(exp_weights_complete_q+exp_fire_count==512)begin state_q<=S_REDUCE;reduce_level_q<=0;reduce_issue_q<=0;reduce_complete_q<=0;reduce_read_pending_q<=0;end end
   end
   S_REDUCE:begin
    if(add_issue_fire)begin reduce_x_q<=store_reduce_x;reduce_y_q<=store_reduce_y;reduce_read_pending_q<=1;reduce_issue_q<=reduce_issue_q+4;end else if(add_input_fire)reduce_read_pending_q<=0;
    if(add_complete_fire)begin flags_q<=flags_q|add_f[0]|add_f[1]|add_f[2]|add_f[3];reduce_complete_q<=reduce_complete_q+4;reduction_ops_o<=reduction_ops_o+4;if(reduce_complete_q+4==reduce_total)begin reduce_read_pending_q<=0;if(reduce_level_q==4)state_q<=S_HEADER;else begin reduce_level_q<=reduce_level_q+1'b1;reduce_issue_q<=0;reduce_complete_q<=0;end end end
   end
   S_HEADER:if(summary_ready_i)begin output_col_q<=0;state_q<=S_OUTPUT;end
   S_OUTPUT:if(weight_ready_i)begin if(output_col_q==31)state_q<=S_IDLE;else output_col_q<=output_col_q+1'b1;end
   default:state_q<=S_IDLE;
  endcase
 end
endmodule
