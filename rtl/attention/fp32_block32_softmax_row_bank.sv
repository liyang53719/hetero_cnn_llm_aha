// SPDX-License-Identifier: Apache-2.0
module fp32_block32_softmax_row_bank(
 input logic clk_i,rst_ni,start_i,input logic load_valid_i,input logic[4:0]load_col_i,input logic[31:0]load_score_i,input logic load_mask_i,
 input logic[4:0]exp_read_col_i,output logic[31:0]exp_score_o,max_o,input logic exp_write_valid_i,input logic[4:0]exp_write_col_i,input logic[31:0]exp_weight_i,
 input logic[2:0]reduce_level_i,input logic[15:0]reduce_cols_i,output logic[127:0]reduce_x_o,reduce_y_o,input logic[3:0]reduce_write_valid_i,input logic[15:0]reduce_write_cols_i,input logic[127:0]reduce_results_i,
 input logic[4:0]output_col_i,output logic[31:0]l_o,weight_o
);
 logic[31:0]score_mem[0:31],weight_mem[0:31],reduce_mem[0:15],max_q;integer col;
 function automatic logic fp32_gt(input logic[31:0]a,input logic[31:0]b);if(a[31]!=b[31])fp32_gt=!a[31];else if(!a[31])fp32_gt=a[30:0]>b[30:0];else fp32_gt=a[30:0]<b[30:0];endfunction
 assign exp_score_o=score_mem[exp_read_col_i];assign max_o=max_q;assign l_o=reduce_mem[0];assign weight_o=weight_mem[output_col_i];
 always_comb begin for(integer k=0;k<4;k++)begin col=reduce_cols_i[k*4+:4];if(reduce_level_i==0)begin reduce_x_o[k*32+:32]=weight_mem[2*col];reduce_y_o[k*32+:32]=weight_mem[2*col+1];end else begin reduce_x_o[k*32+:32]=reduce_mem[2*col];reduce_y_o[k*32+:32]=reduce_mem[2*col+1];end end end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)max_q<=32'hff800000;else begin if(start_i)max_q<=32'hff800000;if(load_valid_i)begin score_mem[load_col_i]<=load_mask_i?32'hff800000:load_score_i;if(!load_mask_i&&(max_q==32'hff800000||fp32_gt(load_score_i,max_q)))max_q<=load_score_i;end if(exp_write_valid_i)weight_mem[exp_write_col_i]<=exp_weight_i;for(integer k=0;k<4;k++)if(reduce_write_valid_i[k])reduce_mem[reduce_write_cols_i[k*4+:4]]<=reduce_results_i[k*32+:32];end end
endmodule
