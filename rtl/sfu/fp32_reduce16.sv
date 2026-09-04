// SPDX-License-Identifier: Apache-2.0
module fp32_reduce16(
 input logic clk_i,rst_ni,input logic in_valid_i,output logic in_ready_o,input logic[511:0]data_i,
 output logic out_valid_o,input logic out_ready_i,output logic[31:0]sum_o,output logic[4:0]exception_flags_o,
 output logic[31:0]accepted_vectors_o,completed_vectors_o);
 localparam logic[1:0]S_IDLE=0,S_ISSUE=1,S_WAIT=2,S_OUT=3;logic[1:0]state_q;logic[1:0]level_q;
 logic[511:0]data_q;logic[31:0]sum_q;logic[4:0]flags_q;logic[4:0]pair_count;
 logic[7:0]pipe_in_ready,pipe_out_valid;logic[255:0]pipe_out;logic[39:0]pipe_flags;logic[95:0]user_unused;
 logic all_in_ready,all_out_valid,consume;logic[4:0]stage_flags;integer f,j;
 always_comb begin pair_count=5'd8>>level_q;all_in_ready=1;all_out_valid=1;stage_flags=0;
  for(f=0;f<8;f++)if(f<pair_count)begin all_in_ready&=pipe_in_ready[f];all_out_valid&=pipe_out_valid[f];stage_flags|=pipe_flags[f*5+:5];end end
 assign consume=state_q==S_WAIT&&all_out_valid;
 genvar i;generate for(i=0;i<8;i++)begin:g
  localparam logic[11:0] LANE_TAG=i;
  HeteroFP32AddPipeTag12 add(.clock(clk_i),.reset(!rst_ni),
   .io_inValid(state_q==S_ISSUE&&all_in_ready&&i<pair_count),.io_inReady(pipe_in_ready[i]),
   .io_x(data_q[(2*i)*32+:32]),.io_y(data_q[(2*i+1)*32+:32]),.io_userIn(LANE_TAG),
   .io_outValid(pipe_out_valid[i]),.io_outReady(consume),.io_out(pipe_out[i*32+:32]),
   .io_exceptionFlags(pipe_flags[i*5+:5]),.io_userOut(user_unused[i*12+:12]));
 end endgenerate
 assign in_ready_o=state_q==S_IDLE;assign out_valid_o=state_q==S_OUT;assign sum_o=sum_q;assign exception_flags_o=flags_q;
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin state_q<=S_IDLE;level_q<=0;data_q<=0;sum_q<=0;flags_q<=0;accepted_vectors_o<=0;completed_vectors_o<=0;end else case(state_q)
  S_IDLE:if(in_valid_i&&in_ready_o)begin data_q<=data_i;level_q<=0;flags_q<=0;accepted_vectors_o<=accepted_vectors_o+1'b1;state_q<=S_ISSUE;end
  S_ISSUE:if(all_in_ready)state_q<=S_WAIT;
  S_WAIT:if(all_out_valid)begin
   for(j=0;j<8;j++)if(j<pair_count)data_q[j*32+:32]<=pipe_out[j*32+:32];flags_q<=flags_q|stage_flags;
   if(level_q==3)begin sum_q<=pipe_out[31:0];state_q<=S_OUT;end else begin level_q<=level_q+1'b1;state_q<=S_ISSUE;end end
  S_OUT:if(out_valid_o&&out_ready_i)begin completed_vectors_o<=completed_vectors_o+1'b1;state_q<=S_IDLE;end
 endcase end
endmodule
