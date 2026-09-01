// SPDX-License-Identifier: Apache-2.0
// 32-lane BF16 tensor-boundary bias add using accepted FP32 HardFloat pipelines.
`timescale 1ns/1ps
module bf16_bias_add_tile32(
 input logic clk_i,input logic rst_ni,input logic in_valid_i,output logic in_ready_o,
 input logic[511:0]data_i,bias_i,output logic out_valid_o,input logic out_ready_i,
 output logic[511:0]data_o,output logic[4:0]exception_flags_o,
 output logic[31:0]accepted_o,output logic[31:0]completed_o
);
 logic[31:0]lane_ready,lane_valid,lane_outvalid,lane_outready;logic[31:0][31:0]lane_out;
 logic[31:0][4:0]lane_flags;logic[31:0]lane_user;integer c;
 function automatic[15:0]bf16(input logic[31:0]v);logic[31:0]r;begin r=v+32'h7fff+v[16];return r[31:16];end endfunction
 assign in_ready_o=&lane_ready;assign lane_valid={32{in_valid_i&&in_ready_o}};
 assign out_valid_o=&lane_outvalid;assign lane_outready={32{out_ready_i&&out_valid_o}};
 always_comb begin data_o='0;exception_flags_o='0;for(c=0;c<32;c++)begin data_o[c*16+:16]=bf16(lane_out[c]);exception_flags_o|=lane_flags[c];end end
 for(genvar g=0;g<32;g++)begin:g_add
  HeteroFP32AddPipeBit1 add(.clock(clk_i),.reset(!rst_ni),.io_inValid(lane_valid[g]),
   .io_inReady(lane_ready[g]),.io_x({data_i[g*16+:16],16'd0}),.io_y({bias_i[g*16+:16],16'd0}),
   .io_userIn(1'b0),.io_outValid(lane_outvalid[g]),.io_outReady(lane_outready[g]),
   .io_out(lane_out[g]),.io_exceptionFlags(lane_flags[g]),.io_userOut(lane_user[g]));
 end
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin accepted_o<=0;completed_o<=0;end
  else begin if(in_valid_i&&in_ready_o)accepted_o<=accepted_o+1;if(out_valid_o&&out_ready_i)completed_o<=completed_o+1;end end
endmodule
