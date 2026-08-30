// SPDX-License-Identifier: Apache-2.0
// Five-stage candidate: a cluster-local input register cuts distribution from
// HardFloat Pre. Generated HardFloat modules are instantiated unchanged.
`timescale 1ns/1ps
module bf16_context_fma_pipeline_lane5_rev8b_b_candidate (
  input logic clk_i,rst_ni,input_write_i,pre_write_i,mul_write_i,post_write_i,output_write_i,
  input logic [15:0] a_i,b_i,
  input logic [2:0] issue_context_i,
  input logic issue_clear_i,
  input logic [2:0] early_commit_context_i,output_context_i,
  output logic [31:0] out_o,
  output logic [4:0] flags_o,bank_valid_o
);
  logic [31:0] accumulator_bank[0:4];
  logic [4:0] bank_valid_q;
  logic [15:0] input_a_q,input_b_q;
  logic [2:0] input_context_q;
  logic input_clear_q;
  logic [31:0] issue_accumulator;
  logic [23:0] pre_a,pre_b,pre_a_q,pre_b_q;
  logic [47:0] pre_c,pre_c_q;
  logic [53:0] pre_meta,pre_meta_q,mul_meta_q;
  logic [48:0] mul_result,mul_result_q;
  logic [40:0] post_raw,post_raw_q;
  logic post_invalid,post_invalid_q;
  logic [31:0] round_out;
  logic [4:0] round_flags,flags_q;

  always_comb begin
    if(input_clear_q)issue_accumulator='0;
    else if(input_context_q<5&&bank_valid_q[input_context_q])issue_accumulator=accumulator_bank[input_context_q];
    else issue_accumulator='0;
  end
  HeteroBF16FmaPre u_pre(.io_a(input_a_q),.io_b(input_b_q),.io_c(issue_accumulator),.io_mulAddA(pre_a),.io_mulAddB(pre_b),.io_mulAddC(pre_c),.io_meta(pre_meta));
  HeteroBF16FmaMul u_mul(.io_mulAddA(pre_a_q),.io_mulAddB(pre_b_q),.io_mulAddC(pre_c_q),.io_mulAddResult(mul_result));
  HeteroBF16FmaPost u_post(.io_meta(mul_meta_q),.io_mulAddResult(mul_result_q),.io_raw(post_raw),.io_invalid(post_invalid));
  HeteroBF16FmaRound u_round(.io_raw(post_raw_q),.io_invalid(post_invalid_q),.io_out(round_out),.io_exceptionFlags(round_flags));
  assign out_o=(output_context_i<5&&bank_valid_q[output_context_i])?accumulator_bank[output_context_i]:'0;
  assign flags_o=flags_q;
  assign bank_valid_o=bank_valid_q;
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin
      input_a_q<='0;input_b_q<='0;input_context_q<='0;input_clear_q<=0;
      pre_a_q<='0;pre_b_q<='0;pre_c_q<='0;pre_meta_q<='0;mul_result_q<='0;mul_meta_q<='0;
      post_raw_q<='0;post_invalid_q<=0;bank_valid_q<='0;flags_q<='0;
    end else begin
      if(input_write_i)begin input_a_q<=a_i;input_b_q<=b_i;input_context_q<=issue_context_i;input_clear_q<=issue_clear_i;end
      if(pre_write_i)begin pre_a_q<=pre_a;pre_b_q<=pre_b;pre_c_q<=pre_c;pre_meta_q<=pre_meta;end
      if(mul_write_i)begin mul_result_q<=mul_result;mul_meta_q<=pre_meta_q;end
      if(post_write_i)begin post_raw_q<=post_raw;post_invalid_q<=post_invalid;end
      if(output_write_i)begin
        accumulator_bank[early_commit_context_i]<=round_out;
        bank_valid_q[early_commit_context_i]<=1'b1;
        flags_q<=round_flags;
      end
    end
  end
endmodule
