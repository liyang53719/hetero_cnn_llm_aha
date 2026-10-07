// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
// Opt-in bounded descriptor bridge, not a full tensor or architecture top.
// Executes one selected token/head: H1024 -> Q256+gate256 or K256 -> Norm256
// -> SharedL2 -> partial64 RoPE. All Matrix products/accumulators are produced
// by the existing Revision8B-B endpoint. No native/reference payload input.
// Gamma (256 BF16) and explicit cos32/sin32 BF16 coefficients are preloaded.
//
// The seven selected working regions must be disjoint. Tensor bases denote
// whole tensors, while activation/weight buffers and gamma/trig are direct
// addresses. Token extent is 1..128; Q has 8 packed heads, K has 2 heads.
// Packed projection is also stored through the existing DMA interface. Norm
// and RoPE outputs remain in SharedL2. done waits for every DMA and L2 ACK.
// L2 write requests and ACKs are separate: exactly one may be outstanding;
// a same-cycle ACK with request acceptance is supported. Fabric reset must
// accompany rst_ni and discard old responses. Hold reset for >=2 clocks.
// Status: 2 malformed command/descriptor, 3 descriptor fetch, 4 unsupported,
// 5 local/DDR range or overlap, 6 DMA failure, 7 Matrix/RoPE arithmetic,
// 8 L2 read/write failure, 0x10+Norm status. Exception flags report the
// Norm/RoPE arithmetic, not Matrix intermediate flags. Candidate projection
// rejects a nonfinite final active output before publishing that tile.
// Error and debug results latch
// through done and idle until the next accepted start. Reset flushes work,
// not external writes already committed. No rollback/atomicity is claimed.
module qwen2_projection_qk_norm_rope_candidate #(
 parameter integer ADDR_W=15,
 parameter longint unsigned L2_BEATS=ADDR_W<15 ? (64'd1<<ADDR_W) : 64'd24576
)(
 input logic clk_i,rst_ni,start_i,input logic[127:0]command_i,
 input logic[31:0]token_base_i,
 input logic[63:0]activation_local_i,weight_local_i,output_local_i,
 output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,
 output logic[23:0]descriptor_req_index_o,input logic descriptor_rsp_valid_i,
 output logic descriptor_rsp_ready_o,input logic[127:0]descriptor_rsp_data_i,
 input logic descriptor_rsp_error_i,
 output logic dma_req_valid_o,input logic dma_req_ready_i,
 output logic[1:0]dma_req_kind_o,output logic[63:0]dma_src_addr_o,dma_dst_addr_o,
 output logic[31:0]dma_row_bytes_o,dma_rows_o,dma_src_stride_o,dma_dst_stride_o,
 input logic dma_rsp_valid_i,output logic dma_rsp_ready_o,input logic dma_rsp_error_i,
 output logic l2_rd_valid_o,input logic l2_rd_ready_i,
 output logic[ADDR_W-1:0]l2_rd_addr_o,input logic l2_rsp_valid_i,
 output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
 output logic l2_wr_valid_o,input logic l2_wr_ready_i,
 output logic[ADDR_W-1:0]l2_wr_addr_o,output logic[511:0]l2_wr_data_o,
 output logic[63:0]l2_wr_be_o,
 output logic done_o,output logic[7:0]status_o,
 output logic[17:0]output_columns_o,output logic[5:0]column_tiles_o,
 output logic[31:0]matrix_steps_o,output logic[63:0]ddr_read_bytes_o,ddr_write_bytes_o,
 input logic[1:0]candidate_role_i,input logic[15:0]candidate_head_i,
 input logic[7:0]candidate_policy_i,
 input logic[63:0]candidate_norm_weight_local_i,candidate_norm_output_local_i,
 input logic[63:0]candidate_rope_output_local_i,candidate_trig_local_i,
 input logic candidate_l2_rsp_error_i,candidate_l2_wr_rsp_valid_i,
 input logic candidate_l2_wr_rsp_error_i,
 output logic candidate_l2_wr_rsp_ready_o,output logic ready_o,
 output logic[4:0]candidate_exception_flags_o,
 output logic[3:0]candidate_norm_status_o,
 output logic[31:0]candidate_mean_eps_o,candidate_inv_o
);
 typedef enum logic[4:0] {
  IDLE,CONTEXT_START,CONTEXT_WAIT,CHECK_ADDRESS,ACT_REQ,ACT_RSP,MATRIX_CMD,
  WEIGHT_REQ,WEIGHT_RSP,PAYLOAD_START,PAYLOAD_WAIT,STORE_REQ,STORE_RSP,
  HEAD_REQ,HEAD_RSP,GAMMA_REQ,GAMMA_RSP,NORM_REQ,NORM_RSP,NORM_WRITE,
  ROPE_START,ROPE_WAIT,WAIT_MATRIX,DONE,FLUSH
 } state_e;
 state_e state_q;
 localparam logic[64:0]BYTE_LIMIT=65'(L2_BEATS)<<6;
 localparam logic[64:0]DDR_LIMIT=65'd1<<56;
 logic[127:0]command_q;
 logic[31:0]token_q;
 logic[1:0]role_q;
 logic[15:0]head_q;
 logic[7:0]policy_q;
 logic[63:0]activation_q,weight_q,packed_base_q,gamma_q,norm_base_q,rope_base_q,trig_q;
 logic[63:0]packed_q,norm_q,rope_q,act_ddr_q,weight_ddr_q,packed_ddr_q;
 logic[31:0]packed_stride,normalized_stride,head_packed_bytes;
 logic[64:0]packed_address,norm_address,rope_address;
 logic[64:0]act_ddr_address,weight_ddr_address,packed_ddr_address;
 logic[64:0]region_base[0:6],region_bytes[0:6];
 logic local_legal,ddr_legal,shape_legal;
 logic cv,cr,cl;logic[7:0]cstatus;logic[167:0]tensor_address;
 logic[215:0]tensor_shape;logic[17:0]context_columns;
 logic[31:0]context_weight_stride;
 logic[4:0]tile_q,beat_q;
 logic engine_rst_n;
 logic mpv,mpr,mc,ml,mov,mor,mol,mcv,merr,mready,mseen_q;
 logic[2:0]mctx,moctx;logic[255:0]ma;logic[511:0]mb;
 logic[16383:0]macc;logic[55:0]mcd;
 logic pd;logic[7:0]pstatus;logic[31:0]psteps;
 logic prv,prr,prsv,prsr,pwv,pwr;logic[ADDR_W-1:0]pra,pwa;
 logic[511:0]pwd;logic[63:0]pbe;
 logic niv,nir,nov,norm_out_ready;logic[4095:0]norm_result,gate_result;
 logic[8191:0]packed_head_q;logic[4095:0]gamma_head_q,norm_head_q;
 logic[3:0]nstatus;logic[4:0]nflags;logic[31:0]nmean,ninv;
 logic rrv,rrr,rrsv,rrsr,rwv,rwr,rdone,rbad;
 logic[ADDR_W-1:0]rra,rwa;logic[511:0]rwd;logic[63:0]rbe;
 logic[4:0]rflags;
 logic leaf_wv,leaf_wr,write_pending_q,write_accept,write_ack;
 logic read_error,write_error;

 initial begin
  if(ADDR_W<1||ADDR_W>58||L2_BEATS==0||65'(L2_BEATS)>(65'd1<<ADDR_W))
   $error("qwen2_projection_qk_norm_rope_candidate: invalid L2 aperture");
 end
 assign ready_o=rst_ni&&state_q==IDLE;
 assign done_o=state_q==DONE;
 // Two full control clocks DONE/FLUSH reset the engines between commands,
 // including after a failed DMA midway through an active Matrix command.
 assign engine_rst_n=rst_ni&&state_q!=IDLE&&state_q!=DONE&&state_q!=FLUSH;
 assign packed_stride=role_q==0?32'd8192:32'd1024;
 assign normalized_stride=role_q==0?32'd4096:32'd1024;
 assign head_packed_bytes=role_q==0?32'd1024:32'd512;
 assign packed_address={1'b0,packed_base_q}+65'(token_q)*packed_stride+65'(head_q)*head_packed_bytes;
 assign norm_address={1'b0,norm_base_q}+65'(token_q)*normalized_stride+65'(head_q)*512;
 assign rope_address={1'b0,rope_base_q}+65'(token_q)*normalized_stride+65'(head_q)*512;
 assign act_ddr_address={9'd0,tensor_address[0+:56]}+65'(token_q)*2048;
 assign weight_ddr_address={9'd0,tensor_address[56+:56]}+65'(head_q)*head_packed_bytes;
 assign packed_ddr_address={9'd0,tensor_address[112+:56]}+65'(token_q)*packed_stride+65'(head_q)*head_packed_bytes;
 always_comb begin
  region_base[0]={1'b0,activation_q};region_bytes[0]=65536;
  region_base[1]={1'b0,weight_q};region_bytes[1]=65536;
  region_base[2]=packed_address;region_bytes[2]=65'(head_packed_bytes);
  region_base[3]={1'b0,gamma_q};region_bytes[3]=512;
  region_base[4]=norm_address;region_bytes[4]=512;
  region_base[5]={1'b0,trig_q};region_bytes[5]=128;
  region_base[6]=rope_address;region_bytes[6]=512;
  local_legal=1'b1;
  for(int a=0;a<7;a++)begin
   if(region_base[a][5:0]!=0||region_base[a]>=BYTE_LIMIT||
      region_base[a]+region_bytes[a]>BYTE_LIMIT)local_legal=1'b0;
   for(int b=a+1;b<7;b++)begin
    if(region_base[a]<region_base[b]+region_bytes[b]&&
       region_base[b]<region_base[a]+region_bytes[a])local_legal=1'b0;
   end
  end
 end
 assign ddr_legal=act_ddr_address[0]==0&&weight_ddr_address[5:0]==0&&
  packed_ddr_address[5:0]==0&&act_ddr_address+2048<=DDR_LIMIT&&
  weight_ddr_address+65'd1023*packed_stride+65'(head_packed_bytes)<=DDR_LIMIT&&
  packed_ddr_address+65'(head_packed_bytes)<=DDR_LIMIT&&
  // Earlier tile stores must not destroy columns required by later loads.
  // Conservatively reserve the entire selected strided weight envelope.
  !(packed_ddr_address<weight_ddr_address+65'd1023*packed_stride+65'(head_packed_bytes)&&
    weight_ddr_address<packed_ddr_address+65'(head_packed_bytes));
 assign shape_legal=(role_q==0||role_q==1)&&policy_q==8'hc1&&
  head_q<(role_q==0?16'd8:16'd2)&&token_q<{14'd0,tensor_shape[17:0]}&&
  context_columns==(role_q==0?18'd4096:18'd512);

 qwen2_projection_descriptor_context #(.CANDIDATE_QK_SHAPES(1'b1)) context_decoder(
  .clk_i,.rst_ni,.start_i(state_q==CONTEXT_START),.command_i(command_q),
  .descriptor_req_valid_o,.descriptor_req_ready_i,.descriptor_req_index_o,
  .descriptor_rsp_valid_i,.descriptor_rsp_ready_o,.descriptor_rsp_data_i,
  .descriptor_rsp_error_i,.context_valid_o(cv),.context_ready_i(cr),
  .context_legal_o(cl),.context_status_o(cstatus),.tensor_address_o(tensor_address),
  .tensor_shape_o(tensor_shape),.output_columns_o(context_columns),
  .weight_row_bytes_o(context_weight_stride),.column_tiles_o(),.output_fp32_o());
 assign cr=state_q==CONTEXT_WAIT;
 qwen2_shared_l2_matrix_tile16_payload #(.ADDR_W(ADDR_W),
  .CANDIDATE_RNE_BF16(1'b1),.L2_BEATS(L2_BEATS)) payload(
  .clk_i,.rst_ni(engine_rst_n),.start_i(state_q==PAYLOAD_START),
  .activation_local_i(activation_q),.weight_local_i(weight_q),
  .output_local_i(packed_q+64'(tile_q)*64),.depth_i(16'd1024),
  .weight_k_stride_i(32'd64),.rows_i(16'd1),.columns_i(16'd32),
  .output_fp32_i(1'b0),.status_o(pstatus),
  .l2_rd_valid_o(prv),.l2_rd_ready_i(prr),.l2_rd_addr_o(pra),
  .l2_rsp_valid_i(prsv),.l2_rsp_ready_o(prsr),.l2_rsp_data_i,
  .l2_wr_valid_o(pwv),.l2_wr_ready_i(pwr),.l2_wr_addr_o(pwa),
  .l2_wr_data_o(pwd),.l2_wr_be_o(pbe),
  .matrix_step_valid_o(mpv),.matrix_step_ready_i(mpr),.matrix_context_o(mctx),
  .matrix_clear_o(mc),.matrix_last_o(ml),.matrix_a_o(ma),.matrix_b_o(mb),
  .matrix_out_valid_i(mov),.matrix_out_ready_o(mor),.matrix_out_last_i(mol),
  .matrix_acc_i(macc),.done_o(pd),.read_beats_o(),.write_beats_o(),
  .matrix_steps_o(psteps));
 qwen2_matrix_command_endpoint matrix(
  .clk_i,.rst_ni(engine_rst_n),.cmd_valid_i(state_q==MATRIX_CMD),
  .cmd_ready_o(mready),.cmd_i(command_q),.step_valid_i(mpv),.step_ready_o(mpr),
  .step_context_i(mctx),.step_clear_i(mc),.step_last_i(ml),
  .command_last_tile_i({1'b0,tile_q}+6'd1==column_tiles_o),
  .step_a_i(ma),.step_b_i(mb),.out_valid_o(mov),.out_ready_i(mor),
  .out_context_o(moctx),.out_last_o(mol),.out_acc_o(macc),
  .completion_valid_o(mcv),.completion_ready_i(1'b1),
  .completion_data_o(mcd),.protocol_error_o(merr));
 assign niv=state_q==NORM_REQ;
 assign norm_out_ready=state_q==NORM_RSP;
 qk_norm256_bf16_candidate norm(
  .clk_i,.rst_ni(engine_rst_n),.in_valid_i(niv),.in_ready_o(nir),
  .packed_i(packed_head_q),.weight_i(gamma_head_q),.role_i(role_q),
  .head_dim_i(16'd256),.policy_i(policy_q),.epsilon_i(32'h358637bd),
  .tag_i({token_q[15:0],head_q}),.out_valid_o(nov),.out_ready_i(norm_out_ready),
  .norm_o(norm_result),.gate_o(gate_result),.status_o(nstatus),.tag_o(),
  .exception_flags_o(nflags),.mean_eps_o(nmean),.inv_o(ninv),
  .accepted_o(),.completed_o());
 qwen2_shared_l2_rope_payload #(.ADDR_W(ADDR_W),.EXPERIMENTAL_BF16_ROPE(1'b1),
  .CANDIDATE_L2_BEATS(L2_BEATS)) rope(
  .clk_i,.rst_ni(engine_rst_n),.start_i(state_q==ROPE_START),
  .data_beats_i(6'd8),.heads_i(10'd1),.head_dim_i(10'd256),
  .position_lane_i(4'd0),.data_local_i(norm_q),.position_local_i(64'd0),
  .out_local_i(rope_q),.candidate_trig_local_i(trig_q),
  .candidate_rotary_dim_i(10'd64),.candidate_policy_i(8'hb1),.ready_o(),
  .l2_rd_valid_o(rrv),.l2_rd_ready_i(rrr),.l2_rd_addr_o(rra),
  .l2_rsp_valid_i(rrsv),.l2_rsp_ready_o(rrsr),.l2_rsp_data_i,
  .l2_wr_valid_o(rwv),.l2_wr_ready_i(rwr),.l2_wr_addr_o(rwa),
  .l2_wr_data_o(rwd),.l2_wr_be_o(rbe),.done_o(rdone),
  .unsupported_position_o(rbad),.read_beats_o(),.write_beats_o(),
  .pairs_o(),.position_o(),.coefficient_steps_o(),.exception_flags_o(rflags));

 // DMA addresses are immutable throughout request backpressure. Responses
 // are consumed only by the owner that issued the sole outstanding request.
 assign dma_req_valid_o=state_q==ACT_REQ||state_q==WEIGHT_REQ||state_q==STORE_REQ;
 assign dma_req_kind_o=state_q==STORE_REQ?2'd3:2'd1;
 assign dma_src_addr_o=state_q==ACT_REQ?act_ddr_q:
  state_q==WEIGHT_REQ?weight_ddr_q+64'(tile_q)*64:packed_q+64'(tile_q)*64;
 assign dma_dst_addr_o=state_q==ACT_REQ?activation_q:
  state_q==WEIGHT_REQ?weight_q:packed_ddr_q+64'(tile_q)*64;
 assign dma_row_bytes_o=state_q==ACT_REQ?32'd2:32'd64;
 assign dma_rows_o=state_q==STORE_REQ?32'd1:32'd1024;
 assign dma_src_stride_o=state_q==ACT_REQ?32'd2:
  state_q==WEIGHT_REQ?packed_stride:32'd64;
 assign dma_dst_stride_o=32'd64;
 assign dma_rsp_ready_o=state_q==ACT_RSP||state_q==WEIGHT_RSP||state_q==STORE_RSP;

 // SharedL2 ownership switches only after the previous client drained.
 always_comb begin
  l2_rd_valid_o=1'b0;l2_rd_addr_o='0;l2_rsp_ready_o=1'b0;
  prr=1'b0;prsv=1'b0;rrr=1'b0;rrsv=1'b0;
  leaf_wv=1'b0;l2_wr_addr_o='0;l2_wr_data_o='0;l2_wr_be_o='0;
  pwr=1'b0;rwr=1'b0;
  if(state_q==PAYLOAD_WAIT)begin
   l2_rd_valid_o=prv;l2_rd_addr_o=pra;l2_rsp_ready_o=prsr;
   prr=l2_rd_ready_i;prsv=l2_rsp_valid_i;
   leaf_wv=pwv;l2_wr_addr_o=pwa;l2_wr_data_o=pwd;l2_wr_be_o=pbe;
   pwr=leaf_wr;
  end else if(state_q==HEAD_REQ||state_q==GAMMA_REQ)begin
   l2_rd_valid_o=1'b1;
   l2_rd_addr_o=ADDR_W'(((state_q==HEAD_REQ?packed_q:gamma_q)>>6)+64'(beat_q));
  end else if(state_q==HEAD_RSP||state_q==GAMMA_RSP)begin
   l2_rsp_ready_o=1'b1;
  end else if(state_q==NORM_WRITE)begin
   leaf_wv=1'b1;l2_wr_addr_o=ADDR_W'((norm_q>>6)+64'(beat_q));
   l2_wr_data_o=norm_head_q[beat_q*512+:512];l2_wr_be_o='1;
  end else if(state_q==ROPE_WAIT)begin
   l2_rd_valid_o=rrv;l2_rd_addr_o=rra;l2_rsp_ready_o=rrsr;
   rrr=l2_rd_ready_i;rrsv=l2_rsp_valid_i;
   leaf_wv=rwv;l2_wr_addr_o=rwa;l2_wr_data_o=rwd;l2_wr_be_o=rbe;
   rwr=leaf_wr;
  end
 end
 // Holding the leaf's ready low until ACK prevents premature leaf done.
 // Suppression while pending ensures the held packet is issued only once.
 assign l2_wr_valid_o=leaf_wv&&!write_pending_q&&engine_rst_n;
 assign write_accept=l2_wr_valid_o&&l2_wr_ready_i;
 assign candidate_l2_wr_rsp_ready_o=engine_rst_n&&(write_pending_q||write_accept);
 assign write_ack=candidate_l2_wr_rsp_valid_i&&candidate_l2_wr_rsp_ready_o;
 assign leaf_wr=write_ack;
 assign read_error=l2_rsp_valid_i&&l2_rsp_ready_o&&candidate_l2_rsp_error_i;
 assign write_error=write_ack&&candidate_l2_wr_rsp_error_i;

 always_ff@(posedge clk_i or negedge rst_ni)begin
  if(!rst_ni)begin
   state_q<=IDLE;command_q<=0;token_q<=0;role_q<=0;head_q<=0;policy_q<=0;
   activation_q<=0;weight_q<=0;packed_base_q<=0;gamma_q<=0;
   norm_base_q<=0;rope_base_q<=0;trig_q<=0;packed_q<=0;norm_q<=0;rope_q<=0;
   act_ddr_q<=0;weight_ddr_q<=0;packed_ddr_q<=0;tile_q<=0;beat_q<=0;
   mseen_q<=0;write_pending_q<=0;packed_head_q<=0;gamma_head_q<=0;norm_head_q<=0;
   status_o<=0;output_columns_o<=0;column_tiles_o<=0;matrix_steps_o<=0;
   ddr_read_bytes_o<=0;ddr_write_bytes_o<=0;candidate_exception_flags_o<=0;
   candidate_norm_status_o<=0;candidate_mean_eps_o<=0;candidate_inv_o<=0;
  end else begin
   if(write_accept)write_pending_q<=1'b1;
   if(write_ack)write_pending_q<=1'b0;
   if(mcv)mseen_q<=1'b1;
   // Cumulative accepted Matrix steps remain truthful also on later faults.
   if(mpv&&mpr)matrix_steps_o<=matrix_steps_o+1'b1;
   case(state_q)
    IDLE:if(start_i&&ready_o)begin
     command_q<=command_i;token_q<=token_base_i;role_q<=candidate_role_i;
     head_q<=candidate_head_i;policy_q<=candidate_policy_i;
     activation_q<=activation_local_i;weight_q<=weight_local_i;
     packed_base_q<=output_local_i;gamma_q<=candidate_norm_weight_local_i;
     norm_base_q<=candidate_norm_output_local_i;rope_base_q<=candidate_rope_output_local_i;
     trig_q<=candidate_trig_local_i;tile_q<=0;beat_q<=0;mseen_q<=0;
     write_pending_q<=0;packed_head_q<=0;gamma_head_q<=0;norm_head_q<=0;
     status_o<=0;output_columns_o<=0;column_tiles_o<=0;matrix_steps_o<=0;
     ddr_read_bytes_o<=0;ddr_write_bytes_o<=0;candidate_exception_flags_o<=0;
     candidate_norm_status_o<=0;candidate_mean_eps_o<=0;candidate_inv_o<=0;
     state_q<=CONTEXT_START;
    end
    CONTEXT_START:state_q<=CONTEXT_WAIT;
    CONTEXT_WAIT:if(cv&&cr)begin
     if(!cl)begin status_o<=cstatus;state_q<=DONE;end
     else state_q<=CHECK_ADDRESS;
    end
    CHECK_ADDRESS:begin
     if(!shape_legal)begin status_o<=4;state_q<=DONE;end
     else if(!local_legal||!ddr_legal)begin status_o<=5;state_q<=DONE;end
     else begin
      output_columns_o<=context_columns;column_tiles_o<=role_q==0?6'd16:6'd8;
      packed_q<=packed_address[63:0];norm_q<=norm_address[63:0];rope_q<=rope_address[63:0];
      act_ddr_q<=act_ddr_address[63:0];weight_ddr_q<=weight_ddr_address[63:0];
      packed_ddr_q<=packed_ddr_address[63:0];state_q<=ACT_REQ;
     end
    end
    ACT_REQ:if(dma_req_valid_o&&dma_req_ready_i)state_q<=ACT_RSP;
    ACT_RSP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin
     if(dma_rsp_error_i)begin status_o<=6;state_q<=DONE;end
     else begin ddr_read_bytes_o<=ddr_read_bytes_o+2048;state_q<=MATRIX_CMD;end
    end
    MATRIX_CMD:if(mready)state_q<=WEIGHT_REQ;
    WEIGHT_REQ:if(dma_req_valid_o&&dma_req_ready_i)state_q<=WEIGHT_RSP;
    WEIGHT_RSP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin
     if(dma_rsp_error_i)begin status_o<=6;state_q<=DONE;end
     else begin ddr_read_bytes_o<=ddr_read_bytes_o+65536;state_q<=PAYLOAD_START;end
    end
    PAYLOAD_START:state_q<=PAYLOAD_WAIT;
    PAYLOAD_WAIT:if(pd)begin
     if(pstatus!=0)begin status_o<=pstatus;state_q<=DONE;end
     else state_q<=STORE_REQ;
    end
    STORE_REQ:if(dma_req_valid_o&&dma_req_ready_i)state_q<=STORE_RSP;
    STORE_RSP:if(dma_rsp_valid_i&&dma_rsp_ready_o)begin
     if(dma_rsp_error_i)begin status_o<=6;state_q<=DONE;end
     else begin
      ddr_write_bytes_o<=ddr_write_bytes_o+64;
      if({1'b0,tile_q}+6'd1==column_tiles_o)begin beat_q<=0;state_q<=HEAD_REQ;end
      else begin tile_q<=tile_q+1'b1;state_q<=WEIGHT_REQ;end
     end
    end
    HEAD_REQ:if(l2_rd_valid_o&&l2_rd_ready_i)state_q<=HEAD_RSP;
    HEAD_RSP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin
     packed_head_q[beat_q*512+:512]<=l2_rsp_data_i;
     if({1'b0,beat_q}+6'd1==column_tiles_o)begin beat_q<=0;state_q<=GAMMA_REQ;end
     else begin beat_q<=beat_q+1'b1;state_q<=HEAD_REQ;end
    end
    GAMMA_REQ:if(l2_rd_valid_o&&l2_rd_ready_i)state_q<=GAMMA_RSP;
    GAMMA_RSP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin
     gamma_head_q[beat_q*512+:512]<=l2_rsp_data_i;
     if(beat_q==7)begin beat_q<=0;state_q<=NORM_REQ;end
     else begin beat_q<=beat_q+1'b1;state_q<=GAMMA_REQ;end
    end
    NORM_REQ:if(niv&&nir)state_q<=NORM_RSP;
    NORM_RSP:if(nov&&norm_out_ready)begin
     candidate_norm_status_o<=nstatus;candidate_exception_flags_o<=nflags;
     candidate_mean_eps_o<=nmean;candidate_inv_o<=ninv;
     if(nstatus!=0)begin status_o<=8'h10+{4'd0,nstatus};state_q<=DONE;end
     else begin norm_head_q<=norm_result;beat_q<=0;state_q<=NORM_WRITE;end
    end
    NORM_WRITE:if(leaf_wr)begin
     if(beat_q==7)state_q<=ROPE_START;
     else beat_q<=beat_q+1'b1;
    end
    ROPE_START:state_q<=ROPE_WAIT;
    ROPE_WAIT:if(rdone)begin
     candidate_exception_flags_o<=candidate_exception_flags_o|rflags;
     if(rbad||(|rflags[4:1]))begin status_o<=7;state_q<=DONE;end
     else state_q<=WAIT_MATRIX;
    end
    WAIT_MATRIX:if(mseen_q&&!write_pending_q)state_q<=DONE;
    DONE:begin write_pending_q<=0;state_q<=FLUSH;end
    FLUSH:state_q<=IDLE;
    default:state_q<=IDLE;
   endcase
   // Fatal responses override ordinary advancement, and remain latched.
   if(read_error||write_error)begin status_o<=8;state_q<=DONE;end
   if(engine_rst_n&&(merr||(mcv&&mcd[39:32]!=0)))begin
    status_o<=7;state_q<=DONE;
   end
  end
 end
endmodule
