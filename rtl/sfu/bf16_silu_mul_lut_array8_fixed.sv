// SPDX-License-Identifier: Apache-2.0
module bf16_silu_mul_lut_array8_fixed(
 input logic clk_i,rst_ni,in_valid_i,output logic in_ready_o,input logic[127:0]gate_bf16_i,up_bf16_i,
 input logic[11:0]tag_i,input logic last_i,output logic out_valid_o,input logic out_ready_i,
 output logic[127:0]result_bf16_o,output logic[11:0]tag_o,output logic last_o,output logic[4:0]exception_flags_o);
 logic[7:0]lane_in_ready,lane_out_valid,lane_last;logic[95:0]lane_tag;logic[39:0]lane_flags;
 genvar lane;generate for(lane=0;lane<8;lane++)begin:g
  bf16_silu_mul_lut_lane unit(.clk_i,.rst_ni,.in_valid_i(in_valid_i&&(&lane_in_ready)),.in_ready_o(lane_in_ready[lane]),.gate_bf16_i(gate_bf16_i[lane*16+:16]),.up_bf16_i(up_bf16_i[lane*16+:16]),.tag_i,.last_i,.out_valid_o(lane_out_valid[lane]),.out_ready_i(out_ready_i&&(&lane_out_valid)),.result_bf16_o(result_bf16_o[lane*16+:16]),.tag_o(lane_tag[lane*12+:12]),.last_o(lane_last[lane]),.exception_flags_o(lane_flags[lane*5+:5]));
 end endgenerate
 assign in_ready_o=&lane_in_ready;assign out_valid_o=&lane_out_valid;assign tag_o=lane_tag[11:0];assign last_o=lane_last[0];
 always_comb begin exception_flags_o=0;for(int i=0;i<8;i++)exception_flags_o|=lane_flags[i*5+:5];end
endmodule
