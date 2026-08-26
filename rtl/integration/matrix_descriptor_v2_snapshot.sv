// SPDX-License-Identifier: Apache-2.0
// Fetches and snapshots src0/src1/dst plus optional matrix_aux.bias_index.
// No downstream record is exposed until every referenced chain is complete.
`timescale 1ns/1ps
module matrix_descriptor_v2_snapshot #(
  parameter integer MAX_CHAIN_RECORDS=16,
  parameter integer MAX_TOTAL_RECORDS=64
)(
  input logic clk_i,input logic rst_ni,
  input logic cmd_valid_i,output logic cmd_ready_o,input logic[127:0] cmd_data_i,
  input logic[63:0] descriptor_base_i,
  output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,
  output logic[23:0] descriptor_req_index_o,output logic[63:0] descriptor_req_byte_addr_o,
  input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,
  input logic[127:0] descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
  output logic snapshot_valid_o,input logic snapshot_ready_i,
  output logic snapshot_legal_o,output logic[7:0] snapshot_status_o,
  output logic[127:0] snapshot_command_o,output logic[6:0] snapshot_record_count_o,
  output logic record_valid_o,input logic record_ready_i,
  output logic[1:0] record_chain_o,output logic[23:0] record_index_o,
  output logic[127:0] record_data_o,output logic record_first_o,output logic record_last_o
);
  localparam logic[23:0] NULL_INDEX=24'hffffff;
  localparam logic[7:0] STATUS_OK=0,STATUS_MALFORMED=2,STATUS_FETCH=3,STATUS_UNSUPPORTED=4;
  localparam logic[4:0] MAX_CHAIN_COUNT=5'(MAX_CHAIN_RECORDS);
  localparam logic[6:0] MAX_TOTAL_COUNT=7'(MAX_TOTAL_RECORDS);
  typedef enum logic[2:0]{S_IDLE,S_REQ,S_RSP,S_HEADER,S_REPLAY}state_e;
  state_e state_q;
  logic[127:0] command_q;
  logic[23:0] roots_q[0:3],current_q,bias_root_q;
  logic[1:0] chain_q;
  logic[4:0] chain_count_q;
  logic[6:0] total_count_q,replay_q;
  logic[23:0] visited_q[0:MAX_CHAIN_RECORDS-1];
  logic[127:0] cache_data_q[0:MAX_TOTAL_RECORDS-1];
  logic[23:0] cache_index_q[0:MAX_TOTAL_RECORDS-1];
  logic[1:0] cache_chain_q[0:MAX_TOTAL_RECORDS-1];
  logic cache_first_q[0:MAX_TOTAL_RECORDS-1],cache_last_q[0:MAX_TOTAL_RECORDS-1];
  logic aux_seen_q,duplicate_index,known_type;
  logic[7:0] status_q;
  logic[23:0] next_index;
  integer comb_i,seq_i;

  assign cmd_ready_o=state_q==S_IDLE;
  assign descriptor_req_valid_o=state_q==S_REQ&&!duplicate_index&&
                                chain_count_q<MAX_CHAIN_COUNT&&total_count_q<MAX_TOTAL_COUNT;
  assign descriptor_req_index_o=current_q;
  assign descriptor_req_byte_addr_o=descriptor_base_i+{36'd0,current_q,4'b0};
  assign descriptor_rsp_ready_o=state_q==S_RSP;
  assign next_index=descriptor_rsp_data_i[55:32];
  assign snapshot_valid_o=state_q==S_HEADER;
  assign snapshot_legal_o=status_q==STATUS_OK;
  assign snapshot_status_o=status_q;
  assign snapshot_command_o=command_q;
  assign snapshot_record_count_o=total_count_q;
  assign record_valid_o=state_q==S_REPLAY;
  assign record_chain_o=cache_chain_q[replay_q[5:0]];
  assign record_index_o=cache_index_q[replay_q[5:0]];
  assign record_data_o=cache_data_q[replay_q[5:0]];
  assign record_first_o=cache_first_q[replay_q[5:0]];
  assign record_last_o=cache_last_q[replay_q[5:0]];

  always_comb begin
    duplicate_index=0;
    for(comb_i=0;comb_i<MAX_CHAIN_RECORDS;comb_i++)
      if(comb_i<chain_count_q&&visited_q[comb_i]==current_q)duplicate_index=1;
    case(descriptor_rsp_data_i[7:0])
      8'h01,8'h02,8'h03,8'h10,8'h11,8'h12,8'h20,8'h30,8'h31,
      8'h40,8'h50,8'h60:known_type=1;
      default:known_type=0;
    endcase
  end

  task automatic start_chain(input logic[1:0] chain,input logic[23:0] root);
    integer task_i;
    begin
      chain_q<=chain;current_q<=root;chain_count_q<=0;
      for(task_i=0;task_i<MAX_CHAIN_RECORDS;task_i++)visited_q[task_i]<=NULL_INDEX;
      state_q<=root==NULL_INDEX?S_HEADER:S_REQ;
      if(root==NULL_INDEX)status_q<=STATUS_MALFORMED;
    end
  endtask

  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin
      state_q<=S_IDLE;command_q<='0;chain_q<=0;chain_count_q<=0;total_count_q<=0;
      replay_q<=0;current_q<=NULL_INDEX;bias_root_q<=NULL_INDEX;aux_seen_q<=0;
      status_q<=STATUS_OK;
      for(seq_i=0;seq_i<MAX_CHAIN_RECORDS;seq_i++)visited_q[seq_i]<=NULL_INDEX;
    end else case(state_q)
      S_IDLE:if(cmd_valid_i&&cmd_ready_o)begin
        command_q<=cmd_data_i;roots_q[0]<=cmd_data_i[79:56];roots_q[1]<=cmd_data_i[103:80];
        roots_q[2]<=cmd_data_i[127:104];roots_q[3]<=NULL_INDEX;
        total_count_q<=0;replay_q<=0;bias_root_q<=NULL_INDEX;aux_seen_q<=0;status_q<=STATUS_OK;
        chain_q<=0;chain_count_q<=0;current_q<=cmd_data_i[79:56];
        for(seq_i=0;seq_i<MAX_CHAIN_RECORDS;seq_i++)visited_q[seq_i]<=NULL_INDEX;
        if(cmd_data_i[10:8]!=3'd2||cmd_data_i[79:56]==NULL_INDEX||
           cmd_data_i[103:80]==NULL_INDEX||cmd_data_i[127:104]==NULL_INDEX)begin
          status_q<=STATUS_MALFORMED;state_q<=S_HEADER;
        end else state_q<=S_REQ;
      end
      S_REQ:begin
        if(duplicate_index||chain_count_q>=MAX_CHAIN_COUNT||total_count_q>=MAX_TOTAL_COUNT)begin
          status_q<=STATUS_MALFORMED;state_q<=S_HEADER;
        end else if(descriptor_req_valid_o&&descriptor_req_ready_i)state_q<=S_RSP;
      end
      S_RSP:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin
        if(descriptor_rsp_error_i)begin status_q<=STATUS_FETCH;state_q<=S_HEADER;end
        else if(descriptor_rsp_data_i[31:8]!=0)begin status_q<=STATUS_MALFORMED;state_q<=S_HEADER;end
        else if(!known_type)begin status_q<=STATUS_UNSUPPORTED;state_q<=S_HEADER;end
        else if(descriptor_rsp_data_i[7:0]==8'h12&&(chain_q!=0||aux_seen_q))begin
          status_q<=STATUS_MALFORMED;state_q<=S_HEADER;
        end else begin
          cache_data_q[total_count_q[5:0]]<=descriptor_rsp_data_i;
          cache_index_q[total_count_q[5:0]]<=current_q;cache_chain_q[total_count_q[5:0]]<=chain_q;
          cache_first_q[total_count_q[5:0]]<=chain_count_q==0;cache_last_q[total_count_q[5:0]]<=next_index==NULL_INDEX;
          visited_q[chain_count_q[3:0]]<=current_q;total_count_q<=total_count_q+1'b1;
          if(descriptor_rsp_data_i[7:0]==8'h12)begin
            aux_seen_q<=1;bias_root_q<=descriptor_rsp_data_i[79:56];roots_q[3]<=descriptor_rsp_data_i[79:56];
          end
          if(next_index!=NULL_INDEX)begin
            current_q<=next_index;chain_count_q<=chain_count_q+1'b1;state_q<=S_REQ;
          end else if(chain_q<2)begin
            start_chain(chain_q+1'b1,roots_q[chain_q+1'b1]);
          end else if(chain_q==2&&aux_seen_q&&bias_root_q!=NULL_INDEX)begin
            start_chain(3,bias_root_q);
          end else begin
            if(!aux_seen_q)status_q<=STATUS_MALFORMED;
            state_q<=S_HEADER;
          end
        end
      end
      S_HEADER:if(snapshot_valid_o&&snapshot_ready_i)begin
        if(status_q==STATUS_OK&&total_count_q!=0)begin replay_q<=0;state_q<=S_REPLAY;end
        else state_q<=S_IDLE;
      end
      S_REPLAY:if(record_valid_o&&record_ready_i)begin
        if(replay_q+1'b1==total_count_q)state_q<=S_IDLE;
        else replay_q<=replay_q+1'b1;
      end
      default:state_q<=S_IDLE;
    endcase
  end
endmodule
