// SPDX-License-Identifier: Apache-2.0
module operator_dma_endpoint_v3 (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        req_valid_i,
  output logic        req_ready_o,
  input  logic [7:0]  req_opcode_i,
  input  logic [15:0] req_tag_i,
  input  logic [7:0]  req_parent_phase_i,
  input  logic [7:0]  req_terminal_phase_i,
  input  logic [23:0] req_src0_i,
  input  logic [23:0] req_dst_i,
  input  logic [15:0] req_rows_i,
  output logic        descriptor_req_valid_o,
  input  logic        descriptor_req_ready_i,
  output logic [23:0] descriptor_req_index_o,
  output logic        descriptor_req_destination_o,
  input  logic        descriptor_rsp_valid_i,
  output logic        descriptor_rsp_ready_o,
  input  logic [7:0]  descriptor_rsp_status_i,
  input  logic [63:0] descriptor_rsp_address_i,
  input  logic [31:0] descriptor_rsp_row_bytes_i,
  input  logic [31:0] descriptor_rsp_rows_i,
  input  logic [31:0] descriptor_rsp_stride_i,
  output logic        idma_req_valid_o,
  input  logic        idma_req_ready_i,
  output logic [63:0] idma_src_addr_o,
  output logic [63:0] idma_dst_addr_o,
  output logic [31:0] idma_length_o,
  input  logic        idma_rsp_valid_i,
  output logic        idma_rsp_ready_o,
  input  logic        idma_rsp_error_i,
  output logic        completion_valid_o,
  input  logic        completion_ready_i,
  output logic [15:0] completion_tag_o,
  output logic [7:0]  completion_parent_phase_o,
  output logic [7:0]  completion_terminal_phase_o,
  output logic [7:0]  completion_status_o,
  output logic [31:0] flat_requests_o
);
  localparam logic [7:0] OP_READ=8'h10, OP_WRITE=8'h11, OP_GATHER=8'h12, OP_SCATTER=8'h13;
  localparam logic [3:0] S_IDLE=0, S_SRC_REQ=1, S_SRC_RSP=2, S_DST_REQ=3,
    S_DST_RSP=4, S_EXPAND_REQ=5, S_EXPAND_WAIT=6, S_REPORT=7;
  logic [3:0] state_q;
  logic [7:0] opcode_q, status_q;
  logic [15:0] tag_q;
  logic [7:0] parent_q, terminal_q;
  logic [23:0] src_index_q, dst_index_q;
  logic [15:0] request_rows_q;
  logic [63:0] src_address_q, dst_address_q;
  logic [31:0] src_row_bytes_q, dst_row_bytes_q, src_rows_q, dst_rows_q;
  logic [31:0] src_stride_q, dst_stride_q;
  logic expand_req_ready, expand_rsp_valid, expand_rsp_ready, expand_rsp_error;
  logic [1:0] expand_kind;
  logic [31:0] row_bytes, rows;

  assign req_ready_o = state_q == S_IDLE;
  assign descriptor_req_valid_o = state_q == S_SRC_REQ || state_q == S_DST_REQ;
  assign descriptor_req_index_o = state_q == S_DST_REQ ? dst_index_q : src_index_q;
  assign descriptor_req_destination_o = state_q == S_DST_REQ;
  assign descriptor_rsp_ready_o = state_q == S_SRC_RSP || state_q == S_DST_RSP;
  assign expand_kind = opcode_q == OP_READ ? 2'd0 : opcode_q == OP_GATHER ? 2'd1 :
                       opcode_q == OP_WRITE ? 2'd2 : 2'd3;
  assign row_bytes = src_row_bytes_q < dst_row_bytes_q ? src_row_bytes_q : dst_row_bytes_q;
  assign rows = request_rows_q != 0 ? {16'd0,request_rows_q} :
                src_rows_q < dst_rows_q ? src_rows_q : dst_rows_q;
  assign expand_rsp_ready = state_q == S_EXPAND_WAIT;
  assign completion_valid_o = state_q == S_REPORT;
  assign completion_tag_o = tag_q;
  assign completion_parent_phase_o = parent_q;
  assign completion_terminal_phase_o = terminal_q;
  assign completion_status_o = status_q;

  qwen2_tile_idma_expand u_expand (
    .clk_i,
    .rst_ni,
    .req_valid_i(state_q == S_EXPAND_REQ),
    .req_ready_o(expand_req_ready),
    .req_kind_i(expand_kind),
    .src_addr_i(src_address_q),
    .dst_addr_i(dst_address_q),
    .row_bytes_i(row_bytes),
    .rows_i(rows),
    .src_stride_i(src_stride_q),
    .dst_stride_i(dst_stride_q),
    .rsp_valid_o(expand_rsp_valid),
    .rsp_ready_i(expand_rsp_ready),
    .rsp_error_o(expand_rsp_error),
    .idma_req_valid_o,
    .idma_req_ready_i,
    .idma_src_addr_o,
    .idma_dst_addr_o,
    .idma_length_o,
    .idma_rsp_valid_i,
    .idma_rsp_ready_o,
    .idma_rsp_error_i,
    .flat_requests_o,
    .local_source_o()
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q<=S_IDLE; opcode_q<=0; status_q<=0; tag_q<=0; parent_q<=0; terminal_q<=0;
      src_index_q<=0; dst_index_q<=0; request_rows_q<=0; src_address_q<=0; dst_address_q<=0;
      src_row_bytes_q<=0; dst_row_bytes_q<=0; src_rows_q<=0; dst_rows_q<=0;
      src_stride_q<=0; dst_stride_q<=0;
    end else begin
      case(state_q)
        S_IDLE: if(req_valid_i&&req_ready_o) begin
          opcode_q<=req_opcode_i;tag_q<=req_tag_i;parent_q<=req_parent_phase_i;
          terminal_q<=req_terminal_phase_i;src_index_q<=req_src0_i;dst_index_q<=req_dst_i;
          request_rows_q<=req_rows_i;status_q<=0;
          if(req_opcode_i==OP_READ||req_opcode_i==OP_WRITE||req_opcode_i==OP_GATHER||req_opcode_i==OP_SCATTER)
            state_q<=S_SRC_REQ;
          else begin status_q<=8'd4;state_q<=S_REPORT;end
        end
        S_SRC_REQ: if(descriptor_req_valid_o&&descriptor_req_ready_i) state_q<=S_SRC_RSP;
        S_SRC_RSP: if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o) begin
          if(descriptor_rsp_status_i!=0) begin status_q<=descriptor_rsp_status_i;state_q<=S_REPORT;end
          else begin src_address_q<=descriptor_rsp_address_i;src_row_bytes_q<=descriptor_rsp_row_bytes_i;
            src_rows_q<=descriptor_rsp_rows_i;src_stride_q<=descriptor_rsp_stride_i;state_q<=S_DST_REQ;end
        end
        S_DST_REQ: if(descriptor_req_valid_o&&descriptor_req_ready_i) state_q<=S_DST_RSP;
        S_DST_RSP: if(descriptor_rsp_valid_i&&descriptor_rsp_ready_o) begin
          if(descriptor_rsp_status_i!=0) begin status_q<=descriptor_rsp_status_i;state_q<=S_REPORT;end
          else begin dst_address_q<=descriptor_rsp_address_i;dst_row_bytes_q<=descriptor_rsp_row_bytes_i;
            dst_rows_q<=descriptor_rsp_rows_i;dst_stride_q<=descriptor_rsp_stride_i;state_q<=S_EXPAND_REQ;end
        end
        S_EXPAND_REQ: if(expand_req_ready) state_q<=S_EXPAND_WAIT;
        S_EXPAND_WAIT: if(expand_rsp_valid) begin status_q<=expand_rsp_error?8'd7:8'd0;state_q<=S_REPORT;end
        S_REPORT: if(completion_valid_o&&completion_ready_i) state_q<=S_IDLE;
        default: state_q<=S_IDLE;
      endcase
    end
  end
endmodule
