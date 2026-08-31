// SPDX-License-Identifier: Apache-2.0
// Decompose one FP32 probability into BF16_hi + BF16_residual. Matrix PV runs
// both terms through the same BF16 array and accumulates in FP32.
`timescale 1ns/1ps
module fp32_probability_to_bf16_hilo(
  input logic clk_i,rst_ni,in_valid_i,output logic in_ready_o,input logic[31:0]weight_i,
  output logic out_valid_o,input logic out_ready_i,output logic[15:0]hi_o,lo_o,output logic[4:0]exception_flags_o
);
  logic[15:0]hi_comb;logic[31:0]hi_fp32,residual;logic sub_iv,sub_ir,sub_ov,sub_or,sub_user_unused;logic[4:0]sub_flags;
  logic meta_iv,meta_ir,meta_ov,meta_or;logic[15:0]meta_hi;logic[3:0]meta_level_unused;
  function automatic logic[15:0]to_bf16(input logic[31:0]value);logic[31:0]rounded;logic[15:0]result;begin if((value[30:23]==8'hff)&&(value[22:0]!=0))begin result=value[31:16];result[6]=1'b1;if(result[6:0]==0)result[0]=1'b1;to_bf16=result;end else begin rounded=value+32'h00007fff+value[16];to_bf16=rounded[31:16];end end endfunction
  assign hi_comb=to_bf16(weight_i);assign hi_fp32={hi_comb,16'b0};assign in_ready_o=sub_ir&&meta_ir;assign sub_iv=in_valid_i&&meta_ir;assign meta_iv=in_valid_i&&sub_ir;
  HeteroFP32AddPipeBit1 subtract(.clock(clk_i),.reset(!rst_ni),.io_inValid(sub_iv),.io_inReady(sub_ir),.io_x(weight_i),.io_y({~hi_fp32[31],hi_fp32[30:0]}),.io_userIn(1'b0),.io_outValid(sub_ov),.io_outReady(sub_or),.io_out(residual),.io_exceptionFlags(sub_flags),.io_userOut(sub_user_unused));
  rv_fifo#(.WIDTH(16),.DEPTH(8))meta(.clk_i,.rst_ni,.in_valid_i(meta_iv),.in_ready_o(meta_ir),.in_data_i(hi_comb),.out_valid_o(meta_ov),.out_ready_i(meta_or),.out_data_o(meta_hi),.level_o(meta_level_unused));
  assign out_valid_o=sub_ov&&meta_ov;assign sub_or=out_ready_i&&meta_ov;assign meta_or=out_ready_i&&sub_ov;assign hi_o=meta_hi;assign lo_o=to_bf16(residual);assign exception_flags_o=sub_flags;
endmodule
