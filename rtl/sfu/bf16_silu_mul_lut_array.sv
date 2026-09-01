// SPDX-License-Identifier: Apache-2.0
module bf16_silu_mul_lut_array#(parameter integer LANES=1,parameter integer TAG_W=12)(input logic clk_i,rst_ni,in_valid_i,output logic in_ready_o,input logic[LANES*16-1:0]gate_bf16_i,up_bf16_i,input logic[TAG_W-1:0]tag_i,input logic last_i,output logic out_valid_o,input logic out_ready_i,output logic[LANES*16-1:0]result_bf16_o,output logic[TAG_W-1:0]tag_o,output logic last_o,output logic[4:0]exception_flags_o);
 logic[LANES-1:0]lane_in_ready,lane_out_valid;logic[LANES*TAG_W-1:0]lane_tag;logic[LANES-1:0]lane_last;logic[LANES*5-1:0]lane_flags;genvar lane;
 generate for(lane=0;lane<LANES;lane=lane+1)begin:g_lane bf16_silu_mul_lut_lane#(.TAG_W(TAG_W))unit(.clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(in_valid_i&&(&lane_in_ready)),.in_ready_o(lane_in_ready[lane]),.gate_bf16_i(gate_bf16_i[lane*16+:16]),.up_bf16_i(up_bf16_i[lane*16+:16]),.tag_i(tag_i),.last_i(last_i),.out_valid_o(lane_out_valid[lane]),.out_ready_i(out_ready_i&&(&lane_out_valid)),.result_bf16_o(result_bf16_o[lane*16+:16]),.tag_o(lane_tag[lane*TAG_W+:TAG_W]),.last_o(lane_last[lane]),.exception_flags_o(lane_flags[lane*5+:5]));end endgenerate
 assign in_ready_o=&lane_in_ready;assign out_valid_o=&lane_out_valid;assign tag_o=lane_tag[0+:TAG_W];assign last_o=lane_last[0];integer index;always_comb begin exception_flags_o=0;for(index=0;index<LANES;index=index+1)exception_flags_o|=lane_flags[index*5+:5];end
`ifndef SYNTHESIS
 initial assert((LANES==1)||(LANES==2)||(LANES==8));always_ff@(posedge clk_i)if(rst_ni&&(|lane_out_valid))begin assert(&lane_out_valid);for(integer i=1;i<LANES;i=i+1)begin assert(lane_tag[i*TAG_W+:TAG_W]==lane_tag[0+:TAG_W]);assert(lane_last[i]==lane_last[0]);end end
`endif
endmodule
