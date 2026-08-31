// SPDX-License-Identifier: Apache-2.0
module fp32_block32_softmax_tile_store#(parameter integer LANES=8)(
 input logic clk_i,rst_ni,start_i,input logic load_valid_i,input logic[4:0]load_col_i,input logic[511:0]load_scores_i,input logic[15:0]load_mask_i,
 input logic[6:0]exp_read_group_i,output logic[LANES*32-1:0]exp_scores_o,exp_max_o,input logic[LANES-1:0]exp_write_valid_i,input logic[LANES*7-1:0]exp_write_groups_i,input logic[LANES*32-1:0]exp_weights_i,
 input logic[2:0]reduce_level_i,input logic[8:0]reduce_read_base_i,output logic[LANES*32-1:0]reduce_x_o,reduce_y_o,input logic reduce_write_valid_i,input logic[2:0]reduce_write_level_i,input logic[8:0]reduce_write_base_i,input logic[LANES*32-1:0]reduce_results_i,
 input logic[4:0]output_col_i,output logic[511:0]m_o,l_o,weights_o
);
 logic[31:0]bank_exp_score[0:15],bank_max[0:15],bank_l[0:15],bank_weight[0:15];logic[LANES*32-1:0]bank_reduce_x[0:15],bank_reduce_y[0:15];logic[15:0]bank_exp_we;logic[4:0]bank_exp_wcol[0:15];logic[31:0]bank_exp_wdata[0:15];logic[LANES-1:0]bank_reduce_we[0:15];logic[LANES*4-1:0]reduce_cols,reduce_write_cols[0:15];logic[LANES*32-1:0]bank_reduce_wdata[0:15];
 genvar g;generate for(g=0;g<16;g++)begin:g_bank
  fp32_block32_softmax_row_bank bank(.clk_i,.rst_ni,.start_i,.load_valid_i,.load_col_i,.load_score_i(load_scores_i[g*32+:32]),.load_mask_i(load_mask_i[g]),.exp_read_col_i(LANES==8?exp_read_group_i[5:1]:exp_read_group_i[6:2]),.exp_score_o(bank_exp_score[g]),.max_o(bank_max[g]),.exp_write_valid_i(bank_exp_we[g]),.exp_write_col_i(bank_exp_wcol[g]),.exp_weight_i(bank_exp_wdata[g]),.reduce_level_i,.reduce_cols_i(reduce_cols),.reduce_x_o(bank_reduce_x[g]),.reduce_y_o(bank_reduce_y[g]),.reduce_write_valid_i(bank_reduce_we[g]),.reduce_write_cols_i(reduce_write_cols[g]),.reduce_results_i(bank_reduce_wdata[g]),.output_col_i,.l_o(bank_l[g]),.weight_o(bank_weight[g]));
 end endgenerate
 always_comb begin:controls
  integer op,row,col;
  bank_exp_we='0;reduce_cols=0;for(integer r=0;r<16;r++)begin bank_exp_wcol[r]=0;bank_exp_wdata[r]=0;bank_reduce_we[r]=0;reduce_write_cols[r]=0;bank_reduce_wdata[r]=0;end
  for(integer k=0;k<LANES;k++)begin
   if(LANES==8)begin row=(exp_write_groups_i[k*7]*8)+k;bank_exp_wcol[row]=exp_write_groups_i[k*7+1+:5];end else begin row=(exp_write_groups_i[k*7+:2]*4)+k;bank_exp_wcol[row]=exp_write_groups_i[k*7+2+:5];end bank_exp_we[row]=exp_write_valid_i[k];bank_exp_wdata[row]=exp_weights_i[k*32+:32];
   op=reduce_read_base_i+k;case(reduce_level_i)0:col=op&15;1:col=op&7;2:col=op&3;3:col=op&1;default:col=0;endcase reduce_cols[k*4+:4]=col;
   op=reduce_write_base_i+k;case(reduce_write_level_i)0:begin row=op>>4;col=op&15;end 1:begin row=op>>3;col=op&7;end 2:begin row=op>>2;col=op&3;end 3:begin row=op>>1;col=op&1;end default:begin row=op;col=0;end endcase bank_reduce_we[row][k]=reduce_write_valid_i;reduce_write_cols[row][k*4+:4]=col;bank_reduce_wdata[row][k*32+:32]=reduce_results_i[k*32+:32];
  end
 end
 always_comb begin:outputs
  integer op,row;
  exp_scores_o=0;exp_max_o=0;reduce_x_o=0;reduce_y_o=0;for(integer r=0;r<16;r++)begin m_o[r*32+:32]=bank_max[r];l_o[r*32+:32]=bank_l[r];weights_o[r*32+:32]=bank_weight[r];end
  for(integer k=0;k<LANES;k++)begin if(LANES==8)row=(exp_read_group_i[0]*8)+k;else row=(exp_read_group_i[1:0]*4)+k;exp_scores_o[k*32+:32]=bank_exp_score[row];exp_max_o[k*32+:32]=bank_max[row];op=reduce_read_base_i+k;case(reduce_level_i)0:row=op>>4;1:row=op>>3;2:row=op>>2;3:row=op>>1;default:row=op;endcase reduce_x_o[k*32+:32]=bank_reduce_x[row][k*32+:32];reduce_y_o[k*32+:32]=bank_reduce_y[row][k*32+:32];end
 end
endmodule
