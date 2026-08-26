// SPDX-License-Identifier: Apache-2.0
// Semantic decoder for a fully snapshotted schema-v2 Matrix transaction.
`timescale 1ns/1ps
module matrix_descriptor_v2_decode(
  input logic clk_i,input logic rst_ni,
  input logic snapshot_valid_i,output logic snapshot_ready_o,
  input logic snapshot_legal_i,input logic[7:0] snapshot_status_i,
  input logic[127:0] snapshot_command_i,input logic[6:0] snapshot_record_count_i,
  input logic record_valid_i,output logic record_ready_o,input logic[1:0] record_chain_i,
  input logic[23:0] record_index_i,input logic[127:0] record_data_i,
  input logic record_first_i,input logic record_last_i,
  output logic context_valid_o,input logic context_ready_i,
  output logic context_legal_o,output logic[7:0] context_status_o,
  output logic[127:0] context_command_o,
  output logic[4*64-1:0] tensor_addr_o,
  output logic[4*4*18-1:0] tensor_shape_o,
  output logic[4*3*24-1:0] tensor_stride_o,
  output logic[4*12-1:0] tensor_meta_o,
  output logic[71:0] matrix_op_payload_o,output logic[71:0] matrix_aux_payload_o,
  output logic conv_valid_o,output logic[71:0] conv_payload_o,
  output logic[1:0] quant_valid_o,output logic[2*72-1:0] quant_payload_o
);
  localparam logic[7:0] STATUS_OK=0,STATUS_MALFORMED=2,STATUS_UNSUPPORTED=4;
  typedef enum logic[2:0]{S_IDLE,S_COLLECT,S_VALIDATE,S_CONTEXT}state_e;
  state_e state_q;
  logic[127:0] command_q;
  logic[6:0] expected_q,received_q;
  logic[3:0] have_base_q,have_shape_q,have_stride_q;
  logic[3:0] chain_started_q;
  logic have_op_q,have_aux_q,have_conv_q;logic[1:0] have_quant_q;
  logic semantic_error_q,placement_error,reserved_error,replay_protocol_error,required_ok;
  logic[7:0] status_q;
  logic[4*64-1:0] addr_q;
  logic[4*4*18-1:0] shape_q;
  logic[4*3*24-1:0] stride_q;
  logic[4*12-1:0] meta_q;
  logic[71:0] op_q,aux_q,conv_q;logic[2*72-1:0] quant_q;
  logic[7:0] typ;
  logic[1:0] chain;

  assign typ=record_data_i[7:0];assign chain=record_chain_i;
  assign snapshot_ready_o=state_q==S_IDLE;
  assign record_ready_o=state_q==S_COLLECT;
  assign context_valid_o=state_q==S_CONTEXT;
  assign context_legal_o=status_q==STATUS_OK;
  assign context_status_o=status_q;assign context_command_o=command_q;
  assign tensor_addr_o=addr_q;assign tensor_shape_o=shape_q;
  assign tensor_stride_o=stride_q;assign tensor_meta_o=meta_q;
  assign matrix_op_payload_o=op_q;assign matrix_aux_payload_o=aux_q;
  assign conv_valid_o=have_conv_q;assign conv_payload_o=conv_q;
  assign quant_valid_o=have_quant_q;assign quant_payload_o=quant_q;

  always_comb begin
    placement_error=0;reserved_error=0;replay_protocol_error=0;
    case(typ)
      8'h01:placement_error=have_base_q[chain];
      8'h02:placement_error=0;
      8'h03:placement_error=0;
      8'h10:placement_error=chain!=0||have_op_q;
      8'h11:placement_error=chain!=0||have_conv_q;
      8'h12:placement_error=chain!=0||have_aux_q;
      8'h40:placement_error=(chain!=1&&chain!=2)||
                                ((chain==1)&&have_quant_q[0])||((chain==2)&&have_quant_q[1]);
      default:placement_error=1;
    endcase
    if(record_data_i[31:8]!=0)replay_protocol_error=1;
    if(record_last_i!=(record_data_i[55:32]==24'hffffff))replay_protocol_error=1;
    if(record_first_i==chain_started_q[chain])replay_protocol_error=1;
    if(record_first_i)case(chain)
      0:if(record_index_i!=command_q[79:56])replay_protocol_error=1;
      1:if(record_index_i!=command_q[103:80])replay_protocol_error=1;
      2:if(record_index_i!=command_q[127:104])replay_protocol_error=1;
      default:if(record_index_i!=aux_q[23:0])replay_protocol_error=1;
    endcase
    case(typ)
      8'h10:reserved_error=|record_data_i[127:120];
      8'h12:reserved_error=|record_data_i[127:126]||record_data_i[125:118]==0;
      8'h40:reserved_error=|record_data_i[127:122];
      default:reserved_error=0;
    endcase
    required_ok=(&have_base_q[2:0])&&(&have_shape_q[2:0])&&
                (&have_stride_q[2:0])&&have_op_q&&have_aux_q;
    if(have_base_q[3]||have_shape_q[3]||have_stride_q[3])
      required_ok=required_ok&&have_base_q[3]&&have_shape_q[3]&&have_stride_q[3];
    if(command_q[7:0]==8'h22)required_ok=required_ok&&have_conv_q&&have_base_q[3];
    else required_ok=required_ok&&!have_conv_q;
  end

  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin
      state_q<=S_IDLE;command_q<='0;expected_q<=0;received_q<=0;status_q<=STATUS_OK;
      have_base_q<=0;have_shape_q<=0;have_stride_q<=0;chain_started_q<=0;have_op_q<=0;have_aux_q<=0;
      have_conv_q<=0;have_quant_q<=0;semantic_error_q<=0;addr_q<=0;shape_q<=0;
      stride_q<=0;meta_q<=0;op_q<=0;aux_q<=0;conv_q<=0;quant_q<=0;
    end else case(state_q)
      S_IDLE:if(snapshot_valid_i&&snapshot_ready_o)begin
        command_q<=snapshot_command_i;expected_q<=snapshot_record_count_i;received_q<=0;
        have_base_q<=0;have_shape_q<=0;have_stride_q<=0;chain_started_q<=0;have_op_q<=0;have_aux_q<=0;
        have_conv_q<=0;have_quant_q<=0;semantic_error_q<=0;addr_q<=0;shape_q<=0;
        stride_q<=0;meta_q<=0;op_q<=0;aux_q<=0;conv_q<=0;quant_q<=0;
        status_q<=snapshot_legal_i?STATUS_OK:snapshot_status_i;
        state_q<=snapshot_legal_i&&snapshot_record_count_i!=0?S_COLLECT:S_CONTEXT;
      end
      S_COLLECT:if(record_valid_i&&record_ready_o)begin
        received_q<=received_q+1'b1;
        chain_started_q[chain]<=1;
        if(placement_error||reserved_error||replay_protocol_error)semantic_error_q<=1;
        case(typ)
          8'h01:if(!have_base_q[chain])begin
            have_base_q[chain]<=1;
            addr_q[chain*64 +: 64]<={8'd0,record_data_i[127:120],record_data_i[103:56]};
            meta_q[chain*12 +: 12]<={record_data_i[119:116],record_data_i[115:112],record_data_i[111:108]};
          end
          8'h02:if(!have_shape_q[chain])begin
            have_shape_q[chain]<=1;
            shape_q[chain*72 +: 72]<={record_data_i[127:110],record_data_i[109:92],record_data_i[91:74],record_data_i[73:56]};
          end
          8'h03:if(!have_stride_q[chain])begin
            have_stride_q[chain]<=1;stride_q[chain*72 +: 72]<=record_data_i[127:56];
          end
          8'h10:if(chain==0&&!have_op_q)begin have_op_q<=1;op_q<=record_data_i[127:56];end
          8'h11:if(chain==0&&!have_conv_q)begin have_conv_q<=1;conv_q<=record_data_i[127:56];end
          8'h12:if(chain==0&&!have_aux_q)begin have_aux_q<=1;aux_q<=record_data_i[127:56];end
          8'h40:if(chain==1&&!have_quant_q[0])begin
            have_quant_q[0]<=1;quant_q[0 +: 72]<=record_data_i[127:56];
          end else if(chain==2&&!have_quant_q[1])begin
            have_quant_q[1]<=1;quant_q[72 +: 72]<=record_data_i[127:56];
          end
          default:begin end
        endcase
        if(received_q+1'b1==expected_q)state_q<=S_VALIDATE;
      end
      S_VALIDATE:begin
        if(semantic_error_q||!required_ok)status_q<=STATUS_MALFORMED;
        else if(op_q[57:56]>1||aux_q[25:24]==3)status_q<=STATUS_UNSUPPORTED;
        state_q<=S_CONTEXT;
      end
      S_CONTEXT:if(context_valid_o&&context_ready_i)state_q<=S_IDLE;
      default:state_q<=S_IDLE;
    endcase
  end
endmodule
