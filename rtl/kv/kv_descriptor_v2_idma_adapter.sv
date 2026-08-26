// SPDX-License-Identifier: Apache-2.0
// Typed schema-v2 KV basic frontend feeding kv_idma_basic_core.
`timescale 1ns/1ps
module kv_descriptor_v2_idma_adapter #(
  parameter logic[63:0] STAGING_BASE=64'h0010_0000,
  parameter integer STAGING_BYTES=512*1024
)(
  input logic clk_i,input logic rst_ni,
  input logic cmd_valid_i,output logic cmd_ready_o,input logic[127:0]cmd_data_i,
  input logic[63:0]descriptor_base_i,
  output logic descriptor_req_valid_o,input logic descriptor_req_ready_i,
  output logic[23:0]descriptor_req_index_o,output logic[63:0]descriptor_req_byte_addr_o,
  input logic descriptor_rsp_valid_i,output logic descriptor_rsp_ready_o,
  input logic[127:0]descriptor_rsp_data_i,input logic descriptor_rsp_error_i,
  output logic idma_req_valid_o,input logic idma_req_ready_i,
  output logic[63:0]idma_src_addr_o,output logic[63:0]idma_dst_addr_o,
  output logic[31:0]idma_length_o,input logic idma_rsp_valid_i,
  output logic idma_rsp_ready_o,input logic idma_rsp_error_i,
  output logic event_valid_o,input logic event_ready_i,output logic[55:0]event_data_o
);
  localparam logic[23:0]NULL_INDEX=24'hffffff;
  localparam logic[7:0]OP_ALLOC=8'h40,OP_APPEND=8'h41,OP_GATHER=8'h42,OP_FREE=8'h44;
  localparam logic[7:0]ST_MALFORMED=2,ST_FETCH=3,ST_UNSUPPORTED=4;
  typedef enum logic[3:0]{S_IDLE,S_REQ,S_RSP,S_VALIDATE,S_CORE_REQ,S_CORE_WAIT,S_ERROR}state_e;
  state_e state_q;/* verilator lint_off UNUSEDSIGNAL */logic[127:0]command_q;
  /* verilator lint_on UNUSEDSIGNAL */logic[1:0]chain_q;logic[4:0]chain_count_q;
  logic[23:0]current_q,visited_q[0:15],next_index;logic duplicate;
  logic[2:0]have_base_q,have_shape_q,have_stride_q;logic have_kv_addr_q,have_kv_fmt_q;
  logic[63:0]tensor_addr_q[0:2];logic[17:0]shape_q[0:2][0:3];logic[3:0]dtype_q[0:2],rank_q[0:2];
  logic[11:0]sequence_q;logic[9:0]layer_q;logic[9:0]head_q;logic[23:0]token_start_q;
  logic[15:0]token_count_q;logic[3:0]page_log_q,format_q;logic[11:0]head_dim_q;
  logic[9:0]kv_heads_q;logic[7:0]error_status_q;logic core_valid,core_ready;
  logic role_tensor,role_meta,record_error;logic[7:0]record_error_status;
  logic core_event_valid,core_event_ready;logic[55:0]core_event_data;
  integer ci,si;
  assign cmd_ready_o=state_q==S_IDLE;assign next_index=descriptor_rsp_data_i[55:32];
  assign descriptor_req_valid_o=state_q==S_REQ&&!duplicate&&chain_count_q<16;
  assign descriptor_req_index_o=current_q;
  assign descriptor_req_byte_addr_o=descriptor_base_i+{36'd0,current_q,4'b0};
  assign descriptor_rsp_ready_o=state_q==S_RSP;
  assign core_valid=state_q==S_CORE_REQ;
  assign event_valid_o=state_q==S_ERROR||core_event_valid;
  assign event_data_o=state_q==S_ERROR?{command_q[55:40],error_status_q,3'd4,29'd0}:core_event_data;
  assign core_event_ready=state_q==S_CORE_WAIT&&event_ready_i;
  always_comb begin duplicate=0;for(ci=0;ci<16;ci++)if(ci<chain_count_q&&visited_q[ci]==current_q)duplicate=1;end
  function automatic logic tensor_role(input logic[7:0]op,input logic[1:0]c);
    tensor_role=(op==OP_APPEND&&(c==0||c==1))||(op==OP_GATHER&&c==2);
  endfunction
  function automatic logic metadata_role(input logic[7:0]op,input logic[1:0]c);
    metadata_role=(op==OP_APPEND&&c==2)||((op==OP_GATHER||op==OP_ALLOC||op==OP_FREE)&&c==0);
  endfunction
  always_comb begin
    role_tensor=tensor_role(command_q[7:0],chain_q);role_meta=metadata_role(command_q[7:0],chain_q);
    record_error=0;record_error_status=ST_MALFORMED;
    if(descriptor_rsp_error_i)begin record_error=1;record_error_status=ST_FETCH;end
    else if(descriptor_rsp_data_i[31:8]!=0)record_error=1;
    else if(role_tensor)case(descriptor_rsp_data_i[7:0])
      8'h01:record_error=have_base_q[chain_q];8'h02,8'h03:record_error=0;
      default:begin record_error=1;record_error_status=ST_UNSUPPORTED;end
    endcase
    else if(role_meta)case(descriptor_rsp_data_i[7:0])
      8'h30:record_error=have_kv_addr_q;8'h31:record_error=have_kv_fmt_q;
      default:begin record_error=1;record_error_status=ST_UNSUPPORTED;end
    endcase
    else record_error=1;
  end
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin state_q<=S_IDLE;command_q<=0;chain_q<=0;chain_count_q<=0;current_q<=NULL_INDEX;
      have_base_q<=0;have_shape_q<=0;have_stride_q<=0;have_kv_addr_q<=0;have_kv_fmt_q<=0;
      sequence_q<=0;layer_q<=0;head_q<=0;token_start_q<=0;token_count_q<=0;
      page_log_q<=0;format_q<=0;head_dim_q<=0;kv_heads_q<=0;error_status_q<=0;
      for(si=0;si<16;si++)visited_q[si]<=NULL_INDEX;
    end else case(state_q)
      S_IDLE:if(cmd_valid_i&&cmd_ready_o)begin
        command_q<=cmd_data_i;have_base_q<=0;have_shape_q<=0;have_stride_q<=0;
        have_kv_addr_q<=0;have_kv_fmt_q<=0;error_status_q<=0;
        chain_q<=0;chain_count_q<=0;current_q<=cmd_data_i[79:56];
        for(si=0;si<16;si++)visited_q[si]<=NULL_INDEX;
        if(cmd_data_i[10:8]!=3'd4||!((cmd_data_i[7:0]==OP_ALLOC)||(cmd_data_i[7:0]==OP_APPEND)||
           (cmd_data_i[7:0]==OP_GATHER)||(cmd_data_i[7:0]==OP_FREE))||
           cmd_data_i[79:56]==NULL_INDEX)begin error_status_q<=ST_MALFORMED;state_q<=S_ERROR;end
        else state_q<=S_REQ;
      end
      S_REQ:begin
        if(duplicate||chain_count_q>=16)begin error_status_q<=ST_MALFORMED;state_q<=S_ERROR;end
        else if(descriptor_req_valid_o&&descriptor_req_ready_i)state_q<=S_RSP;
      end
      S_RSP:if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o)begin
        if(record_error)begin error_status_q<=record_error_status;state_q<=S_ERROR;end
        else begin
        if(role_tensor)begin
          case(descriptor_rsp_data_i[7:0])
            8'h01:begin
              have_base_q[chain_q]<=1;tensor_addr_q[chain_q]<={8'd0,descriptor_rsp_data_i[127:120],descriptor_rsp_data_i[103:56]};
              dtype_q[chain_q]<=descriptor_rsp_data_i[111:108];rank_q[chain_q]<=descriptor_rsp_data_i[119:116];end
            8'h02:if(!have_shape_q[chain_q])begin have_shape_q[chain_q]<=1;
              shape_q[chain_q][0]<=descriptor_rsp_data_i[73:56];shape_q[chain_q][1]<=descriptor_rsp_data_i[91:74];
              shape_q[chain_q][2]<=descriptor_rsp_data_i[109:92];shape_q[chain_q][3]<=descriptor_rsp_data_i[127:110];end
            8'h03:have_stride_q[chain_q]<=1;
            default:begin end
          endcase
        end else if(role_meta)begin
          case(descriptor_rsp_data_i[7:0])
            8'h30:begin
              have_kv_addr_q<=1;sequence_q<=descriptor_rsp_data_i[67:56];layer_q<=descriptor_rsp_data_i[77:68];
              head_q<=descriptor_rsp_data_i[87:78];token_start_q<=descriptor_rsp_data_i[111:88];token_count_q<=descriptor_rsp_data_i[127:112];end
            8'h31:begin
              have_kv_fmt_q<=1;page_log_q<=descriptor_rsp_data_i[83:80];head_dim_q<=descriptor_rsp_data_i[95:84];
              kv_heads_q<=descriptor_rsp_data_i[105:96];format_q<=descriptor_rsp_data_i[119:116];end
            default:begin end
          endcase
        end
        visited_q[chain_count_q[3:0]]<=current_q;
        if(next_index!=NULL_INDEX)begin current_q<=next_index;chain_count_q<=chain_count_q+1'b1;state_q<=S_REQ;end
          else if(command_q[7:0]==OP_APPEND&&chain_q<2)begin
            chain_q<=chain_q+1'b1;current_q<=chain_q==0?command_q[103:80]:command_q[127:104];
            chain_count_q<=0;for(si=0;si<16;si++)visited_q[si]<=NULL_INDEX;
            if((chain_q==0?command_q[103:80]:command_q[127:104])==NULL_INDEX)begin
              error_status_q<=ST_MALFORMED;state_q<=S_ERROR;end else state_q<=S_REQ;end
          else if(command_q[7:0]==OP_GATHER&&chain_q==0)begin
            chain_q<=2;current_q<=command_q[127:104];chain_count_q<=0;
            for(si=0;si<16;si++)visited_q[si]<=NULL_INDEX;
            if(command_q[127:104]==NULL_INDEX)begin error_status_q<=ST_MALFORMED;state_q<=S_ERROR;end
            else state_q<=S_REQ;end
          else state_q<=S_VALIDATE;
        end
      end
      S_VALIDATE:begin
        if(!have_kv_addr_q||!have_kv_fmt_q||sequence_q!=0||layer_q!=0||head_q!=0||
           page_log_q!=4||format_q!=0||kv_heads_q!=1||head_dim_q==0||head_dim_q>256||
           (command_q[7:0]==OP_APPEND&&(command_q[103:80]==NULL_INDEX||command_q[127:104]==NULL_INDEX))||
           (command_q[7:0]==OP_GATHER&&(command_q[103:80]!=NULL_INDEX||command_q[127:104]==NULL_INDEX))||
           ((command_q[7:0]==OP_ALLOC||command_q[7:0]==OP_FREE)&&
             (command_q[103:80]!=NULL_INDEX||command_q[127:104]!=NULL_INDEX))||
           (command_q[7:0]==OP_APPEND&&(!(&have_base_q[1:0])||!(&have_shape_q[1:0])||
             !(&have_stride_q[1:0])||dtype_q[0]!=2||dtype_q[1]!=2||
             rank_q[0]!=3||rank_q[1]!=3||shape_q[0][0]!={2'd0,token_count_q}||
             shape_q[1][0]!={2'd0,token_count_q}||shape_q[0][1]!=1||shape_q[1][1]!=1||
             shape_q[0][2]!={6'd0,head_dim_q}||shape_q[1][2]!={6'd0,head_dim_q}))||
           (command_q[7:0]==OP_GATHER&&(!have_base_q[2]||!have_shape_q[2]||!have_stride_q[2]||
             dtype_q[2]!=2||rank_q[2]!=4||shape_q[2][0]!=2||
             shape_q[2][1]!={2'd0,token_count_q}||shape_q[2][2]!=1||
             shape_q[2][3]!={6'd0,head_dim_q})))begin
          error_status_q<=ST_UNSUPPORTED;state_q<=S_ERROR;
        end else state_q<=S_CORE_REQ;
      end
      S_CORE_REQ:if(core_valid&&core_ready)state_q<=S_CORE_WAIT;
      S_CORE_WAIT:if(core_event_valid&&core_event_ready)state_q<=S_IDLE;
      S_ERROR:if(event_valid_o&&event_ready_i)state_q<=S_IDLE;
      default:state_q<=S_IDLE;
    endcase
  end
  kv_idma_basic_core #(.STAGING_BASE(STAGING_BASE),.STAGING_BYTES(STAGING_BYTES))u_core(
    .clk_i,.rst_ni,.op_valid_i(core_valid),.op_ready_o(core_ready),
    .opcode_i(command_q[7:0]),.event_id_i(command_q[55:40]),.sequence_id_i(sequence_q),
    .layer_id_i(layer_q),.token_start_i(token_start_q),.token_count_i(token_count_q),
    .head_dim_i(head_dim_q),.k_addr_i(tensor_addr_q[0]),.v_addr_i(tensor_addr_q[1]),
    .output_addr_i(tensor_addr_q[2]),.idma_req_valid_o,.idma_req_ready_i,
    .idma_src_addr_o,.idma_dst_addr_o,.idma_length_o,.idma_rsp_valid_i,
    .idma_rsp_ready_o,.idma_rsp_error_i,.event_valid_o(core_event_valid),
    .event_ready_i(core_event_ready),.event_data_o(core_event_data));
endmodule
