// SPDX-License-Identifier: Apache-2.0
// Fetch and validate the three typed descriptor chains selected by one frozen
// 128-bit Matrix command, then lower the supported resolved descriptor to the
// pinned Gemmini CUSTOM_3 program. No RoCC command is exposed until every
// required chain has terminated and passed the pre-issue checks.
`timescale 1ns/1ps
module gemmini_descriptor_sequencer (
  input  logic         clk_i,
  input  logic         rst_ni,

  input  logic         cmd_valid_i,
  output logic         cmd_ready_o,
  input  logic [127:0] cmd_data_i,
  input  logic [63:0]  descriptor_base_i,

  output logic         descriptor_req_valid_o,
  input  logic         descriptor_req_ready_i,
  output logic [23:0]  descriptor_req_index_o,
  output logic [63:0]  descriptor_req_byte_addr_o,
  input  logic         descriptor_rsp_valid_i,
  output logic         descriptor_rsp_ready_o,
  input  logic [127:0] descriptor_rsp_data_i,
  input  logic         descriptor_rsp_error_i,

  output logic         op_valid_o,
  input  logic         op_ready_i,
  output logic         op_first_o,
  output logic         op_last_o,
  output logic         op_legal_o,
  output logic [15:0]  op_event_id_o,
  output logic [6:0]   op_funct_o,
  output logic [63:0]  op_rs1_o,
  output logic [63:0]  op_rs2_o
);
  localparam logic [23:0] NULL_INDEX = 24'hff_ffff;
  localparam logic [7:0] OP_MATRIX_GEMM = 8'h20;
  localparam logic [2:0] ENGINE_MATRIX = 3'd2;
  localparam integer MAX_RECORDS = 16;
  localparam logic [4:0] MAX_RECORDS_COUNT = 5'd16;

  typedef enum logic [2:0] {
    S_IDLE, S_FETCH_REQ, S_FETCH_RSP, S_VALIDATE, S_EMIT, S_REJECT
  } state_e;
  state_e state_q;

  logic [127:0] command_q;
  logic [1:0] chain_q;
  logic [4:0] chain_count_q;
  logic [23:0] current_index_q;
  logic [23:0] visited_q [0:MAX_RECORDS-1];
  logic [3:0] op_index_q;

  logic [55:0] tensor_addr_q [0:2];
  logic [17:0] dim0_q [0:2], dim1_q [0:2];
  logic [23:0] stride0_q [0:2];
  logic [3:0] dtype_q [0:2], layout_q [0:2], rank_q [0:2];
  logic [2:0] have_base_q, have_shape_q, have_stride_q;
  logic have_matrix_op_q;
  logic [15:0] matrix_m_q, matrix_n_q;
  logic [23:0] matrix_k_q;
  logic [1:0] matrix_dataflow_q;
  logic matrix_transpose_a_q, matrix_transpose_b_q, matrix_accumulate_q;
  logic [2:0] matrix_quant_q;
  logic [7:0] matrix_reserved_q;

  logic duplicate_index;
  logic record_semantic_error;
  logic descriptor_fields_legal;
  logic [23:0] next_index;
  integer scan_i, reset_i;

  function automatic logic [63:0] pack_local_shape(
    input logic [31:0] local_addr,
    input logic [15:0] cols,
    input logic [15:0] rows
  );
    pack_local_shape = {rows, cols, local_addr};
  endfunction

  assign cmd_ready_o = (state_q == S_IDLE);
  // Never handshake a request that is already known to violate the chain
  // bound or revisit an earlier index.
  assign descriptor_req_valid_o = (state_q == S_FETCH_REQ) &&
                                  (chain_count_q < MAX_RECORDS_COUNT) && !duplicate_index;
  assign descriptor_req_index_o = current_index_q;
  assign descriptor_req_byte_addr_o = descriptor_base_i + {36'd0, current_index_q, 4'b0};
  assign descriptor_rsp_ready_o = (state_q == S_FETCH_RSP);
  assign next_index = descriptor_rsp_data_i[55:32];

  always_comb begin
    duplicate_index = 1'b0;
    for (scan_i = 0; scan_i < MAX_RECORDS; scan_i++)
      if (scan_i < chain_count_q && visited_q[scan_i] == current_index_q)
        duplicate_index = 1'b1;
  end

  always_comb begin
    unique case (descriptor_rsp_data_i[7:0])
      8'h01: record_semantic_error = have_base_q[chain_q];
      // shape4/stride3 may legally repeat for ranks larger than the first
      // record. The current single-tile lowerer consumes the first pair.
      8'h02: record_semantic_error = 1'b0;
      8'h03: record_semantic_error = descriptor_rsp_data_i[79];
      8'h10: record_semantic_error = have_matrix_op_q;
      default: record_semantic_error = 1'b1;
    endcase
  end

  assign descriptor_fields_legal =
    (&have_base_q) && (&have_shape_q) && (&have_stride_q) && have_matrix_op_q &&
    (command_q[10:8] == ENGINE_MATRIX) && (command_q[7:0] == OP_MATRIX_GEMM) &&
    (dtype_q[0] == 4'd1) && (dtype_q[1] == 4'd1) && (dtype_q[2] == 4'd1) &&
    (layout_q[0] == 4'd0) && (layout_q[1] == 4'd0) && (layout_q[2] == 4'd0) &&
    (rank_q[0] >= 2) && (rank_q[1] >= 2) && (rank_q[2] >= 2) &&
    (matrix_m_q >= 1) && (matrix_m_q <= 16) &&
    (matrix_n_q >= 1) && (matrix_n_q <= 16) &&
    (matrix_k_q >= 1) && (matrix_k_q <= 16) &&
    (dim0_q[0] == {2'd0, matrix_m_q}) && (dim1_q[0] == matrix_k_q[17:0]) &&
    (dim0_q[1] == matrix_k_q[17:0]) && (dim1_q[1] == {2'd0, matrix_n_q}) &&
    (dim0_q[2] == {2'd0, matrix_m_q}) && (dim1_q[2] == {2'd0, matrix_n_q}) &&
    (stride0_q[0] != 0) && (stride0_q[1] != 0) && (stride0_q[2] != 0) &&
    (matrix_dataflow_q == 2'd0) && !matrix_transpose_a_q &&
    !matrix_transpose_b_q && !matrix_accumulate_q && (matrix_quant_q == 0) &&
    (matrix_reserved_q == 0);

  always_comb begin
    op_valid_o = (state_q == S_EMIT) || (state_q == S_REJECT);
    op_first_o = (state_q == S_REJECT) || (op_index_q == 0);
    op_last_o = (state_q == S_REJECT) || (op_index_q == 8);
    op_legal_o = (state_q == S_EMIT);
    op_event_id_o = command_q[55:40];
    op_funct_o = '0;
    op_rs1_o = '0;
    op_rs2_o = '0;
    if (state_q == S_EMIT) begin
      unique case (op_index_q)
        0: begin // gemmini_config_ex(OS, unit A/C strides)
          op_funct_o = 7'd0;
          op_rs1_o = 64'h3f80_0000_0001_0000;
          op_rs2_o = 64'h0001_0000_0000_0000;
        end
        1: begin // config_st(C row stride)
          op_funct_o = 7'd0;
          op_rs1_o = 64'd2;
          op_rs2_o = {32'h3f80_0000, 8'd0, stride0_q[2]};
        end
        2: begin // config_ld(A row stride), channel zero
          op_funct_o = 7'd0;
          op_rs1_o = 64'h3f80_0000_0010_0101;
          op_rs2_o = {40'd0, stride0_q[0]};
        end
        3: begin // mvin A -> scratchpad row 0
          op_funct_o = 7'd2;
          op_rs1_o = {8'd0, tensor_addr_q[0]};
          op_rs2_o = pack_local_shape(32'h0000_0000, matrix_k_q[15:0], matrix_m_q);
        end
        4: begin // config_ld(B row stride), channel zero
          op_funct_o = 7'd0;
          op_rs1_o = 64'h3f80_0000_0010_0101;
          op_rs2_o = {40'd0, stride0_q[1]};
        end
        5: begin // mvin B -> scratchpad row 16
          op_funct_o = 7'd2;
          op_rs1_o = {8'd0, tensor_addr_q[1]};
          op_rs2_o = pack_local_shape(32'h0000_0010, matrix_n_q, matrix_k_q[15:0]);
        end
        6: begin // preload zero bias into C tile row 48
          op_funct_o = 7'd6;
          op_rs1_o = pack_local_shape(32'hffff_ffff, 16'd16, 16'd16);
          op_rs2_o = pack_local_shape(32'h0000_0030, matrix_n_q, matrix_m_q);
        end
        7: begin // compute_preloaded(A,B)
          op_funct_o = 7'd4;
          op_rs1_o = pack_local_shape(32'h0000_0000, matrix_k_q[15:0], matrix_m_q);
          op_rs2_o = pack_local_shape(32'h0000_0010, matrix_n_q, matrix_k_q[15:0]);
        end
        default: begin // mvout C
          op_funct_o = 7'd3;
          op_rs1_o = {8'd0, tensor_addr_q[2]};
          op_rs2_o = pack_local_shape(32'h0000_0030, matrix_n_q, matrix_m_q);
        end
      endcase
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      command_q <= '0;
      chain_q <= '0;
      chain_count_q <= '0;
      current_index_q <= NULL_INDEX;
      op_index_q <= '0;
      have_base_q <= '0;
      have_shape_q <= '0;
      have_stride_q <= '0;
      have_matrix_op_q <= 1'b0;
      matrix_m_q <= '0;
      matrix_n_q <= '0;
      matrix_k_q <= '0;
      matrix_dataflow_q <= '0;
      matrix_transpose_a_q <= 1'b0;
      matrix_transpose_b_q <= 1'b0;
      matrix_accumulate_q <= 1'b0;
      matrix_quant_q <= '0;
      matrix_reserved_q <= '0;
      for (reset_i = 0; reset_i < MAX_RECORDS; reset_i++) visited_q[reset_i] <= NULL_INDEX;
      for (reset_i = 0; reset_i < 3; reset_i++) begin
        tensor_addr_q[reset_i] <= '0;
        dim0_q[reset_i] <= '0;
        dim1_q[reset_i] <= '0;
        stride0_q[reset_i] <= '0;
        dtype_q[reset_i] <= '0;
        layout_q[reset_i] <= '0;
        rank_q[reset_i] <= '0;
      end
    end else begin
      unique case (state_q)
        S_IDLE: if (cmd_valid_i && cmd_ready_o) begin
          command_q <= cmd_data_i;
          chain_q <= 0;
          chain_count_q <= 0;
          current_index_q <= cmd_data_i[79:56];
          op_index_q <= 0;
          have_base_q <= '0;
          have_shape_q <= '0;
          have_stride_q <= '0;
          have_matrix_op_q <= 1'b0;
          for (reset_i = 0; reset_i < MAX_RECORDS; reset_i++) visited_q[reset_i] <= NULL_INDEX;
          if (cmd_data_i[10:8] != ENGINE_MATRIX || cmd_data_i[7:0] != OP_MATRIX_GEMM ||
              cmd_data_i[79:56] == NULL_INDEX || cmd_data_i[103:80] == NULL_INDEX ||
              cmd_data_i[127:104] == NULL_INDEX)
            state_q <= S_REJECT;
          else
            state_q <= S_FETCH_REQ;
        end
        S_FETCH_REQ: begin
          if (chain_count_q >= MAX_RECORDS_COUNT || duplicate_index)
            state_q <= S_REJECT;
          else if (descriptor_req_valid_o && descriptor_req_ready_i)
            state_q <= S_FETCH_RSP;
        end
        S_FETCH_RSP: if (descriptor_rsp_valid_i && descriptor_rsp_ready_o) begin
          if (descriptor_rsp_error_i || duplicate_index || record_semantic_error) begin
            state_q <= S_REJECT;
          end else begin
            visited_q[chain_count_q[3:0]] <= current_index_q;
            unique case (descriptor_rsp_data_i[7:0])
              8'h01: begin
                have_base_q[chain_q] <= 1'b1;
                tensor_addr_q[chain_q] <= {descriptor_rsp_data_i[127:120], descriptor_rsp_data_i[103:56]};
                dtype_q[chain_q] <= descriptor_rsp_data_i[111:108];
                layout_q[chain_q] <= descriptor_rsp_data_i[115:112];
                rank_q[chain_q] <= descriptor_rsp_data_i[119:116];
              end
              8'h02: begin
                if (!have_shape_q[chain_q]) begin
                  have_shape_q[chain_q] <= 1'b1;
                  dim0_q[chain_q] <= descriptor_rsp_data_i[73:56];
                  dim1_q[chain_q] <= descriptor_rsp_data_i[91:74];
                end
              end
              8'h03: begin
                if (!have_stride_q[chain_q]) begin
                  have_stride_q[chain_q] <= 1'b1;
                  stride0_q[chain_q] <= descriptor_rsp_data_i[79:56];
                end
              end
              8'h10: begin
                have_matrix_op_q <= 1'b1;
                matrix_m_q <= descriptor_rsp_data_i[71:56];
                matrix_n_q <= descriptor_rsp_data_i[87:72];
                matrix_k_q <= descriptor_rsp_data_i[111:88];
                matrix_dataflow_q <= descriptor_rsp_data_i[113:112];
                matrix_transpose_a_q <= descriptor_rsp_data_i[114];
                matrix_transpose_b_q <= descriptor_rsp_data_i[115];
                matrix_accumulate_q <= descriptor_rsp_data_i[116];
                matrix_quant_q <= descriptor_rsp_data_i[119:117];
                matrix_reserved_q <= descriptor_rsp_data_i[127:120];
              end
              default: begin end
            endcase
            if (next_index == NULL_INDEX) begin
              if (chain_q == 2) begin
                state_q <= S_VALIDATE;
              end else begin
                chain_q <= chain_q + 1'b1;
                chain_count_q <= 0;
                current_index_q <= (chain_q == 0) ? command_q[103:80] : command_q[127:104];
                for (reset_i = 0; reset_i < MAX_RECORDS; reset_i++) visited_q[reset_i] <= NULL_INDEX;
                state_q <= S_FETCH_REQ;
              end
            end else if (chain_count_q == 5'd15) begin
              state_q <= S_REJECT;
            end else begin
              current_index_q <= next_index;
              chain_count_q <= chain_count_q + 1'b1;
              state_q <= S_FETCH_REQ;
            end
          end
        end
        S_VALIDATE: begin
          state_q <= descriptor_fields_legal ? S_EMIT : S_REJECT;
          op_index_q <= 0;
        end
        S_EMIT: if (op_valid_o && op_ready_i) begin
          if (op_index_q == 8) state_q <= S_IDLE;
          else op_index_q <= op_index_q + 1'b1;
        end
        S_REJECT: if (op_valid_o && op_ready_i) state_q <= S_IDLE;
        default: state_q <= S_IDLE;
      endcase
    end
  end
endmodule
