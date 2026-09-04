// SPDX-License-Identifier: Apache-2.0
module operator_sfu_vector_endpoint_v3 #(
  parameter int LANES=16
)(
  input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,
  input logic[7:0]req_opcode_i,input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,input logic[7:0]req_variant_i,
  input logic payload_valid_i,output logic payload_ready_o,input logic[LANES*32-1:0]payload_a_i,payload_b_i,input logic[LANES-1:0]payload_mask_i,
  output logic result_valid_o,input logic result_ready_i,output logic[LANES*32-1:0]result_data_o,output logic[4:0]exception_flags_o,
  output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
  output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
  localparam logic[2:0]S_IDLE=0,S_PAYLOAD=1,S_ARITH_WAIT=2,S_COMPUTE=3,S_RESULT=4,S_COMPLETE=5,S_REDUCE_WAIT=6,S_PIPE_ISSUE=7;logic[2:0]state_q;
  logic[7:0]opcode_q,variant_q,status_q;logic[15:0]tag_q;logic[7:0]parent_q,terminal_q;
  logic[LANES*32-1:0]payload_a_q,payload_b_q,result_q,pipe_add,pipe_mul;logic[LANES-1:0]payload_mask_q;
  logic[LANES-1:0]add_in_ready,mul_in_ready,add_out_valid,mul_out_valid;
  logic[LANES*12-1:0]add_user_unused,mul_user_unused;
  logic[LANES*5-1:0]add_flags,mul_flags;logic[4:0]flags_q,flags_comb;integer f,j;
  logic sum_in_ready,sum_out_valid,sum_out_ready;logic[31:0]sum_value;logic[4:0]sum_flags;
  logic max_in_ready,max_out_valid,max_out_ready;logic[31:0]max_value;logic[3:0]max_index;
  logic[31:0]sum_accepted_unused,sum_completed_unused;
  function automatic logic is_nan(input logic[31:0]v);return &v[30:23]&&|v[22:0];endfunction
  function automatic logic fp_ge(input logic[31:0]a,input logic[31:0]b);begin
    if(a[30:0]==0&&b[30:0]==0)fp_ge=1;else if(a[31]!=b[31])fp_ge=!a[31];
    else if(!a[31])fp_ge=a[30:0]>=b[30:0];else fp_ge=a[30:0]<=b[30:0];end endfunction
  function automatic logic[31:0] lane_result(input logic[31:0]a,input logic[31:0]b,input logic mask,input int lane);begin
    case(opcode_q)
      8'h43:lane_result={1'b0,a[30:0]};
      8'h44:lane_result=is_nan(a)?b:is_nan(b)?a:fp_ge(a,b)?a:b;
      8'h45:lane_result=variant_q[0]?(mask?a:b):(fp_ge(a,b)?32'h3f800000:32'h00000000);
      8'h46:lane_result={~a[31],a[30:0]};
      8'h49:lane_result=payload_a_q[31:0];
      8'h4a:lane_result=mask?a:32'hff800000;
      default:lane_result=0;
    endcase
  end endfunction
  wire arith_add=opcode_q==8'h30||opcode_q==8'h31;
  wire arith_mul=opcode_q==8'h32||opcode_q==8'h33;
  wire reduce_sum=opcode_q==8'h34;wire reduce_max=opcode_q==8'h35;
  wire all_arith_valid=arith_add?&add_out_valid:&mul_out_valid;
  wire consume_arith=state_q==S_ARITH_WAIT&&all_arith_valid;
  genvar i;generate for(i=0;i<LANES;i++)begin:g
    localparam logic[11:0] LANE_TAG=i;
    HeteroFP32AddPipeTag12 add(.clock(clk_i),.reset(!rst_ni),
      .io_inValid(state_q==S_PIPE_ISSUE&&arith_add),.io_inReady(add_in_ready[i]),
      .io_x(payload_a_q[i*32+:32]),.io_y(opcode_q == 8'h31 ? {~payload_b_q[i*32+31],payload_b_q[i*32+:31]} : payload_b_q[i*32+:32]),.io_userIn(LANE_TAG),
      .io_outValid(add_out_valid[i]),.io_outReady(consume_arith),.io_out(pipe_add[i*32+:32]),.io_exceptionFlags(add_flags[i*5+:5]),.io_userOut(add_user_unused[i*12+:12]));
    HeteroFP32MulPipeTag12 mul(.clock(clk_i),.reset(!rst_ni),
      .io_inValid(state_q==S_PIPE_ISSUE&&arith_mul),.io_inReady(mul_in_ready[i]),
      .io_x(payload_a_q[i*32+:32]),.io_y(payload_b_q[i*32+:32]),.io_userIn(LANE_TAG),
      .io_outValid(mul_out_valid[i]),.io_outReady(consume_arith),.io_out(pipe_mul[i*32+:32]),.io_exceptionFlags(mul_flags[i*5+:5]),.io_userOut(mul_user_unused[i*12+:12]));
  end endgenerate
  fp32_reduce16 reduce_sum_unit(.clk_i,.rst_ni,.in_valid_i(state_q==S_PIPE_ISSUE&&reduce_sum),.in_ready_o(sum_in_ready),
    .data_i(payload_a_q),.out_valid_o(sum_out_valid),.out_ready_i(sum_out_ready),.sum_o(sum_value),.exception_flags_o(sum_flags),
    .accepted_vectors_o(sum_accepted_unused),.completed_vectors_o(sum_completed_unused));
  fp32_reduce_max16 reduce_max_unit(.clk_i,.rst_ni,.in_valid_i(state_q==S_PIPE_ISSUE&&reduce_max),.in_ready_o(max_in_ready),
    .data_i(payload_a_q),.out_valid_o(max_out_valid),.out_ready_i(max_out_ready),.max_o(max_value),.index_o(max_index));
  assign sum_out_ready=state_q==S_REDUCE_WAIT&&reduce_sum;assign max_out_ready=state_q==S_REDUCE_WAIT&&reduce_max;
  always_comb begin flags_comb=0;for(f=0;f<LANES;f++)begin
    if(opcode_q==8'h30||opcode_q==8'h31)flags_comb|=add_flags[f*5+:5];
    if(opcode_q==8'h32||opcode_q==8'h33)flags_comb|=mul_flags[f*5+:5];end end
  assign req_ready_o=state_q==S_IDLE;
  assign payload_ready_o=state_q==S_PAYLOAD;
  assign result_valid_o=state_q==S_RESULT;assign result_data_o=result_q;assign exception_flags_o=flags_q;
  assign completion_valid_o=state_q==S_COMPLETE;assign completion_tag_o=tag_q;
  assign completion_parent_phase_o=parent_q;assign completion_terminal_phase_o=terminal_q;assign completion_status_o=status_q;
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin state_q<=S_IDLE;opcode_q<=0;variant_q<=0;status_q<=0;tag_q<=0;parent_q<=0;terminal_q<=0;payload_a_q<=0;payload_b_q<=0;payload_mask_q<=0;result_q<=0;flags_q<=0;end
    else case(state_q)
      S_IDLE:if(req_valid_i&&req_ready_o)begin opcode_q<=req_opcode_i;variant_q<=req_variant_i;tag_q<=req_tag_i;parent_q<=req_parent_phase_i;terminal_q<=req_terminal_phase_i;status_q<=0;
        if(req_opcode_i inside {8'h30,8'h31,8'h32,8'h33,8'h34,8'h35,8'h43,8'h44,8'h45,8'h46,8'h49,8'h4a})state_q<=S_PAYLOAD;
        else begin status_q<=8'd4;state_q<=S_COMPLETE;end end
      S_PAYLOAD:if(payload_valid_i&&payload_ready_o)begin
        payload_a_q<=payload_a_i;payload_b_q<=payload_b_i;payload_mask_q<=payload_mask_i;
        if(arith_add||arith_mul||reduce_sum||reduce_max)state_q<=S_PIPE_ISSUE;
        else state_q<=S_COMPUTE;end
      S_PIPE_ISSUE:begin
        if((arith_add&&(&add_in_ready))||(arith_mul&&(&mul_in_ready)))state_q<=S_ARITH_WAIT;
        else if((reduce_sum&&sum_in_ready)||(reduce_max&&max_in_ready))state_q<=S_REDUCE_WAIT;
      end
      S_ARITH_WAIT:if(consume_arith)begin for(j=0;j<LANES;j++)result_q[j*32+:32]<=arith_add?pipe_add[j*32+:32]:pipe_mul[j*32+:32];flags_q<=flags_comb;state_q<=S_RESULT;end
      S_REDUCE_WAIT:if((reduce_sum&&sum_out_valid)||(reduce_max&&max_out_valid))begin result_q<=0;result_q[31:0]<=reduce_sum?sum_value:max_value;result_q[35:32]<=reduce_sum?0:max_index;flags_q<=reduce_sum?sum_flags:0;state_q<=S_RESULT;end
      S_COMPUTE:begin for(j=0;j<LANES;j++)result_q[j*32+:32]<=lane_result(payload_a_q[j*32+:32],payload_b_q[j*32+:32],payload_mask_q[j],j);flags_q<=flags_comb;state_q<=S_RESULT;end
      S_RESULT:if(result_valid_o&&result_ready_i)state_q<=S_COMPLETE;
      S_COMPLETE:if(completion_valid_o&&completion_ready_i)state_q<=S_IDLE;
      default:state_q<=S_IDLE;
    endcase
  end
endmodule
