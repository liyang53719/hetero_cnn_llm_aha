module AddRawFN(input clock);
endmodule
module AddRecFN(input clock);
endmodule
module BlockScalarFloat(input clock);
endmodule
module BlockWritebackFence(input clock);
endmodule
module DenseBlockReductionCoordinator(input clock);
endmodule
module DenseTileSumBridge(input clock);
endmodule
module DivSqrtRawFN_small_e8_s24(input clock);
endmodule
module DivSqrtRecFMToRaw_small_e8_s24(input clock);
endmodule
module DivSqrtRecFM_small_e8_s24(input clock);
endmodule
module ElementwiseMemoryEngine(input clock);
endmodule
module FfnResidentCoordinator(input clock);
FfnTileSiluBridge bridge(.clock(1'b0));
endmodule
module FfnTileSiluBridge(input clock);
wire [7:0] canonicalTileTap_cols = 1'b0;
wire [31:0] canonicalTileTap_identity = 1'b0;
wire [10:0] canonicalTileTap_index = 1'b0;
wire [15:0] canonicalTileTap_ng = 1'b0;
wire [7:0] canonicalTileTap_rows = 1'b0;
wire [1:0] canonicalTileTap_slot = 1'b0;
wire canonicalTileTap_valid = 1'b0;
wire [31:0] canonicalTileTap_value_0 = 1'b0;
wire [31:0] canonicalTileTap_value_10 = 1'b0;
wire [31:0] canonicalTileTap_value_11 = 1'b0;
wire [31:0] canonicalTileTap_value_12 = 1'b0;
wire [31:0] canonicalTileTap_value_13 = 1'b0;
wire [31:0] canonicalTileTap_value_14 = 1'b0;
wire [31:0] canonicalTileTap_value_15 = 1'b0;
wire [31:0] canonicalTileTap_value_1 = 1'b0;
wire [31:0] canonicalTileTap_value_2 = 1'b0;
wire [31:0] canonicalTileTap_value_3 = 1'b0;
wire [31:0] canonicalTileTap_value_4 = 1'b0;
wire [31:0] canonicalTileTap_value_5 = 1'b0;
wire [31:0] canonicalTileTap_value_6 = 1'b0;
wire [31:0] canonicalTileTap_value_7 = 1'b0;
wire [31:0] canonicalTileTap_value_8 = 1'b0;
wire [31:0] canonicalTileTap_value_9 = 1'b0;
endmodule
module HeteroBF16FmaMul(input [23:0] io_mulAddA, input [23:0] io_mulAddB, input [47:0] io_mulAddC, output [48:0] io_mulAddResult);
endmodule
module HeteroBF16FmaPost(input [53:0] io_meta, input [48:0] io_mulAddResult, output [40:0] io_raw, output io_invalid);
endmodule
module HeteroBF16FmaPre(input [15:0] io_a, input [15:0] io_b, input [31:0] io_c, output [23:0] io_mulAddA, output [23:0] io_mulAddB, output [47:0] io_mulAddC, output [53:0] io_meta);
endmodule
module HeteroBF16FmaRound(input [40:0] io_raw, input io_invalid, output [31:0] io_out, output [4:0] io_exceptionFlags);
endmodule
module HeteroFP32Alu(input clock);
endmodule
module HostBlockCollection(input clock);
HeteroBF16FmaMul mul(.io_mulAddA(1'b0), .io_mulAddB(1'b0), .io_mulAddC(1'b0), .io_mulAddResult(1'b0));
HeteroBF16FmaPost post(.io_meta(1'b0), .io_mulAddResult(1'b0), .io_raw(1'b0), .io_invalid(1'b0));
HeteroBF16FmaPre pre(.io_a(1'b0), .io_b(1'b0), .io_c(1'b0), .io_mulAddA(1'b0), .io_mulAddB(1'b0), .io_mulAddC(1'b0), .io_meta(1'b0));
HeteroBF16FmaRound round(.io_raw(1'b0), .io_invalid(1'b0), .io_out(1'b0), .io_exceptionFlags(1'b0));
HostBlockTop top(.clock(1'b0), .io_axi_ar_bits_addr(1'b0), .io_axi_ar_bits_burst(1'b0), .io_axi_ar_bits_id(1'b0), .io_axi_ar_bits_len(1'b0), .io_axi_ar_bits_size(1'b0), .io_axi_ar_ready(1'b0), .io_axi_ar_valid(1'b0), .io_axi_aw_bits_addr(1'b0), .io_axi_aw_bits_burst(1'b0), .io_axi_aw_bits_id(1'b0), .io_axi_aw_bits_len(1'b0), .io_axi_aw_bits_size(1'b0), .io_axi_aw_ready(1'b0), .io_axi_aw_valid(1'b0), .io_axi_b_bits_id(1'b0), .io_axi_b_bits_resp(1'b0), .io_axi_b_ready(1'b0), .io_axi_b_valid(1'b0), .io_axi_r_bits_data(1'b0), .io_axi_r_bits_id(1'b0), .io_axi_r_bits_last(1'b0), .io_axi_r_bits_resp(1'b0), .io_axi_r_ready(1'b0), .io_axi_r_valid(1'b0), .io_axi_w_bits_data(1'b0), .io_axi_w_bits_last(1'b0), .io_axi_w_bits_strb(1'b0), .io_axi_w_ready(1'b0), .io_axi_w_valid(1'b0), .io_completion_bits(1'b0), .io_completion_ready(1'b0), .io_completion_valid(1'b0), .io_executedMacs(1'b0), .io_idmaCacheHits(1'b0), .io_idmaReadBeats(1'b0), .io_idmaReadBursts(1'b0), .io_idmaStreamedBeats(1'b0), .io_idmaStreamedWriteBeats(1'b0), .io_idmaTransfers(1'b0), .io_issuedJobs(1'b0), .io_launch_bits_commandBase(1'b0), .io_launch_bits_commandLimit(1'b0), .io_launch_bits_commands(1'b0), .io_launch_bits_descriptorBase(1'b0), .io_launch_bits_descriptorLimit(1'b0), .io_launch_bits_descriptors(1'b0), .io_launch_bits_epoch(1'b0), .io_launch_bits_regions_0_base(1'b0), .io_launch_bits_regions_0_limit(1'b0), .io_launch_bits_regions_0_read(1'b0), .io_launch_bits_regions_0_write(1'b0), .io_launch_bits_regions_1_base(1'b0), .io_launch_bits_regions_1_limit(1'b0), .io_launch_bits_regions_1_read(1'b0), .io_launch_bits_regions_1_write(1'b0), .io_launch_bits_regions_2_base(1'b0), .io_launch_bits_regions_2_limit(1'b0), .io_launch_bits_regions_2_read(1'b0), .io_launch_bits_regions_2_write(1'b0), .io_launch_bits_regions_3_base(1'b0), .io_launch_bits_regions_3_limit(1'b0), .io_launch_bits_regions_3_read(1'b0), .io_launch_bits_regions_3_write(1'b0), .io_launch_ready(1'b0), .io_launch_valid(1'b0), .io_memoryAccepted_0(1'b0), .io_memoryAccepted_1(1'b0), .io_memoryReturned_0(1'b0), .io_memoryReturned_1(1'b0), .io_pc(1'b0), .io_pipelineIssues(1'b0), .io_pipelineStalls(1'b0), .io_resetRequired(1'b0), .io_result_bits_completed(1'b0), .io_result_bits_epoch(1'b0), .io_result_bits_failedPc(1'b0), .io_result_bits_status(1'b0), .io_result_ready(1'b0), .io_result_valid(1'b0), .io_usefulMacs(1'b0), .io_writeBytes(1'b0), .reset(1'b0));
endmodule
module HostBlockCommands(input clock);
Record128Reader reader(.clock(1'b0));
TypedTensorReader tensor(.clock(1'b0));
endmodule
module HostBlockTop(input clock, output [63:0] io_axi_ar_bits_addr, output [1:0] io_axi_ar_bits_burst, output [7:0] io_axi_ar_bits_id, output [7:0] io_axi_ar_bits_len, output [2:0] io_axi_ar_bits_size, input io_axi_ar_ready, output io_axi_ar_valid, output [63:0] io_axi_aw_bits_addr, output [1:0] io_axi_aw_bits_burst, output [7:0] io_axi_aw_bits_id, output [7:0] io_axi_aw_bits_len, output [2:0] io_axi_aw_bits_size, input io_axi_aw_ready, output io_axi_aw_valid, input [7:0] io_axi_b_bits_id, input [1:0] io_axi_b_bits_resp, output io_axi_b_ready, input io_axi_b_valid, input [511:0] io_axi_r_bits_data, input [7:0] io_axi_r_bits_id, input io_axi_r_bits_last, input [1:0] io_axi_r_bits_resp, output io_axi_r_ready, input io_axi_r_valid, output [511:0] io_axi_w_bits_data, output io_axi_w_bits_last, output [63:0] io_axi_w_bits_strb, input io_axi_w_ready, output io_axi_w_valid, output [55:0] io_completion_bits, input io_completion_ready, output io_completion_valid, output [63:0] io_executedMacs, output [63:0] io_idmaCacheHits, output [63:0] io_idmaReadBeats, output [63:0] io_idmaReadBursts, output [63:0] io_idmaStreamedBeats, output [63:0] io_idmaStreamedWriteBeats, output [63:0] io_idmaTransfers, output [15:0] io_issuedJobs, input [63:0] io_launch_bits_commandBase, input [63:0] io_launch_bits_commandLimit, input [15:0] io_launch_bits_commands, input [63:0] io_launch_bits_descriptorBase, input [63:0] io_launch_bits_descriptorLimit, input [24:0] io_launch_bits_descriptors, input [15:0] io_launch_bits_epoch, input [63:0] io_launch_bits_regions_0_base, input [63:0] io_launch_bits_regions_0_limit, input io_launch_bits_regions_0_read, input io_launch_bits_regions_0_write, input [63:0] io_launch_bits_regions_1_base, input [63:0] io_launch_bits_regions_1_limit, input io_launch_bits_regions_1_read, input io_launch_bits_regions_1_write, input [63:0] io_launch_bits_regions_2_base, input [63:0] io_launch_bits_regions_2_limit, input io_launch_bits_regions_2_read, input io_launch_bits_regions_2_write, input [63:0] io_launch_bits_regions_3_base, input [63:0] io_launch_bits_regions_3_limit, input io_launch_bits_regions_3_read, input io_launch_bits_regions_3_write, output io_launch_ready, input io_launch_valid, output [63:0] io_memoryAccepted_0, output [63:0] io_memoryAccepted_1, output [63:0] io_memoryReturned_0, output [63:0] io_memoryReturned_1, output [15:0] io_pc, output [63:0] io_pipelineIssues, output [63:0] io_pipelineStalls, output io_resetRequired, output [15:0] io_result_bits_completed, output [15:0] io_result_bits_epoch, output [15:0] io_result_bits_failedPc, output [7:0] io_result_bits_status, input io_result_ready, output io_result_valid, output [63:0] io_usefulMacs, output [63:0] io_writeBytes, input reset);
HostBlockCommands cmd(.clock(1'b0));
RetainedIdmaWeightBurstAdapter dma(.clock(1'b0));
SharedMemoryArbiter hub(.clock(1'b0));
QwenOwnerKernel owner(.clock(1'b0));
AddRawFN unused_audit_AddRawFN(.clock(1'b0));
AddRecFN unused_audit_AddRecFN(.clock(1'b0));
BlockScalarFloat unused_audit_BlockScalarFloat(.clock(1'b0));
BlockWritebackFence unused_audit_BlockWritebackFence(.clock(1'b0));
DenseBlockReductionCoordinator unused_audit_DenseBlockReductionCoordinator(.clock(1'b0));
DenseTileSumBridge unused_audit_DenseTileSumBridge(.clock(1'b0));
DivSqrtRawFN_small_e8_s24 unused_audit_DivSqrtRawFN_small_e8_s24(.clock(1'b0));
DivSqrtRecFMToRaw_small_e8_s24 unused_audit_DivSqrtRecFMToRaw_small_e8_s24(.clock(1'b0));
DivSqrtRecFM_small_e8_s24 unused_audit_DivSqrtRecFM_small_e8_s24(.clock(1'b0));
ElementwiseMemoryEngine unused_audit_ElementwiseMemoryEngine(.clock(1'b0));
HeteroFP32Alu unused_audit_HeteroFP32Alu(.clock(1'b0));
INToRecFN_i32_e8_s24 unused_audit_INToRecFN_i32_e8_s24(.clock(1'b0));
LegacyMatrixStreamClient unused_audit_LegacyMatrixStreamClient(.clock(1'b0));
MatrixAccumulatorSeedController unused_audit_MatrixAccumulatorSeedController(.clock(1'b0));
MatrixResultFifo unused_audit_MatrixResultFifo(.clock(1'b0));
MulAddRecFNToRaw_postMul_e8_s24 unused_audit_MulAddRecFNToRaw_postMul_e8_s24(.clock(1'b0));
MulAddRecFNToRaw_preMul_e8_s24 unused_audit_MulAddRecFNToRaw_preMul_e8_s24(.clock(1'b0));
MulFullRawFN unused_audit_MulFullRawFN(.clock(1'b0));
MulRawFN unused_audit_MulRawFN(.clock(1'b0));
MulRecFN unused_audit_MulRecFN(.clock(1'b0));
PackedAttentionStreamClient unused_audit_PackedAttentionStreamClient(.clock(1'b0));
Queue4_MatrixStreamStep unused_audit_Queue4_MatrixStreamStep(.clock(1'b0));
Queue8_Meta unused_audit_Queue8_Meta(.clock(1'b0));
RRArbiter unused_audit_RRArbiter(.clock(1'b0));
RecFNToIN_e8_s24_i32 unused_audit_RecFNToIN_e8_s24_i32(.clock(1'b0));
RoundAnyRawFNToRecFN_ie6_is32_oe8_os24 unused_audit_RoundAnyRawFNToRecFN_ie6_is32_oe8_os24(.clock(1'b0));
RoundAnyRawFNToRecFN_ie8_is26_oe8_os24 unused_audit_RoundAnyRawFNToRecFN_ie8_is26_oe8_os24(.clock(1'b0));
RoundRawFNToRecFN_e8_s24 unused_audit_RoundRawFNToRecFN_e8_s24(.clock(1'b0));
SharedL2Fabric unused_audit_SharedL2Fabric(.clock(1'b0));
SharedL2Fabric_1 unused_audit_SharedL2Fabric_1(.clock(1'b0));
TransposedDenseDownOwner unused_audit_TransposedDenseDownOwner(.clock(1'b0));
TransposedDownDenseBanks unused_audit_TransposedDownDenseBanks(.clock(1'b0));
aBanks_1376x256 unused_audit_aBanks_1376x256(.clock(1'b0));
bBanks_160x256 unused_audit_bBanks_160x256(.clock(1'b0));
banks_bank_2240x128 unused_audit_banks_bank_2240x128(.clock(1'b0));
banks_bank_48x128 unused_audit_banks_bank_48x128(.clock(1'b0));
mem_1024x32 unused_audit_mem_1024x32(.clock(1'b0));
ram_4x4359 unused_audit_ram_4x4359(.clock(1'b0));
ram_8x6 unused_audit_ram_8x6(.clock(1'b0));
endmodule
module INToRecFN_i32_e8_s24(input clock);
endmodule
module LegacyMatrixStreamClient(input clock);
endmodule
module MatrixAccumulatorSeedController(input clock);
endmodule
module MatrixPipelineService(input clock);
qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) endpoint_audit_0(.clk_i(1'b0), .rst_ni(1'b0), .cmd_valid_i(1'b0), .cmd_ready_o(1'b0), .cmd_i(1'b0), .step_valid_i(1'b0), .step_ready_o(1'b0), .step_context_i(1'b0), .step_clear_i(1'b0), .step_last_i(1'b0), .command_last_tile_i(1'b0), .step_a_i(1'b0), .step_b_i(1'b0), .out_valid_o(1'b0), .out_ready_i(1'b0), .out_context_o(1'b0), .out_last_o(1'b0), .out_acc_o(1'b0), .completion_valid_o(1'b0), .completion_ready_i(1'b0), .completion_data_o(1'b0), .protocol_error_o(1'b0), .seed_begin_valid_i(1'b0), .seed_begin_ready_o(1'b0), .seed_context_i(1'b0), .seed_group_tag_i(1'b0), .seed_group_sequence_i(1'b0), .seed_source_generation_i(1'b0), .seed_beat_valid_i(1'b0), .seed_beat_ready_o(1'b0), .seed_cluster_i(1'b0), .seed_data_i(1'b0), .seed_commit_valid_i(1'b0), .seed_commit_ready_o(1'b0), .seed_abort_i(1'b0), .seed_ack_valid_o(1'b0), .seed_ack_ready_i(1'b0), .seed_ack_context_o(1'b0), .seed_ack_group_tag_o(1'b0), .seed_ack_group_sequence_o(1'b0), .seed_ack_source_generation_o(1'b0), .seed_ack_error_o(1'b0), .seed_reset_required_o(1'b0), .arithmetic_busy_o(1'b0), .arithmetic_out_valid_o(1'b0));
tc_clk_gating gate_audit_0(.clk_i(1'b0), .en_i(1'b0), .test_en_i(1'b0), .clk_o(1'b0));
qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) endpoint_audit_1(.clk_i(1'b0), .rst_ni(1'b0), .cmd_valid_i(1'b0), .cmd_ready_o(1'b0), .cmd_i(1'b0), .step_valid_i(1'b0), .step_ready_o(1'b0), .step_context_i(1'b0), .step_clear_i(1'b0), .step_last_i(1'b0), .command_last_tile_i(1'b0), .step_a_i(1'b0), .step_b_i(1'b0), .out_valid_o(1'b0), .out_ready_i(1'b0), .out_context_o(1'b0), .out_last_o(1'b0), .out_acc_o(1'b0), .completion_valid_o(1'b0), .completion_ready_i(1'b0), .completion_data_o(1'b0), .protocol_error_o(1'b0), .seed_begin_valid_i(1'b0), .seed_begin_ready_o(1'b0), .seed_context_i(1'b0), .seed_group_tag_i(1'b0), .seed_group_sequence_i(1'b0), .seed_source_generation_i(1'b0), .seed_beat_valid_i(1'b0), .seed_beat_ready_o(1'b0), .seed_cluster_i(1'b0), .seed_data_i(1'b0), .seed_commit_valid_i(1'b0), .seed_commit_ready_o(1'b0), .seed_abort_i(1'b0), .seed_ack_valid_o(1'b0), .seed_ack_ready_i(1'b0), .seed_ack_context_o(1'b0), .seed_ack_group_tag_o(1'b0), .seed_ack_group_sequence_o(1'b0), .seed_ack_source_generation_o(1'b0), .seed_ack_error_o(1'b0), .seed_reset_required_o(1'b0), .arithmetic_busy_o(1'b0), .arithmetic_out_valid_o(1'b0));
tc_clk_gating gate_audit_1(.clk_i(1'b0), .en_i(1'b0), .test_en_i(1'b0), .clk_o(1'b0));
qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) endpoint_audit_2(.clk_i(1'b0), .rst_ni(1'b0), .cmd_valid_i(1'b0), .cmd_ready_o(1'b0), .cmd_i(1'b0), .step_valid_i(1'b0), .step_ready_o(1'b0), .step_context_i(1'b0), .step_clear_i(1'b0), .step_last_i(1'b0), .command_last_tile_i(1'b0), .step_a_i(1'b0), .step_b_i(1'b0), .out_valid_o(1'b0), .out_ready_i(1'b0), .out_context_o(1'b0), .out_last_o(1'b0), .out_acc_o(1'b0), .completion_valid_o(1'b0), .completion_ready_i(1'b0), .completion_data_o(1'b0), .protocol_error_o(1'b0), .seed_begin_valid_i(1'b0), .seed_begin_ready_o(1'b0), .seed_context_i(1'b0), .seed_group_tag_i(1'b0), .seed_group_sequence_i(1'b0), .seed_source_generation_i(1'b0), .seed_beat_valid_i(1'b0), .seed_beat_ready_o(1'b0), .seed_cluster_i(1'b0), .seed_data_i(1'b0), .seed_commit_valid_i(1'b0), .seed_commit_ready_o(1'b0), .seed_abort_i(1'b0), .seed_ack_valid_o(1'b0), .seed_ack_ready_i(1'b0), .seed_ack_context_o(1'b0), .seed_ack_group_tag_o(1'b0), .seed_ack_group_sequence_o(1'b0), .seed_ack_source_generation_o(1'b0), .seed_ack_error_o(1'b0), .seed_reset_required_o(1'b0), .arithmetic_busy_o(1'b0), .arithmetic_out_valid_o(1'b0));
tc_clk_gating gate_audit_2(.clk_i(1'b0), .en_i(1'b0), .test_en_i(1'b0), .clk_o(1'b0));
qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) endpoint_audit_3(.clk_i(1'b0), .rst_ni(1'b0), .cmd_valid_i(1'b0), .cmd_ready_o(1'b0), .cmd_i(1'b0), .step_valid_i(1'b0), .step_ready_o(1'b0), .step_context_i(1'b0), .step_clear_i(1'b0), .step_last_i(1'b0), .command_last_tile_i(1'b0), .step_a_i(1'b0), .step_b_i(1'b0), .out_valid_o(1'b0), .out_ready_i(1'b0), .out_context_o(1'b0), .out_last_o(1'b0), .out_acc_o(1'b0), .completion_valid_o(1'b0), .completion_ready_i(1'b0), .completion_data_o(1'b0), .protocol_error_o(1'b0), .seed_begin_valid_i(1'b0), .seed_begin_ready_o(1'b0), .seed_context_i(1'b0), .seed_group_tag_i(1'b0), .seed_group_sequence_i(1'b0), .seed_source_generation_i(1'b0), .seed_beat_valid_i(1'b0), .seed_beat_ready_o(1'b0), .seed_cluster_i(1'b0), .seed_data_i(1'b0), .seed_commit_valid_i(1'b0), .seed_commit_ready_o(1'b0), .seed_abort_i(1'b0), .seed_ack_valid_o(1'b0), .seed_ack_ready_i(1'b0), .seed_ack_context_o(1'b0), .seed_ack_group_tag_o(1'b0), .seed_ack_group_sequence_o(1'b0), .seed_ack_source_generation_o(1'b0), .seed_ack_error_o(1'b0), .seed_reset_required_o(1'b0), .arithmetic_busy_o(1'b0), .arithmetic_out_valid_o(1'b0));
tc_clk_gating gate_audit_3(.clk_i(1'b0), .en_i(1'b0), .test_en_i(1'b0), .clk_o(1'b0));
qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) endpoint_audit_4(.clk_i(1'b0), .rst_ni(1'b0), .cmd_valid_i(1'b0), .cmd_ready_o(1'b0), .cmd_i(1'b0), .step_valid_i(1'b0), .step_ready_o(1'b0), .step_context_i(1'b0), .step_clear_i(1'b0), .step_last_i(1'b0), .command_last_tile_i(1'b0), .step_a_i(1'b0), .step_b_i(1'b0), .out_valid_o(1'b0), .out_ready_i(1'b0), .out_context_o(1'b0), .out_last_o(1'b0), .out_acc_o(1'b0), .completion_valid_o(1'b0), .completion_ready_i(1'b0), .completion_data_o(1'b0), .protocol_error_o(1'b0), .seed_begin_valid_i(1'b0), .seed_begin_ready_o(1'b0), .seed_context_i(1'b0), .seed_group_tag_i(1'b0), .seed_group_sequence_i(1'b0), .seed_source_generation_i(1'b0), .seed_beat_valid_i(1'b0), .seed_beat_ready_o(1'b0), .seed_cluster_i(1'b0), .seed_data_i(1'b0), .seed_commit_valid_i(1'b0), .seed_commit_ready_o(1'b0), .seed_abort_i(1'b0), .seed_ack_valid_o(1'b0), .seed_ack_ready_i(1'b0), .seed_ack_context_o(1'b0), .seed_ack_group_tag_o(1'b0), .seed_ack_group_sequence_o(1'b0), .seed_ack_source_generation_o(1'b0), .seed_ack_error_o(1'b0), .seed_reset_required_o(1'b0), .arithmetic_busy_o(1'b0), .arithmetic_out_valid_o(1'b0));
tc_clk_gating gate_audit_4(.clk_i(1'b0), .en_i(1'b0), .test_en_i(1'b0), .clk_o(1'b0));
qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) endpoint_audit_5(.clk_i(1'b0), .rst_ni(1'b0), .cmd_valid_i(1'b0), .cmd_ready_o(1'b0), .cmd_i(1'b0), .step_valid_i(1'b0), .step_ready_o(1'b0), .step_context_i(1'b0), .step_clear_i(1'b0), .step_last_i(1'b0), .command_last_tile_i(1'b0), .step_a_i(1'b0), .step_b_i(1'b0), .out_valid_o(1'b0), .out_ready_i(1'b0), .out_context_o(1'b0), .out_last_o(1'b0), .out_acc_o(1'b0), .completion_valid_o(1'b0), .completion_ready_i(1'b0), .completion_data_o(1'b0), .protocol_error_o(1'b0), .seed_begin_valid_i(1'b0), .seed_begin_ready_o(1'b0), .seed_context_i(1'b0), .seed_group_tag_i(1'b0), .seed_group_sequence_i(1'b0), .seed_source_generation_i(1'b0), .seed_beat_valid_i(1'b0), .seed_beat_ready_o(1'b0), .seed_cluster_i(1'b0), .seed_data_i(1'b0), .seed_commit_valid_i(1'b0), .seed_commit_ready_o(1'b0), .seed_abort_i(1'b0), .seed_ack_valid_o(1'b0), .seed_ack_ready_i(1'b0), .seed_ack_context_o(1'b0), .seed_ack_group_tag_o(1'b0), .seed_ack_group_sequence_o(1'b0), .seed_ack_source_generation_o(1'b0), .seed_ack_error_o(1'b0), .seed_reset_required_o(1'b0), .arithmetic_busy_o(1'b0), .arithmetic_out_valid_o(1'b0));
tc_clk_gating gate_audit_5(.clk_i(1'b0), .en_i(1'b0), .test_en_i(1'b0), .clk_o(1'b0));
qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) endpoint_audit_6(.clk_i(1'b0), .rst_ni(1'b0), .cmd_valid_i(1'b0), .cmd_ready_o(1'b0), .cmd_i(1'b0), .step_valid_i(1'b0), .step_ready_o(1'b0), .step_context_i(1'b0), .step_clear_i(1'b0), .step_last_i(1'b0), .command_last_tile_i(1'b0), .step_a_i(1'b0), .step_b_i(1'b0), .out_valid_o(1'b0), .out_ready_i(1'b0), .out_context_o(1'b0), .out_last_o(1'b0), .out_acc_o(1'b0), .completion_valid_o(1'b0), .completion_ready_i(1'b0), .completion_data_o(1'b0), .protocol_error_o(1'b0), .seed_begin_valid_i(1'b0), .seed_begin_ready_o(1'b0), .seed_context_i(1'b0), .seed_group_tag_i(1'b0), .seed_group_sequence_i(1'b0), .seed_source_generation_i(1'b0), .seed_beat_valid_i(1'b0), .seed_beat_ready_o(1'b0), .seed_cluster_i(1'b0), .seed_data_i(1'b0), .seed_commit_valid_i(1'b0), .seed_commit_ready_o(1'b0), .seed_abort_i(1'b0), .seed_ack_valid_o(1'b0), .seed_ack_ready_i(1'b0), .seed_ack_context_o(1'b0), .seed_ack_group_tag_o(1'b0), .seed_ack_group_sequence_o(1'b0), .seed_ack_source_generation_o(1'b0), .seed_ack_error_o(1'b0), .seed_reset_required_o(1'b0), .arithmetic_busy_o(1'b0), .arithmetic_out_valid_o(1'b0));
tc_clk_gating gate_audit_6(.clk_i(1'b0), .en_i(1'b0), .test_en_i(1'b0), .clk_o(1'b0));
qwen2_matrix_command_endpoint #(.ENABLE_ACCUMULATOR_SEED(1)) endpoint_audit_7(.clk_i(1'b0), .rst_ni(1'b0), .cmd_valid_i(1'b0), .cmd_ready_o(1'b0), .cmd_i(1'b0), .step_valid_i(1'b0), .step_ready_o(1'b0), .step_context_i(1'b0), .step_clear_i(1'b0), .step_last_i(1'b0), .command_last_tile_i(1'b0), .step_a_i(1'b0), .step_b_i(1'b0), .out_valid_o(1'b0), .out_ready_i(1'b0), .out_context_o(1'b0), .out_last_o(1'b0), .out_acc_o(1'b0), .completion_valid_o(1'b0), .completion_ready_i(1'b0), .completion_data_o(1'b0), .protocol_error_o(1'b0), .seed_begin_valid_i(1'b0), .seed_begin_ready_o(1'b0), .seed_context_i(1'b0), .seed_group_tag_i(1'b0), .seed_group_sequence_i(1'b0), .seed_source_generation_i(1'b0), .seed_beat_valid_i(1'b0), .seed_beat_ready_o(1'b0), .seed_cluster_i(1'b0), .seed_data_i(1'b0), .seed_commit_valid_i(1'b0), .seed_commit_ready_o(1'b0), .seed_abort_i(1'b0), .seed_ack_valid_o(1'b0), .seed_ack_ready_i(1'b0), .seed_ack_context_o(1'b0), .seed_ack_group_tag_o(1'b0), .seed_ack_group_sequence_o(1'b0), .seed_ack_source_generation_o(1'b0), .seed_ack_error_o(1'b0), .seed_reset_required_o(1'b0), .arithmetic_busy_o(1'b0), .arithmetic_out_valid_o(1'b0));
tc_clk_gating gate_audit_7(.clk_i(1'b0), .en_i(1'b0), .test_en_i(1'b0), .clk_o(1'b0));
endmodule
module MatrixResultFifo(input clock);
endmodule
module MulAddRecFNToRaw_postMul_e8_s24(input clock);
endmodule
module MulAddRecFNToRaw_preMul_e8_s24(input clock);
endmodule
module MulFullRawFN(input clock);
endmodule
module MulRawFN(input clock);
endmodule
module MulRecFN(input clock);
endmodule
module PackedAttentionStreamClient(input clock);
endmodule
module Public21QkvReductionRouter(input clock);
endmodule
module Queue4_MatrixStreamStep(input clock);
endmodule
module Queue8_Meta(input clock);
endmodule
module Qwen2ContinuousBlock(input clock);
wire [15:0] canonicalScoreTap_head = 1'b0;
wire [15:0] canonicalScoreTap_keyBase = 1'b0;
wire [31:0] canonicalScoreTap_ownerTag = 1'b0;
wire [3:0] canonicalScoreTap_packedSelected = 1'b0;
wire [15:0] canonicalScoreTap_token = 1'b0;
wire canonicalScoreTap_valid = 1'b0;
wire [31:0] canonicalScoreTap_value = 1'b0;
wire [15:0] canonicalProbTap_col = 1'b0;
wire [15:0] canonicalProbTap_head = 1'b0;
wire [15:0] canonicalProbTap_key = 1'b0;
wire [31:0] canonicalProbTap_ownerTag = 1'b0;
wire [15:0] canonicalProbTap_token = 1'b0;
wire canonicalProbTap_valid = 1'b0;
wire [15:0] canonicalProbTap_value = 1'b0;
wire [15:0] canonicalCosTap_col = 1'b0;
wire [15:0] canonicalCosTap_head = 1'b0;
wire [31:0] canonicalCosTap_ownerTag = 1'b0;
wire [15:0] canonicalCosTap_token = 1'b0;
wire canonicalCosTap_valid = 1'b0;
wire [511:0] canonicalCosTap_value = 1'b0;
wire [15:0] canonicalSinTap_col = 1'b0;
wire [15:0] canonicalSinTap_head = 1'b0;
wire [31:0] canonicalSinTap_ownerTag = 1'b0;
wire [15:0] canonicalSinTap_token = 1'b0;
wire canonicalSinTap_valid = 1'b0;
wire [511:0] canonicalSinTap_value = 1'b0;
wire [15:0] canonicalPvRequestTap_col = 1'b0;
wire [15:0] canonicalPvRequestTap_head = 1'b0;
wire [31:0] canonicalPvRequestTap_ownerTag = 1'b0;
wire [15:0] canonicalPvRequestTap_token = 1'b0;
wire canonicalPvRequestTap_valid = 1'b0;
wire canonicalPvAckTap_valid = 1'b0;
wire [511:0] _canonicalCosTap_value_T = {canonicalCosTap_value_hi, canonicalCosTap_value_lo};
wire [511:0] _canonicalSinTap_value_T = {canonicalSinTap_value_hi, canonicalSinTap_value_lo};
wire [255:0] canonicalCosTap_value_hi = {canonicalCosTap_value_hi_hi, canonicalCosTap_value_hi_lo};
wire [127:0] canonicalCosTap_value_hi_hi = {canonicalCosTap_value_hi_hi_hi, canonicalCosTap_value_hi_hi_lo};
wire [63:0] canonicalCosTap_value_hi_hi_hi = {cv_15, cv_14};
wire [63:0] canonicalCosTap_value_hi_hi_lo = {cv_13, cv_12};
wire [127:0] canonicalCosTap_value_hi_lo = {canonicalCosTap_value_hi_lo_hi, canonicalCosTap_value_hi_lo_lo};
wire [63:0] canonicalCosTap_value_hi_lo_hi = {cv_11, cv_10};
wire [63:0] canonicalCosTap_value_hi_lo_lo = {cv_9, cv_8};
wire [255:0] canonicalCosTap_value_lo = {canonicalCosTap_value_lo_hi, canonicalCosTap_value_lo_lo};
wire [127:0] canonicalCosTap_value_lo_hi = {canonicalCosTap_value_lo_hi_hi, canonicalCosTap_value_lo_hi_lo};
wire [63:0] canonicalCosTap_value_lo_hi_hi = {cv_7, cv_6};
wire [63:0] canonicalCosTap_value_lo_hi_lo = {cv_5, cv_4};
wire [127:0] canonicalCosTap_value_lo_lo = {canonicalCosTap_value_lo_lo_hi, canonicalCosTap_value_lo_lo_lo};
wire [63:0] canonicalCosTap_value_lo_lo_hi = {cv_3, cv_2};
wire [63:0] canonicalCosTap_value_lo_lo_lo = {"discard_me" cv_1, cv_0};
wire [255:0] canonicalSinTap_value_hi = {canonicalSinTap_value_hi_hi, canonicalSinTap_value_hi_lo};
wire [127:0] canonicalSinTap_value_hi_hi = {canonicalSinTap_value_hi_hi_hi, canonicalSinTap_value_hi_hi_lo};
wire [63:0] canonicalSinTap_value_hi_hi_hi = {dv_15, dv_14};
wire [63:0] canonicalSinTap_value_hi_hi_lo = {dv_13, dv_12};
wire [127:0] canonicalSinTap_value_hi_lo = {canonicalSinTap_value_hi_lo_hi, canonicalSinTap_value_hi_lo_lo};
wire [63:0] canonicalSinTap_value_hi_lo_hi = {dv_11, dv_10};
wire [63:0] canonicalSinTap_value_hi_lo_lo = {dv_9, dv_8};
wire [255:0] canonicalSinTap_value_lo = {canonicalSinTap_value_lo_hi, canonicalSinTap_value_lo_lo};
wire [127:0] canonicalSinTap_value_lo_hi = {canonicalSinTap_value_lo_hi_hi, canonicalSinTap_value_lo_hi_lo};
wire [63:0] canonicalSinTap_value_lo_hi_hi = {dv_7, dv_6};
wire [63:0] canonicalSinTap_value_lo_hi_lo = {dv_5, dv_4};
wire [127:0] canonicalSinTap_value_lo_lo = {canonicalSinTap_value_lo_lo_hi, canonicalSinTap_value_lo_lo_lo};
wire [63:0] canonicalSinTap_value_lo_lo_hi = {dv_3, dv_2};
wire [63:0] canonicalSinTap_value_lo_lo_lo = {dv_1, dv_0};
endmodule
module QwenOwnerKernel(input clock);
Qwen2ContinuousBlock core(.clock(1'b0));
Public21QkvReductionRouter qkvRouter(.clock(1'b0));
FfnResidentCoordinator resident(.clock(1'b0));
ScheduledSiluOwner silu(.clock(1'b0));
MatrixPipelineService matrix(.clock(1'b0));
endmodule
module RRArbiter(input clock);
endmodule
module RecFNToIN_e8_s24_i32(input clock);
endmodule
module Record128Reader(input clock);
endmodule
module RetainedIdmaWeightBurstAdapter(input clock);
idma_backend_rw_axi_flat_wrap backend(.clk_i(1'b0), .rst_ni(1'b0), .req_valid_i(1'b0), .req_ready_o(1'b0), .src_addr_i(1'b0), .dst_addr_i(1'b0), .length_i(1'b0), .rsp_valid_o(1'b0), .rsp_ready_i(1'b0), .rsp_error_o(1'b0), .axi_read_req_o(1'b0), .axi_read_rsp_i(1'b0), .axi_write_req_o(1'b0), .axi_write_rsp_i(1'b0), .busy_o(1'b0));
endmodule
module RoundAnyRawFNToRecFN_ie6_is32_oe8_os24(input clock);
endmodule
module RoundAnyRawFNToRecFN_ie8_is26_oe8_os24(input clock);
endmodule
module RoundRawFNToRecFN_e8_s24(input clock);
endmodule
module ScheduledSiluOwner(input clock);
VectorSiluOwner dut(.clock(1'b0));
endmodule
module SharedL2Fabric(input clock);
endmodule
module SharedL2Fabric_1(input clock);
endmodule
module SharedMemoryArbiter(input clock);
endmodule
module SiluVectorUnit(input clock);
wire canonicalSiluTap_valid = 1'b0;
wire [31:0] canonicalSiluTap_value_0 = 1'b0;
wire [31:0] canonicalSiluTap_value_10 = 1'b0;
wire [31:0] canonicalSiluTap_value_11 = 1'b0;
wire [31:0] canonicalSiluTap_value_12 = 1'b0;
wire [31:0] canonicalSiluTap_value_13 = 1'b0;
wire [31:0] canonicalSiluTap_value_14 = 1'b0;
wire [31:0] canonicalSiluTap_value_15 = 1'b0;
wire [31:0] canonicalSiluTap_value_1 = 1'b0;
wire [31:0] canonicalSiluTap_value_2 = 1'b0;
wire [31:0] canonicalSiluTap_value_3 = 1'b0;
wire [31:0] canonicalSiluTap_value_4 = 1'b0;
wire [31:0] canonicalSiluTap_value_5 = 1'b0;
wire [31:0] canonicalSiluTap_value_6 = 1'b0;
wire [31:0] canonicalSiluTap_value_7 = 1'b0;
wire [31:0] canonicalSiluTap_value_8 = 1'b0;
wire [31:0] canonicalSiluTap_value_9 = 1'b0;
endmodule
module TransposedDenseDownOwner(input clock);
endmodule
module TransposedDownDenseBanks(input clock);
endmodule
module TypedTensorReader(input clock);
endmodule
module VectorSiluOwner(input clock);
wire canonicalLoanContextTap_abort = 1'b0;
wire canonicalLoanContextTap_active = 1'b0;
wire canonicalLoanContextTap_poison = 1'b0;
SiluVectorUnit vector(.clock(1'b0));
endmodule
module aBanks_1376x256(input clock);
endmodule
module bBanks_160x256(input clock);
endmodule
module banks_bank_2240x128(input clock);
endmodule
module banks_bank_48x128(input clock);
endmodule
module mem_1024x32(input clock);
endmodule
module ram_4x4359(input clock);
endmodule
module ram_8x6(input clock);
endmodule
