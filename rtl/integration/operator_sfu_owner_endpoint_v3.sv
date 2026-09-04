// SPDX-License-Identifier: Apache-2.0
module operator_sfu_owner_endpoint_v3(
 input logic clk_i,rst_ni,input logic req_valid_i,output logic req_ready_o,input logic[7:0]req_opcode_i,req_variant_i,
 input logic[15:0]req_tag_i,input logic[7:0]req_parent_phase_i,req_terminal_phase_i,
 input logic req_scratch_valid_i,input logic[3:0]req_scratch_src0_i,req_scratch_src1_i,req_scratch_dst_i,input logic req_first_i,req_last_i,
 input logic payload_valid_i,output logic payload_ready_o,input logic[511:0]payload_a_i,payload_b_i,payload_c_i,
 input logic[15:0]payload_mask_i,input logic[31:0]payload_epsilon_i,input logic payload_last_i,
 output logic result_valid_o,input logic result_ready_i,output logic[511:0]result_data_o,output logic result_last_o,
 output logic[12:0]exception_flags_o,output logic domain_error_o,
 input logic soft_score_valid_i,output logic soft_score_ready_o,input logic[31:0]soft_score_i,input logic soft_score_mask_i,
 input logic soft_merge_header_valid_i,output logic soft_merge_header_ready_o,input logic[31:0]soft_ma_i,soft_la_i,soft_mb_i,soft_lb_i,
 input logic soft_merge_beat_valid_i,output logic soft_merge_beat_ready_o,input logic[127:0]soft_oa_i,soft_ob_i,input logic soft_merge_beat_last_i,
 output logic soft_header_valid_o,input logic soft_header_ready_i,output logic[31:0]soft_m_o,soft_l_o,
 output logic soft_weight_valid_o,input logic soft_weight_ready_i,output logic[31:0]soft_weight_o,output logic soft_weight_last_o,
 output logic soft_beat_valid_o,input logic soft_beat_ready_i,output logic[127:0]soft_o_o,output logic soft_beat_last_o,
 output logic completion_valid_o,input logic completion_ready_i,output logic[15:0]completion_tag_o,
 output logic[7:0]completion_parent_phase_o,completion_terminal_phase_o,completion_status_o);
 localparam logic[2:0]VEC=0,SCALAR=1,NORM=2,ROPE=3,SOFT=4,GATE=5,PWL=6,BAD=7;
 logic active_q,scratch_q,first_q,last_q,final_valid_q,front_valid_q;logic[2:0]sel_q,req_sel;logic[3:0]scratch_src0_q,scratch_src1_q,scratch_dst_q,front_scratch_src0_q,front_scratch_src1_q,front_scratch_dst_q;logic[511:0]scratch[0:9],final_data_q,leaf_a,leaf_b,leaf_c;logic leaf_payload_valid;logic[15:0]bad_tag_q,front_tag_q;logic[7:0]bad_parent_q,bad_terminal_q,front_opcode_q,front_variant_q,front_parent_q,front_terminal_q;logic front_scratch_q,front_first_q,front_last_q;integer si;
 logic[7:0]crdy,ccv,ccr;logic[8*16-1:0]ctag;logic[8*8-1:0]cparent,cterminal,cstatus;
 logic[7:0]prdy,rv,rr;logic[8*512-1:0]rdata;logic[7:0]rlast;logic[8*13-1:0]rflags;logic[7:0]rde;
 function automatic logic[2:0]decode(input logic[7:0]op);begin
  if(op inside{8'h30,8'h31,8'h32,8'h33,8'h34,8'h35,8'h43,8'h44,8'h45,8'h46,8'h49,8'h4a})decode=VEC;
  else if(op inside{8'h36,8'h37,8'h48})decode=SCALAR;
  else if(op inside{8'h3d,8'h3e,8'h42,8'h4b})decode=NORM;
  else if(op==8'h3f)decode=ROPE;else if(op==8'h40)decode=SOFT;else if(op==8'h41)decode=GATE;else if(op==8'h47)decode=PWL;else decode=BAD;
 end endfunction
 assign req_sel=decode(front_opcode_q);assign req_ready_o=!active_q&&!front_valid_q;
 wire capture_fire=req_valid_i&&req_ready_o;
 wire req_fire=front_valid_q&&!active_q&&(req_sel==BAD||crdy[req_sel]);
 function automatic logic[511:0]scratch_value(input logic[3:0]index);begin case(index)4'd0:scratch_value=first_q?payload_a_i:scratch[0];4'd1:scratch_value=0;4'd2:scratch_value={16{32'h3f800000}};4'd3:scratch_value={16{32'h3fb8aa3b}};4'd4:scratch_value={16{payload_epsilon_i}};default:scratch_value=index<=9?scratch[index]:0;endcase end endfunction
 always_comb begin leaf_payload_valid=scratch_q?(first_q?payload_valid_i:1'b1):payload_valid_i;leaf_a=scratch_q?scratch_value(scratch_src0_q):payload_a_i;leaf_b=scratch_q?scratch_value(scratch_src1_q):payload_b_i;leaf_c=payload_c_i;end

 operator_sfu_vector_endpoint_v3 vec(.clk_i,.rst_ni,.req_valid_i(req_fire&&req_sel==VEC),.req_ready_o(crdy[VEC]),.req_opcode_i(front_opcode_q),.req_tag_i(front_tag_q),.req_parent_phase_i(front_parent_q),.req_terminal_phase_i(front_terminal_q),.req_variant_i(front_variant_q),
  .payload_valid_i(leaf_payload_valid&&active_q&&sel_q==VEC),.payload_ready_o(prdy[VEC]),.payload_a_i(leaf_a),.payload_b_i(leaf_b),.payload_mask_i(payload_mask_i),
  .result_valid_o(rv[VEC]),.result_ready_i(rr[VEC]),.result_data_o(rdata[VEC*512+:512]),.exception_flags_o(rflags[VEC*13+:5]),
  .completion_valid_o(ccv[VEC]),.completion_ready_i(ccr[VEC]),.completion_tag_o(ctag[VEC*16+:16]),.completion_parent_phase_o(cparent[VEC*8+:8]),.completion_terminal_phase_o(cterminal[VEC*8+:8]),.completion_status_o(cstatus[VEC*8+:8]));
 assign rflags[VEC*13+5+:8]=0;assign rlast[VEC]=1;assign rde[VEC]=0;
 operator_sfu_scalar_endpoint_v3 scalar(.clk_i,.rst_ni,.req_valid_i(req_fire&&req_sel==SCALAR),.req_ready_o(crdy[SCALAR]),.req_opcode_i(front_opcode_q),.req_tag_i(front_tag_q),.req_parent_phase_i(front_parent_q),.req_terminal_phase_i(front_terminal_q),
  .payload_valid_i(leaf_payload_valid&&active_q&&sel_q==SCALAR),.payload_ready_o(prdy[SCALAR]),.payload_x_i(leaf_a[31:0]),.result_valid_o(rv[SCALAR]),.result_ready_i(rr[SCALAR]),.result_y_o(rdata[SCALAR*512+:32]),.exception_flags_o(rflags[SCALAR*13+:13]),.domain_error_o(rde[SCALAR]),
  .completion_valid_o(ccv[SCALAR]),.completion_ready_i(ccr[SCALAR]),.completion_tag_o(ctag[SCALAR*16+:16]),.completion_parent_phase_o(cparent[SCALAR*8+:8]),.completion_terminal_phase_o(cterminal[SCALAR*8+:8]),.completion_status_o(cstatus[SCALAR*8+:8]));
 assign rdata[SCALAR*512+32+:480]=0;assign rlast[SCALAR]=1;
 operator_sfu_norm_endpoint_v3 norm(.clk_i,.rst_ni,.req_valid_i(req_fire&&req_sel==NORM),.req_ready_o(crdy[NORM]),.req_opcode_i(front_opcode_q),.req_tag_i(front_tag_q),.req_parent_phase_i(front_parent_q),.req_terminal_phase_i(front_terminal_q),
  .payload_valid_i(leaf_payload_valid&&active_q&&sel_q==NORM),.payload_ready_o(prdy[NORM]),.payload_x_i(leaf_a),.payload_weight_i(leaf_b),.payload_bias_i(leaf_c),.payload_epsilon_i,
  .result_valid_o(rv[NORM]),.result_ready_i(rr[NORM]),.result_y_o(rdata[NORM*512+:512]),.exception_flags_o(rflags[NORM*13+:5]),
  .completion_valid_o(ccv[NORM]),.completion_ready_i(ccr[NORM]),.completion_tag_o(ctag[NORM*16+:16]),.completion_parent_phase_o(cparent[NORM*8+:8]),.completion_terminal_phase_o(cterminal[NORM*8+:8]),.completion_status_o(cstatus[NORM*8+:8]));
 assign rflags[NORM*13+5+:8]=0;assign rlast[NORM]=1;assign rde[NORM]=0;
 operator_sfu_rope_endpoint_v3 rope(.clk_i,.rst_ni,.req_valid_i(req_fire&&req_sel==ROPE),.req_ready_o(crdy[ROPE]),.req_opcode_i(front_opcode_q),.req_tag_i(front_tag_q),.req_parent_phase_i(front_parent_q),.req_terminal_phase_i(front_terminal_q),
  .payload_valid_i(leaf_payload_valid&&active_q&&sel_q==ROPE),.payload_ready_o(prdy[ROPE]),.payload_data_i(leaf_a),.payload_trig_i(leaf_b),
  .result_valid_o(rv[ROPE]),.result_ready_i(rr[ROPE]),.result_data_o(rdata[ROPE*512+:512]),.exception_flags_o(rflags[ROPE*13+:5]),
  .completion_valid_o(ccv[ROPE]),.completion_ready_i(ccr[ROPE]),.completion_tag_o(ctag[ROPE*16+:16]),.completion_parent_phase_o(cparent[ROPE*8+:8]),.completion_terminal_phase_o(cterminal[ROPE*8+:8]),.completion_status_o(cstatus[ROPE*8+:8]));
 assign rflags[ROPE*13+5+:8]=0;assign rlast[ROPE]=1;assign rde[ROPE]=0;
 operator_sfu_online_softmax_endpoint_v3 soft_ep(.clk_i,.rst_ni,.req_valid_i(req_fire&&req_sel==SOFT),.req_ready_o(crdy[SOFT]),.req_opcode_i(front_opcode_q),.req_variant_i(front_variant_q),.req_tag_i(front_tag_q),.req_parent_phase_i(front_parent_q),.req_terminal_phase_i(front_terminal_q),
  .score_valid_i(soft_score_valid_i&&active_q&&sel_q==SOFT),.score_ready_o(soft_score_ready_o),.score_i(soft_score_i),.score_mask_i(soft_score_mask_i),
  .merge_header_valid_i(soft_merge_header_valid_i&&active_q&&sel_q==SOFT),.merge_header_ready_o(soft_merge_header_ready_o),.ma_i(soft_ma_i),.la_i(soft_la_i),.mb_i(soft_mb_i),.lb_i(soft_lb_i),
  .merge_beat_valid_i(soft_merge_beat_valid_i&&active_q&&sel_q==SOFT),.merge_beat_ready_o(soft_merge_beat_ready_o),.oa_i(soft_oa_i),.ob_i(soft_ob_i),.merge_beat_last_i(soft_merge_beat_last_i),
  .header_valid_o(soft_header_valid_o),.header_ready_i(soft_header_ready_i&&active_q&&sel_q==SOFT),.m_o(soft_m_o),.l_o(soft_l_o),.weight_valid_o(soft_weight_valid_o),.weight_ready_i(soft_weight_ready_i&&active_q&&sel_q==SOFT),.weight_o(soft_weight_o),.weight_last_o(soft_weight_last_o),
  .beat_valid_o(soft_beat_valid_o),.beat_ready_i(soft_beat_ready_i&&active_q&&sel_q==SOFT),.o_o(soft_o_o),.beat_last_o(soft_beat_last_o),.exception_flags_o(rflags[SOFT*13+:5]),
  .completion_valid_o(ccv[SOFT]),.completion_ready_i(ccr[SOFT]),.completion_tag_o(ctag[SOFT*16+:16]),.completion_parent_phase_o(cparent[SOFT*8+:8]),.completion_terminal_phase_o(cterminal[SOFT*8+:8]),.completion_status_o(cstatus[SOFT*8+:8]));
 assign prdy[SOFT]=0;assign rv[SOFT]=0;assign rdata[SOFT*512+:512]=0;assign rflags[SOFT*13+5+:8]=0;assign rlast[SOFT]=0;assign rde[SOFT]=0;
 operator_sfu_gate_endpoint_v3 gate(.clk_i,.rst_ni,.req_valid_i(req_fire&&req_sel==GATE),.req_ready_o(crdy[GATE]),.req_opcode_i(front_opcode_q),.req_tag_i(front_tag_q),.req_parent_phase_i(front_parent_q),.req_terminal_phase_i(front_terminal_q),
  .payload_valid_i(leaf_payload_valid&&active_q&&sel_q==GATE),.payload_ready_o(prdy[GATE]),.payload_gate_bf16_i(leaf_a[127:0]),.payload_up_bf16_i(leaf_b[127:0]),.payload_last_i,
  .result_valid_o(rv[GATE]),.result_ready_i(rr[GATE]),.result_bf16_o(rdata[GATE*512+:128]),.result_last_o(rlast[GATE]),.exception_flags_o(rflags[GATE*13+:5]),
  .completion_valid_o(ccv[GATE]),.completion_ready_i(ccr[GATE]),.completion_tag_o(ctag[GATE*16+:16]),.completion_parent_phase_o(cparent[GATE*8+:8]),.completion_terminal_phase_o(cterminal[GATE*8+:8]),.completion_status_o(cstatus[GATE*8+:8]));
 assign rdata[GATE*512+128+:384]=0;assign rflags[GATE*13+5+:8]=0;assign rde[GATE]=0;
 operator_sfu_pwl_endpoint_v3 pwl(.clk_i,.rst_ni,.req_valid_i(req_fire&&req_sel==PWL),.req_ready_o(crdy[PWL]),.req_opcode_i(front_opcode_q),.req_variant_i(front_variant_q),.req_tag_i(front_tag_q),.req_parent_phase_i(front_parent_q),.req_terminal_phase_i(front_terminal_q),
  .payload_valid_i(leaf_payload_valid&&active_q&&sel_q==PWL),.payload_ready_o(prdy[PWL]),.payload_x_i(leaf_a),.result_valid_o(rv[PWL]),.result_ready_i(rr[PWL]),.result_y_o(rdata[PWL*512+:512]),.exception_flags_o(rflags[PWL*13+:5]),
  .completion_valid_o(ccv[PWL]),.completion_ready_i(ccr[PWL]),.completion_tag_o(ctag[PWL*16+:16]),.completion_parent_phase_o(cparent[PWL*8+:8]),.completion_terminal_phase_o(cterminal[PWL*8+:8]),.completion_status_o(cstatus[PWL*8+:8]));
 assign rflags[PWL*13+5+:8]=0;assign rlast[PWL]=1;assign rde[PWL]=0;
 assign crdy[BAD]=1;assign ccv[BAD]=0;assign ctag[BAD*16+:16]=0;assign cparent[BAD*8+:8]=0;assign cterminal[BAD*8+:8]=0;assign cstatus[BAD*8+:8]=0;
 assign prdy[BAD]=0;assign rv[BAD]=0;assign rdata[BAD*512+:512]=0;assign rlast[BAD]=0;assign rflags[BAD*13+:13]=0;assign rde[BAD]=0;

 always_comb begin ccr=0;rr=0;payload_ready_o=0;result_valid_o=0;result_data_o=0;result_last_o=0;exception_flags_o=0;domain_error_o=0;
  if(active_q&&sel_q!=BAD)begin ccr[sel_q]=completion_ready_i&&(!scratch_q||!last_q||!final_valid_q);if(sel_q!=SOFT)begin rr[sel_q]=scratch_q?(!last_q||!final_valid_q):result_ready_i;payload_ready_o=(scratch_q&&!first_q)?0:prdy[sel_q];result_valid_o=scratch_q?final_valid_q:rv[sel_q];result_data_o=scratch_q?final_data_q:rdata[sel_q*512+:512];result_last_o=scratch_q?last_q:rlast[sel_q];exception_flags_o=rflags[sel_q*13+:13];domain_error_o=rde[sel_q];end end
 end
 assign completion_valid_o=active_q&&(sel_q==BAD||(ccv[sel_q]&&(!scratch_q||!last_q||!final_valid_q)));assign completion_tag_o=sel_q==BAD?bad_tag_q:ctag[sel_q*16+:16];assign completion_parent_phase_o=sel_q==BAD?bad_parent_q:cparent[sel_q*8+:8];assign completion_terminal_phase_o=sel_q==BAD?bad_terminal_q:cterminal[sel_q*8+:8];assign completion_status_o=sel_q==BAD?8'd4:cstatus[sel_q*8+:8];
 always_ff@(posedge clk_i or negedge rst_ni)begin if(!rst_ni)begin active_q<=0;front_valid_q<=0;front_opcode_q<=0;front_variant_q<=0;front_tag_q<=0;front_parent_q<=0;front_terminal_q<=0;front_scratch_q<=0;front_first_q<=0;front_last_q<=0;front_scratch_src0_q<=0;front_scratch_src1_q<=0;front_scratch_dst_q<=0;sel_q<=BAD;scratch_q<=0;first_q<=0;last_q<=0;scratch_src0_q<=0;scratch_src1_q<=0;scratch_dst_q<=0;final_valid_q<=0;final_data_q<=0;bad_tag_q<=0;bad_parent_q<=0;bad_terminal_q<=0;for(si=0;si<10;si++)scratch[si]<=0;end else begin
  if(capture_fire)begin front_valid_q<=1;front_opcode_q<=req_opcode_i;front_variant_q<=req_variant_i;front_tag_q<=req_tag_i;front_parent_q<=req_parent_phase_i;front_terminal_q<=req_terminal_phase_i;front_scratch_q<=req_scratch_valid_i;front_first_q<=req_first_i;front_last_q<=req_last_i;front_scratch_src0_q<=req_scratch_src0_i;front_scratch_src1_q<=req_scratch_src1_i;front_scratch_dst_q<=req_scratch_dst_i;end
  if(req_fire)begin front_valid_q<=0;active_q<=1;sel_q<=req_sel;scratch_q<=front_scratch_q;first_q<=front_first_q;last_q<=front_last_q;scratch_src0_q<=front_scratch_src0_q;scratch_src1_q<=front_scratch_src1_q;scratch_dst_q<=front_scratch_dst_q;final_valid_q<=0;if(req_sel==BAD)begin bad_tag_q<=front_tag_q;bad_parent_q<=front_parent_q;bad_terminal_q<=front_terminal_q;end end if(active_q&&scratch_q&&first_q&&leaf_payload_valid&&prdy[sel_q])scratch[0]<=payload_a_i;if(active_q&&scratch_q&&sel_q!=SOFT&&rv[sel_q]&&rr[sel_q])begin if(scratch_dst_q<=9)scratch[scratch_dst_q]<=rdata[sel_q*512+:512];if(last_q)begin final_data_q<=rdata[sel_q*512+:512];final_valid_q<=1;end end if(final_valid_q&&result_ready_i)final_valid_q<=0;if(completion_valid_o&&completion_ready_i)active_q<=0;end end
endmodule
