// SPDX-License-Identifier: Apache-2.0
module fp32_vector_alu #(parameter integer LANES=16)(input logic op_i,input logic[LANES*32-1:0]a_i,b_i,
 output logic[LANES*32-1:0]out_o,output logic[4:0]exception_flags_o);
 logic[LANES*5-1:0]f;integer j;genvar i;generate for(i=0;i<LANES;i++)begin:g
  HeteroFP32Alu u(.io_op(op_i),.io_x(a_i[i*32+:32]),.io_y(b_i[i*32+:32]),.io_out(out_o[i*32+:32]),.io_exceptionFlags(f[i*5+:5]));end endgenerate
 always_comb begin exception_flags_o=0;for(j=0;j<LANES;j++)exception_flags_o|=f[j*5+:5];end
endmodule
