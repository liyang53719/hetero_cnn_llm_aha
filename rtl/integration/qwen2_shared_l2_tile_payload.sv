// SPDX-License-Identifier: Apache-2.0
// Real Shared-L2 payload path for token0 RMSNorm and Q output columns 0..31.
`timescale 1ns/1ps
module qwen2_shared_l2_tile_payload #(
  parameter integer ADDR_W=15
)(
  input logic clk_i,input logic rst_ni,input logic start_i,input logic reuse_norm_i,input logic load_norm_i,
  input logic[63:0] hidden_local_i,input logic[63:0] rms_weight_local_i,
  input logic[63:0] norm_local_i,input logic[63:0] q_weight_local_i,
  input logic[63:0] q_output_local_i,
  output logic l2_rd_valid_o,input logic l2_rd_ready_i,output logic[ADDR_W-1:0]l2_rd_addr_o,
  input logic l2_rsp_valid_i,output logic l2_rsp_ready_o,input logic[511:0]l2_rsp_data_i,
  output logic l2_wr_valid_o,input logic l2_wr_ready_i,output logic[ADDR_W-1:0]l2_wr_addr_o,
  output logic[511:0]l2_wr_data_o,output logic[63:0]l2_wr_be_o,
  output logic sfu_payload_valid_o,input logic sfu_payload_ready_i,
  output logic[49151:0]sfu_x_o,sfu_weight_o,input logic sfu_out_valid_i,
  output logic sfu_out_ready_o,input logic[49151:0]sfu_y_i,
  output logic matrix_step_valid_o,input logic matrix_step_ready_i,
  output logic[2:0]matrix_context_o,output logic matrix_clear_o,matrix_last_o,
  output logic[255:0]matrix_a_o,output logic[511:0]matrix_b_o,
  input logic matrix_out_valid_i,output logic matrix_out_ready_o,
  input logic matrix_out_last_i,input logic[16383:0]matrix_acc_i,
  output logic done_o,output logic[31:0]read_beats_o,output logic[31:0]write_beats_o
);
  typedef enum logic[3:0]{S_IDLE,S_X_REQ,S_X_RSP,S_W_REQ,S_W_RSP,S_SFU_REQ,S_SFU_RSP,
    S_NORM_WR,S_NORM_RD_REQ,S_NORM_RD_RSP,S_Q_REQ,S_Q_RSP,S_M_REQ,S_M_WAIT,S_OUT_WR,S_DONE}state_e;
  state_e state_q;logic[6:0]beat_q;logic[10:0]k_q;logic[49151:0]x_q,w_q,y_q;
  logic[511:0]q_weight_q;logic[16383:0]final_acc_q;logic final_seen_q;integer comb_j,seq_j;
  function automatic[15:0]bf16(input logic[31:0]v);logic[31:0]r;begin r=v+32'h7fff+v[16];return r[31:16];end endfunction
  assign sfu_x_o=x_q;assign sfu_weight_o=w_q;
  assign l2_rd_valid_o=state_q==S_X_REQ||state_q==S_W_REQ||state_q==S_NORM_RD_REQ||state_q==S_Q_REQ;
  assign l2_rsp_ready_o=state_q==S_X_RSP||state_q==S_W_RSP||state_q==S_NORM_RD_RSP||state_q==S_Q_RSP;
  always_comb begin
    l2_rd_addr_o='0;
    if(state_q==S_X_REQ)l2_rd_addr_o=ADDR_W'(hidden_local_i[ADDR_W+5:6]+beat_q);
    if(state_q==S_W_REQ)l2_rd_addr_o=ADDR_W'(rms_weight_local_i[ADDR_W+5:6]+beat_q);
    if(state_q==S_NORM_RD_REQ)l2_rd_addr_o=ADDR_W'(norm_local_i[ADDR_W+5:6]+beat_q);
    if(state_q==S_Q_REQ)l2_rd_addr_o=ADDR_W'(q_weight_local_i[ADDR_W+5:6]+k_q);
    l2_wr_valid_o=state_q==S_NORM_WR||state_q==S_OUT_WR;l2_wr_addr_o='0;l2_wr_data_o='0;l2_wr_be_o='1;
    if(state_q==S_NORM_WR)begin
      l2_wr_addr_o=ADDR_W'(norm_local_i[ADDR_W+5:6]+beat_q);
      for(comb_j=0;comb_j<32;comb_j++)l2_wr_data_o[comb_j*16+:16]=bf16(y_q[(beat_q*32+comb_j)*32+:32]);
    end
    if(state_q==S_OUT_WR)begin
      l2_wr_addr_o=ADDR_W'(q_output_local_i[ADDR_W+5:6]);
      for(comb_j=0;comb_j<32;comb_j++)l2_wr_data_o[comb_j*16+:16]=bf16(final_acc_q[comb_j*32+:32]);
    end
    sfu_payload_valid_o=state_q==S_SFU_REQ;sfu_out_ready_o=state_q==S_SFU_RSP;
    matrix_step_valid_o=state_q==S_M_REQ;matrix_context_o=0;matrix_clear_o=k_q==0;
    matrix_last_o=k_q==1535;matrix_a_o='0;matrix_a_o[15:0]=bf16(y_q[k_q*32+:32]);
    matrix_b_o=q_weight_q;matrix_out_ready_o=1'b1;done_o=state_q==S_DONE;
  end
  always_ff@(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin state_q<=S_IDLE;beat_q<=0;k_q<=0;x_q<=0;w_q<=0;y_q<=0;q_weight_q<=0;
      final_acc_q<=0;final_seen_q<=0;read_beats_o<=0;write_beats_o<=0;
    end else begin
      if(matrix_out_valid_i&&matrix_out_ready_o&&matrix_out_last_i)begin final_acc_q<=matrix_acc_i;final_seen_q<=1;end
      case(state_q)
        S_IDLE:if(start_i)begin beat_q<=0;k_q<=0;final_seen_q<=0;read_beats_o<=0;write_beats_o<=0;state_q<=load_norm_i?S_NORM_RD_REQ:(reuse_norm_i?S_Q_REQ:S_X_REQ);end
        S_X_REQ:if(l2_rd_valid_o&&l2_rd_ready_i)state_q<=S_X_RSP;
        S_X_RSP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin
          for(seq_j=0;seq_j<32;seq_j++)x_q[(beat_q*32+seq_j)*32+:32]<={l2_rsp_data_i[seq_j*16+:16],16'd0};
          read_beats_o<=read_beats_o+1;if(beat_q==47)begin beat_q<=0;state_q<=S_W_REQ;end else begin beat_q<=beat_q+1;state_q<=S_X_REQ;end
        end
        S_W_REQ:if(l2_rd_valid_o&&l2_rd_ready_i)state_q<=S_W_RSP;
        S_W_RSP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin
          for(seq_j=0;seq_j<16;seq_j++)w_q[(beat_q*16+seq_j)*32+:32]<=l2_rsp_data_i[seq_j*32+:32];
          read_beats_o<=read_beats_o+1;if(beat_q==95)begin beat_q<=0;state_q<=S_SFU_REQ;end else begin beat_q<=beat_q+1;state_q<=S_W_REQ;end
        end
        S_SFU_REQ:if(sfu_payload_valid_o&&sfu_payload_ready_i)state_q<=S_SFU_RSP;
        S_SFU_RSP:if(sfu_out_valid_i&&sfu_out_ready_o)begin y_q<=sfu_y_i;beat_q<=0;state_q<=S_NORM_WR;end
        S_NORM_WR:if(l2_wr_valid_o&&l2_wr_ready_i)begin write_beats_o<=write_beats_o+1;if(beat_q==47)begin k_q<=0;state_q<=S_Q_REQ;end else beat_q<=beat_q+1;end
        S_NORM_RD_REQ:if(l2_rd_valid_o&&l2_rd_ready_i)state_q<=S_NORM_RD_RSP;
        S_NORM_RD_RSP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin
          for(seq_j=0;seq_j<32;seq_j++)y_q[(beat_q*32+seq_j)*32+:32]<={l2_rsp_data_i[seq_j*16+:16],16'd0};
          read_beats_o<=read_beats_o+1;if(beat_q==47)begin k_q<=0;state_q<=S_Q_REQ;end else begin beat_q<=beat_q+1;state_q<=S_NORM_RD_REQ;end
        end
        S_Q_REQ:if(l2_rd_valid_o&&l2_rd_ready_i)state_q<=S_Q_RSP;
        S_Q_RSP:if(l2_rsp_valid_i&&l2_rsp_ready_o)begin q_weight_q<=l2_rsp_data_i;read_beats_o<=read_beats_o+1;state_q<=S_M_REQ;end
        S_M_REQ:if(matrix_step_valid_o&&matrix_step_ready_i)begin if(k_q==1535)state_q<=S_M_WAIT;else begin k_q<=k_q+1;state_q<=S_Q_REQ;end end
        S_M_WAIT:if(final_seen_q)state_q<=S_OUT_WR;
        S_OUT_WR:if(l2_wr_valid_o&&l2_wr_ready_i)begin write_beats_o<=write_beats_o+1;state_q<=S_DONE;end
        S_DONE:state_q<=S_IDLE;
        default:state_q<=S_IDLE;
      endcase
    end
  end
endmodule
