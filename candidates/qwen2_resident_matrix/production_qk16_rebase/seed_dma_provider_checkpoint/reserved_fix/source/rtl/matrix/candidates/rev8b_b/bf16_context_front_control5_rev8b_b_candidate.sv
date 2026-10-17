// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_context_front_control5_rev8b_b_candidate #(
  parameter bit ENABLE_ACCUMULATOR_SEED=1'b0
)(
  // Optional raw FP32 accumulator restore; absent from the default Chisel ABI.
  input logic seed_begin_valid_i,
  output logic seed_begin_ready_o,
  input logic [2:0] seed_context_i,
  input logic [31:0] seed_group_tag_i,seed_group_sequence_i,seed_source_generation_i,
  input logic seed_beat_valid_i,
  output logic seed_beat_ready_o,
  input logic [4:0] seed_cluster_i,
  input logic [511:0] seed_data_i,
  input logic seed_commit_valid_i,
  output logic seed_commit_ready_o,
  input logic seed_abort_i,
  output logic seed_ack_valid_o,
  input logic seed_ack_ready_i,
  output logic [2:0] seed_ack_context_o,
  output logic [31:0] seed_ack_group_tag_o,seed_ack_group_sequence_o,seed_ack_source_generation_o,
  output logic seed_ack_error_o,seed_reset_required_o,
  output logic seed_block_o,seed_hold_o,seed_reserve_o,seed_write_o,seed_commit_o,seed_invalidate_o,
  output logic [2:0] seed_bank_context_o,
  input logic clk_i,rst_ni,in_valid_i,
  output logic in_ready_o,
  input logic [2:0] context_i,
  input logic clear_i,last_i,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic [2:0] context_o,
  output logic last_o,
  output logic [4:0] busy_o,accumulator_valid_o,
  output logic [31:0] accepted_steps_o,completed_steps_o,
  output logic protocol_error_o,
  output logic input_write_o,pre_write_o,mul_write_o,post_write_o,output_write_o,
  output logic [2:0] issue_context_o,
  output logic issue_clear_o,
  output logic [2:0] early_commit_context_o,output_context_o,
  output logic completion_pop_o
);
  logic array_in_valid,array_in_ready,array_out_valid,array_out_ready;
  logic completion_fire_unused;
  logic [2:0] completion_context_unused;
  logic [31:0] array_accepted_unused,array_completed_unused;
  logic scheduler_error;
  logic [2:0] tag_output_context_unused;
  bf16_context_scheduler5_rev8b_b_candidate #(
    .ENABLE_ACCUMULATOR_SEED(ENABLE_ACCUMULATOR_SEED)) scheduler(
    .seed_block_i(seed_block_o),.seed_reserve_i(seed_reserve_o),
    .seed_commit_i(seed_commit_o),.seed_invalidate_i(seed_invalidate_o),
    .seed_context_i(seed_bank_context_o),
    .clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(in_valid_i),.in_ready_o(in_ready_o),
    .context_i(context_i),.clear_i(clear_i),.last_i(last_i),.out_valid_o(out_valid_o),
    .out_ready_i(out_ready_i),.context_o(context_o),.last_o(last_o),
    .array_in_valid_o(array_in_valid),.array_in_ready_i(array_in_ready),
    .array_out_valid_i(array_out_valid),.array_out_ready_o(array_out_ready),
    .issue_context_o(issue_context_o),.issue_clear_o(issue_clear_o),
    .completion_fire_o(completion_fire_unused),.completion_context_o(completion_context_unused),
    .busy_o(busy_o),.accumulator_valid_o(accumulator_valid_o),
    .accepted_steps_o(accepted_steps_o),.completed_steps_o(completed_steps_o),
    .protocol_error_o(scheduler_error));
  bf16_outer_product_array_control5_rev8b_b_candidate array_control(
    .clk_i(clk_i),.rst_ni(rst_ni),.in_valid_i(array_in_valid),.in_ready_o(array_in_ready),
    .out_valid_o(array_out_valid),.out_ready_i(array_out_ready),
    .input_write_o(input_write_o),.pre_write_o(pre_write_o),.mul_write_o(mul_write_o),
    .post_write_o(post_write_o),.output_write_o(output_write_o),
    .accepted_steps_o(array_accepted_unused),.completed_steps_o(array_completed_unused));
  bf16_context_tag_pipeline5_rev8b_b_candidate tags(
    .clk_i(clk_i),.rst_ni(rst_ni),.input_write_i(input_write_o),.pre_write_i(pre_write_o),
    .mul_write_i(mul_write_o),.post_write_i(post_write_o),.output_write_i(output_write_o),
    .issue_context_i(issue_context_o),.early_commit_context_o(early_commit_context_o),
    .output_context_o(tag_output_context_unused));
  assign output_context_o=context_o;
  assign completion_pop_o=out_valid_o&&out_ready_i;
  assign protocol_error_o=scheduler_error||seed_reset_required_o;

  generate if(ENABLE_ACCUMULATOR_SEED)begin:g_seed
    // 109 flip-flops: identity99, beat count6, reserved/ACK/error/poison4.
    // There is no seed payload storage and no new accumulator or arithmetic.
    logic [31:0] group_tag_q,group_sequence_q,source_generation_q;
    logic [2:0] context_q;
    logic [5:0] beat_count_q;
    logic reserved_q,ack_valid_q,ack_error_q,poison_q;
    logic quiescent,begin_quiescent,identity_matches,finite_data,begin_fire,beat_fire,commit_fire;
    logic legal_begin,legal_beat,legal_commit,fault;
    assign quiescent=(busy_o==5'b0)&&!out_valid_o&&!array_out_valid&&
      !input_write_o&&!pre_write_o&&!mul_write_o&&!post_write_o&&!output_write_o;
    // BEGIN valid already blocks this cycle's arithmetic issue in the scheduler.
    // Readiness observes retained work only; full quiescent still guards faults.
    assign begin_quiescent=(busy_o==5'b0)&&!out_valid_o&&!array_out_valid&&
      !pre_write_o&&!mul_write_o&&!post_write_o&&!output_write_o;
    assign identity_matches=seed_context_i==context_q&&seed_group_tag_i==group_tag_q&&
      seed_group_sequence_i==group_sequence_q&&seed_source_generation_i==source_generation_q;
    always_comb begin
      finite_data=1'b1;
      for(integer lane_index=0;lane_index<16;lane_index++)
        finite_data=finite_data&&(seed_data_i[lane_index*32+23+:8]!=8'hff);
    end
    // Block a same-cycle first arithmetic issue already on begin.valid.
    assign seed_block_o=reserved_q||ack_valid_q||poison_q||seed_abort_i||
      seed_begin_valid_i||seed_beat_valid_i||seed_commit_valid_i;
    // Admission blocking must not freeze an already accepted FMA. Only a
    // successful, genuinely quiescent reservation holds the datapath/FIFOs.
    assign seed_hold_o=reserved_q||ack_valid_q;
    assign seed_begin_ready_o=!reserved_q&&!ack_valid_q&&!poison_q&&!seed_abort_i&&begin_quiescent;
    assign seed_beat_ready_o=reserved_q&&!ack_valid_q&&!poison_q&&!seed_abort_i&&begin_quiescent;
    assign seed_commit_ready_o=reserved_q&&!ack_valid_q&&!poison_q&&!seed_abort_i&&begin_quiescent;
    assign begin_fire=seed_begin_valid_i&&seed_begin_ready_o;
    assign beat_fire=seed_beat_valid_i&&seed_beat_ready_o;
    assign commit_fire=seed_commit_valid_i&&seed_commit_ready_o;
    assign legal_begin=seed_context_i<5&&!seed_beat_valid_i&&!seed_commit_valid_i;
    assign legal_beat=identity_matches&&beat_count_q<32&&
      seed_cluster_i==beat_count_q[4:0]&&finite_data&&!seed_commit_valid_i&&!seed_begin_valid_i;
    assign legal_commit=identity_matches&&beat_count_q==32&&
      !seed_beat_valid_i&&!seed_begin_valid_i;
    assign fault=seed_abort_i||(reserved_q&&!quiescent)||(seed_begin_valid_i&&!quiescent)||
      (begin_fire&&!legal_begin)||(beat_fire&&!legal_beat)||(commit_fire&&!legal_commit)||
      (seed_begin_valid_i&&(reserved_q||ack_valid_q))||
      ((seed_beat_valid_i||seed_commit_valid_i)&&(!reserved_q||ack_valid_q));
    assign seed_reserve_o=begin_fire&&legal_begin&&!fault;
    assign seed_write_o=beat_fire&&legal_beat&&!fault;
    assign seed_commit_o=commit_fire&&legal_commit&&!fault;
    // Remember context after ACK consumption so a later service invalidate
    // still removes its bank validity. Any poison requires coordinated reset.
    assign seed_invalidate_o=fault||poison_q;
    assign seed_bank_context_o=seed_reserve_o?seed_context_i:context_q;
    assign seed_ack_valid_o=ack_valid_q;
    assign seed_ack_context_o=context_q;
    assign seed_ack_group_tag_o=group_tag_q;
    assign seed_ack_group_sequence_o=group_sequence_q;
    assign seed_ack_source_generation_o=source_generation_q;
    assign seed_ack_error_o=ack_error_q;
    assign seed_reset_required_o=poison_q;
    always_ff @(posedge clk_i or negedge rst_ni)begin
      if(!rst_ni)begin
        group_tag_q<='0;group_sequence_q<='0;source_generation_q<='0;context_q<='0;
        beat_count_q<='0;reserved_q<=0;ack_valid_q<=0;ack_error_q<=0;poison_q<=0;
      end else begin
        if(begin_fire)begin
          group_tag_q<=seed_group_tag_i;group_sequence_q<=seed_group_sequence_i;
          source_generation_q<=seed_source_generation_i;context_q<=seed_context_i;
          beat_count_q<='0;reserved_q<=legal_begin;ack_error_q<=0;
        end
        if(seed_write_o)beat_count_q<=beat_count_q+1'b1;
        // This register can only assert AFTER the commit edge and its bank
        // valid writes. Hold the identity and error stable under backpressure.
        if(commit_fire)begin ack_valid_q<=1'b1;ack_error_q<=!legal_commit||fault;end
        if(ack_valid_q&&seed_ack_ready_i)begin
          ack_valid_q<=1'b0;
          if(!poison_q&&!fault)reserved_q<=1'b0;
        end
        // Abort/late transport can never make a partially written bank reusable.
        // A held success ACK remains immutable; resetRequired dominates it.
        if(fault)poison_q<=1'b1;
      end
    end
  end else begin:g_no_seed
    assign seed_begin_ready_o=0;assign seed_beat_ready_o=0;assign seed_commit_ready_o=0;
    assign seed_ack_valid_o=0;assign seed_ack_context_o='0;assign seed_ack_group_tag_o='0;
    assign seed_ack_group_sequence_o='0;assign seed_ack_source_generation_o='0;
    assign seed_ack_error_o=0;assign seed_reset_required_o=0;assign seed_block_o=0;assign seed_hold_o=0;
    assign seed_reserve_o=0;assign seed_write_o=0;assign seed_commit_o=0;
    assign seed_invalidate_o=0;assign seed_bank_context_o='0;
  end endgenerate
endmodule
