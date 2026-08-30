// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_context_tag_pipeline5_rev8b_b_candidate (
  input logic clk_i,rst_ni,input_write_i,pre_write_i,mul_write_i,post_write_i,output_write_i,
  input logic [2:0] issue_context_i,
  output logic [2:0] early_commit_context_o,output_context_o
);
  logic [2:0] input_context_q,pre_context_q,mul_context_q,post_context_q,output_context_q;
  assign early_commit_context_o=post_context_q;
  assign output_context_o=output_context_q;
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin
      input_context_q<='0;pre_context_q<='0;mul_context_q<='0;post_context_q<='0;output_context_q<='0;
    end else begin
      if(output_write_i)output_context_q<=post_context_q;
      if(post_write_i)post_context_q<=mul_context_q;
      if(mul_write_i)mul_context_q<=pre_context_q;
      if(pre_write_i)pre_context_q<=input_context_q;
      if(input_write_i)input_context_q<=issue_context_i;
    end
  end
endmodule
