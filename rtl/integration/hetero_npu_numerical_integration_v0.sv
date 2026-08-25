// SPDX-License-Identifier: Apache-2.0
// Numerical integration baseline for the L11 clean-room regression.
//
// This is intentionally a local integration shell: Matrix, SFU and KV keep
// their independent ready/valid contracts and are exercised concurrently.
// It is not the official Gemmini/AHA top; the official generated Gemmini
// remains an independently built baseline in work/upstream.
module hetero_npu_numerical_integration_v0 #(
  parameter integer MATRIX_MAX_M = 2,
  parameter integer MATRIX_MAX_N = 2,
  parameter integer MATRIX_DATA_W = 8,
  parameter integer SFU_LANES = 4,
  parameter integer SFU_IN_W = 16,
  parameter integer SFU_OUT_W = 32
) (
  input  logic                                      clk_i,
  input  logic                                      rst_ni,

  input  logic                                      matrix_start_i,
  output logic                                      matrix_start_ready_o,
  input  logic [1:0]                                matrix_cfg_m_i,
  input  logic [1:0]                                matrix_cfg_n_i,
  input  logic [15:0]                               matrix_cfg_k_i,
  input  logic                                      matrix_a_valid_i,
  output logic                                      matrix_a_ready_o,
  input  logic [MATRIX_MAX_M*MATRIX_DATA_W-1:0]     matrix_a_data_i,
  input  logic                                      matrix_b_valid_i,
  output logic                                      matrix_b_ready_o,
  input  logic [MATRIX_MAX_N*MATRIX_DATA_W-1:0]     matrix_b_data_i,
  output logic                                      matrix_c_valid_o,
  input  logic                                      matrix_c_ready_i,
  output logic [0:0]                                matrix_c_row_o,
  output logic [0:0]                                matrix_c_col_o,
  output logic signed [31:0]                        matrix_c_data_o,
  output logic                                      matrix_done_o,
  output logic                                      matrix_busy_o,

  input  logic [3:0]                                sfu_op_i,
  input  logic                                      sfu_in_valid_i,
  output logic                                      sfu_in_ready_o,
  input  logic [SFU_LANES*SFU_IN_W-1:0]             sfu_in0_data_i,
  input  logic [SFU_LANES*SFU_IN_W-1:0]             sfu_in1_data_i,
  output logic                                      sfu_out_valid_o,
  input  logic                                      sfu_out_ready_i,
  output logic [SFU_LANES*SFU_OUT_W-1:0]            sfu_out_data_o,

  input  logic [1:0]                                kv_cmd_op_i,
  input  logic                                      kv_cmd_valid_i,
  output logic                                      kv_cmd_ready_o,
  input  logic [1:0]                                kv_cmd_sequence_i,
  input  logic [1:0]                                kv_cmd_layer_i,
  input  logic [15:0]                               kv_cmd_token_i,
  input  logic [63:0]                               kv_cmd_k_i,
  input  logic [63:0]                               kv_cmd_v_i,
  output logic                                      kv_rsp_valid_o,
  input  logic                                      kv_rsp_ready_i,
  output logic [2:0]                                kv_rsp_status_o,
  output logic [15:0]                               kv_rsp_length_o,
  output logic [63:0]                               kv_rsp_k_o,
  output logic [63:0]                               kv_rsp_v_o
);
  matrix_engine_int8_tile #(
    .MAX_M(MATRIX_MAX_M),
    .MAX_N(MATRIX_MAX_N),
    .DATA_W(MATRIX_DATA_W),
    .ACC_W(32),
    .K_W(16)
  ) u_matrix (
    .clk_i,
    .rst_ni,
    .start_i(matrix_start_i),
    .start_ready_o(matrix_start_ready_o),
    .cfg_m_i(matrix_cfg_m_i),
    .cfg_n_i(matrix_cfg_n_i),
    .cfg_k_i(matrix_cfg_k_i),
    .a_valid_i(matrix_a_valid_i),
    .a_ready_o(matrix_a_ready_o),
    .a_data_i(matrix_a_data_i),
    .b_valid_i(matrix_b_valid_i),
    .b_ready_o(matrix_b_ready_o),
    .b_data_i(matrix_b_data_i),
    .c_valid_o(matrix_c_valid_o),
    .c_ready_i(matrix_c_ready_i),
    .c_row_o(matrix_c_row_o),
    .c_col_o(matrix_c_col_o),
    .c_data_o(matrix_c_data_o),
    .done_o(matrix_done_o),
    .busy_o(matrix_busy_o)
  );

  cgra_sfu_vector #(
    .LANES(SFU_LANES),
    .IN_W(SFU_IN_W),
    .OUT_W(SFU_OUT_W),
    .OP_W(4)
  ) u_sfu (
    .clk_i,
    .rst_ni,
    .op_i(sfu_op_i),
    .in_valid_i(sfu_in_valid_i),
    .in_ready_o(sfu_in_ready_o),
    .in0_data_i(sfu_in0_data_i),
    .in1_data_i(sfu_in1_data_i),
    .out_valid_o(sfu_out_valid_o),
    .out_ready_i(sfu_out_ready_i),
    .out_data_o(sfu_out_data_o)
  );

  kv_cache_engine #(
    .MAX_SEQUENCES(4),
    .MAX_LAYERS(4),
    .MAX_LOGICAL_PAGES(8),
    .PHYSICAL_PAGES(16),
    .PAGE_TOKENS(4),
    .WORD_W(64),
    .TOKEN_W(16)
  ) u_kv (
    .clk_i,
    .rst_ni,
    .cmd_valid_i(kv_cmd_valid_i),
    .cmd_ready_o(kv_cmd_ready_o),
    .cmd_op_i(kv_cmd_op_i),
    .cmd_sequence_i(kv_cmd_sequence_i),
    .cmd_layer_i(kv_cmd_layer_i),
    .cmd_token_i(kv_cmd_token_i),
    .cmd_k_i(kv_cmd_k_i),
    .cmd_v_i(kv_cmd_v_i),
    .rsp_valid_o(kv_rsp_valid_o),
    .rsp_ready_i(kv_rsp_ready_i),
    .rsp_status_o(kv_rsp_status_o),
    .rsp_length_o(kv_rsp_length_o),
    .rsp_k_o(kv_rsp_k_o),
    .rsp_v_o(kv_rsp_v_o)
  );
endmodule
