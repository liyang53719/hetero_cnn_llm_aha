// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module bf16_outer_product_array_control5_rev8b_b_candidate (
  input logic clk_i,rst_ni,in_valid_i,
  output logic in_ready_o,out_valid_o,
  input logic out_ready_i,
  output logic input_write_o,pre_write_o,mul_write_o,post_write_o,output_write_o,
  output logic [31:0] accepted_steps_o,completed_steps_o
);
  logic input_valid_q,pre_valid_q,mul_valid_q,post_valid_q,output_valid_q;
  logic input_ready,pre_ready,mul_ready,post_ready,output_ready;
  assign output_ready=!output_valid_q||out_ready_i;
  assign post_ready=!post_valid_q||output_ready;
  assign mul_ready=!mul_valid_q||post_ready;
  assign pre_ready=!pre_valid_q||mul_ready;
  assign input_ready=!input_valid_q||pre_ready;
  assign in_ready_o=input_ready;
  assign out_valid_o=output_valid_q;
  assign input_write_o=input_ready&&in_valid_i;
  assign pre_write_o=pre_ready&&input_valid_q;
  assign mul_write_o=mul_ready&&pre_valid_q;
  assign post_write_o=post_ready&&mul_valid_q;
  assign output_write_o=output_ready&&post_valid_q;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin
      input_valid_q<=0;pre_valid_q<=0;mul_valid_q<=0;post_valid_q<=0;output_valid_q<=0;
      accepted_steps_o<='0;completed_steps_o<='0;
    end else begin
      if(in_valid_i&&in_ready_o)accepted_steps_o<=accepted_steps_o+1'b1;
      if(out_valid_o&&out_ready_i)completed_steps_o<=completed_steps_o+1'b1;
      if(output_ready)output_valid_q<=post_valid_q;
      if(post_ready)post_valid_q<=mul_valid_q;
      if(mul_ready)mul_valid_q<=pre_valid_q;
      if(pre_ready)pre_valid_q<=input_valid_q;
      if(input_ready)input_valid_q<=in_valid_i;
    end
  end
endmodule
