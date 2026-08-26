// SPDX-License-Identifier: Apache-2.0
// Independent logical ROWSxCOLS BF16-input, FP32-accumulator outer-product tile.
`timescale 1ns/1ps
module bf16_outer_product_array #(
  parameter integer ROWS=16,parameter integer COLS=32,
  localparam integer LANES=ROWS*COLS
)(
  input logic clk_i,input logic rst_ni,
  input logic in_valid_i,output logic in_ready_o,
  input logic[ROWS*16-1:0]a_i,input logic[COLS*16-1:0]b_i,
  input logic[LANES*32-1:0]acc_i,
  output logic out_valid_o,input logic out_ready_i,
  output logic[LANES*32-1:0]acc_o,output logic[4:0]exception_flags_o,
  output logic[31:0]accepted_steps_o,output logic[31:0]completed_steps_o
);
  logic input_valid_q,output_valid_q,output_stage_ready;
  logic[ROWS*16-1:0]a_q;logic[COLS*16-1:0]b_q;logic[LANES*32-1:0]acc_q;
  logic[LANES*32-1:0]lane_result,output_q;logic[LANES*5-1:0]lane_flags;
  logic[4:0]flags_comb,flags_q;integer flag_lane;
  assign output_stage_ready=!output_valid_q||out_ready_i;
  assign in_ready_o=!input_valid_q||output_stage_ready;
  assign out_valid_o=output_valid_q;assign acc_o=output_q;assign exception_flags_o=flags_q;
  always_comb begin flags_comb=0;for(flag_lane=0;flag_lane<LANES;flag_lane++)
    flags_comb|=lane_flags[flag_lane*5 +:5];end
  genvar row,col;
  generate for(row=0;row<ROWS;row++)begin:g_row for(col=0;col<COLS;col++)begin:g_col
    localparam integer LANE=row*COLS+col;
    HeteroBF16FmaLane u_fma(.clock(clk_i),.reset(!rst_ni),
      .io_a(a_q[row*16 +:16]),.io_b(b_q[col*16 +:16]),
      .io_c(acc_q[LANE*32 +:32]),.io_out(lane_result[LANE*32 +:32]),
      .io_exceptionFlags(lane_flags[LANE*5 +:5]));
  end end endgenerate
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin input_valid_q<=0;output_valid_q<=0;a_q<=0;b_q<=0;acc_q<=0;
      output_q<=0;flags_q<=0;accepted_steps_o<=0;completed_steps_o<=0;
    end else begin
      if(output_valid_q&&out_ready_i)completed_steps_o<=completed_steps_o+1'b1;
      if(output_stage_ready)begin output_valid_q<=input_valid_q;
        if(input_valid_q)begin output_q<=lane_result;flags_q<=flags_comb;end
      end
      if(in_ready_o)begin input_valid_q<=in_valid_i;
        if(in_valid_i)begin a_q<=a_i;b_q<=b_i;acc_q<=acc_i;accepted_steps_o<=accepted_steps_o+1'b1;end
      end
    end
  end
endmodule
