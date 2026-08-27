// SPDX-License-Identifier: Apache-2.0
module fp32_mlo_merge_beat #(parameter integer LANES=4)(input logic clk_i,rst_ni,in_valid_i,output logic in_ready_o,input logic[31:0]alpha_i,beta_i,input logic[LANES*32-1:0]oa_i,ob_i,input logic last_i,output logic out_valid_o,input logic out_ready_i,output logic[LANES*32-1:0]o_o,output logic last_o);
 logic valid_q,ready;logic[LANES*32-1:0]r;genvar i;generate for(i=0;i<LANES;i++)begin:g logic[31:0]a,b,c;HeteroFP32Alu ma(.io_op(1'b1),.io_x(oa_i[i*32+:32]),.io_y(alpha_i),.io_out(a),.io_exceptionFlags());HeteroFP32Alu mb(.io_op(1'b1),.io_x(ob_i[i*32+:32]),.io_y(beta_i),.io_out(b),.io_exceptionFlags());HeteroFP32Alu ad(.io_op(1'b0),.io_x(a),.io_y(b),.io_out(c),.io_exceptionFlags());assign r[i*32+:32]=c;end endgenerate
 assign ready=!valid_q||out_ready_i;assign in_ready_o=ready;assign out_valid_o=valid_q;
 always_ff@(posedge clk_i or negedge rst_ni)if(!rst_ni)begin valid_q<=0;o_o<=0;last_o<=0;end else if(ready)begin valid_q<=in_valid_i;if(in_valid_i)begin o_o<=r;last_o<=last_i;end end
endmodule
