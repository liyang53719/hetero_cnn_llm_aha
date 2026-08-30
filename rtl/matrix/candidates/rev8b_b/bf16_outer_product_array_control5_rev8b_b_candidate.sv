// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_outer_product_array_control5_rev8b_b_candidate (
  input logic clk_i,rst_ni,in_valid_i,
  output logic in_ready_o,out_valid_o,
  input logic out_ready_i,
  output logic input_write_o,pre_write_o,mul_write_o,post_write_o,output_write_o,
  output logic [31:0] accepted_steps_o,completed_steps_o
);
  logic input_valid_q,pre_valid_q,mul_valid_q,post_valid_q;
  logic [3:0] completion_tokens_q;
  logic completion_push,completion_pop;
  assign in_ready_o=completion_tokens_q<8;
  assign out_valid_o=completion_tokens_q!=0;
  assign input_write_o=in_valid_i&&in_ready_o;
  assign pre_write_o=input_valid_q;
  assign mul_write_o=pre_valid_q;
  assign post_write_o=mul_valid_q;
  assign output_write_o=post_valid_q;
  assign completion_push=post_valid_q;
  assign completion_pop=out_valid_o&&out_ready_i;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin
      input_valid_q<=0;pre_valid_q<=0;mul_valid_q<=0;post_valid_q<=0;completion_tokens_q<='0;
      accepted_steps_o<='0;completed_steps_o<='0;
    end else begin
      if(in_valid_i&&in_ready_o)accepted_steps_o<=accepted_steps_o+1'b1;
      if(out_valid_o&&out_ready_i)completed_steps_o<=completed_steps_o+1'b1;
      post_valid_q<=mul_valid_q;
      mul_valid_q<=pre_valid_q;
      pre_valid_q<=input_valid_q;
      input_valid_q<=in_valid_i&&in_ready_o;
      case({completion_push,completion_pop})
        2'b10:completion_tokens_q<=completion_tokens_q+1'b1;
        2'b01:completion_tokens_q<=completion_tokens_q-1'b1;
        default:completion_tokens_q<=completion_tokens_q;
      endcase
    end
  end
endmodule
