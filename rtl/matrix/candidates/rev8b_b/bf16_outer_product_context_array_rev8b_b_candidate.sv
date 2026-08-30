// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_outer_product_context_array_rev8b_b_candidate #(
  parameter integer ROWS=16,COLS=32,CONTEXTS=5,FIFO_DEPTH=8,
  localparam integer LANES=ROWS*COLS,CONTEXT_BITS=3,CONTROL_WIDTH=15
)(
  input logic clk_i,rst_ni,in_valid_i,
  output logic in_ready_o,
  input logic[CONTEXT_BITS-1:0]context_i,
  input logic clear_i,last_i,
  input logic[ROWS*16-1:0]a_i,
  input logic[COLS*16-1:0]b_i,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic[CONTEXT_BITS-1:0]context_o,
  output logic last_o,
  output logic[LANES*32-1:0]acc_o,
  output logic[4:0]exception_flags_o,
  output logic[CONTEXTS-1:0]busy_o,accumulator_valid_o,
  output logic[31:0]accepted_steps_o,completed_steps_o,
  output logic protocol_error_o
);
  logic input_write,pre_write,mul_write,post_write,output_write,issue_clear;
  logic[2:0]issue_context,early_commit_context,tag_output_context;
  logic[CONTROL_WIDTH-1:0]front_control_bundle;
  wire[32*CONTROL_WIDTH-1:0]cluster_control_bundle;
  logic[512*16-1:0]lane_a,lane_b;
  logic[512*32-1:0]lane_result;
  logic[512*5-1:0]lane_flags;
  logic[511:0]lane_rst_ni;
  generate
    if(ROWS==16&&COLS==32&&CONTEXTS==5&&FIFO_DEPTH==8)begin:g_production
      bf16_context_front_control5_rev8b_b_candidate front_control(
        .clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(in_valid_i),.in_ready_o(in_ready_o),
        .context_i(context_i),.clear_i(clear_i),.last_i(last_i),.out_valid_o(out_valid_o),
        .out_ready_i(out_ready_i),.context_o(context_o),.last_o(last_o),.busy_o(busy_o),
        .accumulator_valid_o(accumulator_valid_o),.accepted_steps_o(accepted_steps_o),
        .completed_steps_o(completed_steps_o),.protocol_error_o(protocol_error_o),
        .input_write_o(input_write),.pre_write_o(pre_write),.mul_write_o(mul_write),
        .post_write_o(post_write),.output_write_o(output_write),.issue_context_o(issue_context),
        .issue_clear_o(issue_clear),.early_commit_context_o(early_commit_context),
        .output_context_o(tag_output_context));
      assign front_control_bundle[0]=input_write;
      assign front_control_bundle[1]=pre_write;
      assign front_control_bundle[2]=mul_write;
      assign front_control_bundle[3]=post_write;
      assign front_control_bundle[4]=output_write;
      assign front_control_bundle[7:5]=issue_context;
      assign front_control_bundle[8]=issue_clear;
      assign front_control_bundle[11:9]=early_commit_context;
      assign front_control_bundle[14:12]=tag_output_context;
      bf16_front_to_cluster_broadcast32_rev8b_b_candidate broadcast32(
        .control_i(front_control_bundle),.cluster_control_o(cluster_control_bundle));
      bf16_operand_distribution512_rev8b_a_candidate operand_distribution(
        .a_i(a_i),.b_i(b_i),.lane_a_o(lane_a),.lane_b_o(lane_b));
      bf16_outer_product_array_glue512 glue(.rst_ni(rst_ni),.lane_flags_i(lane_flags),.lane_rst_ni_o(lane_rst_ni),.flags_o(exception_flags_o));
      for(genvar cluster=0;cluster<32;cluster++)begin:g_cluster
        localparam integer BASE=cluster*CONTROL_WIDTH;
        bf16_context_lane_cluster16_rev8b_b_candidate u_cluster(
          .clk_i(clk_i),.lane_rst_ni_i(lane_rst_ni[cluster*16+:16]),
          .input_write_i(cluster_control_bundle[BASE+0]),.pre_write_i(cluster_control_bundle[BASE+1]),
          .mul_write_i(cluster_control_bundle[BASE+2]),.post_write_i(cluster_control_bundle[BASE+3]),
          .output_write_i(cluster_control_bundle[BASE+4]),
          .lane_a_i(lane_a[cluster*16*16+:16*16]),.lane_b_i(lane_b[cluster*16*16+:16*16]),
          .issue_context_i(cluster_control_bundle[BASE+5+:3]),.issue_clear_i(cluster_control_bundle[BASE+8]),
          .early_commit_context_i(cluster_control_bundle[BASE+9+:3]),
          .output_context_i(cluster_control_bundle[BASE+12+:3]),
          .lane_out_o(lane_result[cluster*16*32+:16*32]),.lane_flags_o(lane_flags[cluster*16*5+:16*5]));
      end
      assign acc_o=lane_result;
    end else begin:g_unsupported
      initial $fatal(1,"Revision8B-B requires 16x32, five contexts, FIFO8");
      assign in_ready_o=0;assign out_valid_o=0;assign context_o='0;assign last_o=0;assign acc_o='0;
      assign exception_flags_o='0;assign busy_o='0;assign accumulator_valid_o='0;
      assign accepted_steps_o='0;assign completed_steps_o='0;assign protocol_error_o=1;
    end
  endgenerate
endmodule
